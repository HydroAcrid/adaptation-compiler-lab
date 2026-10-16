# Real repository comparison results

Recorded 2026-10-15 UTC. Tested source: `6eecc34e63565a0a20cc13ed11d11e9ccbfa5e31`.

**The selection prototype did not demonstrate an added repair-quality benefit
over using the extensions directly.** The baseline also passed the diagnostic
repair checks. With selection charged in full, the selected condition took more
total time and used more uncached input than direct use in this small sample.
There is no basis here for a general speed, cost, or reliability claim.

This supports keeping guidance composition experimental. It does not justify
expanding Temper into a framework catalog on the strength of this mechanism.
Actual capability provisioning, compatibility, conflicts and recovery remain
different hypotheses that this experiment has not tested.

## Actual SWE work

Twelve repairs used full historical repository checkouts, real search/edit/test
tools and fresh native Codex contexts: two tasks, three conditions, two repetitions.
All used catalog-verified `gpt-6.1-sol` with `medium` effort and saved ChatGPT
authentication. There was no API-key fallback, model substitution or GitHub CI.

- **Temper:** refresh live project registration without expanding signed grants;
  discover native instructions from an exact custom Codex home, preserving
  override/config/legacy behavior and excluding Temper-managed authority. Each
  candidate changed six files. The independently restored acceptance suite has
  55 checks; the original fails three and the known repair passes all 55.
- **Kairn:** carry exact Node/WASM package identity through embeddings, SQLite
  migration, indexing, retrieval and reusable corpus caches. Each candidate
  changed 12–14 files. The acceptance suite has 98 checks plus TypeScript; the
  original fails five runtime checks and typechecking, while the known repair
  passes both.

The baseline received task/repository policy and the same tools. Direct use
received the complete, relevant, manually preselected
[Ponytail skill](https://github.com/DietrichGebert/ponytail/blob/84740e3d344b69b4a133201fa519eb37a62a2b2a/skills/ponytail/SKILL.md)
and [pstack TDD skill](https://github.com/backnotprop/pstack/blob/1f0f9c3bac03c4297f6fc8f7644fa412eda57085/skills/tdd/SKILL.md)
through explicit native skill inputs and a read-only skill-file mount. Selection
used a separate read-only model turn per task to choose exact attributed source
paragraphs, reused for both repetitions. Both selectors chose the same seven
paragraphs. They supplied no generated implementation hints.

Actual tool output confirms complete guide loading in all four direct runs and
complete selected-material loading in all four selected runs. All twelve native
repair turns completed, with no out-of-scope file changes or existing-file
deletions. Every candidate's changed tests failed against the original and passed
against its repair in the corrected Git-aware sensitivity audit. This establishes
test sensitivity, not proof of TDD or that every failure had the intended cause.

## Quality and the grading limitation

| Check | Baseline | Direct skills | Selected guidance |
| --- | ---: | ---: | ---: |
| Temper frozen acceptance, 55/55 | 2/2 | 2/2 | 2/2 |
| Kairn frozen runtime acceptance, 98/98 | 1/2 | 2/2 | 2/2 |
| Kairn frozen TypeScript gate | 0/2 | 0/2 | 0/2 |
| Kairn actual candidate TypeScript | 2/2 | 2/2 | 2/2 |
| Kairn diagnostic API-neutral acceptance, 98/98 | 2/2 | 2/2 | 2/2 |
| Combined diagnostic contract/build checks | 4/4 | 4/4 | 4/4 |

The original strict completion score is **2/4 for every condition**. The frozen
verdict is `no_repeated_completion_advantage`. Its files and scores are preserved;
no frozen promotion gate is declared passed.

The Kairn task explicitly permits updating typed callers and fixtures when adding
runtime identity. The hidden historical fixtures instead assume the known fix's
internal API: they omit `runtimeBackend` at cache-key boundaries. Every frozen
TypeScript failure is in those historical test files; each exact candidate with
its own updated callers/fixtures independently compiles. One baseline candidate
also requires identity on its scoring helper, so the old context-free scoring
fixture produces the single runtime failure.

After observing the first results, a uniform diagnostic replay supplied complete
identity at four internal helper boundaries. It changed no assertion, query,
expected result or candidate production code. Its controls still reject the
original source, 93/98, and accept the known repair, 98/98. All six Kairn candidates
pass that replay. Candidate test helpers were unchanged. These are post-result
diagnostics, not a new prospective release evaluation.

The original secondary test-sensitivity check also omitted `.git` from its repaired
tree. Kairn's corpus tests need Git provenance. The separate audit restores valid
Git metadata on both sides and retains the original secondary results. Full
details are in [SUPPLEMENTAL_ANALYSIS.md](SUPPLEMENTAL_ANALYSIS.md).

## Execution cost, including selection

Whole-work totals include repository/Git setup, fresh native auth/catalog/context,
skill publication, model and tool execution, fixed grading, candidate-test
counterfactual checks, encrypted persistence and cleanup. Selected totals include
both selector turns, without charging them to another condition.

| Condition, four repairs each | Native turns | Shell calls, including selector | Whole-work minutes | Reported cumulative tokens |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 4 | 103 | 26.79 | 5,126,382 |
| Direct skills | 4 | 105 | 25.39 | 5,309,078 |
| Selected guidance | 6 | 102 | 27.38 | 4,539,120 |

Reported tokens count repeated model/tool context, not unique text or provider
requests. Cache usage changes their interpretation:

| Condition | Uncached input | Cached input | Output | Reasoning, already included in output |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 298,277 | 4,778,240 | 49,865 | 7,343 |
| Direct skills | 330,749 | 4,936,576 | 41,753 | 5,553 |
| Selected guidance | 368,230 | 4,121,856 | 49,034 | 8,130 |

Selection itself used **80,817 reported tokens, six shell calls and 65.406 seconds**
over two native turns. It was amortized across the two repetitions of each task.
The lower selected headline token count does not establish lower cost: uncached
input and output are both higher than direct use. No monetary cost is inferred
from subscription usage, and provider request counts are unavailable.

Per-repair whole-work seconds, median (minimum–maximum), excluding selector time
from this table only:

| Task | Baseline | Direct skills | Selected guidance |
| --- | ---: | ---: | ---: |
| Temper | 314.19 (312.36–316.02) | 291.27 (272.66–309.89) | 275.22 (274.55–275.89) |
| Kairn | 489.51 (483.84–495.17) | 470.32 (427.70–512.94) | 513.48 (513.39–513.56) |

The primary comparison took **79.57 minutes**. Two repetitions, mixed task costs,
uncontrolled remote caches, local filesystem effects and concurrent diagnostic
audits do not support a general performance conclusion. Nonzero shell exits also
include deliberate failing regression tests; they are not counts of failed tasks.

## Setup, failures and maintenance overhead

- Initial automated public-repository/source acquisition took 4.50 seconds;
  Ponytail reused a pinned local snapshot. This was not a fully cold install.
- Five fresh local file-source profiles fetched both guides and licenses over
  HTTPS, verified their digests and wrote four files each. Times were 0.438,
  0.156, 0.172, 0.172 and 0.187 seconds. Remote caches were uncontrolled. This
  measures file-source setup, not human discovery, native registration, framework
  installation or Temper onboarding.
- Mechanical local publication/removal medians were below timer resolution for
  both conditions, with observed maxima 0.015/0.016 seconds. This does not mean
  setup is free; selected text in that mechanical probe was a placeholder.
- Python/Node dependencies were already installed. Fresh-machine dependency
  installation, model downloads, signing, GUI setup and Mac validation were not
  measured.
- Request-to-v3-admission preparation took **60.33 wall minutes**, including
  research, instrument development, controls, repairs, probes and waits. Active
  coordinator work and token usage are unavailable, not zero. This is experiment
  development, not a product onboarding time.
- Earlier attempts included missing runtime aliases, Windows long paths, UTF-8
  binding, Vite cache/Git setup, a missing read-only Node mountpoint, inaccessible
  skill content and malformed tool-argument handling. Three native probes and two
  aborted instrument attempts are preserved. They add **920,869 known reported
  tokens**, plus one partial solver turn whose usage was not retained. Their task
  scores are excluded from the final comparison.
- Current comparison usage is **14,974,580 reported tokens** across fourteen native
  turns. The entire study attempted 23 native turns with **15,895,449 known tokens**,
  plus the unavailable partial turn and coordinator usage. These are agent turns,
  not individual provider requests.
- Supplemental per-candidate audits add **676.13 seconds of recorded work**, run
  partly concurrently. Control runs and audit development add further unmeasured
  overhead. Do not simply add concurrent/nested timers to whole-run elapsed time.

These unknowns prevent a claim of proven net time savings or lower ownership
cost. They are explicitly retained rather than assigned zero.

## Interpretation and limits

This is substantially more demanding than a fictional prompt screen: complete
repositories, multi-file repairs, a real database migration, fixed acceptance
tests, TypeScript, and failing-before/passing-after candidate checks. Nevertheless,
the baseline also solved the diagnostic checks and wrote sensitive tests. Added
guardrail prose did not show a distinct quality benefit on these cases.

This tests a **Temper-style guidance selector**, not a released Temper router,
the full pstack suite, Pi's runtime, automatic tool installation, multi-agent
coordination or the market niche as a whole. The coordinator knew the historical
fixes; solvers received neither future history nor reference patches. Two tasks
from familiar public repos are not an independent unseen holdout.

If the infrastructure direction proceeds, the next discriminating test should
exercise actual capabilities: configuring tools in a fresh repository, resolving
conflicting instructions, selecting different workflows, and recovering from
failed setup or interrupted work. It should compare against direct native use
with measured operator intervention. Repeating generic guidance compression
until it produces a win would not establish that value.

The installed Windows app, observation grant, native instruction profile and
separate habit-learning evaluation were not changed. Raw responses, patches and
native events remain encrypted outside Git and the shared vault. No GitHub CI
was used.

## Evidence

[results.json](results.json) contains sanitized trial, selector, usage, timing,
control and diagnostic receipts. All fourteen durable journal usage records match
their final receipts. All bound v3 source/input hashes remained unchanged.

- Protocol: [protocol-validated-v3.json](protocol-validated-v3.json), SHA-256
  `acbd3cbb65506a5291e116af81cb51d29b75c3d52afadc238e7ddc8285ccfde3`.
- Setup/control record: [instrument-admission-v3.json](instrument-admission-v3.json).
- Exact source licenses, commits and digests: [sources.json](sources.json).
- Task/base/reference bindings: [cases.json](cases.json).
- Execution and reproduction limits: [README.md](README.md).
