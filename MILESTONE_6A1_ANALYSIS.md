# Milestone 6A.1: Compact Runtime Projection

Status: implementation and local validation complete; no live comparison executed.

Protocol note (2026-07-27): unexecuted v1.0 through v1.6 registrations are preserved. Review first
identified scalar/list-to-tuple coercion, then demonstrated that imported policy code could exit
the trusted scorer process after printing fabricated checks, and finally identified a pre-exec
resource-limit exception that could escape without a failure receipt. A final pass separated
untrusted policy workers from official observation output and preserved scope on verification
clauses. A further pass showed that worker stdout was still writable by generated code, target
compatibility was not enforced by the compact path, and same-ID transition substitution could
misstate lifecycle history. V1.5 restricts executable policy syntax to a capability-free
subset, binds target profile compatibility, binds each snapshot to the complete transition digest,
and retains exact links through all prior designs. V1.6 is a metadata-only successor that
binds formatter-normalized observer bytes after the integrity gate rejected post-freeze source
drift; it reuses the exact v1.5 runtime fixture. V1.7 also requires a known Codex target
family at the Codex renderer itself, preventing a Claude- or unknown-target projection from being
labeled and delivered as Codex output. V1.8 requires each active governance binding to
match its lifecycle introductions across evidence, consent, capture, evaluation, reviewer, and
policy metadata, and accepts only normalized safe relative paths in the shared envelope. Current
v1.9 aligns the exported portable JSON Schema with that path boundary. No live profile, target, or
judge session preceded any amendment.

## Question

Can the compiler retain its governed lifecycle while sending the target an instruction set as
compact and disciplined as an excellent static profile?

This milestone does not reinterpret Milestone 6A. Milestone 6A remains a failed product gate:
compiled and static tied on automated correctness, compiled produced 3/6 valid target records
versus 6/6, and compiled ended at 1,652 bytes versus 462 bytes. The blind judge cannot rescue
that result.

## Read-only integrity audit

The complete Milestone 6A public binding chain and its local private plan were audited without
writing historical artifacts or opening the deferred external-validation study.

- Outcome: pass.
- Exact private-plan digest:
  `sha256:c140d87a290661a014f4f7a3ca4a8f2805d017a7380e35703292e9c865ca5718`.
- Randomization-seed commitment:
  `sha256:8c6ee3468a6a97f2d486b6598dee957ee544da94b3abd0eebb0507310f2ab204`.
- Blind-report digest:
  `sha256:3c01f4be904cf635e3b39d28d645efcd5f9ec260dcfcd184799728978c795961`.
- No frozen artifact was modified and no sealed external-validation material was accessed.

The audit also preserved the known profile-receipt defect instead of correcting history:
receipts recorded 226, 507, and 461 bytes, while the exact newline-normalized files contain 227,
508, and 462 bytes. Future receipt construction now measures the normalized bytes actually
written.

## Instrument repairs

All five post-merge PR #18 findings were confirmed and repaired for future coordinators:

1. Unblinding verifies the exact private-plan file digest before parsing its mapping or run order.
2. Generated policy scoring runs in a Linux user/mount/network/PID namespace and read-only chroot
   with dropped capabilities plus hard wall, CPU, memory, file, descriptor, and process ceilings.
   Host files, the network, coordinator processes, benchmark files, and task files are unavailable
   or read-only. Timeout, `SystemExit`, `os._exit`, crash, and malformed JSON become failed scores
   with durable receipts.
3. Leakage scanning fingerprints normalized windows from the actual condition materials rather
   than checking a few labels.
4. Git state uses NUL-delimited porcelain-v1 parsing, reads both status columns, and handles
   rename/copy source paths.
5. Profile receipts measure exact normalized UTF-8 bytes, including the final newline.

These changes are prospective. No Milestone 6A observation, receipt, score, or rating was
rewritten.

PR #19 added six pre-merge hardening requirements. The implementation now resolves activation
conditions and exclusions as independent scope dimensions, rejects and defensively omits revoked
artifacts, requires complete artifact/scope/evidence equality in governance bindings, compares
manifest input with an exact deterministic re-render, uses the namespace/chroot scorer described
above, and binds a deterministic digest of every runtime-fixture artifact into preregistration.
Regression tests cover every finding, including same-length fixture substitution.

The final lineage/path passes reject serialized releases whose active governance claims cannot be
reproduced from lifecycle introductions. It also prevents absolute paths, traversal,
non-normalized separators, control characters, and prose-like injection from entering the
rendered shared execution envelope. V1.8 binds the initial path-validation change and v1.9 binds
portable-schema parity while every task, condition material, scorer, observer, sandbox, fixture,
measurement, and shared-envelope digest remains identical to v1.7. The lifecycle validator now
includes scope-limiting evidence and accepts only semantically valid introducing transitions.
These are prospective governed-release integrity repairs and do not change frozen target material.

The second PR #19 pass added four more fail-closed constraints: root coordinators cannot start the
scorer because Linux exempts outer UID 0 from `RLIMIT_NPROC`; manifest construction recomputes the
canonical projection from the release and context before rendering; the temporary pre-execution
review-refresh path was removed after the corrected freeze; and short condition/provenance markers
remain leakage even when they are too short for copied-excerpt windows.

The last PR #19 pass also converts `subprocess.SubprocessError` raised before exec—such as when a
host hard resource limit is already below the requested sandbox limit—into the same durable
crashed receipt used for other sandbox startup failures. Both the longitudinal scorer and compact
policy observer share this boundary. V1.2 remains byte-identical; v1.3 is its linked, unexecuted
successor with the repaired sandbox digest.

The next pass moved generated policy import/calls into child workers whose bytes are treated only
as untrusted return observations; trusted supervisors alone emit observation records, and the
parent alone compares them with hidden expected outcomes. The future longitudinal coordinator now
uses the same separation instead of executing the immutable historical Milestone 6A scorer.
Verification clauses retain the same unresolved scope as their source behavior and deduplicate
only at equal effective scope. V1.4 binds these repairs and a new versioned runtime fixture.

The next pass rejects imports, process exits, I/O, ambient builtins, attributes, decorators, and
other capability-bearing syntax before a generated policy can run. Only literal decision logic,
safe helper functions, and `ValueError` are available, so worker-channel bytes are emitted only by
the wrapper. Runtime projection now fails closed when an applicable artifact excludes the selected
Codex profile. Dogfood snapshots carry the canonical digest of the complete approved transition,
and external release construction requires an exact match before creating lifecycle events. V1.5
binds these repairs and a new versioned fixture while preserving v1.0 through v1.4 byte-for-byte.
V1.6 preserves v1.5 byte-for-byte and changes only the observer source digest required after
deterministic formatting.
V1.7 preserves v1.6 byte-for-byte, reuses the exact v1.5 runtime fixture, and binds the independent
Codex renderer target-family guard.
Its loader and issuer also require every unchanged task, scorer, observer, sandbox, fixture,
measurement, and envelope digest to equal v1.6 before accepting the renderer-only amendment.

## Clause-level analysis

`development_benchmark_compact_projection/CLAUSE_ANALYSIS-v1.2.json` classifies every line,
including blank-line bytes, in all three old compiled packs, all three strong profiles, and all
three proposed runtime projections. A line may retain secondary semantic roles where one compact
sentence combines action, scope, or verification.

| Stage | Old compiled | Strong profile | Compact runtime | Shared envelope |
| --- | ---: | ---: | ---: | ---: |
| 1 | 922 | 227 | 163 | 362 |
| 2 | 1,629 | 508 | 454 | 362 |
| 3 | 1,652 | 462 | 461 | 362 |

The shared envelope is identical between future conditions and is excluded from adaptation-byte
comparisons.

Old compiled byte classification:

| Category | Stage 1 | Stage 2 | Stage 3 |
| --- | ---: | ---: | ---: |
| Actionable behavior | 107 | 217 | 224 |
| Necessary scope | 0 | 28 | 28 |
| Necessary verification | 56 | 112 | 112 |
| Universal execution/security boundary | 239 | 239 | 239 |
| Audit-only provenance | 360 | 728 | 736 |
| Redundant metadata or boilerplate | 111 | 221 | 221 |
| Potentially distracting or harmful instruction | 49 | 84 | 92 |

The old target material exposed its experimental label, artifact headings, artifact IDs,
versions, evidence IDs, evaluation IDs, authority labels, target-profile labels, and numeric
precedence. Those fields remain valuable externally but are not needed by the acting target.
Universal safety text was also embedded only in the compiled condition, creating asymmetric
condition material.

The compact projection contains only behavior, unresolved scope, an explicit plain-language
precedence rule when necessary, and deduplicated verification:

| Category | Stage 1 | Stage 2 | Stage 3 |
| --- | ---: | ---: | ---: |
| Actionable behavior (including conditional action lines) | 107 | 250 | 257 |
| Necessary precedence or exception | 0 | 65 | 65 |
| Necessary verification | 56 | 56 | 56 |

This is an engineering compactness result, not performance evidence. The wording is generated
from the governed behavioral contracts and scopes; it is not copied from the static profiles.

## Invalid-run postmortem

The three invalid Milestone 6A compiled runs were inspected through the preserved encrypted 6A
target bundles. No rerun occurred.

| Task | Direct trace evidence | Automated behavior | Evidence-backed cause |
| --- | --- | --- | --- |
| Stage 1 persistent plan | Changed both `policy.py` and forbidden `test_policy.py` | Objective 1/1; diagnostic 0/1; neutral 0/1 | The agent ignored the allowed-path boundary and implemented the wrong existing-destination plan. |
| Stage 3 disposable plan | Changed both `policy.py` and forbidden `test_policy.py` | Objective 1/1; diagnostic 0/1; neutral 0/1 | The agent ignored the allowed-path boundary and failed to implement atomic replacement without a backup. |
| Stage 3 persistent action | Searched a parent `/tmp` path outside its workspace | Objective, diagnostic, and neutral all 1/1 | The patch was behaviorally correct, but the agent violated workspace isolation. |

The required behavior was present in each corresponding compiled pack, so missing information is
not supported as the cause. The two incorrect patches also conflict with explicit pack wording,
so their immediate cause is agent noncompliance. The old pack's audit-heavy presentation,
numeric precedence, condition label, and duplicated security boundary may have reduced behavioral
salience or encouraged searches for additional policy, but that remains a hypothesis. One run per
cell cannot separate renderer effects from ordinary run variance, and length alone is not treated
as causal.

## Representation split

The implementation now derives two outputs from one canonical governed release:

- The external governed release retains active artifact versions, exact evidence and consent
  lineage, evaluation and review references, cumulative lifecycle events, scope decisions,
  supersession and revocation history, parent-release rollback links, renderer version, and
  reproducible digests.
- The runtime projection resolves known context, omits inactive and superseded rules, preserves a
  minimal conditional when context is unknown, deduplicates verification, and contains no study
  labels or audit identifiers.

Every runtime clause is bound through a non-target-visible manifest to the exact active artifact
governance binding. The external governed release, canonical projection, rendered text, and
manifest all have independent digests.

| Stage | External governed release | Canonical runtime representation | External clause manifest | Target text |
| --- | ---: | ---: | ---: | ---: |
| 1 | 5,297 | 1,306 | 1,044 | 163 |
| 2 | 10,280 | 2,559 | 2,000 | 454 |
| 3 | 11,744 | 2,590 | 2,000 | 461 |

## Separated maintenance measurements

The previous combined “maintenance actions” comparison is retired. The new record keeps unlike
measurements separate:

- deterministic full-cycle operations: three lifecycle applications, three governed release
  freezes, three runtime projections, and three clause-manifest bindings;
- machine time: 200 complete three-stage cycles averaged approximately 0.0061 seconds per cycle
  on the recorded Python 3.12 Linux environment;
- user review touches: three explicit approvals;
- historical static-profile effort: three author sessions, three valid reviewer sessions, one
  replacement reviewer attempt, about 29.61 author seconds, and 29.91 reviewer seconds; and
- target cost: 163/454/461 adaptation bytes, estimated as 41/114/116 tokens.

No synthetic combined effort score is calculated.

## Remaining limitations

- Compactness is established only against the public engineering fixture; target behavior has not
  been measured under this renderer.
- Natural-language semantic equivalence is protected by table-driven and property tests, not a
  general theorem prover.
- The shared envelope is designed and hashed but has not been exercised in a live target run.
- The historical static-profile timing values are session measurements, not human labor estimates.
- One target-specific renderer exists (Codex). The canonical runtime representation itself is
  target-independent, but additional adapters remain future work.

The next product evidence must come from the frozen fresh comparison. No tuning is allowed after
seeing its live outputs under renderer version 1.0.0.
