# Temper native packaging

Build each desktop artifact on its target architecture. Cross-compilation is not accepted for the
private alpha.

## Windows x64 development candidate

1. Start from a clean native Windows checkout.
   Reuse the current checkout rather than cloning a copy for every candidate. Keep at least
   8 GiB free before a native build; the builder refuses to start below that reserve.
2. Run `uv sync --locked --dev --group release`.
3. Run `uv run python packaging/build_native.py`. This compiles the governed Python engine and the
   no-console Rust hook helper as target-suffixed sidecars required by Tauri, then writes separate
   build manifests binding their binary
   digest, engine version, target triple, and public schema digest. Before the manifest is written,
   the builder launches the compiled binary in an isolated, empty user profile and requires two
   exact protocol responses from the same process within 15 seconds: the unconfigured closed-world
   handshake and the first `setup.status` read. Provider credentials and product-runtime overrides
   are removed from the admission environment. A binary that merely compiles or starts but cannot
   serve its first real product request is not admitted. The helper must be a native x64 Windows
   GUI-subsystem binary and must exit successfully without output when Temper is unavailable.
4. In `desktop_ui`, run `pnpm install --frozen-lockfile` followed by
   `pnpm tauri build --bundles nsis`.
5. Exercise an internal unsigned development candidate with:

   ```powershell
   ./packaging/windows/smoke_package.ps1 `
     -InstallerPath ./desktop_ui/src-tauri/target/release/bundle/nsis/Temper_0.3.0-alpha.2_x64-setup.exe `
     -SignaturePolicy development
   ```

The development policy exists only for local and ephemeral CI validation. An unsigned candidate is
not an alpha release and must not be published or offered to a tester. The smoke requires the
packaged uninstaller to remove the application, engine, and hook helper before its bounded temporary residue
cleanup runs. A current-user install uses `%LOCALAPPDATA%\Programs\Temper`; the separate
`%LOCALAPPDATA%\Temper` governed-data root is never an executable install destination and is not
removed by uninstall.

### Windows storage bounds

Windows sidecars reuse one `.temper-engine-cache` beside their executable. Desktop and MCP
launches use the same slot; starts, crashes, and restarts must not create a new full runtime
in `%TEMP%`. Nuitka validates the cached files against the embedded payload on every launch.
The native Windows launcher verifies the payload's SHA-256, serializes cache initialization,
then permits concurrent sessions. A Windows job owns the launcher and its descendants so
forced termination cannot leave an inner worker running. The launcher rejects redirected
cache paths and cache contents above 256 MiB. The Tauri Windows bundle includes the launcher,
compiled payload, and hook helper; macOS retains its existing engine path.
The install directory must remain writable by its owner. Close clients using the old engine
before upgrading: Windows cannot replace a loaded DLL. The installer removes the old slot
before replacement and stops the upgrade if it is still in use.

Desktop transport failures are limited to three automatic restart attempts per hour, with
at least a minute between attempts. A valid response resets the failure count. Windows
refuses a new engine start below 1 GiB of available disk space. These checks do not change
learning permissions, evidence retention, or qualification.

Before any native build or Cargo tests, run `python packaging/build_native.py --check-storage`
with the repository's venv interpreter. Admission rejects more than 4 GiB in the known generated
roots, and preserves an 8 GiB free-space reserve. Native Rust development builds disable debug symbols and incremental object retention. Nuitka
uses two compiler jobs and removes its compilation output after a successful build. Windows
build admission runs concurrent cold starts, repeated starts, damaged-cache repair, and forced
bootstrap interruptions in a fictional profile and rejects storage growth. After a candidate's checks and install,
use `cargo clean --manifest-path desktop_ui/src-tauri/Cargo.toml` and the equivalent hook-helper
command when generated targets are no longer needed. Preserve source edits, manifests, installed
binaries and private evidence; do not delete whole checkouts or recovery directories as cache cleanup.

The development smoke refuses to run when the current Windows account already has a Temper
installation. It installs silently into one bounded temporary root, performs the same two-frame
engine admission under a separate empty process profile, checks application-process liveness,
invokes the packaged uninstaller, and verifies removal of binaries, uninstall metadata, the saved
install location, and shortcuts. This is a packaging smoke, not UI automation or a separate-user
test. It does not prove that onboarding renders, controls work, credentials enroll, or Codex
connects. The current bundle also skips WebView2 installation, so arbitrary clean-machine
compatibility is not claimed until the supported Windows baseline or a bootstrap policy is frozen.

## Trusted Windows alpha

Configure a real Authenticode code-signing identity through the Windows certificate store, Azure
Artifact Signing, or another Tauri-supported signing command. Keep every credential outside the
repository. After `pnpm tauri build --bundles nsis`, run the same smoke script without overriding
its default `trusted` signature policy. It refuses unsigned or untrusted installers before
installation.

Only an installer that passes the trusted signature gate on a separate clean Windows runner may
enter a private release manifest. The current repository contains no signing credential and never
generates a self-signed certificate to imitate this gate.

## macOS Apple Silicon

The same builder produces arm64-only `temper-engine-aarch64-apple-darwin` and
`temper-hook-aarch64-apple-darwin` binaries. Internal
candidate builds run only on a native `macos-15` Apple Silicon runner, set macOS 13 as the minimum,
and produce both `Temper.app` and a DMG. The separate clean-runner job verifies both Mach-O
architectures, both exact sidecar digests, the unconfigured engine handshake, bundle metadata, DMG contents,
a visible first-run window, clean teardown, and one unique Keychain round trip that is deleted.

The clean-runner package command defaults to the trusted policy:

```bash
uv run python packaging/macos/smoke_package.py \
  --app /path/to/Temper.app \
  --dmg /path/to/Temper.dmg \
  --manifest /path/to/temper-engine-aarch64-apple-darwin.manifest.json \
  --hook-manifest /path/to/temper-hook-aarch64-apple-darwin.manifest.json \
  --expected-version 0.3.0a2
```

CI must pass `--signature-policy development` explicitly for an ad hoc sealed, one-day internal
candidate. The development builder seals the completed app bundle before constructing the DMG;
the smoke verifies the complete seal and exact app bytes inside the DMG. This exception verifies
internal functionality and bundle integrity only. A distributable macOS alpha still requires
a Developer ID Application identity, nested-code signing, hardened runtime, notarization,
stapling, and the same clean-machine smoke under the default trusted policy. The trusted policy
checks `codesign`, Gatekeeper assessment, and stapled tickets for the app and DMG. None of those
states may be inferred from an internal or Windows build.

Signing keys remain in the native certificate store, Keychain, or managed signing service. They
must never be committed, placed in `.env`, or uploaded with raw governed data.
