# Temper engine protocol v1

The Tauri renderer cannot read files, launch processes, access credentials, or call arbitrary
engine methods. It can invoke two read-only Rust commands in the foundation release:

- `engine_handshake`
- `snapshot_get`

Rust supervises the Python engine over bounded newline-delimited JSON on standard input and
standard output. No localhost port is opened. Every frame is bound to
`temper-engine-protocol/v1` and a unique request ID. A mismatched version, response ID,
oversized frame, malformed response, or unavailable process fails closed with a sanitized
message.

The Python side exposes the existing `DesktopApplicationService`; it does not reimplement the
compiler or persistence. Its snapshot is explicitly raw-free. Browser development remains a
synthetic visual showcase, while a Tauri runtime removes demo suggestions and loads registered
projects and status from the live engine.

Development can locate the engine with `TEMPER_ENGINE_BINARY` or use
`python -m adaptation_compiler_lab.desktop.engine_main`. The optional
`TEMPER_RUNTIME_CONFIG` and `TEMPER_PREDECESSOR_CONFIG` values are read only by Rust and passed
to the sidecar; they are never delivered to the renderer. Packaged builds will resolve the
bundled `temper-engine` executable beside the Tauri binary.
