# Milestone 6A.2G — Repository-Informed Synthetic Stimulation

Status: implemented and executed as a synthetic detector-development instrument. The conservative
calibrated-promotion gate did not pass; production dogfood remains in review mode.

## Why this milestone exists

Genuine longitudinal dogfood remains the authoritative product test, but waiting for enough new
interactions makes detector development unnecessarily slow. This milestone adds a second lane that
can generate broad, repeatable pressure without pretending that model-written messages are Kevin's
real feedback.

The two lanes are intentionally different:

1. Real dogfood observes only newly completed, registered Codex work and can create reviewable
   evidence under the standing policy.
2. Synthetic stimulation uses fictional messages for instrument calibration only. It cannot
   create evidence, learning, releases, packs, or activations.

## Read-only source abstraction

Five repositories were inspected by five fresh `gpt-5.6-luna`/low Codex CLI sessions. Every
session used saved ChatGPT authentication, an auth-only temporary home, `--ephemeral`, an enforced
read-only sandbox, ignored ambient user configuration and repository rules, and prohibited edits,
builds, tests, installs, execution, network tools, Git internals, credentials, and reads outside
the selected repository.

Each session could return only closed generic categories. The resulting anonymous archetypes were
kept outside Git with mode 0600. The repository contains only their content digests and context IDs.
A scan found no source repository names, source paths, private paths, URLs, credentials, API-key
markers, or raw code/content in the benchmark directory.

Repository content and the archetype model output remain untrusted context. Neither is user
authority or supporting evidence for a promoted artifact.

## Frozen design

The label-first plan froze 100 cases before detector execution:

- 50 calibration and 50 untouched holdout cases;
- 25 positive and 25 negative cases in each split;
- five anonymous contexts with ten cases per context per split;
- synthetic turn positions 1, 3, 5, 10, and 15, each represented 20 times;
- durable preferences, procedures, rules, corrections, memories, examples, and exact revocations;
- task requests, quoted authority, undecided or hypothetical preferences, immediate-only
  directions, inferred-topic traps, retired preferences, and prompt-injection-shaped quotations;
- ten controlled wording styles, including bad grammar, fragments, acronyms, slang, typos, and
  mixed intent.

Turn position is metadata rather than accumulated transcript content. Because source pickup treats
every newly observed user message as a separate exact evidence unit, this tests position-invariant
detection, not memory over a growing context window.

## Instrument repairs discovered during execution

The process failed closed and was repaired several times before scoring:

1. The real polling schema allowed nullable behavior/route fields for non-revocation signals even
   though the domain model prohibited them. The model-facing schema now has distinct learning and
   revocation branches, interpreter/prompt version 1.3/v4, and tamper/shape coverage. A real poll
   then processed four new interactions successfully without promotion.
2. The generic Pydantic generation schema did not mark defaulted fields as required under the
   structured-output API. The benchmark now normalizes every model-facing object to an
   all-properties-required, additional-properties-forbidden contract.
3. A model copied one character of a generation digest incorrectly. Models no longer supply
   authoritative bindings: deterministic local attestation replaces every echoed plan,
   generation, audit, and remediation digest.
4. Audit output paired `pass` with a non-clean reason. The model-facing audit schema now encodes
   the cross-field invariant as strict alternative object shapes.
5. Re-auditing all 100 cases after two wording changes produced unrelated verdict variance. The
   final procedure audits only changed cases and composes them with prior verdicts for unchanged
   bytes. Failed full audits remain preserved rather than rerun until favorable.
6. The evaluator previously could not score exact revocations because they correctly have no
   artifact route. Revocation-only expectations and route scoring now support that shape.
7. `runtime detector-evaluate` can now write its raw-free envelope through an explicit `--output`
   option, avoiding shell redirection and preserving exact report bytes.
8. Evaluation v1.0 counted scope mismatches in metrics but omitted scope-only cases from the failure
   index. Report v1.1 derives the index from detection, route, and scope correctness; original v1.0
   envelopes remain preserved and no model was rerun.

## Exact result

Authentication was reconfirmed as `Logged in using ChatGPT`. No `CODEX_API_KEY` or
`OPENAI_API_KEY` was set. The interpreter used the exact pinned Codex 0.146.0 Linux binary,
`gpt-5.6-luna`, medium reasoning, an empty temporary workspace, and one schema-bound 50-case batch
per split. Provider-billed cost was USD $0.

| Split | TP | FP | TN | FN | Precision | Recall | Specificity | Route | Scope |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Calibration | 24 | 0 | 25 | 1 | 1.00 | 0.96 | 1.00 | 0.833 | 1.00 |
| Holdout | 25 | 0 | 25 | 0 | 1.00 | 1.00 | 1.00 | 0.680 | 0.92 |
| Combined | 49 | 0 | 50 | 1 | 1.00 | 0.98 | 1.00 | 0.755 | 0.959 |

Detection was perfect for every negative family and all but one positive. Clean and mixed-intent
styles were perfect on every reported dimension. The only detection miss was a generated memory
sentence written in the third person (“Synthetic user …”), which is properly suspicious under the
real trust model. Acronym cases had the weakest route score; fragments contained the one detection
miss. Context and turn slices do not show a monotonic late-turn decline, but this instrument cannot
measure accumulated conversational learning.

The gate remains closed. Route errors cluster around preference versus procedure versus hard rule,
and two scope failures come from revocation/project phrasing. Several answer-key labels are too
narrow for the generated surface text. Preserving those failures is more honest than loosening the
metric after seeing holdout.

Exact bindings:

- protocol: `sha256:02b4d6c8c94f730b95d77b00c682bb8708d2a03c5b9251bd9dbc5861d2eea215`
- plan: `sha256:0dfae34dacf3a0a0e174e7522bcd2c474d6bd2099bdf7e42a0e2da299bfc9ec0`
- accepted generation: `sha256:30d88816ffb0b063c3bb90bf6628d2c0cde92169f208b606aa313a1b436d4ccb`
- final composed audit: `sha256:9ffc4d476554036de455caf729a5580c71d00e30329a0c3c29c42bcb103150d9`
- corpus: `sha256:ec3aabc847b4c0a3fb97e1fff0844deb3392ff13d0c28bef2d596462e0279c0a`
- corrected calibration report: `sha256:e7e7e44237e524cf5fdca13160d2d5d5bfa22696e819e1780e09ebc28dca1f76`
- corrected holdout report: `sha256:c550bf2ca19627606c1c10231855aaa66dd8bbd3db7d468f527ba2af9de2b04d`

## Product interpretation and next step

This materially improves confidence in automatic *selection*: the sensor did not turn ordinary
requests, quotations, third-party statements, hypotheticals, or prompt injection into durable
learning across 50 adversarial negatives. It also found nearly every intended positive despite
messy language.

It does not yet justify unattended artifact routing. The smallest principled next development step
is a fresh route-specific corpus whose surface form explicitly distinguishes:

- preference: a first-person desired style, priority, or choice;
- procedure: a repeatable trigger and ordered workflow;
- prompt rule: a hard invariant or prohibition;
- memory: a first-person non-normative fact; and
- example: an explicitly endorsed prior pattern.

That corpus should use blind classification audits rather than showing auditors the intended label,
freeze a new holdout before interpreter execution, and continue to keep real dogfood in review
mode. This is benchmark repair, not a reason to rewrite the completed v3 reports or promote
synthetic learning.

## Unchanged boundaries

No source repository was edited. No existing Codex thread was resumed or modified. No watcher was
installed. No synthetic item entered the production dogfood ledger. The deferred Milestone 6
Claude registration, held-out bundle, mapping, order, authorization gate, and custody records were
not accessed or modified. No provider-billed model call, weight training, Kairn integration, tool
creation, web UI, or public release occurred.

## Verification

`uv sync --locked --dev`, Ruff format/check, strict mypy, the complete pytest suite, schema
snapshots, package build, Git diff validation, and a changed-scope credential/private-path scan all
pass. The final suite formats 632 files, type-checks 303 source files, and passes 814 tests with one
Windows-only check skipped under WSL. Both wheel and source distribution build successfully.
