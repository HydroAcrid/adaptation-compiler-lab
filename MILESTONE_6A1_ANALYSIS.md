# Milestone 6A.1: Compact Runtime Projection

Status: implementation and local validation complete; no live comparison executed.

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

## Clause-level analysis

`development_benchmark_compact_projection/CLAUSE_ANALYSIS-v1.0.json` classifies every line,
including blank-line bytes, in all three old compiled packs, all three strong profiles, and all
three proposed runtime projections. A line may retain secondary semantic roles where one compact
sentence combines action, scope, or verification.

| Stage | Old compiled | Strong profile | Compact runtime | Shared envelope |
| --- | ---: | ---: | ---: | ---: |
| 1 | 922 | 227 | 163 | 362 |
| 2 | 1,629 | 508 | 371 | 362 |
| 3 | 1,652 | 462 | 378 | 362 |

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
| 2 | 10,280 | 2,389 | 1,780 | 371 |
| 3 | 11,744 | 2,420 | 1,780 | 378 |

## Separated maintenance measurements

The previous combined “maintenance actions” comparison is retired. The new record keeps unlike
measurements separate:

- deterministic full-cycle operations: three lifecycle applications, three governed release
  freezes, three runtime projections, and three clause-manifest bindings;
- machine time: 200 complete three-stage cycles averaged approximately 0.0081 seconds per cycle
  on the recorded Python 3.12 Linux environment;
- user review touches: three explicit approvals;
- historical static-profile effort: three author sessions, three valid reviewer sessions, one
  replacement reviewer attempt, about 29.61 author seconds, and 29.91 reviewer seconds; and
- target cost: 163/371/378 adaptation bytes, estimated as 41/93/95 tokens.

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
