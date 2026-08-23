# Native preview packaging

Build on the target architecture. Cross-compilation is not accepted for the private alpha.

1. Run `uv sync --locked --dev --group release` on a clean native checkout.
2. Run `uv run python packaging/build_native.py`. The checked-in builder uses Nuitka standalone
   mode, includes only the product QML data directory, and refuses a non-Windows/non-macOS host.
3. On Windows x64, sign the application binaries and the Inno Setup installer with the dedicated
   Authenticode certificate, then verify with `signtool verify /pa`.
4. On Apple Silicon macOS 14+, sign the `.app` with hardened runtime and the supplied entitlements,
   create the DMG, notarize it, staple it, and verify with `codesign` and `spctl`.
5. Generate a `DesktopReleaseManifest` only after both signatures and macOS notarization verify.
6. Upload artifacts to the private `adaptation-compiler-preview-builds` bucket and distribute only
   15-minute invitation-bound URLs.

Signing keys remain in the native certificate store/Keychain. They must never be committed, placed
in `.env`, or uploaded with an application artifact. No unsigned external installation is allowed.
