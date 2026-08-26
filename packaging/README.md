# Temper native packaging

Build each desktop artifact on its target architecture. Cross-compilation is not accepted for the
private alpha.

## Windows x64 development candidate

1. Start from a clean native Windows checkout.
2. Run `uv sync --locked --dev --group release`.
3. Run `uv run python packaging/build_native.py`. This compiles the governed Python engine as the
   target-suffixed Nuitka sidecar required by Tauri and writes a build manifest binding its binary
   digest, engine version, target triple, and public schema digest.
4. In `desktop_ui`, run `pnpm install --frozen-lockfile` followed by
   `pnpm tauri build --bundles nsis`.
5. Exercise an internal unsigned development candidate with:

   ```powershell
   ./packaging/windows/smoke_package.ps1 `
     -InstallerPath ./desktop_ui/src-tauri/target/release/bundle/nsis/Temper_0.3.0-alpha.1_x64-setup.exe `
     -SignaturePolicy development
   ```

The development policy exists only for local and ephemeral CI validation. An unsigned candidate is
not an alpha release and must not be published or offered to a tester.

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

The same sidecar builder produces `temper-engine-aarch64-apple-darwin`. A distributable macOS alpha
still requires Developer ID signing, hardened runtime, notarization, stapling, and clean-machine
verification on Apple Silicon. None of those states may be inferred from a Windows build.

Signing keys remain in the native certificate store, Keychain, or managed signing service. They
must never be committed, placed in `.env`, or uploaded with raw governed data.
