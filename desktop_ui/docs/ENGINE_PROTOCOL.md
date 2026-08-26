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

Development can locate the engine with `TEMPER_ENGINE_BINARY` or use
`python -m adaptation_compiler_lab.desktop.engine_main`. The optional
`TEMPER_RUNTIME_CONFIG` and `TEMPER_PREDECESSOR_CONFIG` values are read only by Rust and passed to
the sidecar; they are never delivered to the renderer. Packaged builds resolve the bundled
`temper-engine` executable beside the Tauri binary. Release compilation refuses a missing
target-specific build manifest. At runtime Rust hashes the sidecar before launch and verifies the
engine version plus public snapshot-schema digest returned by the handshake.
`TEMPER_ENGINE_BINARY` is a debug-only override and cannot replace the bundled engine in a release
application.
