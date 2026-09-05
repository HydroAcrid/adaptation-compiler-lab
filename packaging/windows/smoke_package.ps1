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

function Start-EngineAdmission {
    param(
        [Parameter(Mandatory = $true)][string]$EnginePath,
        [Parameter(Mandatory = $true)][string]$ProfileRoot
    )

    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $EnginePath
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.Environment.Remove("TEMPER_RUNTIME_CONFIG") | Out-Null
    $start.Environment.Remove("TEMPER_PREDECESSOR_CONFIG") | Out-Null
    $start.Environment.Remove("CODEX_HOME") | Out-Null
    $start.Environment.Remove("CLAUDE_CONFIG_DIR") | Out-Null
    $start.Environment.Remove("OPENAI_API_KEY") | Out-Null
    $start.Environment.Remove("CODEX_API_KEY") | Out-Null
    $start.Environment.Remove("CLAUDE_API_KEY") | Out-Null
    $start.Environment.Remove("ANTHROPIC_API_KEY") | Out-Null
    $start.Environment.Remove("ANTHROPIC_AUTH_TOKEN") | Out-Null
    $start.Environment.Remove("ANTHROPIC_BASE_URL") | Out-Null
    $start.Environment.Remove("ANTHROPIC_BEDROCK_BASE_URL") | Out-Null
    $start.Environment.Remove("ANTHROPIC_VERTEX_BASE_URL") | Out-Null
    $start.Environment.Remove("OPENAI_BASE_URL") | Out-Null
    $start.Environment["HOME"] = $ProfileRoot
    $start.Environment["USERPROFILE"] = $ProfileRoot
    $start.Environment["APPDATA"] = Join-Path $ProfileRoot "AppData\Roaming"
    $start.Environment["LOCALAPPDATA"] = Join-Path $ProfileRoot "AppData\Local"
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) {
            throw "Temper engine did not start."
        }
        $handshakeRequest = @{
            protocol_version = "temper-engine-protocol/v1"
            request_id = "windows-clean-smoke"
            method = "system.handshake"
            params = @{}
            expected_snapshot_digest = $null
            idempotency_key = $null
        } | ConvertTo-Json -Compress
        $setupRequest = @{
            protocol_version = "temper-engine-protocol/v1"
            request_id = "windows-clean-smoke-setup"
            method = "setup.status"
            params = @{}
            expected_snapshot_digest = $null
            idempotency_key = $null
        } | ConvertTo-Json -Compress
        $process.StandardInput.WriteLine($handshakeRequest)
        $process.StandardInput.WriteLine($setupRequest)
        $process.StandardInput.Flush()
        $handshakeRead = $process.StandardOutput.ReadLineAsync()
        if (-not $handshakeRead.Wait(15000)) {
            throw "Temper engine admission timed out."
        }
        $setupRead = $process.StandardOutput.ReadLineAsync()
        if (-not $setupRead.Wait(15000)) {
            throw "Temper engine setup admission timed out."
        }
        $response = $handshakeRead.Result | ConvertFrom-Json
        $setupResponse = $setupRead.Result | ConvertFrom-Json
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
        if (
            -not $setupResponse.ok -or
            $setupResponse.protocol_version -ne "temper-engine-protocol/v1" -or
            $setupResponse.request_id -ne "windows-clean-smoke-setup" -or
            $setupResponse.result.configuration_state -ne "unconfigured" -or
            $setupResponse.result.raw_payloads_exposed -ne $false -or
            -not $setupResponse.snapshot_digest.StartsWith("sha256:")
        ) {
            throw "Temper engine setup admission failed closed-world validation."
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

$manufacturerKey = "HKCU:\Software\hydroacrid\Temper"
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Temper"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("DesktopDirectory")) "Temper.lnk"
$programsShortcut = Join-Path ([Environment]::GetFolderPath("Programs")) "Temper.lnk"
$legacyExecutable = Join-Path $env:LOCALAPPDATA "Temper\Temper.exe"
$programsExecutable = Join-Path $env:LOCALAPPDATA "Programs\Temper\Temper.exe"
$savedInstallLocation = $null
if (Test-Path -LiteralPath $manufacturerKey) {
    $savedInstallLocation = (Get-Item -LiteralPath $manufacturerKey).GetValue("")
}
if (
    (Test-Path -LiteralPath $uninstallKey) -or
    -not [string]::IsNullOrWhiteSpace([string]$savedInstallLocation) -or
    (Test-Path -LiteralPath $desktopShortcut) -or
    (Test-Path -LiteralPath $programsShortcut) -or
    (Test-Path -LiteralPath $legacyExecutable -PathType Leaf) -or
    (Test-Path -LiteralPath $programsExecutable -PathType Leaf)
) {
    throw "The clean package smoke requires a disposable Windows user without an existing Temper installation."
}

$smokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("temper-clean-smoke-" + [guid]::NewGuid())
$installRoot = Join-Path $smokeRoot "installed"
$profileRoot = Join-Path $smokeRoot "profile"
$resolvedTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$resolvedSmoke = [System.IO.Path]::GetFullPath($smokeRoot)
if (-not $resolvedSmoke.StartsWith($resolvedTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing an unsafe smoke directory."
}

$appProcess = $null
$uninstaller = $null
$hookHelper = $null
$uninstallCompleted = $false
$installLocationClean = $false
$uninstallRegistryClean = $false
$shortcutsClean = $false
$receipt = $null
try {
    New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $profileRoot -Force | Out-Null
    $installerProcess = Start-Process -FilePath $installer -ArgumentList @("/S", "/NS", "/D=$installRoot") -PassThru -Wait -WindowStyle Hidden
    if ($installerProcess.ExitCode -ne 0) {
        throw "Temper installer returned a failure."
    }

    $app = Get-ChildItem -LiteralPath $installRoot -Filter "Temper.exe" -File -Recurse |
        Select-Object -First 1
    $engine = Get-ChildItem -LiteralPath $installRoot -Filter "temper-engine.exe" -File -Recurse |
        Select-Object -First 1
    $hookHelper = Get-ChildItem -LiteralPath $installRoot -Filter "temper-hook.exe" -File -Recurse |
        Select-Object -First 1
    $uninstaller = Get-ChildItem -LiteralPath $installRoot -Filter "uninstall.exe" -File -Recurse |
        Select-Object -First 1
    if ($null -eq $app) {
        throw "The installed Temper.exe application is unavailable."
    }
    if ($null -eq $engine) {
        throw "The installed temper-engine.exe sidecar is unavailable."
    }
    if ($null -eq $hookHelper) {
        throw "The installed temper-hook.exe helper is unavailable."
    }
    if ($null -eq $uninstaller) {
        throw "The installed Temper uninstaller is unavailable."
    }

    $handshake = Start-EngineAdmission -EnginePath $engine.FullName -ProfileRoot $profileRoot

    $appStart = [System.Diagnostics.ProcessStartInfo]::new()
    $appStart.FileName = $app.FullName
    $appStart.WorkingDirectory = $app.DirectoryName
    $appStart.UseShellExecute = $false
    $appStart.CreateNoWindow = $true
    $appStart.Environment.Remove("TEMPER_RUNTIME_CONFIG") | Out-Null
    $appStart.Environment.Remove("TEMPER_PREDECESSOR_CONFIG") | Out-Null
    $appStart.Environment.Remove("CODEX_HOME") | Out-Null
    $appStart.Environment.Remove("CLAUDE_CONFIG_DIR") | Out-Null
    $appStart.Environment.Remove("OPENAI_API_KEY") | Out-Null
    $appStart.Environment.Remove("CODEX_API_KEY") | Out-Null
    $appStart.Environment.Remove("CLAUDE_API_KEY") | Out-Null
    $appStart.Environment.Remove("ANTHROPIC_API_KEY") | Out-Null
    $appStart.Environment.Remove("ANTHROPIC_AUTH_TOKEN") | Out-Null
    $appStart.Environment.Remove("ANTHROPIC_BASE_URL") | Out-Null
    $appStart.Environment.Remove("ANTHROPIC_BEDROCK_BASE_URL") | Out-Null
    $appStart.Environment.Remove("ANTHROPIC_VERTEX_BASE_URL") | Out-Null
    $appStart.Environment.Remove("OPENAI_BASE_URL") | Out-Null
    $appStart.Environment["HOME"] = $profileRoot
    $appStart.Environment["USERPROFILE"] = $profileRoot
    $appStart.Environment["APPDATA"] = Join-Path $profileRoot "AppData\Roaming"
    $appStart.Environment["LOCALAPPDATA"] = Join-Path $profileRoot "AppData\Local"
    $appProcess = [System.Diagnostics.Process]::Start($appStart)
    if ($null -eq $appProcess) {
        throw "Temper application did not start."
    }
    Start-Sleep -Seconds $StartupSeconds
    if ($appProcess.HasExited) {
        throw "Temper application exited during startup."
    }

    $receipt = [ordered]@{
        receipt_version = "1.1.0"
        installer_filename = [System.IO.Path]::GetFileName($installer)
        signature_policy = $SignaturePolicy
        signature_status = [string]$signature.Status
        engine_version = [string]$handshake.engine_version
        schema_digest = [string]$handshake.snapshot_schema_digest
        engine_configured = [bool]$handshake.configured
        hook_helper_installed = $true
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
                $hookRemoved =
                    $null -eq $hookHelper -or
                    -not (Test-Path -LiteralPath $hookHelper.FullName -PathType Leaf)
                if (
                    -not (Test-Path -LiteralPath $app.FullName -PathType Leaf) -and
                    -not (Test-Path -LiteralPath $engine.FullName -PathType Leaf) -and
                    $hookRemoved
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
    $remainingInstallLocation = $null
    if (Test-Path -LiteralPath $manufacturerKey) {
        $remainingInstallLocation = (Get-Item -LiteralPath $manufacturerKey).GetValue("")
    }
    $installLocationClean = [string]::IsNullOrWhiteSpace([string]$remainingInstallLocation)
    $uninstallRegistryClean = -not (Test-Path -LiteralPath $uninstallKey)
    $shortcutsClean =
        -not (Test-Path -LiteralPath $desktopShortcut) -and
        -not (Test-Path -LiteralPath $programsShortcut)
    if (-not $installLocationClean -or -not $uninstallRegistryClean -or -not $shortcutsClean) {
        throw "The Temper uninstaller left Windows installation metadata behind."
    }
    if ($null -ne $uninstallError) {
        throw $uninstallError
    }
}

$receipt["uninstall_completed"] = $uninstallCompleted
$receipt["saved_install_location_removed"] = $installLocationClean
$receipt["uninstall_registry_removed"] = $uninstallRegistryClean
$receipt["shortcut_residue_absent"] = $shortcutsClean
$receipt | ConvertTo-Json -Compress
