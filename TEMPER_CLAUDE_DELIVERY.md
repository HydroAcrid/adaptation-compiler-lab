# Temper Claude Code Delivery

Status: **local product contract, governed runtime, native private transport, bundle integrity, and
explicit signed connection lifecycle implemented; authorized live Claude smoke remains pending**

## Purpose

Temper's Claude integration is a cooperative source-and-target loop over Claude Code's official
hooks. It does not replace Claude memory, read transcripts, receive Anthropic credentials, or make
a provider call from a hook. The ordinary path is:

```text
Claude Code hook event
        ↓
manifest-bound local temper-hook helper
        ↓
permission-restricted local Tauri channel
        ↓
Python hook broker
        ↓
registered-project + consent + native-environment + projection verification
        ↓
exact cached projection or silent no-op
```

The implementation follows Claude Code's documented [hook lifecycle and JSON
contract](https://code.claude.com/docs/en/hooks). `UserPromptSubmit` may return an
`additionalContext` value; `Stop`, `StopFailure`, and `SessionEnd` close the local observation
lifecycle without supplying guidance back to Claude.

## Implemented boundary

- Strict transient models accept only the fields needed for the four supported events. The
  supplied transcript path and every unknown field are discarded before dispatch.
- Exact user prompts are captured as `user_authored_input` only when the project is registered,
  consent is current, and learning is enabled. Capture alone never calls a model, creates Evidence,
  or upgrades ordinary input into approved feedback.
- Assistant output and failure details remain untrusted outcome context.
- Delivery uses a precompiled signed lease. The hook verifies owner, project, native instruction
  environment, issue/expiry window, material digest, release digest, projection manifest, and
  Ed25519 signature.
- The hook path has no semantic-interpreter or model-call interface.
- Invalid, absent, expired, cross-project, or stale projections produce an exit-success no-op with
  no target-visible text.
- Successful delivery emits only Claude's official structured `additionalContext` object, bounded
  below both 10,000 characters and 12,000 UTF-8 bytes.
- Raw payloads use the existing AES-256-GCM content-addressed store. Signed capture receipts bind
  the consent and prospective project registration while explicitly keeping assistant/failure
  content untrusted.
- Raw-free signed capture and audit receipts enter a hash-chained append-only local index that
  fails closed on signature, ordering, predecessor, owner, or mid-run file drift.

## Governed runtime

The concrete runtime maps a resolved working directory to exactly one non-overlapping registered
project and rehashes Claude's documented instruction sources before every event. Projection
preparation is a separate non-hook operation: it compiles the applicable approved release for
Claude, applies deterministic native coverage and conflict resolution using only semantic
relations already cached by an explicit/background analysis, and signs a five-minute in-memory
lease. The manifest retains included, native-covered, and blocked clause digests plus the exact
native source chain.

The hook request can only retrieve that cache; it has no projection-provider or model-call path.
If instructions change, consent expires, the project is unknown, or the lease is absent or stale,
Claude receives no Temper text. A prompt is user-authored input, not automatically a correction or
preference, and promotion remains in the ordinary governed review path.

## Connection lifecycle

Temper can prepare an exact diff for the four hook entries in Claude's user settings. The product
offers Connect only after exact executable/version/digest conformance and local authenticated
status. It does not initiate authentication or read a credential. Apply:

- requires explicit 30-day consent for the exact registered projects;
- verifies the settings and helper digests from the preview;
- preserves unrelated settings and hooks;
- stores the exact original bytes in the encrypted raw store;
- writes atomically and verifies the resulting digest;
- durably records a signed, idempotent receipt; and
- supports restart-safe rollback for 30 days, including restoring the original absence of a
  settings file;
- records a separately signed consent and chained connection receipt; and
- restarts the sidecar, then reports Connected only after current-state verification.

Disconnect removes only Temper-owned hook entries and leaves unrelated Claude configuration
unchanged. A two-minute Tauri-owned maintenance pass refreshes five-minute projection leases only
while the engine is already running. It does not call a model. Drift or expiry changes the
connection to Attention and makes delivery a silent no-op.

The renderer sees no helper path, Claude home path, credential, prompt, transcript, or backup
content. A signature proves local change integrity; it does not grant authority to Claude content.

## Native private transport

The bundled Rust `temper-hook` helper reads one bounded official hook event from standard input and
uses no command-line secret, environment secret, localhost port, shell, or renderer capability. It
discovers only Temper's fixed product-owned endpoint descriptor. Tauri owns a randomized endpoint
and 256-bit per-start token, then forwards the event to an already-running Python engine with a
100 ms engine deadline. It never starts the engine from a Claude hook.

On Windows the transport is a randomized named pipe with an owner-only DACL. On macOS and other
Unix development hosts it is a randomized Unix-domain socket with owner-only directory, socket,
descriptor, and peer-UID checks. Frames are capped at 1 MiB; client I/O is bounded to 125 ms.
Missing, stale, malformed, oversized, cross-user, mistokened, timed-out, or panicking paths return
exit success with no output so Temper cannot block ordinary Claude work. Descriptor replacement is
atomic, and an older Temper instance cannot remove a newer instance's endpoint.

Release packaging now bundles both `temper-engine` and `temper-hook`. The native builder verifies
the helper architecture, Windows GUI subsystem, silent-down behavior, exact digest, and protocol
manifest. Release compilation rehashes both binaries and refuses a missing or mismatched manifest.
The helper has no console window in a Windows release build.

## Remaining live gate

The UI may say Connected only for a currently verified receipt. Disposable end-to-end lifecycle
tests cover preview, consent, settings installation, restart, runtime activation, drift, disconnect,
and idempotent replay. Before claiming live interoperability, Temper still needs an explicitly
authorized smoke on a host with the pinned Claude Code release. Genuine publisher signatures remain
the separate external-distribution gate.

Historical Codex-only approvals retain their target restriction and are not silently widened.
After connection, a separate portable-Core review may authorize exact active artifact versions for
one project and Claude for 30 days. The signed transition is bound to the current release and prior
authorization state, changes only target compatibility, and is included in the delivery manifest.
New or superseding artifact versions remain excluded until another review. An empty confirmed
selection revokes the target authorization.

No hook has been installed on this machine, no Claude authentication has been initiated, no API
key has been read, and no paid call was made by this increment. The deferred Milestone 6 study
remains sealed and unrelated.
