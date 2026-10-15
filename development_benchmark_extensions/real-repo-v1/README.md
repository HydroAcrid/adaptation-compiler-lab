# Real repository extension comparison

This development experiment asks whether selecting and composing guidance adds
value over direct use of relevant upstream skills during actual software repair.
It follows the earlier fictional screen, whose complete tie remains unchanged.

## Tasks and comparisons

Two public historical repairs are replayed from their actual parent commits:

- Temper: repair stale learning-service project registration and native instruction
  discovery for an exact custom Codex home, while preserving grant scope and legacy
  adapter callers. The authoritative suite has 55 tests; the starting tree with
  the withheld regression checks applied fails
  three and the reference repair passes all 55.
- Kairn: isolate embeddings and reusable corpus caches by the exact Node/WASM
  inference package identity, including SQLite migration and typed callers. The
  authoritative suite has 98 tests plus TypeScript checking; the starting tree
  with the withheld regression checks applied
  fails five tests and typechecking, while the reference repair passes both.

Targets receive the complete starting repository, a natural task specification,
local dependencies and normal search/edit/test tools. They do not receive future
Git history, reference repairs, hidden test revisions, or other trials' outputs.
The coordinator inspected the known fixes to author the tasks. These are
retrospective repairs, not an unseen holdout or release calibration.

Each task runs twice under each condition, with counterbalanced order and a fresh
native Codex context: 12 solver turns plus two task-selector turns. The same
configured, catalog-verified model and effort are used throughout; saved ChatGPT
authentication is used without an API-key provider or model fallback. Subscription
capacity must be known and at least 20% before each model call.

| Condition | Guidance |
| --- | --- |
| Baseline | Current task, repository policy and the same tools |
| Direct skills | Full pinned Ponytail and pstack TDD, explicitly invoked |
| Temper-style selection | A separate model inspects the repo read-only and selects exact attributed paragraphs from those same sources |

The direct comparator receives relevant, manually preselected skills, rather than
a large irrelevant catalog. Both upstream skills are self-contained for this
single-agent workflow. Native skill input items and a read-only `/skills` mirror
let the agent read the exact files through the tool interface. The selector can
copy at most 24 paragraphs and 8,000 UTF-8 bytes; it cannot generate implementation
hints. A native probe verifies actual skill-content loading, shell execution,
file editing and assertion execution before target comparisons start.

The model uses an actual shell tool loop. Shell commands run in a WSL Bubblewrap
namespace containing only the disposable repository, read-only preinstalled
Python/Node dependencies and optional skill files. Commands have no network or
credentials; temporary Vite caches are private writable mounts. Native plugins,
other tools, memory and delegation are disabled. The product's analysis profile
is unchanged: this benchmark alone enables the native code-mode host needed for
dynamic tools. No GitHub CI runs or package installation are requested.

## Success rule and measurement

A completion advantage over direct skills must repeat on the same task, without
any completion regression against baseline or direct use. A tie does not establish
an added quality benefit. A valid unsuccessful repair remains a failure, including
an import/compilation failure; infrastructure failures invalidate conclusions.
Authoritative test files are restored independently of candidate edits. Missing
checks cannot pass. Out-of-scope changes and deletion of existing files fail the
task. Reference controls must reject the original defects and accept the repair.

Report per trial:

- Authoritative tests, TypeScript results where applicable, and task completion.
- Actual tools, nonzero command exits, changed paths and skill delivery.
- Whether proposed test changes fail on the original implementation and pass on
  the candidate. This is a counterfactual check, not proof that the agent performed
  TDD or that every failed check failed for the intended reason.
- Reported model usage, including both selectors; input/cache/output/reasoning
  fields stay separate so reasoning is not double-counted.
- Workspace and Git setup, native auth/catalog/context setup, skill-file
  publication, agent/tool execution, independent grading, candidate-test
  counterfactuals, encrypted persistence and safe cleanup. Component timers that
  are nested are not added twice; whole-trial wall time is authoritative.

Selectors are called once per task and reused for two repetitions. Their full
cost is charged to the selected lane. Three preliminary native probe attempts
(including two unsuccessful setup attempts) are retained as common instrument
setup costs, outside the 14 comparison calls. Failed pre-execution controls are
also preserved. Five local file-publication samples measure only mechanical
setup, not human installation effort. Shared repository/source acquisition is
reported separately, including warm source reuse. Dependencies were already
installed; fresh-machine onboarding and model downloads are not measured.
Five additional fresh local profiles include actual pinned HTTPS source/license
retrieval, digest verification and publication of both full skills. Remote caches
are uncontrolled; this measures file-source setup rather than human discovery or
installation of Temper itself.

The coordinator's research, prototype development and active maintenance effort
and token counts are not fully instrumented. Unavailable accounting must be
reported as unavailable, never zero. A request-to-execution preparation wall
interval can be reported separately; it includes research and harness repairs,
not just product setup. This prevents a claim of proven net savings from this
experiment alone. Two repetitions cannot establish a general speed or efficiency
result; report the median/range and exact usage descriptively.

## Reproduction

The protocol is frozen only after non-model controls, harness checks and the
native skill/tool probe pass, then committed before the first task selector.
The source and exact reference-file hashes are in `cases.json`; full upstream
text, source commits and MIT licenses are in `sources.json`. Historical sources
and grading/reference files are materialized outside Git by the preparation
script. Raw model responses, patches and native events stay encrypted outside Git
and Obsidian. A new execution refuses to overwrite an existing output directory.

From the repository's Windows environment:

```text
.venv\Scripts\python.exe scripts/prepare_repo_extension_screen.py --fixtures <new-private-fixtures>
.venv\Scripts\python.exe scripts/run_repo_extension_screen.py --fixtures <fixtures> --controls --output <new-private-controls>
.venv\Scripts\python.exe scripts/run_repo_extension_screen.py --fixtures <fixtures> --probe --config <personal-config> --output <new-private-probe>
```

Record verified controls/probes in `instrument-admission.json`, then freeze and
commit the exact candidate. Afterward:

```text
.venv\Scripts\python.exe scripts/run_repo_extension_screen.py --fixtures <fixtures> --freeze
.venv\Scripts\python.exe scripts/run_repo_extension_screen.py --fixtures <fixtures> --config <personal-config> --output <new-private-run>
```

Platform runtime/dependency paths in the runner are specific to this local
development instrument. Porting the instrument requires new admission and a new
freeze. This does not validate a shipping capability router, the entire pstack
suite, Pi's runtime, cross-agent orchestration, native GUI behavior, market demand
or the separate habit-learning release gates. Personal observation permissions
and the installed Temper application remain unchanged.
