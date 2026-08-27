# Temper native product completion

Status: native onboarding, the everyday governed React loop, platform credential parity, React
recovery parity, Qt retirement, and the Apple Silicon build/smoke contract are implemented. A
fresh same-host Windows checkout has built and passed the current `0.3.0a2` development smoke; it
is not an independent clean-runner result. The Apple candidate has not yet run because the private
repository's GitHub Actions budget currently prevents jobs from starting. WSL cannot substitute
for the native macOS runtime, so this remains unavailable evidence rather than a passing result.

## Product boundary

Temper is becoming useful before installer publisher credentials are treated as a release gate.
The local Python engine remains authoritative for identity, consent, evidence, artifacts, project
scope, and delivery. Rust owns native dialogs and process supervision. React receives only
versioned raw-free presentation models and opaque preview tokens. Browser URLs remain synthetic
design scenes; installed Tauri state is authoritative.

External distribution stays fail-closed until genuine Authenticode and Apple Developer ID
credentials are available. That gate is independent of telemetry and does not block product
implementation or unsigned internal clean-runner testing.

## Phase 1: native onboarding and truthful Connections

Implemented:

- unconfigured sidecar startup with a setup-capable protocol handshake;
- live raw-free setup, secure-store, Codex, Claude, and existing-installation summaries;
- exact new-identity initialization with 30-day local consent and all observation/automation
  switches off;
- explicit existing-runtime preview and adoption without rewriting identity or lineage;
- Rust-owned folder and config dialogs, with paths retained exclusively by Rust and Python;
- prospective project previews and signed project registration with historical work excluded;
- exact Codex Desktop conformance pin for `codex-cli 0.150.0-alpha.8`, including executable,
  generated schema-bundle, and selected-schema digests;
- `codex login status` admission that requires saved ChatGPT authentication and strips API-key
  variables from every probe;
- honest capability separation between prospective source learning, fresh Temper-managed target
  delivery, and unavailable ambient injection;
- detection-only Claude inspection that offers no connection, authentication, hook, source, or
  target operation; and
- sidecar restart after initialization or adoption, followed by a configured handshake.

The renderer never receives executable paths, project paths, Codex homes, credentials, raw task
content, or decrypted evidence. Setup and adoption mutations are digest-bound, idempotent, and
stale-state protected.

## Continuous sequence

1. Reuse the repository smoke on an independent Windows machine or self-hosted runner, and execute
   the Apple Silicon `0.3.0a2` build/smoke on a native Mac. GitHub-hosted Actions is optional.
2. Add genuine publisher signing and notarization only when external installer distribution is
   authorized, and rerun both default trusted gates on clean machines.

## Phase 2: everyday governed loop

Implemented:

- desktop snapshot v1.1 raw-free suggestions, adaptations, activation feedback, and 24-hour undo
  handles, leaving persisted governed schemas unchanged;
- multiple live review suggestions with exact proposal/digest decisions, project-only or explicit
  scope narrowing, ignore, and revocation approval/rejection;
- exact active-artifact revocation, immutable-notice undo, delivery-receipt feedback, consent
  renewal, and persistent observation preferences;
- stale-snapshot rejection, strict parameter allowlists, proposal/artifact/delivery tamper checks,
  and in-process idempotent replay protection for every mutation;
- live Core revoke confirmation and recent undo, plus helped/hurt/irrelevant on Today;
- Rust-owned tray lifecycle and five-minute scheduler that never polls while learning is off or
  consent is expired; and
- generic native proposal notifications only when OS permission is already granted, with no raw
  behavior or evidence text.

React no longer maintains a second native suggestion or adaptation state. Browser routes remain
explicit synthetic scenes; installed Tauri state comes entirely from the local engine.

## Phase 3: platform credential parity

Implemented:

- one `PlatformCredentialStore` contract used by setup and recovery operations;
- immutable read compatibility for Windows DPAPI metadata v1.0 and v1.1 metadata for new Windows
  and macOS enrollments;
- unchanged CurrentUser DPAPI protection with plaintext carried only through the fixed PowerShell
  operation's standard input;
- native macOS generic-password storage through Security.framework FFI, without the `security`
  command-line tool or a plaintext fallback;
- one Keychain value containing both managed keys and an embedded subject/configuration/signer
  binding, plus raw-free local metadata and protected-payload digest verification;
- fail-closed Keychain status, unlock, atomic rebind with rollback, revocation, cross-subject
  denial, and external-change detection;
- an exact macOS CI round trip that uses a unique temporary Keychain service and deletes it; and
- desktop preferences v1.1 plus Temper-branded new-install paths, while reading historical
  AdaptationCompiler preferences and preserving their governed runtime pointers without moving
  raw evidence.

Learning, telemetry, decision notifications, and launch at login remain off when absent from old
preferences. A locked or unavailable native credential store disables mutations rather than
falling back to environment variables, renderer IPC, repository files, or plaintext storage.

## Phase 4: React parity and Qt retirement

Implemented:

- live learning, telemetry, decision-notification, and launch-at-login controls through one
  digest-bound preference mutation;
- transactional native launch-at-login through Tauri's platform autostart integration, with
  rollback if the engine refuses the matching preference write;
- live Advanced task execution, untrusted agent-result presentation, exact diff review,
  commit-bound Apply, Discard, and content-free diagnostics;
- exact protocol and renderer tests for task/run/apply/discard, diagnostics, preference allowlists,
  stale state, idempotency, and raw-payload denial;
- notification delivery only when the separate notification preference is enabled; and
- retirement of PySide6, QML, Qt controllers, `pytest-qt`, and the old Qt executable entry point.

React, Rust, and the retained `temper` terminal CLI all consume the same governed Python
application services. The renderer has no generic process or filesystem command, and browser
preview controls remain explicitly synthetic.

## Phase 5: Apple Silicon package contract

Implemented in source:

- product version `0.3.0a2`, Apple Silicon-only target `aarch64-apple-darwin`, and macOS 13 minimum;
- target-native Nuitka arm64 sidecar compilation plus `lipo` rejection of universal or non-arm64
  output before manifest admission;
- a manifest binding the engine version, target, minimum OS, public schema digest, binary name,
  size, and SHA-256 digest;
- Tauri `.app` and `.dmg` candidate construction on GitHub's `macos-15` arm64 runner with an empty
  entitlement set—no false App Sandbox, network, JIT, or library-validation exception claims;
- a separate clean-runner smoke that verifies checksums, arm64 Mach-O binaries, bundle identity,
  minimum OS, exact sidecar handshake, read-only DMG contents, a visible first-run window, a real
  temporary Security.framework Keychain round trip, bounded teardown, and residue cleanup;
- an explicit `development` policy for the ephemeral unsigned internal candidate; and
- a default `trusted` policy that requires Developer ID Application signing, Gatekeeper
  assessment, and stapled notarization on both the app and DMG.

The native Settings screen also no longer presents inactive cloud-reporting controls as working.
It shows current governed consent, allows an inherited reporting permission to be turned off, and
states that this internal build uploads nothing. The browser report is labeled as sample data.

The workflow YAML and package policy have passed local structural/unit validation, but the actual
Apple `.app`/`.dmg` build and fresh-runner smoke are **not yet observed results**. GitHub currently
rejects new Actions jobs for budget reasons. An unsigned or ad-hoc candidate cannot satisfy the
trusted policy, and this source implementation must not be described as a distributable macOS
alpha until the native job actually passes.

The Windows half has stronger current-head local evidence: product commit `253083e` and desktop
tree `aec90f0` produced the actual MSVC/Nuitka sidecar and Tauri NSIS installer from a fresh native
checkout. The explicit development
policy passed install, exact sidecar handshake, six-second application liveness, packaged
uninstall, and cleanup; the default trusted policy rejected the unsigned candidate before any
installation. See
[`conformance/windows-native-local-smoke-0.3.0a2.json`](conformance/windows-native-local-smoke-0.3.0a2.json).
Because the builder and smoke shared one Windows host, this does not replace independent
clean-machine or signed-release admission.

The sealed deferred Milestone 6 external-validation study remains outside this work and unchanged.
