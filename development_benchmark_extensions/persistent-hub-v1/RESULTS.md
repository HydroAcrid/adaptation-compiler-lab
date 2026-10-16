# Persistent hub: separate Kairn work sessions

Temper was slower in this single observed journey. Its persistent controller
recovered the updated profile and preserved the concurrent note, and both strong
baselines did too. **Actual owner-effort savings remain unmeasured.** This is a
working prototype and a development study, not evidence for a superiority claim.

The owner chose Kairn's next substantial update and its website. The implemented
work is one release-readiness prerequisite: a task-cluster pilot diagnostic, a
safe CLI with input provenance/overwrite refusal, and a bounded experiment
proposal; plus truthful website source/beta/research copy and regression guards.
It is not the whole next Kairn release, a new efficacy campaign, or a promotion.

## Candidate and method

Primary candidate: `9e4e6050852958d13f020745cfb91e3dfdeabf2b`. Protocol SHA-256:
`8c400d6a1a3d2d5a74db41a01b92242d1f222b72aaf2adceb22611536f9655d2`. The frozen inputs and original grades are
unchanged. Current controller code `d745841e74c7a5a83889f15111c480baeadbdb71` adds
per-source cache-space reservation; that later fix was qualified separately.
Replay the original study from its exact candidate, not by updating its hashes.

Nine fresh native processes/threads, three per condition. Files, manager HOME/index
and local handoffs persist; previous transcripts do not. Baselines may keep helpers
and automate their own maintenance. Order: native/SkillKit/Temper, then reversed,
then forward. Each turn has 600 seconds and 60 tool requests. One three-session
journey per arm is descriptive; different tasks are not replication.

Native Windows Codex 0.162.0-alpha.17.2, configured gpt-6.1-sol/medium, saved
ChatGPT authentication; capacity/model admission before each turn, no paid API
fallback or substitution. Managers run in credential-free WSL namespaces: Skills
1.7.2, optional-free SkillKit 1.24.0, Node 24.18.0. The exact binaries, source trees,
code and private snapshots are bound by the protocol. Workers have no network.

Kairn base `99e2416bc756d6b581c89ee01f0273c745901aff`; site base
`096eb859d2d3f364057330176244c537226448a4`. Original repositories are untouched.
Each receives the same approved 74-skill registry and two-skill budget. All selected
only `verification-before-completion`. No unrelated automatic activation was
observed in these cases. This is not open-world discovery or a general scope test.

## Observed work and timing

| Condition | Session seconds | Repo prep seconds | Tool requests | Nonzero results | Functional sessions | Original full grade |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| native_managers | 703.766 | 7.500 | 65 | 11 | 3/3 | 1/3 |
| skillkit | 708.938 | 6.688 | 67 | 15 | 3/3 | 1/3 |
| persistent_hub | 780.671 | 6.812 | 66 | 17 | 3/3 | 1/3 |

Session time includes native admission, discovery/selection/indexing, all visible
model/tool work, retries, handoffs, faults, independent grading and encrypted
evidence persistence. Repository extraction/copy/Git setup is separate. Total
primary wall span was 2214.340 seconds (about 36m54s).
Tool/check timings are nested within sessions and must not be added again. No
limiter or timing variance was established; these values do not prove a causal
performance effect. Background observer/timer activity is not isolated profiling.

Every native request reached the real isolated tool implementation: 198 requests,
198 executions, no silently dropped requests. Nonzero results include intentional
red tests and recoverable environment/argument errors, not just product bugs.

All nine turns completed. Independent behavior checks passed for the diagnostic,
website source guard/evidence gates, and return-session CLI/profile recovery.
All three restored the updated complete skill and preserved the external note.
Published beta and historical source/evidence/release files remained unchanged.
Actual source bytes, approved catalog material, vault snapshots and pilot input
were independently checked after execution; only the controlled source update
was present. The historical 45-pair/15-task input is not new efficacy evidence.

## Grading defect and separate specification review

Original full grades are **3/9**, one first-session pass per condition. The frozen
path allowlist wrongly rejected README edits, differently named new regression
tests/helpers, and an added npm test command. Those are allowed by the actual task;
dependencies and existing commands were unchanged. Cumulative scope checks carried
the same website flags into all three return sessions. Functional checks are 9/9;
do not replace the original full-grade statistic with that number.

[Scope adjudication](scope-adjudication.json) preserves the first supplemental
rules after the first website result, and a second explicit addition after the
native implementation extracted a matcher helper. This is transparent post-hoc
specification review, not a new preregistered pass rate. Applied uniformly, all
three changed-path sets fit the request, existing manifests/commands remain
intact, and their added regression suites execute successfully. The actual
diffs were reviewed. This checker defect prevents a clean preregistered claim of
complete quality and must be fixed in a separately versioned future study.

## Tokens and missing accounting

| Condition | Input | Cached input | Uncached input | Output | Reasoning (within output) |
| --- | ---: | ---: | ---: | ---: | ---: |
| native_managers | 2098090 | 1914240 | 183850 | 27535 | 3270 |
| skillkit | 2015165 | 1806592 | 208573 | 25785 | 2675 |
| persistent_hub | 1848772 | 1659264 | 189508 | 29916 | 5466 |

Primary total: 6,045,263 observed tokens. Two additional
native loading probes used 14,498 tokens (14,451 input, no cached input, 47 output),
for 6,059,761 across 11 known experiment turns. No hidden
selector model was used: the connected operator makes applicability decisions
within these turns. Native SkillKit recommendations alone cannot publish a rule.

Every final usage value was reconciled with its encrypted event journal and raw
tool/model record. Cached input is not free billing, and reasoning is already
within output. Coordinator/helper authoring tokens, Mac coordination tokens,
opaque provider retries/billing and coordinator active time are unavailable.
They are **unknown, not zero**. These counts cannot support an all-in token/cost
saving. Fewer cached tokens alone are not an owner-effort benefit.

## Setup, storage and additional overhead

New manager preparation from the exact locks: Skills 1.000s / 4,526,335 bytes;
optional-free SkillKit 2.485s / 41,401,662 bytes. Temper requires both managers.
The stronger optional-free baseline avoids comparing against an unnecessarily
large default install. Cache/download provenance and receipt sizes remain private.
Existing Node/Python/WSL/Codex/auth setup and project dependencies were reused
read-only: Kairn 846,238,685 bytes; site 531,532,796 bytes. Their original install
and research cost is unknown, not a free new-user prerequisite.

Measured per-arm profile/controller state after the journey (logical file bytes;
not total application, source-cache or runtime footprint):

| Condition | Project profile bytes | Manager HOME bytes | Hub state bytes |
| --- | ---: | ---: | ---: |
| native_managers | 7456 | 32 | 0 |
| skillkit | 8012 | 45529 | 0 |
| persistent_hub | 7456 | 5118 | 592813 |

Shared preparation and later verification are additional study overhead:

- Five final native fixture journeys (14 fresh CLI processes each) passed:
  median 26.796s, range 26.734–27.406s.
  These small mechanics controls are not real-SWE or owner-effort wins. One earlier
  successful fixture and five earlier repeats, an SDK import failure and the
  irrelevant-rank discovery remain retained; successful old fixtures were not
  relabeled as applicability evidence.
- Six live source-watcher processes across three revisions of the implementation
  checked public HEAD/cold intake and restart cache reuse, with zero model turns
  and zero project writes. All saw the same HEAD, not a real release transition.
  The comparative compatible update/resource loss is a controlled replay.
- Instrument admission included 22.656s of recorded initial checks, positive
  reference implementations, pristine failures, an incorrect independent-pair
  bootstrap, vacuous-success rejection and broken-link controls. Earlier scope
  bookkeeping/re-admission failures and their receipts remain available.
- Added website regression verification: 8.313s.
  Clean normal-font production builds for all three: 30.110s
  total after the timed run, with fresh build caches and real font files. Earlier
  offline font failures and Temper's explicitly mocked offline compilation smoke
  are retained; the latter was not counted as production-font validation.
- Six app-only patches applied to independent original archives with exact byte
  readback: 11.297s.
  Two failed Windows long-path/newline application attempts (outer tool durations
  5.323s and 2.647s) remain recorded, not discarded or counted as success.
- Owner-edit mutation detected by the real guard test: 1.531s.
  Current focused tests: 27 passed in 2.92s; Ruff and Mypy pass. Namespace-flag and
  test-attribute typecheck retries are preparation overhead, not product gains.
- Cleanup removed eight redundant, verified reconstructible application-check
  copies (338,288,866 bytes) in 1.578s.
  Private candidate patches, source inputs, encrypted raw evidence and three
  working review environments remain. Shared sources/dependencies are preserved.
- Mac read-only coordination was 26.291s; its tokens are unknown. No Mac source
  synchronization, native validation or implementation was performed.

Other authoring, debugging, repeated admission, browser review, participant
briefing and measurement time is only partially instrumented. **Total study
overhead is unknown.** Do not add nested figures or present this list as a complete
numeric total. All visible primary failures/retries are retained in encrypted raw
records; earlier qualification failures and supplementary checks remain private.

## Actual website and owner review

Actual production pages were inspected at desktop and 390×844 viewport settings
(375px content width). All three load real fonts, show the unchanged beta identity
and research qualification, expose the correct focusable source anchor, and
navigate to installation docs. No horizontal overflow observed. Visible keyboard
focus was confirmed on Temper's source link; the viewport override was reset.
Only the expected local Vercel Analytics script-unavailable log was observed.
No form/backend mutation, deployment, analytics setup, or accessibility-audit
completion is claimed. Screenshots are in the tool history.

The owner accepted a hands-on trial. At the recorded audit, the participant timer
had no events: effort is unmeasured, not zero. The review candidates and local timer
are ready. Record real research, setup, switches, update/recovery decisions,
review and measurement overhead; keep unattended waiting separate. Later review
intervals cannot retroactively measure earlier setup. One owner's repeated work
also has order/learning effects. Helpful/harmful outcomes remain unassessed.

## What this establishes and what remains

Persistent approved-source/project state, agent applicability decisions, complete
native staging, known-good recovery, owner-edit pause, rollback and source polling
are implemented. The current cache guard reserves each bounded acquisition;
automatic compaction and arbitrary framework/runtime compatibility are unfinished.
Two native loading probes support fresh-client metadata loading; a published file
does not prove an already-running chat reloaded it, followed it or found it useful.

The decisive next evidence is the owner's recorded natural-work cycle across the
conditions. Neither this run nor the [earlier discovery study](../discovery-maintenance-v2/RESULTS.md)
establishes an owner-effort win. Keep the habit learner's frozen evaluation and
promotion gates separate. These programmatic tasks and generated agent messages
are not independent human preference evidence.

This CLI prototype is not installed in the personal Temper app. Native macOS,
signed packages and independent clean-machine checks remain outside this study.
No GitHub CI, push, PR, source synchronization, deployment, new campaign or public
post occurred. No signing or release-readiness claim follows. The website and
Kairn candidate patches are private, reviewable work, not a published major update.
