# Milestone 5 Conformance Record

Status: **in progress; source capture and reviewed artifact construction passed; condition freeze
blocked on independent profile/custody roles**

Milestone 5 constructs the first consented Codex corpus and four frozen target condition
materials. The project may continue automatically through technical work, but it cannot
impersonate the source subject, independent profile author, custodian, or scorer.

## Desktop source runtime

The Codex Desktop app stores state in a schema that the npm `0.145.0` binary rejects. The project
therefore adds a separate immutable source lock for the Desktop-bundled
`codex-cli 0.145.0-alpha.30` executable. The lock contains its SHA-256, exact version output,
complete version-generated 341-file schema-tree digest, and exact initialize/list/read response
schema digests. Executable paths remain external.

The Windows-interoperable verifier accepts only resolved `/mnt/<drive>` paths, converts them
without an unpinned helper, regenerates schemas in a user-owned external toolchain, and fails
before source access on any drift. A live call on 2026-07-23 verified the binary and schema digest,
initialized the app server, and returned 11 completed metadata records with no next page. The
admitted output contained no preview, raw path, or task body.

## Exact-consent capture boundary

`source capture` accepts one task ID, one consent receipt ID, one unused capture receipt ID, and
one capture time. Before `thread/read`, it verifies:

- one exact `codex_app_server` selector and the configured subject/signer/fingerprint;
- the consent role, signature ledger, validity window, and retention deadline;
- the complete frozen pilot use set and no more than 30 days' retention;
- presence in bounded minimized inventory plus at least 15 minutes without an update;
- an external AES-256-GCM key and encrypted raw store; and
- an unused capture identity.

Only then may the connector return canonical full-thread bytes. The service binds their exact
source version/schema/payload digests into a signed receipt, stores ciphertext, and returns only
digests, byte count, encrypted locator, and turn descriptors. A failed receipt append removes a
newly created ciphertext entry.

On 2026-07-23 the subject supplied exact consent for eight task IDs. Eight separately signed
consent receipts and eight capture receipts were issued, and all eight full persisted threads were
stored as AES-256-GCM ciphertext in the external local raw boundary. No raw source bytes, private
paths, task IDs, or credentials entered Git, GitHub, or synchronized storage.

## Corpus, review, and condition controls

Synthetic tests require exactly eight sorted, separately consented/captured source tasks, created
by the construction cutoff and spanning at least four human-assigned source families. Review
projection is channel-based only: explicit user messages are eligible user authority;
agent messages, plans, reasoning, tools, webpages, hooks, and unknown/system items stay untrusted.
The real projection produced 63 consent/capture-bound Evidence v1.1 records from explicit user
messages. The subject confirmed eight extracted behavioral evaluations as accurate. Those
decisions were signed, converted into consent-narrowed Outcomes and independently checked
LessonCandidates, and routed through the least-invasive policy into four prompt rules, three
procedures, and one preference. One attempted cross-consent derivative failed closed on scope and
privacy broadening before any lesson or artifact was persisted; the accepted records retain one
exact task consent per promoted behavior.

Ordinary memory is chronological approved user feedback with exact canonical-digest deduplication
and no procedure inference. The strong profile requires an independent human-reviewer identity,
the same corpus digest, no held-out/scoring role, and at most 90 minutes. All non-base conditions
bind the same eight task IDs and evaluation-case IDs. Freeze rejects secrets, unsupported Claude
control syntax, unapproved raw fragments, padding, more than 3,000 target tokens, or more than
12,000 UTF-8 bytes. Target tokens are measured through Anthropic's pinned Messages token-count
endpoint using the frozen Claude model ID and a versioned system-prompt request envelope; local
tokenizer estimates are not accepted.

## Remaining objective gates

The exact-consent, capture, recovery-drill, channel-classification, human semantic review, and
construction-side promotion gates have passed. Corpus and condition freeze still require:

- an identified independent skilled strong-profile author with no holdout or scoring access;
- a real signed benchmark registration and independent custody procedure before condition freeze;
- all four secret/leakage/cutoff/budget scans passing before any held-out reveal.

The metadata inventory proves source connectivity and minimization only. It is not evidence that a
compiled adaptation pack improves Claude Code.
