# Mac Codex 0.157.0 analysis metadata

`manifest.json` binds four `--experimental` app-server schemas to the exact
verified Apple Silicon Codex 0.157.0 executable. `native-proof.json` records
sanitized local evidence. It contains no account identifier, quota percentage,
authentication material, prompt, model response, or private task history.

The four native schemas were regenerated from the executable named in the Mac
product pin. The quota request and both catalog schemas match the checked-in
Windows 0.160.1 versions byte-for-byte. The quota response differs only in
`PlanType`: Windows includes `promax` and Mac 0.157.0 does not. Both expose
`ordinaryUsageAllowed`, the `codex` subscription bucket, primary and secondary
windows, individual limits, rate-limit reasons, and spend-control state. The
capacity evaluator must still reject missing permission, stale or malformed
windows, spent capacity, and non-Codex buckets.

A read-only native probe validated quota and catalog responses against these
schemas. The strict temporary auth-only profile initialized and admitted the
configured model and effort. One authorized fictional turn completed with an
empty workspace, disabled capabilities, no ambient instructions, read-only
network-denied sandbox, and provider fallback disabled. The response was
encrypted in disposable storage, validated without printing it, and deleted
with the temporary auth profile. This proves one local transport path; it does
not authorize personal capture, calibrate the fictional evaluation, or show
real-work efficacy. The shared runtime still selects a Windows-only analysis
contract until its platform routing is reviewed.

## Separate admission blockers

The pinned `thread/read` schema gives `userMessage` an opaque `clientId` plus
content, ID, and type. `source`, `originator`, and `parentThreadId` describe the
thread, not each message's human producer. [Official app-server documentation](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)
describes `clientInfo.name` as supplied by the calling app. The supported
[`UserPromptSubmit` hook](https://learn.chatgpt.com/docs/hooks) exposes prompt
and turn ID but does not document an attested typed-human-versus-delegated
origin. A hook callback or caller-supplied client ID is therefore not proof of
human authorship. Unknown message origins remain ineligible for learning.

The versioned native instruction adapter can enumerate personal and project
`AGENTS.md` sources and select `AGENTS.override.md` precedence. This is
instruction inventory, not a semantic conflict verdict. Temper must admit a
native conflict checker against the effective owner/project instructions before
trial or publication; the present Mac contract does not enable one.
