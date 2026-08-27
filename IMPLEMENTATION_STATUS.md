# Implementation Status

Last updated: 2026-08-27

## Native product completion

The native onboarding and everyday governed-loop phases now replace synthetic first-run and
mutation assumptions with typed engine state.
Unconfigured startup, explicit new setup, explicit existing-runtime adoption, prospective project
registration, live connection inspection, and configured restart are implemented across Python,
Rust, and React. All setup mutations are bound to the reviewed state digest and an idempotency key;
native paths remain outside renderer state.

The Windows Codex product pin is refreshed to exact `codex-cli 0.150.0-alpha.8` executable and
generated schema digests. Connection readiness requires saved ChatGPT authentication. The UI
separately describes source learning, fresh managed delivery, and unavailable ambient delivery.
Claude is detection-only and has no Connect action, hook, provider login, or API-key path.

Configured Tauri now receives desktop snapshot v1.1 with typed live suggestions, approved
adaptations, pending activation feedback, and still-valid 24-hour undo handles. React can approve,
project-narrow, explicitly narrow, ignore, approve/reject revocation, revoke, undo, rate an exact
delivery, renew consent, and persist learning, telemetry, notification, and launch-at-login
preferences. Every mutation is
bound to the current snapshot, exact proposal/artifact/delivery/notice identity, a strict parameter
allowlist, and an idempotency key. Core no longer pretends native artifacts can be edited directly.

Closing Temper now hides it to a native tray. A Rust-owned five-minute scheduler first reads the
governed state and performs no poll while learning is off or consent is expired. New proposals may
produce a generic native notification only when OS permission is already granted; raw evidence and
behavior text never enter the notification. Browser preview state remains explicitly synthetic.

Platform credential parity is now implemented. New Windows and macOS enrollments use raw-free
credential metadata v1.1; immutable v1.0 Windows DPAPI envelopes remain readable. Windows retains
same-user CurrentUser DPAPI. macOS stores the managed Ed25519 and AES keys as one
subject/configuration/signer-bound Keychain value through native Security.framework calls, with
tamper detection, atomic rebind rollback, revocation, cross-subject denial, and no plaintext or
`security`-CLI fallback. Preferences v1.1 use Temper-branded paths for new installations while
reading historical preferences without moving raw evidence or creating a second identity. Every
new observation/startup preference defaults off.

React/Tauri now also exposes the existing governed fresh-task runner, transient agent report,
exact diff review, commit-bound Apply, Discard, and raw-free diagnostics. Agent reports are labeled
untrusted and the native UI does not claim checks passed without an independent receipt. Rust owns
transactional OS launch-at-login changes and proposal notifications respect the separate
notification preference. PySide6, QML, Qt controllers, `pytest-qt`, and the old Qt entry point are
removed; the `temper` terminal command remains the recovery surface.

The `0.3.0a2` source now includes the complete Apple Silicon build and clean-runner admission
contract. It builds an arm64-only Nuitka sidecar and Tauri app/DMG on `macos-15`, then a separate
arm64 runner verifies checksums, Mach-O architecture, bundle metadata, the exact unconfigured
engine handshake, DMG contents, a visible first-run window, a native Keychain round trip, and
cleanup. The internal job opts into a `development` signature policy explicitly; the smoke
script's default `trusted` policy requires Developer ID Application signing, Gatekeeper approval,
and stapled notarization. The Apple jobs have not executed on this revision because the
repository's GitHub Actions budget currently prevents jobs from starting. WSL cannot substitute
for native macOS execution because it cannot run the arm64 Mach-O app, Security.framework
Keychain, WKWebView, Gatekeeper, or DMG mount path. That is unavailable evidence, not a passing
result.

Native Settings now exposes the current raw-free consent state and no longer displays inert upload
history or cloud-deletion actions. Aggregate reporting remains off and disabled when unavailable;
an inherited enabled permission can be turned off. Nothing in the internal build uploads data, and
the browser-only report remains clearly sample data.

This is not the external release gate. Unsigned internal candidates are permitted only by an
explicit development policy. The current `0.3.0a2` Windows package has now passed a same-host
native development smoke from a fresh checkout, but not an independent clean runner. Apple remains
unobserved. Default trusted distribution remains blocked on genuine publisher credentials and
final signed/notarized clean-machine verification.

## Windows native alpha gate

Temper now has a target-native Windows packaging path rather than the historical Qt/Inno
prototype path. The release-group builder compiles the Python engine as the exact target-suffixed
Nuitka sidecar expected by Tauri, writes a manifest binding the engine version, public snapshot
schema digest, binary digest, filename, size, and target triple, and requires the compiled binary
itself to pass an unconfigured closed-world protocol handshake before the manifest is admitted.
The Tauri release build binds those values at compile time and verifies the bundled sidecar digest
again before launch.

The first real Windows builds exposed four packaging defects that source tests could not reveal:
the sidecar entry point collided with Python's standard-library `platform` module; the Rust bridge
could wait forever for a failed child; Tauri preserved the internal `temper-desktop.exe` name; and
Nuitka 2.8.10 could compile but not execute several Python 3.12 PEP 695 generic functions. Each
failed attempt remains visible in branch and CI history. The repaired engine uses an isolated
entry point, bounded response reads and teardown, the customer-facing `Temper.exe` identity, lazy
public imports for a small startup path, and equivalent `TypeVar` generic contracts for native
compiler compatibility.

A native Windows x64 rebuild now passes the mandatory post-build handshake with version
`0.3.0a1`, schema digest
`sha256:b45e9ad4a58ceb9d080a9886323b18678e92f48cd2745b00adfacc03d4f16cf2`,
`configured=false`, and `mutation_enabled=false`. Ten fresh process launches completed in
1.02–1.19 seconds. The separate clean-runner workflow installs the unsigned internal NSIS
candidate, repeats the engine handshake, launches the installed Tauri application, and removes the
temporary installation through its packaged uninstaller before residue cleanup. Its
development-signature exception exists only inside CI; the default
local smoke gate still rejects any installer without a trusted Authenticode publisher.

Final-head workflow run
[`32987944410`](https://github.com/HydroAcrid/adaptation-compiler-lab/actions/runs/32987944410)
passed the Linux, macOS, and Windows native contracts, the Windows package build, and the separate
clean-runner smoke. Its immutable console receipt records installer
`Temper_0.3.0-alpha.1_x64-setup.exe`, `signature_status=NotSigned`, exact engine/schema binding,
six seconds of healthy application startup, and `uninstall_completed=true`. A local invocation of
the same smoke script with its default `trusted` policy rejected that exact downloaded candidate
before installation. The one-day artifact is verification evidence only.

This does not create an external alpha release. The Windows CurrentUser certificate store and the
private repository's Actions secrets contain no code-signing identity. Temper will not create a
self-signed substitute, publish an unsigned installer, or describe the development candidate as
safe for invitees. Authenticode acquisition and a trusted clean-machine rerun remain external
release blockers, alongside the product/onboarding and Apple Silicon blockers in the readiness
audit.

The current `0.3.0a2` product source commit
`253083e2d83e4c6b01a2f55a89a4560a409ef5b7` (desktop tree `aec90f0`) was also rebuilt from a fresh
checkout directly on the Windows host without GitHub Actions. Nuitka used MSVC, the compiled
sidecar passed its mandatory
closed-world handshake, and Tauri produced
`Temper_0.3.0-alpha.2_x64-setup.exe` (20,235,800 bytes; SHA-256
`0226DD35A7AA31D1283531798C8BADFB9A22488D5B9AF85D41B160C58048E8BD`). The explicit development
smoke installed it, verified engine `0.3.0a2` and schema digest
`sha256:7319765ed344bbccd4d0302c6e518f5e735bb7f0f88e0b1034180169ba618c24`, kept the app alive for
six seconds, uninstalled it, and found a clean install root. The default trusted policy rejected
the same unsigned bytes before installation. This closes the current-head same-host Windows
instrument check; it is deliberately not described as an independent clean-machine result or
external-release admission. The raw-free local receipt is
[`conformance/windows-native-local-smoke-0.3.0a2.json`](conformance/windows-native-local-smoke-0.3.0a2.json).

## Temper React/Tauri rebuild

The accepted React 19/Vite product now runs inside a restrictive Tauri 2 shell and communicates
with the existing Python engine over `temper-engine-protocol/v1` framed stdio. Native state loads
registered projects and approved Core items from the real raw-free application service. Browser
URLs remain deterministic synthetic showcases and explicitly disable native writes.

Core now exposes real encrypted offline profile export/import through Rust-owned file dialogs.
Exports contain only signed active behavioral specifications and digested lineage. Imports verify
an exact preview and stage a locally signed inactive receipt; the source signature never transfers
instruction authority. Modes is now a separate actual route backed by the evaluated first-party
Frontend Studio Mode. It can run one exact registered-project task through the existing fresh
isolated Codex subscription gateway, records signed activation/delivery/deactivation, and returns
changes for review without directly writing the canonical project.

Frontend formatting, ESLint, strict TypeScript, component/engine tests, production build, and
34 Playwright visual/accessibility/product-interaction scenes pass. The Chromium interaction suite
caught and repaired an overlay stacking defect that made Core dialog controls unclickable. The
configured WebKit proxy still cannot launch on this WSL host without administrator-installed
system libraries, so native macOS validation remains open until the new Apple workflow executes.
Qt has been retired; the `temper` terminal command remains the internal diagnostic and recovery
surface. No release claim, signed installer, Claude hook, or external-study action has occurred. See
[`TEMPER_DESKTOP_REBUILD.md`](TEMPER_DESKTOP_REBUILD.md) and
[`TEMPER_ALPHA_READINESS_AUDIT.md`](TEMPER_ALPHA_READINESS_AUDIT.md).

The same audit found seven high-severity production advisories in the separate invitation portal.
The portal now pins Next.js and its matching ESLint configuration to 16.2.11, overrides Sharp to
0.35.0 and PostCSS to 8.5.23, declares the exact Turbopack root, and rebuilds with zero known
production vulnerabilities. This repairs the dependency tree; it does not make invitation
enrollment or telemetry upload operational.

Milestone 6B distinguishes private profile portability, future sanitized shareable behavior packs,
and lower-authority temporary Modes. The first and third now have real governed types and desktop
flows; a public Mode marketplace, third-party pack activation, and automatic preset generation do
not exist.

Repository-wide Ruff, strict mypy over 380 source files, source/wheel builds, and the serial Python
suite pass: 1,058 tests with three expected platform skips on WSL. React formatting, ESLint,
TypeScript, 40 unit tests, production build, and nine Windows WebView2 compatibility checks also
pass after the native package build. Rust formatting passes locally, and native Windows Rust
linking/package construction is observed above. Linux GUI and macOS native linking remain delegated
to suitable hosts because this WSL environment cannot supply or emulate their system runtimes.

## Desktop private-alpha foundation

The native desktop foundation is engineering-complete for internal existing-runtime dogfood. A
typed raw-free application service and React/Tauri UI expose the same signed runtime operations as
the terminal product: polling, exact proposal approval/rejection, exact artifact revocation,
activation feedback, explicit 30-day renewal, and a fresh governed Codex task.
The default interface hides operator detail; Advanced mode exposes route, evidence, digest, and
scope data.

The writable path now remains explicitly two phase. Codex operates in the existing disposable
gateway; the desktop loads the encrypted captured bundle locally and renders its unified diff.
Nothing reaches the canonical repository until Apply. Application requires the reviewed commit,
a clean tree, exact before-bytes and modes, and independent postflight checks; failures are refused
or rolled back and durably recorded. Discard creates a receipt bound to the bundle and its real
baseline rather than a placeholder head.

First-run UI safely validates and imports an existing governed config while leaving background
observation and aggregate reporting off. Windows and macOS autostart adapters, atomic local
preferences, a target-native Nuitka builder, Inno Setup definition, macOS entitlements, and
signature-gated release types exist. The private Next.js/Supabase foundation uses separate
`adaptation_compiler_*` tables and a private build bucket, verifies invitation tokens and Ed25519
aggregate signatures, rejects unknown report fields, supports explicit report deletion, and
enforces 90-day aggregate retention.

This is not yet an externally installable alpha. One-click new-user enrollment, current native
Codex pins, macOS Keychain credentials, deployed client-side invite/report flow, clean native
two-platform builds, Authenticode, Apple Developer ID/notarization, and clean-machine install tests
remain release blockers. Monday outreach may recruit design partners and show screenshots but must
not distribute an unsigned installer. See [`DESKTOP_PRIVATE_ALPHA.md`](DESKTOP_PRIVATE_ALPHA.md).

Final branch verification passes: locked Python 3.12 dependency sync, 747-file format check, Ruff,
strict mypy across 365 source files, **1,000 tests passed with one expected Windows-only skip**, source
and wheel builds, package-data inspection, schema/migration regressions, Git whitespace
and changed-file safety scans, plus the portal's TypeScript check, four Node tests, ESLint, and
optimized Next.js production build.

## Milestone 6A.3 terminal alpha surface

Phases 1 and 2 are implemented. `temper` is a separate product command over the existing typed
automatic-runtime services; it does not own a second database, learning engine, or raw-data path.
Its default read-only dashboard and `status`, `review`, `adaptations`, `history`, `health`, and
`gate` views consume one `TerminalAlphaSnapshot`. Its `poll`, `approve`, `reject`, `run`,
`feedback`, and `undo` commands call the already signed service operations. Approval requires the
exact proposal digest plus `--confirm-future-use`; undo requires an exact artifact ID plus
`--confirm`.

Rich terminal output, ANSI-free phone/plain output, and canonical JSON share the same typed
snapshot. Reviewed fixtures exercise a 13/20 all-allowances-used dashboard, a normalized review
card with exact evidence linkage, one active adaptation, a pending activation rating, and
80-column rendering. Renderer dependency tests reject direct persistence, raw-store, connector,
and runner access. Targeted automatic-runtime and CLI verification passes 190 tests with two
expected platform skips.

The first installed Windows command exposed one post-merge display defect: plain `health`,
`history`, and `gate` still fell back to Rich box characters, which a CP-1252 host stream rejected.
That failure is preserved as the local validation finding. Every plain view now has a dedicated
box-free renderer, the CLI configures UTF-8 on reconfigurable host streams, and a regression checks
all six plain views under legacy CP-1252 encoding. All six installed real-ledger views now run.

The product command was installed into an isolated local Windows development environment and its
read-only view was run against the exact signed predecessor-plus-successor dogfood lineage. It
reported 13/20 eligible interactions, four dates, two of six activation attempts, one rated
activation, no pending review or feedback, no active adaptation, enrolled credentials, an inactive
watcher, and all three error allowances used. This was an operational validation only: it did not
poll, decrypt raw evidence, mutate a ledger, count a new interaction, or alter the frozen external
study.

Phase 3 is therefore active but evidence-dependent. The remaining seven ordinary-work
interactions and at least four additional fresh activations cannot be simulated or manufactured.
The Base-versus-Temper comparison remains blocked until the genuine gate and exact compact pack
are frozen. The design-partner guide exists as a draft; no alpha build, tag, public release, or
partner onboarding is frozen yet.

Repository-wide verification passes: locked dependency sync, 722-file format check, Ruff, strict
mypy over 342 source files, 955 tests with two expected platform skips, source and wheel builds,
byte-identical automatic-runtime schema regeneration, focused migration/schema/foundation checks,
Git whitespace validation, and zero changed-file findings for provider secrets, private keys,
private paths, consented source-task IDs, or raw/private terminal-snapshot markers.

## Genuine 6A.2C cumulative checkpoint

The exact Windows-DPAPI managed successor was recovered without resetting its ledger. One stale
task-context-only proposal—“Treat Kairn as the target instead of the previously referenced
tool”—was rejected and immutably assessed as a false positive; nothing was promoted. A bounded
saved-ChatGPT poll then appended four genuine 2026-08-18 interactions, all with no explicit durable
signal and no review card.

Successor reporting previously showed only the new empty cryptographic lineage. The runtime now
fails closed unless `daily` and `gate-report` receive the exact predecessor config whenever a
signed successor receipt exists. It verifies both signer fingerprints, subject, cutoff,
predecessor config binding, and successor authorization before combining the ledgers. The live
cumulative result is 13 interactions across four dates, one missed learning, one false-positive
learning decision, one false activation, two activation attempts, and seven interactions
remaining. The current miss, false-learning, and false-activation allowances are therefore all
consumed.

An outdated installed Windows CLI also exposed an actionable-diagnostics defect. Unsupported
config versions now instruct the user to update the local Temper installation; malformed content
still receives only a generic raw-free error. The active product runway is Base versus Temper
after longitudinal completion, followed by a three-to-five-person local review-mode alpha. See
[`TEMPER_PRIVATE_ALPHA_PLAN.md`](TEMPER_PRIVATE_ALPHA_PLAN.md).

## Persona v3.2 fresh behavioral canary

The first fresh post-fix behavioral canary now passes its bounded gate. Compiled adaptation and an
independently authored/reviewed strong static profile each achieved 8/8 checks on the applicable
Tide Ledger task and 8/8 on the unrelated Ember Quay control. Neither condition falsely activated
in the control. The condition-blind quality judge tied the control and preferred the compiled
output on the applicable task. The study used the preregistered nine saved-ChatGPT sessions and
zero provider-billed calls.

The originally emitted final report is preserved and invalidated. A restricted scorer rejected
ordinary capability-free Python used by both conditions, while the first final gate failed to
require direct check totals. A versioned post-unblind amendment rescored only the exact frozen
diffs, accepted both implementation styles symmetrically, retained wrong-behavior and
host-capability rejection controls, and made no model call. A subsequent strict JSON finalization
failure also emitted no report and is preserved before the v1.4.1 repair.

The permitted conclusion is narrow: Temper matched this strong profile on two fresh tasks and its
compiled output received the better blinded quality judgment on the one applicable task. This is
genuine end-to-end effectiveness evidence, not proof of general superiority, cross-agent transfer,
or completion of the prospective ordinary-use gate. See
[`development_benchmark_persona_v32/README.md`](development_benchmark_persona_v32/README.md).

## Pre-v3 static engineering gate

The gate is implemented and passing without agent sessions. The successor persona interface
separates behavioral proposals from host-owned scope: model-authored scope strings cannot control
delivery, both conditions consume one exact scope registry, unknown evidence turns and scope
substitution fail closed, and the latest cited visible turn determines the registered scope. A
revealed-only audit bound all 39 reviewed v2.1 claims across 24 snapshots with zero fuzzy matches;
24 claims were applicable to their public scenarios. This is a transport repair for the successor,
not a retroactive repair of v2.1.

Lifecycle scoring is now non-vacuous and before/after based. Deterministic fixtures passed separate
addition, scoped-exception, correction, revocation, and neutral slices. A deliberately empty prior
state does not receive revocation credit. Least-invasive routing keeps a preference as a preference
and retains multi-route semantics for review. The report explicitly records zero language
evaluation, zero effectiveness evidence, zero agent sessions, and zero provider-billed calls.

The next model-facing work is a separately frozen v3 protocol followed by one one-persona
construction smoke. A full fresh v3 grid may begin only if that smoke proves both lanes receive
non-empty applicable material where expected and all deterministic accounting remains valid. V3
then measures semantic extraction and target behavior, not compiler plumbing. See
[`PRE_V3_STATIC_ENGINEERING_GATE.md`](PRE_V3_STATIC_ENGINEERING_GATE.md).

## Milestone 6A.2L.2 — Persona evaluation v2.1 execution

V2.1 executed through its objective gate and stopped. The compiled condition was exact on 10/24
states (41.7%); the independently authored/reviewed static condition was exact on 8/24 (33.3%).
Both missed the frozen 75% floor. Guidance sessions executed: zero. The experiment reports no
condition winner and does not count toward ordinary-use evidence.

On the 16 states requiring an active behavior, compiled was exact on 3 and static on 0. The
compiled path missed all six narrow exceptions, made six route errors, and failed several
lifecycle chains. The static roles authored 39 evidence-cited claims, but their packets omitted
the runtime's canonical scope vocabulary; exact target applicability therefore filtered every
claim. This is an invalid static comparator channel plus a genuine negative compiled objective
result. A typed gate report now prevents accidental guidance execution after failure.

The 18 accepted Luna sensor sessions and 48 accepted Sol author/reviewer sessions used saved
ChatGPT authentication and zero provider-billed calls. Five model-started non-results and two
pre-inference provider schema rejections are preserved in the incident ledger. No Milestone 6
external-validation material was accessed. See
[`MILESTONE_6A2L2_PERSONA_EXECUTION.md`](MILESTONE_6A2L2_PERSONA_EXECUTION.md).

## Milestone 6A.2L.1 — Persona instrument hardening

The evaluator was hardened and deterministically calibrated before v2.1 ran. Public role packets
now contain only stage-bounded turn numbers and message text. Expected labels, transition labels,
final persona summaries, future evidence, forbidden claims, and condition cues fail closed. Static
profiles require separate one-persona author and reviewer outputs with exact visible-turn lineage.
Compiled materials require exact semantic-interpreter, deterministic-detector, and review-receipt
bindings; reference projections cannot enter the v2.1 compiled path.

Internal state is no longer decided by an AI preference vote. Trusted code scores active evidence
turns, routes, scopes, forbidden lifecycle turns, and lineage against a construction-hidden oracle.
Fresh counterbalanced judges evaluate target-visible guidance only, after both conditions use one
neutral renderer. Guidance adjudication and unresolved rates are tracked separately, along with
first-position bias. Invalid instruments suppress condition interpretation.

The zero-call Lantern Docs calibration passed nine boundary checks covering redaction, stage
isolation, reviewer lineage, objective state, correction, revocation, exception scope, unrelated
activation, neutral rendering, and condition-cue rejection. It is explicitly non-evidentiary. V1
files are byte-bound by an immutability manifest. The original v2 preregistration is unchanged and
superseded before execution by a pinned 120-session-maximum v2.1 protocol. Author and reviewer
roles are stage-specific, so no context asked to produce an earlier snapshot can see a later turn.
The hardening quality gate passed before execution. No agent session or provider-billed call was
used for the hardening itself.

## Milestone 6A.2L — Naïve-agent persona evaluation

The framework is implemented and v1 is sealed as an evaluator-instrument failure. It enforces one
persona per isolated role, counterbalanced anonymous presentation, two independent Sol/xhigh
judgments, max-only disagreement adjudication, host-bound identities, encrypted external traces,
and synthetic-only claim boundaries.

V1 completed 63 accepted subscription sessions. Both tracks achieved 79.2% agreement and all 12
sentinel track outcomes were correct, but nine of 24 cases required adjudication, exceeding the
frozen six-case ceiling. The result cannot compare conditions. V1 also omitted the planned live
Luna sensor and used deterministic reference compiled projections, which independently prevents an
end-to-end product claim. The original fresh-case v2 design is preserved as unexecuted history. Its
v2.1 successor was then constructed and executed as the separate 6A.2L.2 instrument above.

## Current milestone

**Milestone 6A.2C remains the active ordinary-use evidence gate, now running on the implemented
6A.2D writable automatic gateway instrument.** A signed bounded
standing policy can govern explicit low-risk user feedback through encrypted raw capture, exact
Evidence v1.1 consent/capture lineage, an EvaluationCase candidate, deterministic promotion,
arbitrary-length addition/correction/supersession/revocation compilation, compact Codex
projection, signed release/activation events, exact-once task delivery, notification, undo, and
helped/hurt/irrelevant measurement. Untrusted content is rejected before capture; secrets are
blocked; ambiguous and capability-changing proposals remain inactive.

Milestone 6A.2J is engineering-complete. The internal-alpha surface now presents the runtime as one
review-mode daily loop under the working display name `Temper`: pending raw-free proposal cards,
exact evidence/consent/capture digests, completed activations awaiting feedback, recent notices,
credential/watcher health, review latency, pending age, scope-refinement count, activation-feedback
latency, and the unchanged 6A.2C gate. `runtime daily` is read-only; `--poll-now` performs one
bounded pickup before the same snapshot. The name does not change repository, package, schema, or
governance identities.

Owner review now supports strict scope refinement in addition to exact approval or rejection.
Task classes, environments, activation conditions, and exclusions may only narrow the immutable
proposal. The original queue item and v1.0 resolution format remain canonical. A refined approval
issues a typed v1.1 resolution, signs the exact newly evaluated decision, binds its narrower
artifact into the append-only ledger and release, and rejects widening, no-op refinement, rejected
refinement, or partial revocation. Automatic promotion remains disabled. Synthetic CLI conformance
proved proposal-to-refinement-to-daily-snapshot flow without touching production dogfood state;
the complete suite passes 859 tests with two platform skips. Genuine longitudinal product evidence
still must accrue prospectively under the frozen 6A.2C criteria.

Milestone 6A.2K is engineering-complete. A deterministic isolated simulation now drives the real
encrypted capture, signed review, append-only ledger, compiler, scoped projection, activation,
acknowledgement, feedback, and gate-report path through 20 interactions on three synthetic dates
and six later activations. The synthetic product gate passed: 18 correct learning assessments,
one false positive, one intentional miss, five content promotions, two revocations, six exact
activation sets, zero false or missed activation, three helped/one hurt/two irrelevant ratings,
zero repeated corrections, and projection sizes `0/190/209/302/227/0` bytes.

The simulation repaired three real defects: receipts now identify only artifacts contributing to
the task projection; reviewed revocations count as revocations rather than promotions; and
semantic corrections retain the exact host-bound artifact target. All simulated promoted captures
carry an exact synthetic selector and `synthetic=true`. Intermediate SQLite, encrypted raw bytes,
and keys are destroyed. The raw-free report declares `counts_toward_ordinary_use_gate=false`; this
does not complete or weaken the genuine 6A.2C gate.

Current verification is green: locked dependency sync, 670-file formatting, Ruff, strict mypy
over 323 source files, 900 tests passed with two expected platform skips, source and wheel builds,
schema and migration coverage, byte-identical v2.1 schema regeneration, idempotent material/score
reproduction, and zero new credential, private-path, consented-task-ID, or raw-payload findings.

Permanent-profile and current-context ownership is implemented. Capability-preset and personal
overlay references are typed and composition-checked, but no preset is imported or active. The
runtime correctly emits a zero-byte projection when no adaptation applies or the final rule is
revoked, so revoked behavior cannot survive as target-visible boilerplate.

Milestone 6A.2I has now implemented the bounded successor to 6A.2H. The model no longer selects an
artifact label. It extracts evidence-bound semantic properties—assertion kind, normative strength,
workflow structure, endorsed-example intent, transition intent, durability, clarity, and scope.
Deterministic code recomputes the least-invasive compatible route, rejects route substitution, and
requires review for unresolved combinations or multiple durable signals. Immutable legacy
semantic records remain readable and canonically stable.

After preserving calibration, construction, and audit-transport failures, the final fresh 64-case
holdout passed its preregistered development gate: 100% durable detection, 100% scope, 98.4%
semantic-class accuracy, and 90.6% exact feature/route decisions. Revocation, correction, and
multi-intent safety classes were perfect. Indexed blind auditors scored 98.4% and 100%, with 98.4%
agreement. This authorizes continued review-mode development only. Automatic promotion remains
disabled; synthetic evidence is not user authority and cannot mutate production state. No source
repository, real dogfood state, provider-billed API, or sealed external study was accessed.

The concrete adapter pins Codex 0.146.0 on Linux and Windows, requires saved ChatGPT
authentication, reads only post-cutoff user-authored messages from allowlisted completed
interactive tasks, durably checkpoints hashed prefixes, and keeps post-task learning separate from
later task activation and acknowledgement. Local `runtime` commands expose initialization, poll,
fresh one-turn execution, status, review, notices, exact undo, and helped/hurt/irrelevant feedback.
The target fails closed on model, approval, network, workspace, writable-root, or external
instruction-source substitution. A network-denied, rootless `readOnly` response is accepted as a
strict reduction from requested workspace-write authority for the legacy inspection command; any
network or root expansion remains forbidden.

Milestone 6A.2F removes manual cryptographic setup from local dogfood without creating an unsigned
mode. `runtime init` now defaults to independent in-memory Ed25519/AES generation and direct
Windows CurrentUser DPAPI enrollment. New configs, logs, receipts, and child environments contain
no keys, passphrases, or secret locators. V1 external-reference envelopes remain readable. For the
existing unavailable-key state, `runtime credentials rebootstrap` requires explicit lost-key
confirmation, preserves the predecessor unchanged, starts an empty prospective successor, copies
no evidence, and emits a new-key-signed `RuntimeSuccessorReceipt` that labels old ciphertext
unrecoverable. This is operational succession, not old-key rotation.

Milestone 6A.2E adds prospective multi-project dogfood onboarding without widening source access.
Config v1.4 gives each newly registered project its own signed creation-time cutoff and retains the
complete additive standing-policy lineage. Existing append-only runtime state remains bound to the
original policy digest. Registration may add exactly one project and cannot change routes, uses,
targets, limits, retention, expiry, or any non-project scope. Overlapping project roots fail closed.
`runtime project preview` uses only `account/read` and `thread/list`; it cannot read turns or message
content. Live metadata-only previews found two historical completed tasks in Green Meadow and two
in Kairn, with zero prospectively eligible tasks and zero `thread/read` calls. Those four historical
tasks remain excluded. Managed succession removed the lost external-signing-credential blocker;
both projects are now signed and registered prospectively. The first three-project poll appended
zero items, advanced only the raw-free source checkpoint, and left generation/artifact/review/
activation/feedback counts at zero. Watcher installation remains separate. Neither repository nor
any existing Codex task is modified by onboarding.

Milestone 6A.2D adds explicit DPAPI same-user unlock, a renewable background watcher, generic
Windows toasts plus an append-only local inbox, v1.3 project verification configuration, and a
one-shot/multi-turn governed gateway. Editable sessions use an exact detached worktree on a local
Windows-mounted volume and refuse read-only fallback. The agent cannot change protected verifier
inputs; candidate changes are encrypted, replayed into a second clean worktree for independent
testing, and shown locally before an explicit all-or-nothing canonical apply. Stale/dirty targets
are refused and failed post-apply checks restore touched bytes and modes. No gateway action commits
or pushes. Managed enrollment is automatic at new initialization; watcher installation and
canonical application remain explicit.

An isolated saved-ChatGPT development canary now proves the exact Windows gateway path rather than
only its synthetic fakes. A fresh pinned Luna session used an auth-only home and network-denied
native sandbox, created exactly one requested file in a disposable worktree, passed independent
postflight verification, produced an encrypted one-file review bundle, and applied it only after
an explicit exact-HEAD decision. Duplicate application was refused. Production dogfood state and
the sealed external-validation study were not used. This is instrument conformance, not completion
of the multi-day longitudinal evidence gate or proof of general superiority.

The first genuine post-cutoff semantic pickup is durably checkpointed. Its interrupted handoff
exposed and repaired typed-scope JSON serialization and poll-time-dependent observation digests;
exact replay appended no duplicate and advanced the source checkpoint once. The proposal's wording
accurately described the topic Kevin wanted in that chat, and Kevin approved it on that basis, but
the underlying reusable preference was never expressed. It therefore became the gate's first
false activation rather than positive product evidence.

Migration 0010 and `runtime review-decide` close the local review loop without weakening the raw
boundary. `runtime review` shows the normalized proposal, route, scope, and exact digest while raw
support remains encrypted. Approval or rejection appends one signed immutable resolution and
correct/false-positive assessment. Approval rechecks current governance and compiler invariants,
advances one release generation, and still requires a later explicit target activation; rejection
leaves state unchanged. Review output now asks whether the behavior should influence future
sessions, identifies rejection as the context-only action, and requires `--confirm-future-use` for
approval. Accuracy for the present chat is no longer sufficient authorization.

The original approval advanced the runtime to generation one. Its first target attempt failed
before turn start when Windows Codex safely reduced the WSL UNC workspace to read-only; the failure
remains immutable. After the sandbox repair, a new activation completed and followed the injected
preference, proving delivery but not learning validity. Kevin then clarified that the preference
was unexpressed and current-chat-only. The completed activation is append-only `irrelevant`
feedback, the artifact is revoked, and generation two has zero active artifacts. Prompt v3 now
forbids task-topic-to-preference inference. A targeted live eight-case ChatGPT-subscription smoke
correctly rejected four ordinary task topics and retained four explicitly durable statements.

Configuration v1.1 separates source-CWD aliases, the canonical target root, and optional distinct
source/target Codex endpoints. The active topology runs native Windows Codex with saved ChatGPT
authentication, admits only the registered Desktop project CWD, and targets the canonical WSL
repository through UNC. Windows Codex exposes that UNC workspace read-only, which is sufficient for
inspection-only activations but not editable target tasks; those require a future writable,
allowlisted target mirror. The construction cutoff remains frozen.

Migration 0009 adds immutable correct/false-positive/missed learning assessments. Activation
feedback now retains meaningful relevant-versus-activated sets, and the typed gate report measures
learning quality, activation correctness, repeated correction, pack size, latency, maintenance,
and deterministic readiness across 20 interactions, three dates, and six activations.

**Milestone 6A.5 previously completed a valid 15-turn persistent-conversation canary.** The original run is
preserved as instrument-invalid because resumed turns were read-only. A versioned runner repair
reasserted `workspace-write` on every resume, passed a live two-turn edit-and-test smoke, and then
produced 30/30 conformant target turns across the strong-profile and compiled conditions.

Both conditions completed all 13 work tasks objectively, preserved the neutral control, and made
no unsupported verification claims. Their automated behavior scores tied through Turn 10. The
frozen scorer placed the profile one check ahead at Turn 15, but post-hoc review showed that the
only difference was a narrow keyword false negative on a valid compiled purpose statement. The
raw result remains unchanged and the literal preregistered comparative gate remains failed.

The isolated condition-blind Sol/xhigh judge selected compiled adaptation overall: five compiled
task wins, one profile win, and seven ties. Its cumulative preference moved from 0–1 at Turn 3 to
3–1 at Turn 10 and 5–1 at Turn 15. The staged compiled material was 18.2% smaller at Stage 3 and
used 9.7% less terminal cumulative input in this canary. This is favorable, hypothesis-generating
longitudinal evidence—not a repeatable trend estimate or general superiority result.

The long-horizon registration bound the original Milestone 6A.4 staged snapshots, which predate
the later 974-byte communication-only expression repair. It therefore tests staged lifecycle
behavior, not the latest final renderer revision. A future replication must use fresh tasks,
multiple seeds, semantic scorers, more neutral controls, and current-renderer snapshots.

The claim remains bounded: this is internally blinded Codex development evidence with one
persistent episode per condition, not a powered general result or new cross-model proof. The deferred
Milestone 6 Claude study remains sealed, unchanged, and optional. Portable Specialty Presets
(Milestone 6B) remain a docs-only architecture draft; no preset has been imported, activated, or
evaluated.

## Completed scope

- Added typed standing-policy, interaction, capture, detection, evaluation, transition,
  composition-layer, state, cycle, delivery, notification, activation-feedback, metrics, and
  capability-preset-reference contracts for the automatic runtime.
- Added authority-first feedback detection. Deterministic grammar remains available, while a
  bounded semantic candidate generator covers natural phrasing without acquiring authority.
  Ordinary task instructions are not durable; agent/tool/repository/web/retrieval/system sources
  cannot acquire user authority by imitating feedback.
- Added automatic task-exact signed consent and capture receipts, encrypted local raw storage,
  evaluation-first promotion, signed review/release/activation actions, reproducible release
  history, compact context selection, exact revocation, zero-byte removal, and exact-once Codex
  task delivery.
- Added append-only automatic state/cycle/feedback tables in migration 0007, deterministic current
  state derivation, compare-and-swap stale-head refusal, helped/hurt/irrelevant feedback, and
  activation/pack-size/update-latency/maintenance metrics.
- Added append-only review and signed-event persistence plus a typed host coordinator and narrow
  interaction/delivery/review/notice ports. Duplicate observations cannot fork history; interrupted
  deliveries reproduce the exact historical receipt and rely on idempotent sinks rather than
  learning twice.
- Added a pinned Codex 0.146.0 product connector, Linux and Windows runtime locks, exact generated
  schemas, saved-ChatGPT-auth enforcement, post-cutoff project scoping, user-message-only pickup,
  hashed durable cursors, and a fresh one-turn target launcher.
- Added separate append-only learning-cycle, activation, target-acknowledgement, source-checkpoint,
  and activation-feedback records in migration 0008; completed source work never receives a
  retroactive delivery claim.
- Added local `runtime init|poll|run|status|review|review-decide|notices|undo|feedback` controls and live
  read-only Linux/Windows connection smokes with zero model/provider-billed calls.
- Added automatic-runtime and updated governance schema snapshots plus unit, security-property,
  migration, scope, revocation, secret, tool, preset, signature-tamper, and persistence tests.
- Added a typed 15-turn scenario grammar, deterministic within-stage task ordering, three
  cumulative snapshot deliveries, explicit feedback boundaries, 3/10/15 checkpoints, persistent
  Codex session isolation, independent per-task scoring, encrypted traces, anonymous outputs, and
  a condition-blind judge for Milestone 6A.5.
- Preserved the invalid v1 long-horizon run, repaired resumed-turn write policy in a separate
  runner, corrected cumulative-token accounting, passed a two-turn live resume smoke, and
  completed the valid v1.1 two-condition comparison without accessing the deferred study.
- Added portable external governed releases with cumulative lifecycle history, active artifact
  versions, exact lineage, scoped supersession/revocation, parent-release rollback, renderer
  identity, and reproducible digests.
- Added a schema-driven target-independent runtime projection that resolves known context, retains
  the smallest sufficient conditional for unknown context, removes inactive and superseded
  behavior, deduplicates verification, and expresses unresolved claim-specific precedence.
- Added a compact Codex renderer with exact normalized UTF-8 accounting and a non-target-visible
  clause-binding manifest. Audit IDs, condition names, evidence IDs, versions, authority labels,
  and audit headings do not enter target text.
- Moved universal execution/security rules into a separate shared envelope with exact allowed
  paths, untrusted-context boundaries, no auxiliary files/tests, no parent/host access, and
  workspace-bounded verification.
- Added generic table-driven and property coverage for stable ordering/digests, addition, scoped
  exceptions, precedence, supersession, revocation, partial/full context, no unrelated leakage,
  activation/deactivation, provenance binding, byte accounting, and varied generated scopes.
- Froze the unexecuted fresh three-task comparison, exact task/scorer/renderer/envelope digests,
  isolated role packets, corrected anonymous judge contract, primary automated gate, stopping
  rules, and nine-session maximum.
- Added a docs-only Milestone 6B Portable Specialty Presets architecture with temporary
  activation, clean deactivation, source/license/trust review, progressive loading, rollback,
  personal overlays, and the proposed Frontend Studio demonstration.
- All compiler, provenance, review, release, target-rendering, governance, encrypted evidence,
  withdrawal, recall, conflict, activation, benchmark custody, registry, preregistration, and
  immutable-result controls from Milestones 1–3 remain intact and backward compatible.
- Added an immutable Desktop source lock for `codex-cli 0.145.0-alpha.30`, its exact executable,
  full 341-file generated schema digest, and six request/response snapshots. The real verifier and
  minimized inventory pass through the same app-server adapter.
- Added `source inventory|capture`. Capture checks one exact signed selector, frozen uses,
  subject/signer/fingerprint, validity/retention, unused receipt identity, and external AES storage
  before `thread/read`; only ciphertext and signed digest metadata persist.
- Added exactly-eight/four-family payload-free corpus validation, non-escalating source-channel
  review projection, deterministic approved-feedback memory, independent-profile separation,
  equal-information four-condition freeze, budget/no-padding rules, and condition leakage/control
  syntax scans.
- Added explicit structural `SourceConnector`, `TargetRunner`, and `Scorer` ports with strict
  transient request/result values. Scorer input has no condition-label field and rejects metadata
  keys that could smuggle condition identity.
- Pinned `@openai/codex` `0.145.0` by npm integrity, executable SHA-256, and exact version output.
  Every source connection regenerates the complete experimental app-server schema bundle and
  compares a canonical semantic digest.
- Packaged exact version-generated `initialize`, `thread/list`, and `thread/read` schema snapshots.
  The adapter validates both request and response payloads and never reads/parses Codex
  rollout/session files.
- Source inventory uses `useStateDbOnly=true`, withholds preview/raw CWD, and returns only minimized
  local metadata. Exact reads require full persisted items, at least one turn, and terminal
  completed/interrupted/failed states; canonical full-thread bytes remain marked untrusted.
- Pinned `@anthropic-ai/claude-code` `2.1.218`, model `claude-sonnet-5`, direct Anthropic API base,
  Node `24.18.0` LTS installer archive, and exact Ubuntu 22.04 bubblewrap/socat package and binary
  identities.
- Added a Claude runner with bare mode, fresh configuration, empty setting sources, no session
  persistence, one digest-bound condition file, stdin task delivery, stream JSON, explicit model,
  turn/cost/time ceilings, and process-group timeout teardown.
- Restricted data/action tools to `Read`, `Glob`, `Grep`, `Edit`, `Write`, and Bash; only sorted,
  task-manifest-approved Bash patterns are preapproved. The documented non-removable
  `EndConversation` control may terminate a run; `dontAsk` denies anything else.
- Disabled Agent, web, MCP, plugins, skills, workflows, auto memory, attachments, artifacts,
  background tasks, updates, telemetry, error reporting, marketplace installation, alternate
  providers, and nonessential traffic.
- Added hard-fail WSL2 bubblewrap isolation with no unsandboxed escape, no automatic Bash approval,
  sensitive host-path denials, workspace-only allowances, and all Bash-subprocess network domains
  denied.
- Added exact Claude `system/init` model/tool/MCP/plugin validation plus trace-wide forbidden-tool
  rejection. API keys may come from the process environment or one mode-0600 external file and are
  never included in commands/results.
- Added fake Codex and Claude fixtures plus unit/property tests for binary/schema drift,
  substitution, minimized source inventory, partial/active source rejection, clean target state,
  condition injection, tool/network denial, arbitrary ambient instructions, arbitrary synthetic
  key non-exposure, missing/insecure credentials, alternate providers, timeout, and teardown.
- Verified the real pinned Codex binary by regenerating its schemas and performing initialize plus
  an empty `thread/list` against a newly created empty source home. It returned zero tasks and
  accessed no user source data.
- Added a sanitized machine-readable conformance status and a detailed Milestone 4 conformance
  record. No raw trace, executable path, private path, credential, or research payload is stored.
- Passed the accepted authenticated Claude smoke against the pinned model for USD $0.01566765. It
  independently verified exact synthetic output, captured only allowed `Read` and `Edit` uses,
  destroyed the workspace/configuration, and persisted only a minimized digest receipt.
- Captured exactly eight owner-consented Codex tasks into the external AES-256-GCM raw boundary
  with separate signed consent/capture receipts and a 30-day maximum retention deadline.
- Admitted 63 explicit user messages as Evidence v1.1 while agent, tool, web, repository, and
  system content remained untrusted; Kevin confirmed eight behavioral evaluations and four source
  families.
- Promoted eight reviewed artifacts, froze a release and Claude TargetPack, and added a narrow
  exact-consent-set union rule only for target-pack aggregation.
- Added the internal feasibility v1.1 preregistration, isolated author/reviewer role packets and
  receipts, deterministic software custody, secret-seed commitment and 32-cell shuffle, sealed
  held-out schemas, Kevin-blind presentation/rating models, and optional secondary AI scoring.
- Froze all conditions with equal source access: base 0/0; ordinary memory 2,849 tokens/7,772
  bytes; strong static profile 2,563/8,080; compiled adaptation 936/2,892.
- Sealed and verified the complete AES-256-GCM pilot bundle outside Git/workspace, then removed
  temporary clear packets, drafts, profiles, comparator material, and condition staging files.
- Added four public non-held-out development tasks, a pinned ChatGPT-authenticated Codex runner,
  a separate blind seed/mapping, AES-256-GCM trace bundles, anonymous output presentation, and
  objective/diagnostic/neutral scorers.
- Completed 16 sequential `codex exec --ephemeral` cells with the same CLI/model/reasoning/
  sandbox/one-turn/timeout contract. All traces conformed, all workspaces/configurations were
  destroyed, and no timeout, nonzero exit, API-key environment, or forbidden ambient surface was
  observed.
- Recorded the negative/inconclusive result without post-hoc repair: objective scores ceilinged,
  one task separated conditions, compiled adaptation trailed the strong profile on diagnostics,
  and Python-bytecode drift contaminated the neutral-control evidence uniformly.
- Moved condition material to a mode-0600 temporary Codex profile and task text to stdin after an
  excluded setup attempt revealed that command-line delivery was process-inspectable. Future
  fixture digests/copies exclude runtime caches and Python bytecode creation is disabled.
- Made future neutral checks deterministic even if bytecode exists: independent scorers now
  compare tracked/untracked material paths, exclude only `__pycache__`, `.pyc`, and `.pyo`, and
  bind the helper into the scorer-tree digest.
- Documented that the only separating task used a negated-substring false failure and a weak
  `descriptive` lexical proxy. The result cannot distinguish pack-expression weakness from normal
  implementation variance and does not justify a compiler or pack change.
- Designed four natural, non-leading replacement tasks covering all eight approved behaviors.
  Implemented the research-integrity task with structural hidden cases and deterministic neutral
  state. The other three tasks are now implemented with structural scorers; defective/reference
  mutation checks prove that each scorer detects its intended behavior before live execution.
- Preregistered the remaining 3 x 2 Luna gate with exact fixture/scorer digests, a six-run
  isolation contract, blind preference procedure, and conservative no-regression decision rule.
- Added a versioned Codex execution contract so the historical Terra/high gate remains immutable
  while new runs can pin explicit Luna/medium/Standard settings. Added live `model/list`
  verification and trace-level reroute invalidation.
- Completed two blinded Luna cells comparing only strong profile and compiled adaptation. Both
  were valid, tied on every check count, preserved every negative outcome and frozen input, and
  shared one ambiguous `blocked` versus `inconclusive` classification miss.
- Froze Kevin's first-output preference and rationale before opening the development mapping.
  Unblinding showed that compiled adaptation produced the preferred output while the strong static
  profile produced the other. This remains same-agent development evidence only.
- Froze Kevin's three remaining-task preferences before opening the development mapping.
  Unblinding showed that every preferred output came from the strong static profile. Both
  conditions tied on all aggregate automated counts; the only miss was the same environment-safety
  preflight check for each. The typed result classifies compiled adaptation below the strong
  profile under the preregistered rule.
- Completed the bounded Claude Haiku instrument repair through immutable v9-v11 failure receipts
  and a passing v12 receipt. The final runner puts the whole target in a minimal pinned Bubblewrap
  filesystem, mounts only the exact WSL resolver target needed for provider access, retains
  Claude's inner command sandbox, exposes only generated unittest aliases, validates `dontAsk`,
  and records quality independently from execution validity.
- The final v12 strong-profile and compiled-adaptation cells were both valid and perfect on this
  one public instrument task. Exact cost was USD $0.05902235. This establishes a functioning
  measurement path, not adaptation superiority or general cross-agent transfer.
- Completed and unblinded the corrected Claude Haiku strong-profile-versus-compiled grid under
  preregistration v2.9. All 16 public development cells were valid. Kevin's checksum-bound ratings
  were pushed before unblinding; compiled won 5–2 with one tie and led independent objective and
  diagnostic counts without a neutral regression. The exact mapping, costs, limitations, and
  product interpretation are in `CLAUDE_CORRECTED_COMPARISON.md`.
- Added a separate versioned public benchmark repair without rewriting the completed v2.9 tasks.
  Communication now structurally requires canonical POSIX shell-literal paths; environment safety
  now exercises recursive differences, layout containment, unused backups, exact restoration, and
  no-op identical publishes. Scenario-granular independent checks and defective/reference
  conformance fixtures prove sensitivity.
- Froze the two-task/two-condition/one-repetition Haiku design to the unchanged strong and compiled
  materials, pinned runtime, exact task/scorer/conformance digests, no-retry rule, and USD $1 hard
  ceiling. All four live records are valid.
- Added a reusable isolated Codex blind-rating gate pinned to `codex-cli 0.145.0`,
  `gpt-5.6-sol`, and `xhigh` reasoning with saved ChatGPT authentication. It mounts only an empty
  workspace and fresh configuration, disables ambient context and tools, validates structured
  output, encrypts its trace externally, and binds exact packet/output IDs before rating.
- Preserved three failed isolated-rating setup attempts with failure evidence, then completed
  preregistration v1.4. The durable rating was pushed while blind; unblinding found one compiled
  win and one tie, with both conditions perfect on all automated checks.
- Added typed longitudinal transitions, exact active-instruction lineage, deterministic scoped
  supersession, pack size/growth and update-effort measurements, clean Codex delivery receipts,
  append-only helped/hurt/irrelevant feedback, and derived correction/activation metrics.
- Added SQLite migration 0006 with update/delete guards for immutable dogfood feedback.
- Added six public stage-sensitive fixtures with independent objective, diagnostic, and neutral
  scenarios. Seeded implementations fail their intended diagnostic; references pass all checks.
- Froze and executed the 12-target-run longitudinal design plus isolated author, reviewer, and
  judge roles. The original final reviewer failed closed on malformed provenance; one explicitly
  authorized amendment raised the attempted-session ceiling from 19 to 20 and recovered the five
  valid encrypted outputs before one replacement review. No target rerun occurred.
- Completed and unblinded all 12 Luna/medium target cells only after the anonymous packet and
  Sol/xhigh judgment were frozen. Nine records were valid. Compiled tied all automated correctness
  counts but failed the validity, compactness, and maintenance gates.
- Completed the six-task Milestone 6A.3 fair task-channel comparison. All 12 target records were
  valid; compiled won five pairs and tied one while remaining smaller at every evidence stage.
- Completed Milestone 6A.4 through immutable adapter, oracle, sandbox, and valid-comparison
  failures; a v3 runner smoke; eight valid v3 target records; and a communication-only expression
  repair. The final four fresh target records and one blind judge passed the scoped gate.
- Bound the final 974-byte compiled pack to the same eligible evidence as the unchanged 986-byte
  profile, proved every non-communication rule byte-identical, and recorded the bounded
  four-family claim without touching the deferred external-validation study.

## Verification performed

From the canonical WSL repository:

```bash
uv sync --locked --dev
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv build
```

The current full suite checks formatting for 692 files, passes Ruff lint, passes strict typing
across 334 source files, passes 925 tests with two Windows-only checks skipped under WSL, and builds
both the source distribution and wheel. Immutable anonymous target outputs are excluded from
formatter/linter mutation.
Wheel inspection confirms the ports, adapters, runner, both
runtime locks, and both six-schema Codex snapshot sets are packaged. The original Codex runtime
verifier matched its pinned binary and canonical generated-schema digest
`sha256:e2d36bf67743ea6d89f93b598efaaffd873a1be0668a775401ab8817b808a851`.
The Desktop source verifier matched
`sha256:dbe5fd79870a16e9d2c3ebddb6e71c3c766aa1849af5efc09003c1f97b09ca2b`
and returned 11 minimized completed-task records.
The real Claude/sandbox verifier matched all local binary/version/helper pins and successfully
started a bubblewrap user namespace. The accepted authenticated smoke then exercised the API under
the frozen model/tool/sandbox contract.

The source, custody, runtime, and smoke checks establish instrument readiness. Milestones 6A.3 and
6A.4 additionally provide bounded same-agent development evidence about compiled-versus-profile
quality; they do not establish powered general or held-out cross-model transfer.

## Explicitly not implemented or exercised

- No held-out Claude target trial, held-out task reveal, held-out condition-bearing trace, Sonnet
  canary, or paid Milestone 6 pilot. The study is preserved unchanged and deferred for budget
  reasons as optional future research.
- No Kevin rating for the held-out pilot, held-out blinded adjudication, comparative pilot
  analysis, statistical report, or retention purge of the real payloads. The completed isolated-AI
  rating applies only to the public repair tasks and is not Kevin-specific preference evidence.
- No claim of independent human authorship, third-party custody, or independently conducted study;
  the active design is internally blinded with automated functional separation.
- No valid cross-agent result about base versus ordinary memory and no held-out cross-agent
  superiority result. The public Claude comparison gives a favorable descriptive
  strong-versus-compiled result, but the small development sample and scorer sensitivity defects
  do not establish a general transfer or product-advantage claim.
- No weight training/fine-tuning/LoRA, automatic tool creation/installation, Kairn, web UI, public
  publication, powered study, or remote research-data storage.

## Gate result and next action

Milestone 6A.2B is implemented and read-only live-conformant. Linux/WSL and Windows Codex 0.146.0
both verified the exact generated schema digest and saved ChatGPT account, then performed
post-cutoff list-only pickup with no model or provider-billed call and no private thread read.
Focused tests cover cursor replay/tamper, origin filtering, project/cutoff scope, separate
learning/activation/acknowledgement, append-only persistence, credential scrubbing, and target
sandbox/ambient-state substitution.

The current bounded product answer remains affirmative and is stronger longitudinally:
compilation has beaten the profile on lifecycle-stage scoping, matched or beaten it across the
approved behavior families, and now matched functional behavior while winning blind quality in
one valid 15-turn canary with a smaller pack. The strict raw 6A.5 gate did not pass, the staged
materials predate the final 6A.4 expression repair, and the project must not claim universal
superiority, a repeatable widening trend, independent replication, or held-out cross-model
transfer.

The automatic detector now has a schema-bound semantic interpretation port with grammar, shadow,
review, and calibrated modes. A real grammar-only cycle that missed a natural naming preference is
durably assessed as `missed`. The replacement runs one tool-free, network-denied, ephemeral Codex
batch, requires exact user-text support, and leaves authority, secrets, route, registered scope,
policy, corrections, promotion, and revocation deterministic. The first 48-case corpus failed its
holdout and remains preserved. A fresh v2 corpus passed 20/20 calibration and 20/20 untouched
holdout cases at 1.00 precision, recall, negative specificity, and route accuracy. This permits
review-mode dogfood, not a universal language-understanding claim or automatic promotion claim.

The active evidence gate is the ordinary-use 6A.2C dogfood period: at least 20 eligible interactions
across at least three dates, explicit polling, at least six fresh-session task activations, and
measurement of false
learning, review rate, correct/false activation, repeated correction, update latency, pack growth,
undo, and helped/hurt/irrelevant feedback. Only after that gate should an optional background
watcher and persistent multi-turn gateway be considered. Existing pre-cutoff tasks and simulated
dates do not count.

The React acceptance prototype now demonstrates a three-item ranked suggestion queue and a
separate evidence-strength/automation-disposition contract. Extensive synthetic detector and
persona results justify this ranked presentation and a future shadow policy, but they do not erase
the cumulative genuine gate's miss, false-learning decision, or false activation. Automatic
low-risk learning is therefore visible but off by default and non-mutating. The first proposed
eligible class is limited to explicit or corroborated, reversible, project-scoped preferences;
procedures, skills, global rules, conflicts, exceptions, revocations, and sensitive or ambiguous
material remain manual. See `TEMPER_CONFIDENCE_POLICY.md`.

The React identity prototype also replaces the rejected italic `T` monogram with a locally bundled
CC0 _Wind_ silhouette from Openclipart. The exact sanitized vector is digest-bound, contains no
active or external SVG content, and is recolored through the existing copper accent token. A
targeted brand snapshot now complements the full-window gallery so small identity regressions
cannot hide below the sparse-interface whole-image threshold.

No Portable Specialty Preset exists yet. Milestone 6B remains the following product milestone and
is currently architecture documentation only. The sealed external-validation study is not
required for either milestone and must remain untouched unless separately revived with funding.

Milestone 6A.2G adds an accelerated synthetic-only calibration lane without changing that
ordinary-use gate. Five repositories were abstracted under read-only Luna sessions into external
anonymous archetypes; no source content or path entered Git. A label-first 100-case corpus then
measured natural semantic selection across five contexts, ten wording styles, and synthetic turn
positions 1/3/5/10/15. The exact combined result was 49 true positives, zero false positives, 50
true negatives, and one false negative: precision 1.00, recall 0.98, specificity 1.00, route
accuracy 0.755, and scope accuracy 0.959. The calibrated gate remains closed because routing did
not meet threshold. Synthetic materials cannot enter the production ledger or count toward 6A.2C.
Milestone 6A.2H completed that next bounded step with six matched route classes, blind labels, two
independent auditors, exact revocation targets, and a fresh holdout. Final-v4 detection and scope
were perfect, but route accuracy was 90% on calibration and 85% on holdout. The flat-label route
gate remains closed. The next detector iteration must decompose meaning into evidence-bound
features and let deterministic policy choose the least invasive route; real dogfood remains in
review mode.

Milestone 6A.2I completed that structured successor. Public calibration under interpreter v1.7
reached 100% detection and scope with 95% route accuracy. The final indexed-audit v5 holdout then
passed the frozen gate at 100% detection, 100% scope, 98.4% semantic class, and 90.6% exact feature
decision accuracy. The development result validates the hybrid architecture; it does not authorize
unattended promotion. The active next evidence remains genuine 6A.2C review-mode dogfood, with
borderline rule/procedure and preference/example cases retained as review candidates.

Persona v3 instrument calibration is now complete at the construction-channel level. The original
Sable smoke remains a valid negative record: compiled activated nothing and static found both
behaviors but exposed an ambiguous preference/procedure oracle. The fresh Nola replacement removed
those confounds; its independently reviewed static profile scored 2/2 exactly, while its original
compiled sensor exposed positive-example bias from overlapping structured-output branches. The
route-neutral schema remediation and non-durable binder amendment preserved both failed launches,
then produced an exact 2/2 compiled state with zero task-only false activations and correct
host-owned scopes. All sessions used the pinned Codex CLI, saved ChatGPT authentication, isolated
state, encrypted external traces, and zero provider-billed calls.

This is instrument calibration, not Temper-effectiveness evidence. The successful sensor diagnostic
reused the public Nola calibration fixture after a prior result; no target behavior task was run.
The original v3 and v3.1 results were not rewritten, the full v3 grid was not launched, and the
deferred external-validation study was not accessed. The next AI evaluation must use fresh
post-remediation personas and scenarios; static tests remain responsible for transport, binding,
scope, lifecycle, and scoring mechanics.
