# Temper engine protocol v1

The Tauri renderer cannot read files, launch processes, access credentials, or call arbitrary
engine methods. It invokes a fixed Rust command allowlist. Rust supervises the existing Python
Temper engine over bounded newline-delimited JSON on standard input and standard output; no
localhost port is opened.

Every request is bound to `temper-engine-protocol/v1` and a unique request ID. Mutations also
require the exact snapshot digest and an idempotency key. A mismatched version or response ID,
oversized frame, malformed response, unavailable process, stale snapshot, replay conflict, or
unknown method fails closed with a sanitized message.

## Renderer command allowlist

- `engine_handshake`
- `snapshot_get`
- `learning_poll`
- `review_decide`
- `adaptation_revoke`
- `adaptation_undo`
- `feedback_record`
- `consent_renew`
- `preferences_update`
- `profile_export_preview`
- `profile_export`
- `profile_import_preview`
- `profile_import_stage`
- `modes_list`
- `mode_run_task`

There is no renderer command for a generic filesystem path, shell command, process, URL, or engine
method. Profile paths are selected in native Rust file dialogs and passed directly to Python; they
never enter renderer state or responses. Passphrases cross only the local IPC boundary and are not
logged, cached in mutation fingerprints, written to profile files, or returned to React.

## Python methods

- `system.handshake` reports protocol, engine version, snapshot-schema digest, and configuration
  state.
- `snapshot.get` returns the existing raw-free `DesktopApplicationService` snapshot.
- `learning.poll` performs one bounded poll only while local learning is enabled and consent is
  current.
- `review.decide` approves, project-narrows, explicitly narrows, ignores, or resolves a revocation
  against one exact queue item and proposal digest.
- `adaptation.revoke` removes one exact active artifact only when its current product digest still
  matches.
- `adaptation.undo` uses an immutable notice digest and active artifact ID and expires after 24
  hours.
- `feedback.record` binds helped/hurt/irrelevant to one exact activation and delivery receipt.
- `consent.renew` binds renewal to the currently displayed expiration.
- `preferences.update` persists only background learning and aggregate reporting switches.
- `portability.export.preview` builds a signed raw-free preview from the active governed release.
- `portability.export.create` encrypts and exclusively writes the previewed package.
- `portability.import.preview` decrypts and verifies one selected profile and returns an opaque
  15-minute preview token.
- `portability.import.stage` writes an append-only locally signed inactive review receipt.
- `mode.list` returns the raw-free evaluated first-party Mode catalog.
- `mode.task.run` binds Frontend Studio to one exact registered project and fresh governed Codex
  task, then returns only status, projection size, and change-review availability.

Opaque preview tokens bind export/import actions to the exact package retained inside the engine.
Import additionally binds the reviewed package digest. Mode delivery uses the existing disposable
writable gateway: repository changes remain outside the canonical project until the separate
governed Apply path is used. The signed Mode lifecycle records activation and delivery before the
target run and clean deactivation after success or failure.

The Python side exposes the existing presentation-neutral application service; it does not
reimplement the compiler or persistence. Browser development remains a synthetic visual showcase,
while a configured Tauri runtime removes demo state and loads registered projects, Core items, and
Mode availability from the local engine.

The transient renderer snapshot is `1.1.0`. It adds typed `SuggestionSummaryV1`,
`AdaptationSummaryV1`, `ActivationFeedbackSummaryV1`, and `RecentUndoSummaryV1` collections while
retaining the raw-free terminal projection temporarily for Advanced/recovery parity. Persisted
governed schemas are unchanged. All mutation responses use `MutationReceiptV1`; cached idempotent
replays return the original result and a conflicting reuse fails closed.

Tauri owns the five-minute scheduler. It reads the exact snapshot before polling, performs no poll
while learning is off or consent is expired, and sends only generic behavior-free notification
copy when a new proposal appears and OS permission is already granted. Closing the main window
hides it to the tray. The tray can reopen Temper, pause/resume learning through the same typed
preference method, or explicitly quit and tear down the scheduler.

Development can locate the engine with `TEMPER_ENGINE_BINARY` or use
`python -m adaptation_compiler_lab.desktop.engine_main`. The optional
`TEMPER_RUNTIME_CONFIG` and `TEMPER_PREDECESSOR_CONFIG` values are read only by Rust and passed to
the sidecar; they are never delivered to the renderer. Packaged builds resolve the bundled
`temper-engine` executable beside the Tauri binary. Release compilation refuses a missing
target-specific build manifest. At runtime Rust hashes the sidecar before launch and verifies the
engine version plus public snapshot-schema digest returned by the handshake.
`TEMPER_ENGINE_BINARY` is a debug-only override and cannot replace the bundled engine in a release
application.

## Claude hook channel

Claude hooks do not enter through the renderer command surface. The bundled `temper-hook` helper
reads one bounded JSON event from standard input and connects to a randomized local endpoint owned
by the running Tauri application. Windows uses an owner-only named pipe; Unix uses an owner-only
domain socket and peer-UID verification. Authentication is a 256-bit per-start token stored only in
an owner-restricted product descriptor. Neither the endpoint nor token is accepted from CLI
arguments or an environment override.

Tauri forwards the payload only to an already-running engine through the internal
`claude.hook.handle` method. The renderer cannot invoke that method. Hook calls cannot start or wait
for a new engine and use stricter 125 ms transport and 100 ms engine bounds. Any unavailable,
malformed, stale, oversized, unauthenticated, or timed-out path returns no output and exit success.
Release builds bundle and independently manifest-bind both `temper-engine` and `temper-hook`.
