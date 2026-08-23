# Adaptation Compiler desktop private alpha

Status: engineering foundation implemented on 2026-08-23; not yet an externally installable build.

## Purpose

The desktop application is a calm owner-facing surface over the existing governed runtime. It does
not create another memory database, reinterpret evidence, or bypass signed decisions. The working
internal engine name remains Temper; the preview UI uses the public recruitment name **Adaptation
Compiler** until naming clearance is complete.

The application is designed to answer four everyday questions:

1. Is my behavior layer working?
2. Does it need a decision from me?
3. Which adaptations are active and where do they apply?
4. Can I run one fresh Codex task with the smallest relevant projection?

Advanced provenance, digest, route, evidence, and gate details remain available without dominating
the default experience.

## Implemented experience

- PySide6/Qt Quick desktop shell with Home, Suggestions, Adaptations, Run, Activity, Settings, and
  an explicit Advanced mode.
- One typed, raw-free application service shared with the terminal product surface.
- Exact-digest approval and rejection, exact-artifact revocation, helped/hurt/irrelevant feedback,
  explicit 30-day consent renewal, and read-only polling.
- A one-shot governed Codex work surface. It injects one scoped compact projection into a fresh
  isolated session and never changes ordinary Codex tasks or installs ambient repository memory.
- Two-phase write safety: target changes remain in a disposable worktree, the desktop renders a
  local unified diff, and the owner must Apply or Discard. Apply checks the reviewed Git head,
  requires a clean canonical tree, reruns bounded independent verification, and rolls back on
  failure.
- First-run import of an existing governed config with exact validation. Both background observation
  and aggregate reporting remain unchecked and off after import.
- Same-user Windows Task Scheduler and macOS LaunchAgent adapters. Disabling background operation
  writes the watcher stop signal before removing autostart.
- Target-native standalone Nuitka builder, Windows Inno Setup definition, macOS hardened-runtime
  entitlements, and a release manifest that rejects unsigned Windows artifacts or unnotarized macOS
  artifacts.

## Privacy and telemetry boundary

Raw evidence and target traces remain encrypted locally and never enter the preview service. The
only proposed remote payload is a strict, device-signed aggregate report containing allowlisted
counts, enums, dates, and projection sizes. Its Python and TypeScript schemas reject unknown fields
and have no prompt, output, behavior, evidence, repository, or path fields.

The private preview backend deliberately reuses the existing Supabase account, not Kairn's data
model. It creates only `adaptation_compiler_*` tables, a separate private build bucket, service-role
RPCs, RLS, invitation-bound installation tokens, signature verification, explicit deletion, and a
database-enforced 90-day aggregate-report expiry. The Next.js portal is a separate Vercel app.

Reporting is not operational in the desktop build yet. The local preference is separate and off by
default, but client enrollment, report preview/approval, and upload are intentionally disabled until
the private Vercel endpoint is deployed and its installation credentials can be stored in the
native credential facility. The UI states this rather than implying an upload occurred.

## What is deliberately not claimed

- This does not finish the genuine longitudinal 20-interaction/six-activation gate.
- It does not establish that compiled adaptation generally beats an excellent static profile.
- It does not activate specialty presets, automatically promote proposed learning, train weights,
  expose Milestone 6 custody, or perform cross-agent validation.
- It is not a public beta, web memory product, Codex plugin, or direct modification of ordinary
  Codex sessions.

## External-release blockers

The code and offscreen UI tests are usable for internal development, but external installation is
blocked until all of the following are true:

1. One-click prospective setup replaces the existing-config import screen and generates an exact
   project scope, managed identity, consent, and safe verification profile.
2. A current Codex executable and app-server schema lock is frozen for Windows x64 and macOS arm64;
   saved ChatGPT authentication is verified without accepting an API key fallback.
3. Managed secrets work through Windows CurrentUser DPAPI and macOS Keychain. The current runtime
   credential implementation is Windows-first.
4. Invitation enrollment, local report preview, explicit upload, and remote deletion are connected
   end to end—or reporting is omitted from the build.
5. Clean native builds pass on Windows 11 x64 and macOS 14+ Apple Silicon.
6. The Windows application and installer are Authenticode-signed. The macOS application/DMG is
   Developer ID signed, notarized, and stapled. The project currently has neither credential.
7. A clean-machine install/uninstall test and the full quality/security gate pass on both targets.

Until those gates pass, Monday outreach may recruit design partners and show reviewed screenshots;
it must not link to an unsigned installer or describe the alpha as ready to download.

## Verification contract

The repository gate remains the Python 3.12 locked sync, formatting, Ruff, strict mypy, full pytest,
source/wheel build, schema drift and migration checks, credential/private-path/raw-payload scans, and
clean Git status. The preview portal additionally requires TypeScript checking, Node tests, ESLint,
and a production Next.js build. Release validation adds native signature/notarization checks and
`DesktopReleaseManifest` generation.

The 2026-08-23 branch gate passed with 747 formatted files, 365 strict-mypy source files, 1,000 passing
tests and one expected Windows-only skip, source/wheel builds, four passing portal tests (including
the exact Python-to-TypeScript signature vector), ESLint, and a production Next.js build.
