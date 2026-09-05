# Temper Claude Code Delivery

Status: **local product contract, native private transport, and bundle integrity implemented;
governed runtime connection and live Claude use remain unavailable**

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
- Exact user prompts are eligible user-authority evidence only when the project is registered,
  consent is current, and learning is enabled.
- Assistant output and failure details remain untrusted outcome context.
- Delivery uses a precompiled signed lease. The hook verifies owner, project, native instruction
  environment, issue/expiry window, material digest, release digest, projection manifest, and
  Ed25519 signature.
- The hook path has no semantic-interpreter or model-call interface.
- Invalid, absent, expired, cross-project, or stale projections produce an exit-success no-op with
  no target-visible text.
- Successful delivery emits only Claude's official structured `additionalContext` object, bounded
  below both 10,000 characters and 12,000 UTF-8 bytes.
- Raw-free signed audit receipts retain only digests, project identity, event, disposition, and
  time.

## Connection lifecycle

Temper can prepare an exact diff for the four hook entries in Claude's user settings. Apply:

- verifies the settings and helper digests from the preview;
- preserves unrelated settings and hooks;
- stores the exact original bytes in the encrypted raw store;
- writes atomically and verifies the resulting digest;
- durably records a signed, idempotent receipt; and
- supports restart-safe rollback for 30 days, including restoring the original absence of a
  settings file.

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

## Still required before the UI may say Connected

1. Connect the broker to the real governed runtime, encrypted capture store, audit ledger, and
   cached reconciled projection builder.
2. Add explicit preview/apply/disconnect protocol methods and truthful React states.
3. Pass disposable fake-Claude end-to-end tests and an explicitly authorized live smoke.
4. Apply genuine platform publisher signatures only at the external-distribution gate.

No hook has been installed on this machine, no Claude authentication has been initiated, no API
key has been read, and no paid call was made by this increment. The deferred Milestone 6 study
remains sealed and unrelated.
