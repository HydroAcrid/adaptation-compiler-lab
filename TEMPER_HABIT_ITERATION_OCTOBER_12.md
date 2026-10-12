# Habit learner iteration — October 12

The owner requested fixes for confusing task requirements with personal habits and missing
changing preferences, followed by rapid local reruns. Keep the fixed 95% precision / 80% recall
thresholds, three-task/two-date trial eligibility and 14-day trial defaults. No GitHub CI is used.

## Evidence classification and scope

The semantic wire response now classifies each cited episode as a discretionary personal choice,
task requirement, quoted/learned instruction or uncertain evidence. Exact quotations must be
substrings of supplied human episodes. Deterministic code rejects invented/duplicate references,
filters nonhuman/nonterminal/ephemeral sources, and compiles only reviewed style defaults from
personal choices. It can record one task as weak provisional support; it cannot manufacture trial
eligibility from repetition within that task.

Every supplied known habit must receive one fresh assessment. A relevant personal correction can
pause it without a replacement positive proposal or surviving old raw evidence. Temporary task
exceptions take precedence for that answer without changing the underlying habit. Missing or
inconsistent assessments fail closed.

The next contract distinguishes length, order, explanatory depth, prose/list format and suggestion
count. Incidental language must not create companion habits. Required style includes content and
detail constraints as well as visual formatting; context can exclude evidence but cannot establish
a personal preference.

Episodes now optionally retain observed task-class context. The sensor and host both reject
support/counterevidence crossing that class. Legacy episodes without the hint remain readable and
keep their replay identity. The frozen evaluator previously discarded its supplied task-class
field; it now passes the same typed context accepted by the runtime. Fictional attribution and
task hints do not establish a production Codex origin signal or automatic task classification.

## Preserved results and separate runs

The complete v3 failure remains unchanged: 55 TP / 17 FP / 25 FN, 76.39% precision, 68.75% recall,
14/20 contradiction pauses. Previously seen cases are development regression data from now on.

The first classified-evidence regression, v4 run `b3787c58727b4bbe8f3d16f4`, stopped at 76/140
phases after a strict validation failure. Its partial report covered 73 cases: 32 TP / 11 FP /
1 FN, 74.42% precision and 96.97% recall. These are incomplete scores, not a completed evaluation.
All 30 stable targets were found, alongside seven extra hypotheses. Three of twenty requirement
controls produced false hypotheses, down from sixteen in v3. Early changing cases also exposed
overlapping styles and one processing failure. Do not silently retry or relabel this bound run.

V5 binds the narrower contract, typed scope, unchanged regression labels, complete host/transport
source fingerprints and exact configured saved-ChatGPT model/runtime. Fresh prospective materials
were authored and pushed before any v5 execution: 120 fictional cases in the same preregistered
cohort counts, independently worded from the regression set. Dataset digest:
`sha256:c40711bc864a1122455da4e382e3851a5ba884cd53f9d73f0078d3d2e1367c68`.

The foreground driver uses separate signed/encrypted stores for regression and `--prospective`.
Neither can install serving calibration. Capacity must remain known and at least 20%; runs are
sequential, with no paid fallback or model substitution. The personal background budget remains
five-minute polling and twelve analyses per rolling day. Raw outputs remain encrypted outside Git
and the shared vault for 30 days.

Local checks: 112 learner tests passed with one Mac-only skip. The surrounding runtime checks
passed 381 tests with three platform skips. Changed-source/script typing and lint/format passed.
Broad Windows mypy additionally reports pre-existing POSIX-only symbols in unrelated runners;
no full-project Windows typing pass is claimed. Native serving/loading, production human origin,
fresh Mac checks, everyday usefulness, signing and independent packages remain separate gates.

## Public source

Temper and Kairn are public, as authorized. See [the scoped audit](TEMPER_PUBLIC_SOURCE_AUDIT.md).
GitHub automatically produced a dependency-graph metadata run after visibility changed; no CI
check or release was requested. Repository Actions permissions are now disabled on both repos
and were read back as `enabled: false`, matching the owner's no-CI instruction.

Windows implementation stays on the draft autonomy branch. No Mac source/runtime was synchronized,
no historical research was promoted, and no personal grant or native profile was installed.
