# Milestone 5 Conformance Record

Status: **complete; consented corpus, two-pass static profile, four condition materials, and
software custody frozen**

Milestone 5 constructs the first consented Codex corpus and four frozen target condition
materials. On 2026-07-23 the owner replaced third-party staffing with an internally blinded design:
two fresh AI profile contexts, deterministic sealed software custody, Kevin-blinded preference
scoring, and optional secondary isolated-AI quality annotations. This is functional separation,
not independent conduct.

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

Ordinary memory selects the newest complete, scanner-safe, exact-deduplicated feedback items that
fit its ceiling, then renders those retained items chronologically without procedure inference; it
records exact retained and excluded item digests. The strong profile used distinct fresh AI
author/reviewer contexts, the same corpus digest, exact packet/output receipts, no
pack/held-out/mapping/result/ambient-memory access, and at most 90 minutes total. All non-base
conditions bind the same eight task IDs and evaluation-case IDs. The full provenance-rich
`TargetPack` remains the audit asset; the compiled condition is a deterministic target-visible
projection of all eight approved behavioral contracts, omitting target-irrelevant lineage
verbosity while retaining the frozen release and pack bindings. Freeze rejects secrets, unsupported Claude
control syntax, unapproved raw fragments, padding, more than 3,000 target tokens, or more than
12,000 UTF-8 bytes. Target tokens are measured through Anthropic's pinned Messages token-count
endpoint using the frozen Claude model ID and a versioned system-prompt request envelope; local
tokenizer estimates are not accepted.

## Frozen operational result

The exact-consent, capture, recovery-drill, channel-classification, human semantic review,
source-family assignment, construction-side promotion, profile isolation, target token-count,
secret/leakage, cutoff, and custody gates passed. The final corpus digest is
`sha256:91f002684b1dafced9f265ce05c6998023e3d65f13fc682038b0af11363ef3d1`.
The corrected pre-construction registration digest is
`sha256:997408b26919b24f0ea5c3fd490e740d501a66a9dd4cdaf5d6d6f3076a34f4ee`.
The signed frozen release and validated Claude pack digests are
`sha256:807e0e8bdab2d701f6ef3f5f70d38fcea739dc4c4c94e8cba4f1f2d214037c60`
and `sha256:767ad009a2812d679cab709034677112f50e5c8841f56aa6494103eb9e19ab0f`.

The final condition-set digest is
`sha256:d4bca1e5d4d30271b37585522793a2f164d473203d2ddad4583ab61223f7ea43`.
Its target-visible sizes are:

| Condition | Anthropic tokens | UTF-8 bytes |
| --- | ---: | ---: |
| Base | 0 | 0 |
| Ordinary memory | 2,849 | 7,772 |
| Strong static profile | 2,563 | 8,080 |
| Compiled adaptation | 936 | 2,892 |

The deterministic custodian accepted four signed receipts, sealed one complete encrypted bundle
containing the four hidden tasks, secret condition mapping, committed 32-cell order, and exact
condition payloads, and verified the seal. Its safe complete-bundle digest is
`sha256:c85fbfd964058cd87be6ccc82fcd923f5e8707bd1b0ffb7ecd6d62938be392d2`;
its ciphertext digest is
`sha256:edc9af42c1ce56ada6f61564e3dca176c9da5d7ac9d5f51fd36d83a476ffe1ea`.
Temporary plaintext author/review packets, draft/final profiles, comparator projections, and
condition staging files were removed after the encrypted freeze. Signed receipts, safe manifests,
digests, encrypted stores, and append-only audit records remain.

## Next authorization gate

Milestone 5 is complete. No hidden task has been revealed to construction or to the user, and no
target trial or score exists. The next action would spend provider funds on the preregistered 32
Claude Code runs. It requires Kevin's explicit paid-run authorization after the final branch,
runtime, model, environment, condition, and custody digests are reported. After valid runs, Kevin's
blind ratings are the next mandatory user-input gate.

This conformance result proves instrument/custody readiness only. It is not evidence that a
compiled adaptation pack improves Claude Code.
