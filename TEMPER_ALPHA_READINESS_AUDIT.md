# Temper alpha readiness audit

Date: 2026-08-27
Scope: current React/Tauri product, governed-engine boundary, Windows/macOS credential stores,
target-native packaging contracts, and external-user admission. The sealed deferred Milestone 6
study was not accessed.

## Verdict

**Temper's planned native product behavior is implemented in source, but Temper is not yet ready
for external installer invitations.**

The prior product blockers are closed: first-run setup is live, an existing governed identity can
be adopted without rewriting lineage, projects are registered prospectively, Codex and Claude
capabilities are described truthfully, the everyday review/revoke/undo/feedback loop is live,
Windows DPAPI and macOS Keychain fail closed, Advanced task review is governed, and Qt has been
retired. Browser routes remain synthetic demonstrations; installed Tauri state is authoritative.

The remaining boundary is independent native release evidence. A previous unsigned Windows
`0.3.0a1` candidate passed its development-policy clean-runner smoke. The current `0.3.0a2` Windows
candidate now passes the equivalent build/install/handshake/launch/uninstall flow on the same
Windows host from a fresh checkout, with its default trusted policy independently confirmed to
reject the unsigned bytes. This is useful current-head instrument evidence, but it is not a clean
runner. The Apple Silicon candidate has not run because GitHub currently prevents Actions jobs
from starting for budget reasons, and WSL cannot execute the relevant macOS surfaces. External
distribution additionally requires genuine Authenticode and Developer ID credentials plus the
default trusted clean-machine gates.

## Product behavior now implemented

- New setup and existing-runtime adoption preserve one identity, signer, consent ledger, project
  registry, and evidence lineage.
- Learning, automatic promotion, telemetry, notifications, and launch at login start off.
- Native folder selection keeps paths in Rust/Python and gives React only content-free project
  previews and opaque expiring tokens.
- Codex is admitted only at exact pinned version/schema/binary conformance with saved ChatGPT
  authentication. Learning is prospective and delivery is limited to fresh Temper-managed tasks;
  arbitrary existing task injection is not claimed.
- Claude is detection-only. Temper neither connects it nor initiates authentication or billed use.
- Multiple proposals can be kept, project-narrowed, explicitly narrowed, ignored, or adjudicated
  as revocations. Active adaptations can be revoked; exact recent promotions can be undone for 24
  hours; exact delivery receipts can be rated Helped, Hurt, or Irrelevant.
- Every mutation is target/digest-bound, stale-state protected, idempotent, and parameter
  allowlisted. React receives no raw evidence, credentials, private paths, or tool transcripts.
- Closing hides to the tray; explicit Quit terminates. Background polling is bounded and disabled
  while learning is off or consent is expired.
- Windows CurrentUser DPAPI and native Security.framework Keychain stores reject tampering,
  cross-subject access, unavailable protection, and identity drift without plaintext fallback.
- The governed task lab keeps changes isolated until exact diff review and Apply; agent prose is
  labeled untrusted and cannot stand in for independent verification.
- Native telemetry controls no longer imply a service exists. This internal build uploads nothing;
  the browser preview says it is sample data.

## Package evidence

Observed:

- Prior Windows unsigned-development run
  [`32987944410`](https://github.com/HydroAcrid/adaptation-compiler-lab/actions/runs/32987944410)
  passed all five `0.3.0a1` jobs, including install, exact sidecar handshake, launch, uninstall, and
  cleanup. The default trusted policy rejected the unsigned installer.
- Local locked Python, React, protocol, packaging-policy, and cross-target Rust checks cover the
  `0.3.0a2` source contract.
- A fresh same-host native Windows checkout at product commit `253083e` and desktop tree `aec90f0`
  built the real `0.3.0a2` MSVC
  sidecar and NSIS installer. The explicit development smoke verified the bundled engine, launched
  the installed app, uninstalled it, and left a clean install root. The exact raw-free receipt and
  installer digest are in
  [`conformance/windows-native-local-smoke-0.3.0a2.json`](conformance/windows-native-local-smoke-0.3.0a2.json).
  The default trusted gate rejected the same unsigned candidate before installation.
- A real Security.framework Keychain round trip previously passed on GitHub's macOS arm64 runner.

Implemented but not yet observed:

- Independent clean-runner confirmation of the current `0.3.0a2` Windows candidate.
- `0.3.0a2` arm64-only sidecar, Tauri `.app`/`.dmg`, and independent Apple Silicon clean smoke.
- First-run WKWebView rendering from the packaged app.

The Apple development smoke verifies file and `lipo` architecture, bundle ID, macOS 13 minimum,
manifest and sidecar SHA-256 binding, exact unconfigured protocol handshake, read-only DMG
contents, a PID-bound visible window of at least 720×540, a unique temporary Keychain round trip,
and bounded cleanup. The default trusted policy separately requires Developer ID Application,
`spctl`, and stapled tickets for app and DMG.

## Remaining external-user gates

1. Use an independent Windows machine/self-hosted runner for current-head confirmation and a
   native Apple Silicon Mac for the unobserved app/DMG development-policy receipt; GitHub-hosted
   Actions is not required.
2. Obtain genuine organization-backed Authenticode and Apple Developer ID Application identities.
3. Sign nested binaries and installers in the required order, notarize/staple macOS artifacts, and
   pass the unchanged default trusted smoke on clean machines.
4. Complete final manual keyboard/screen-reader review, branding/trademark clearance, installer
   icon exports, support/recovery copy, and invitation-bound download handling before public
   distribution.

No automatic updater, Claude hooks, provider API key flow, cloud evidence sync, automatic broad
promotion, or public preset marketplace is required or claimed for this alpha.

## Evidence and marketing boundary

Temper may now be shown to design partners through screenshots, browser demonstrations labeled
synthetic, and owner-run native development builds. It should not yet be offered as a general
download or described as signed, notarized, Apple-validated, or ready for users to entrust with
their work.

The product evidence shows that governed adaptation works end to end and that the native UI can
operate the governed services. It still does not prove that compiled adaptation generally beats an
excellent static profile or that silent automatic learning is broadly safe. Those claims remain
subject to genuine longitudinal use and future optional comparative research.
