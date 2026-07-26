# Claude Corrected Development Comparison

Status: **complete, unblinded, and descriptively favorable to compiled adaptation**

Date: 2026-07-25

This report covers the public, non-held-out Claude Haiku v2.9 development comparison. It is not
the sealed Milestone 6 pilot. Kevin's eight preferences were checksum-bound, committed, and pushed
while the condition mapping and automated scores were still hidden. Only then was the encrypted
mapping opened.

## Result in one sentence

Compiled adaptation won Kevin's blind preference **5–2 with one tie** and passed more independent
objective and diagnostic checks than the strong static profile, but the task tests and parts of the
independent scorer are not yet sensitive enough to establish a durable product advantage.

## Condition totals

| Measure | Strong static profile | Compiled adaptation |
| --- | ---: | ---: |
| Kevin preference wins | 2 | 5 |
| Kevin preference ties | 1 | 1 |
| Valid runs | 8/8 | 8/8 |
| Independent objective checks | 25/32 (78.1%) | 28/32 (87.5%) |
| Independent diagnostic checks | 18/32 (56.3%) | 20/32 (62.5%) |
| Neutral-control checks | 32/32 (100%) | 32/32 (100%) |
| Provider cost | $0.34201990 | $0.33382705 |

The successful 16-run grid cost exactly **$0.67584695**. The nine failed-closed corrected-runner
attempts cost exactly **$0.89338870**, so the complete corrected-comparison repair and execution
program cost **$1.56923565**. Earlier runner canaries v2–v12 cost another known exact
**$0.62505060**; the first canary's exact charge was unavailable and was bounded by $0.25. The
known exact Claude development spend represented by these records is therefore **$2.19428625**,
with a conservative ceiling of **$2.44428625** after including the unknown first-canary charge.

## Task-level matrix

`C` means compiled adaptation, `S` means strong static profile, and `T` means tie. Check counts
aggregate both repetitions for that condition.

| Task | Kevin preferences, reps 1/2 | Strong objective / diagnostic | Compiled objective / diagnostic | Interpretation |
| --- | --- | ---: | ---: | --- |
| Communication | C / S | 8/8 / 6/8 | 8/8 / 5/8 | Split. Neither condition consistently rendered shell-literal paths safely. |
| Debugging and verification | C / C | 8/8 / 6/8 | 8/8 / 6/8 | Implementations were identical; Kevin preferred the compiled explanations in both repetitions. |
| Environment safety | C / S | 3/8 / 2/8 | 6/8 / 5/8 | Split preference. Compiled led the scorer, but each condition had a materially incomplete implementation. |
| Research integrity | T / C | 6/8 / 4/8 | 6/8 / 4/8 | The second compiled run was plainly best to Kevin, while the hidden checks exposed remaining report-contract omissions. |

The repeated tasks matter: communication and environment safety switched winners between
repetitions. The result therefore contains ordinary agent variance as well as adaptation effects.
The debugging preference difference came entirely from explanation quality because all four
patches were the same.

## Anonymous-output mapping

| Task | Rep | First | Second | Kevin result |
| --- | ---: | --- | --- | --- |
| Communication | 1 | `output-2e74c19c888f18d4d0e2d6aa` = strong | `output-5b7916d4e7ab51a7ff785ea9` = compiled | Compiled |
| Communication | 2 | `output-3bdc50de898b7c335011b3e8` = compiled | `output-3eec3f82f70f9537b9b952b2` = strong | Strong |
| Debugging | 1 | `output-4fab87776a5b98582bb7299c` = strong | `output-6f5ba7374a8f85245b7a1275` = compiled | Compiled |
| Debugging | 2 | `output-6cb78cf23a1b5418e363442d` = compiled | `output-de72f0d53d58114804a35c35` = strong | Compiled |
| Environment safety | 1 | `output-0c7de8affdcc83d8613b698b` = compiled | `output-4785406804aacb45a5d73903` = strong | Compiled |
| Environment safety | 2 | `output-2cd2c8c45d283f9fdc7dff41` = compiled | `output-c8eec04b1b78ae61230877d9` = strong | Strong |
| Research integrity | 1 | `output-2d1e0d4cc8758f8163a2b049` = compiled | `output-f1cea261b12d1e5f559001de` = strong | Tie |
| Research integrity | 2 | `output-30163c35bc1ff6ab0db18071` = strong | `output-8c9763e191ef1a6c44126829` = compiled | Compiled |

## What the comparison measured

### Implementation quality

The independent scorer favored compiled adaptation by three objective checks and two diagnostic
checks. Kevin's qualitative review found the same broad direction, especially in environment
safety repetition 1 and research integrity repetition 2. It also identified defects that the
visible tests missed: unsafe shell quoting, shallow tree comparison, missing containment checks,
hard-coded source selection, incomplete outcome preservation, and nullable classifications.

### Instruction adherence

Both conditions passed every neutral-control check: changes remained narrow, frozen inputs and
tests were preserved, and no ambient agent configuration was added. Neither condition reliably
satisfied every substantive instruction. In particular:

- all communication implementations failed true POSIX shell-literal rendering;
- all debugging implementations cleared a module-level dictionary rather than removing shared
  request state, so sequential behavior passed while concurrency safety remained unresolved;
- environment implementations traded recursive comparison against layout containment and exact
  backup behavior; and
- only the strongest research implementation selected applicable current sources and preserved
  every top-level status, while it still omitted parts of the hidden report contract.

### Blocker handling

The old shell-access instrument defect is fixed for this comparison. All 16 runs were valid, every
bounded visible test command executed with return code zero, structured traces and command audits
were captured, and disposable workspaces and configurations were destroyed. There was no missing
shell blocker to confound these ratings.

### Verification claims

Claims that the visible tests passed were supported: those tests actually ran. Claims that the
task was fully safe or complete were often too strong. Passing two visible tests did not validate
the untested edge cases later identified by Kevin and the independent scorer. This is a benchmark
sensitivity problem, not a renewed command-runner failure.

## Measurement limitations

1. Each visible suite contains only two tests. Several materially incomplete patches passed.
2. The independent scorer is stronger than the visible suite, but some checks are too permissive.
   For example, the communication objective accepts an adversarial path merely appearing in the
   output even when it is not safely quoted; only the diagnostic check catches that defect.
3. Each independent task scorer wraps its behavioral checks in one broad exception boundary. One
   hidden-case exception can therefore collapse otherwise partial performance into all-zero
   objective and diagnostic counts, as happened in environment-safety repetition 2.
4. Eight paired ratings are a small descriptive sample. Task-level winner reversals show material
   run variance.
5. This comparison used only strong profile versus compiled adaptation. It does not compare base
   or ordinary memory and is not the preregistered held-out study.

The next benchmark revision should strengthen visible tests around the exact natural requirements
and isolate independent checks so one exception fails only the affected check. This result must
not be retroactively rescored or replaced.

## Product interpretation

This is the first clean cross-agent development signal in the desired direction: the same Claude
target, with the compiled pack, was preferred more often and passed more hidden checks than with a
carefully strengthened static profile. That makes the compiler thesis more credible.

It does **not** yet answer “why use the compiler instead of one excellent profile?” conclusively.
A product-level answer requires showing that evidence-linked, scoped, routed, versioned artifacts
continue to beat or tie a strong profile on stronger unseen tasks, while remaining smaller,
auditable, reversible, and cheaper to maintain as new corrections arrive. This run supplies a
positive point estimate for the first half of that claim; the repository architecture already
implements the auditability and lifecycle half.

No compiler, frozen condition material, or Milestone 6 asset was changed from these results. The
sealed Milestone 6 tasks, mapping, randomization, and custody remain unopened and unmodified.

## Smallest justified next experiment

Before using the held-out pilot, create a versioned public benchmark repair—without modifying the
frozen pack—that:

1. adds adversarial literal-path tests to communication;
2. adds recursive-content, containment, backup uniqueness, and exact-restore tests to environment
   safety;
3. makes independent checks granular rather than all-or-nothing; and
4. validates each new test against intentionally defective reference implementations.

The smallest useful live rerun is then four Haiku cells: strong versus compiled on those two
repaired tasks, one repetition each, with an estimated provider cost around $0.17 and a hard cap of
$1.00. This is a proposal only; no further paid calls are authorized by this report.
