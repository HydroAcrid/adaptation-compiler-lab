[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,

    [ValidateSet("trusted", "development")]
    [string]$SignaturePolicy = "trusted",

    [ValidateRange(3, 30)]
    [int]$StartupSeconds = 6
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-ExactFile {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    $resolved = (Resolve-Path -LiteralPath $LiteralPath -ErrorAction Stop).Path
    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        throw "Required file is unavailable."
    }
    return $resolved
}

function Stop-SmokeProcess {
    param([System.Diagnostics.Process]$Process)

    if ($null -ne $Process -and -not $Process.HasExited) {
        $Process.Kill($true)
        $Process.WaitForExit(5000) | Out-Null
    }
    if ($null -ne $Process) {
        $Process.Dispose()
    }
}

function Start-EngineHandshake {
    param([Parameter(Mandatory = $true)][string]$EnginePath)

    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $EnginePath
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.Environment.Remove("TEMPER_RUNTIME_CONFIG") | Out-Null
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) {
            throw "Temper engine did not start."
        }
        $request = @{
            protocol_version = "temper-engine-protocol/v1"
            request_id = "windows-clean-smoke"
            method = "system.handshake"
            params = @{}
            expected_snapshot_digest = $null
            idempotency_key = $null
        } | ConvertTo-Json -Compress
        $process.StandardInput.WriteLine($request)
        $process.StandardInput.Flush()
        $read = $process.StandardOutput.ReadLineAsync()
        if (-not $read.Wait(15000)) {
            throw "Temper engine handshake timed out."
        }
        $response = $read.Result | ConvertFrom-Json
        if (
            -not $response.ok -or
            $response.protocol_version -ne "temper-engine-protocol/v1" -or
            $response.request_id -ne "windows-clean-smoke" -or
            $response.result.configured -ne $false -or
            $response.result.mutation_enabled -ne $false -or
            -not $response.result.snapshot_schema_digest.StartsWith("sha256:")
        ) {
            throw "Temper engine handshake failed closed-world validation."
        }
        return $response.result
    }
    finally {
        Stop-SmokeProcess -Process $process
    }
}

$installer = Resolve-ExactFile -LiteralPath $InstallerPath
$signature = Get-AuthenticodeSignature -LiteralPath $installer
if ($SignaturePolicy -eq "trusted" -and $signature.Status -ne "Valid") {
    throw "The Temper installer is not signed by a trusted publisher."
}

$smokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("temper-clean-smoke-" + [guid]::NewGuid())
$installRoot = Join-Path $smokeRoot "installed"
$resolvedTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$resolvedSmoke = [System.IO.Path]::GetFullPath($smokeRoot)
if (-not $resolvedSmoke.StartsWith($resolvedTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing an unsafe smoke directory."
}

$appProcess = $null
$uninstaller = $null
$uninstallCompleted = $false
$receipt = $null
try {
    New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
    $installerProcess = Start-Process -FilePath $installer -ArgumentList @("/S", "/D=$installRoot") -PassThru -Wait -WindowStyle Hidden
    if ($installerProcess.ExitCode -ne 0) {
        throw "Temper installer returned a failure."
    }

    $app = Get-ChildItem -LiteralPath $installRoot -Filter "Temper.exe" -File -Recurse |
        Select-Object -First 1
    $engine = Get-ChildItem -LiteralPath $installRoot -Filter "temper-engine.exe" -File -Recurse |
        Select-Object -First 1
    $uninstaller = Get-ChildItem -LiteralPath $installRoot -Filter "uninstall.exe" -File -Recurse |
        Select-Object -First 1
    if ($null -eq $app) {
        throw "The installed Temper.exe application is unavailable."
    }
    if ($null -eq $engine) {
        throw "The installed temper-engine.exe sidecar is unavailable."
    }
    if ($null -eq $uninstaller) {
        throw "The installed Temper uninstaller is unavailable."
    }

    $handshake = Start-EngineHandshake -EnginePath $engine.FullName

    $appStart = [System.Diagnostics.ProcessStartInfo]::new()
    $appStart.FileName = $app.FullName
    $appStart.WorkingDirectory = $app.DirectoryName
    $appStart.UseShellExecute = $false
    $appStart.CreateNoWindow = $true
    $appStart.Environment.Remove("TEMPER_RUNTIME_CONFIG") | Out-Null
    $appProcess = [System.Diagnostics.Process]::Start($appStart)
    if ($null -eq $appProcess) {
        throw "Temper application did not start."
    }
    Start-Sleep -Seconds $StartupSeconds
    if ($appProcess.HasExited) {
        throw "Temper application exited during startup."
    }

    $receipt = [ordered]@{
        receipt_version = "1.0.0"
        installer_filename = [System.IO.Path]::GetFileName($installer)
        signature_policy = $SignaturePolicy
        signature_status = [string]$signature.Status
        engine_version = [string]$handshake.engine_version
        schema_digest = [string]$handshake.snapshot_schema_digest
        engine_configured = [bool]$handshake.configured
        app_startup_seconds = $StartupSeconds
        app_remained_running = $true
        clean_install_root = $true
    }
}
finally {
    Stop-SmokeProcess -Process $appProcess
    $uninstallError = $null
    if ($null -ne $uninstaller -and (Test-Path -LiteralPath $uninstaller.FullName -PathType Leaf)) {
        try {
            $uninstallerProcess = Start-Process `
                -FilePath $uninstaller.FullName `
                -ArgumentList "/S" `
                -PassThru `
                -Wait `
                -WindowStyle Hidden
            if ($uninstallerProcess.ExitCode -ne 0) {
                throw "The Temper uninstaller returned a failure."
            }
            for ($attempt = 0; $attempt -lt 25; $attempt++) {
                if (
                    -not (Test-Path -LiteralPath $app.FullName -PathType Leaf) -and
                    -not (Test-Path -LiteralPath $engine.FullName -PathType Leaf)
                ) {
                    $uninstallCompleted = $true
                    break
                }
                Start-Sleep -Milliseconds 200
            }
            if (-not $uninstallCompleted) {
                throw "The Temper uninstaller left application binaries behind."
            }
        }
        catch {
            $uninstallError = $_.Exception.Message
        }
    }
    if (Test-Path -LiteralPath $resolvedSmoke) {
        $confirmed = [System.IO.Path]::GetFullPath($resolvedSmoke)
        if (
            $confirmed.StartsWith($resolvedTemp, [System.StringComparison]::OrdinalIgnoreCase) -and
            [System.IO.Path]::GetFileName($confirmed).StartsWith(
                "temper-clean-smoke-",
                [System.StringComparison]::Ordinal
            )
        ) {
            Remove-Item -LiteralPath $confirmed -Recurse -Force
        }
    }
    if ($null -ne $uninstallError) {
        throw $uninstallError
    }
}

$receipt["uninstall_completed"] = $uninstallCompleted
$receipt | ConvertTo-Json -Compress
