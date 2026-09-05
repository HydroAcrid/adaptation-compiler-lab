# Temper Claude Code Delivery

Status: **local product contract and fixture-tested hook broker implemented; native transport and
live connection remain unavailable**

## Purpose

Temper's Claude integration is a cooperative source-and-target loop over Claude Code's official
hooks. It does not replace Claude memory, read transcripts, receive Anthropic credentials, or make
a provider call from a hook. The ordinary path is:

```text
Claude Code hook event
        ↓
signed local temper-hook helper
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

## Still required before the UI may say Connected

1. Bundle a signed `temper-hook` helper.
2. Add the per-user Windows named-pipe and Unix-domain-socket transport between the helper and
   Tauri, with bounded frames, timeouts, peer restrictions, and a fast no-op when Temper is down.
3. Connect the broker to the real governed runtime, encrypted capture store, audit ledger, and
   cached reconciled projection builder.
4. Add explicit preview/apply/disconnect protocol methods and truthful React states.
5. Pass disposable fake-Claude end-to-end tests and an explicitly authorized live smoke.

No hook has been installed on this machine, no Claude authentication has been initiated, no API
key has been read, and no paid call was made by this increment. The deferred Milestone 6 study
remains sealed and unrelated.
