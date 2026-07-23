# Milestone 5 Conformance Record

Status: **in progress; metadata-only source conformance passed, payload access blocked**

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
newly created ciphertext entry. No task body has crossed this boundary yet.

## Corpus, review, and condition controls

Synthetic tests require exactly eight sorted, separately consented/captured source tasks, created
by the construction cutoff and spanning at least four human-assigned source families. Review
projection is channel-based only: explicit user messages are eligible user authority;
agent messages, plans, reasoning, tools, webpages, hooks, and unknown/system items stay untrusted.
It never infers an outcome, correction, failure, or lesson.

Ordinary memory is chronological approved user feedback with exact canonical-digest deduplication
and no procedure inference. The strong profile requires an independent human-reviewer identity,
the same corpus digest, no held-out/scoring role, and at most 90 minutes. All non-base conditions
bind the same eight task IDs and evaluation-case IDs. Freeze rejects secrets, unsupported Claude
control syntax, unapproved raw fragments, padding, more than 3,000 target tokens, or more than
12,000 UTF-8 bytes.

## Remaining objective gates

No real task body may be read until the user explicitly confirms the proposed eight task IDs and
terms and eight signed per-task consent receipts exist. Corpus freeze then additionally requires:

- external signing/raw keys with documented recovery and 30-day purge limitations;
- human review of the local source packet and attributable structured outcomes/lessons;
- an identified independent skilled strong-profile author with no holdout or scoring access;
- a real signed benchmark registration and independent custody procedure before condition freeze;
- an exact target token-counting identity; and
- all four secret/leakage/cutoff/budget scans passing before any held-out reveal.

The metadata inventory proves source connectivity and minimization only. It is not evidence that a
compiled adaptation pack improves Claude Code.
