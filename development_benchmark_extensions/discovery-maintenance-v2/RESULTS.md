# Discovery and maintenance prototype: local development results

Recorded 2026-10-15. **All six corrected journeys passed, but this screen did
not demonstrate a convenience or effort advantage for Temper.** Temper was
slower and needed about as many operator tool calls as native Skills. Every
condition finished without a simulated owner escalation. Actual human attention,
research time, satisfaction, billing and coordinator model costs are unmeasured.

The result supports the feasibility of a bounded maintenance controller. It does
not establish the value of an unattended discovery hub or a launch claim.

## Candidate and comparison

- Candidate: `fdc465e615523d12a1b150ee7bddf846857390a0`.
- Protocol SHA-256:
  `1999a539e0cbac435e2ef361b310adb2c4535a3721ddcdfe6a98496c2b2e930c`.
- Frozen before the corrected run at `2026-10-15T17:00:29.132996+00:00`.
- All 30 bound files and all three shared public source trees still match.
- Model: configured `gpt-6.1-sol`, medium effort, saved ChatGPT authentication.
  Native Windows Codex `0.162.0-alpha.17.2`; binary SHA-256
  `e98c516f1c8935789aabe9122ee7e05ec4c3efd1ba6acf179242e031c495b99e`.
- Native tools: Skills CLI `1.7.2`, SkillKit `1.24.0`, Node `24.18.0`, Python
  `3.12.13`. Exact default dependency locks are in the v1 artifact directory.
- Same native agent, goals, budgets and finite registry in every condition.
  Two repetitions per condition, forward then reverse order; one continuous
  native model turn per eight-phase journey. No extra selector/model calls.
- Full historical Temper/Python and Kairn/TypeScript repository trees, including
  Git and existing native policy; disposable copies on the Windows filesystem.
  Managers run in credential-free, offline WSL namespaces. Network is enabled
  separately only for public package/source acquisition.

The bound hashes describe the executed working-tree bytes. A final replay audit
also checked candidate Git blobs: 29 match exactly; the older
`development_benchmark_extensions/lifecycle-v1/sources.json` fixture uses CRLF
in the frozen working tree and LF in Git. Its parsed values and all other bytes
are identical. No code, labels or source revisions differ. Fresh checkouts must
restore those line endings before the frozen runner's strict byte check; the
recipe below verifies the expected hash before writing. The protocol is unchanged.

The registry contains 74 canonical main-root skills from pinned
[pstack](https://github.com/backnotprop/pstack/tree/1f0f9c3bac03c4297f6fc8f7644fa412eda57085),
[Ponytail](https://github.com/DietrichGebert/ponytail/tree/84740e3d344b69b4a133201fa519eb37a62a2b2a),
and [Superpowers](https://github.com/obra/superpowers/tree/bb92a77741419a4ab5f06e711a283343f1ada0c3).
This is a preapproved registry replay, not open-world research. SkillKit's native
discovery/frontmatter/index APIs populate its cache from the same corpus with
neutral defaults; no relevance labels are injected. Online index building,
embedding and extra reasoning providers are outside this comparison.

## What was built and exercised

The sandbox CLI acquires configured public GitHub revisions, validates bounded
archives and cache integrity, discovers metadata, selects a small profile from a
natural work goal, and maintains separate project profiles. It preserves complete
skill resources and detected same-source dependencies, defers declared runtime
incompatibility, pauses on externally edited managed files, retains owner content,
and recovers interrupted publication. No skill names were supplied in work goals.

The same agent operates either ordinary Skills plus filesystem helpers, actual
SkillKit plus allowed recovery helpers, or Temper's prototype CLI. Temper managed
profile writes must go through its CLI; manually copying the desired profile is
not allowed. Existing managers may automate and preserve their own state.

All six corrected journeys passed all eight phase checks:

| Phase | Verified result |
|---|---|
| Setup | Small relevant Python debugging/regression workflow; complete resources |
| Project switch | Appropriate TypeScript documentation profile, with required dependencies |
| Return visit | Prior Python profile remains usable |
| Compatible update | Updated skill body and supporting resource installed |
| Incompatible update | Working version retained when offered release requires Node 99 |
| Recovery | Deleted resource repaired; concurrent owner note and policy edits preserved |
| Task-class switch | Irrelevant specialization removed for plain branch inspection |
| Cleanup | Both profiles/registrations removed; owner content/config and app code preserved |

Updates and the Node 99 compatibility event are controlled snapshot edits. The
fault is a deleted supporting file, not a killed competitor installer. Separate
prototype tests exercise an actual abrupt child exit during publication.
Real native `skills/list` checks confirm metadata discoverability without errors;
they do not establish that a running chat loaded, implicitly invoked, followed,
or benefited from the instructions. Upstream invocation restrictions remain intact.

## Corrected primary measurements

Totals are for **two complete journeys per condition**. Elapsed time includes
repository extraction/Git/index setup, native authentication/model/capacity
admission, reasoning, all tool failures/retries, checks, native inventory readers,
evidence persistence, and subsequent measured disposal of each fixture workspace.
One-time lab setup and diagnostics are reported separately below.

| Measure | Native Skills | SkillKit | Temper prototype |
|---|---:|---:|---:|
| Complete passing journeys | 2/2 | 2/2 | 2/2 |
| Total elapsed including fixture disposal | 471.204 s | 512.985 s | 662.937 s |
| Median per journey | 235.602 s | 256.493 s | 331.469 s |
| Journey range | 228.735–242.469 s | 253.781–259.204 s | 331.047–331.890 s |
| Fixture/index setup, within totals | 69.735 s | 70.922 s | 71.281 s |
| Fixture disposal, within totals | 7.078 s | 7.063 s | 8.015 s |
| Operator tool calls | 54 | 60 | 56 |
| Nonzero tool results, retained | 4 | 4 | 2 |
| Operator tool time, within totals | 147.814 s | 167.376 s | 346.736 s |
| Instrument observation time, within totals | 41.625 s | 43.645 s | 43.621 s |
| Simulated owner escalation requests | 0 | 0 | 0 |
| Observed peak writable workspace bytes | 123,339,979–123,364,528 | 123,344,400–123,344,794 | 123,331,050–123,331,432 |

Component times are nested; do not add them to whole elapsed time. Sampled
workspace storage includes repository/source copies, backups and writable manager
state. It is a lower bound on transient peak usage, excludes shared dependencies,
and is not a prompt-context measurement.

Both Temper runs had an initial compound inspection/recommendation timeout of
about 43–44 seconds. These commands also included Git inspection, so the entire
timeout cannot be attributed to the prototype. Ordinary prototype calls repeatedly
scan/validate the mounted source trees and often took roughly 7–8 seconds. All
timeouts, additional inspections and retries remain in the totals. Other arms'
nonzero calls include unavailable optional inspection tools and native local
update/recovery fallbacks. SkillKit's local-source `update` sometimes skipped
entries; the operator used reinstall and owner-note backups. This does not test
or establish a limitation in SkillKit's online upstream-update support.

| Native reported cumulative token traffic | Native Skills | SkillKit | Temper prototype |
|---|---:|---:|---:|
| Total input + output | 2,066,649 | 1,823,003 | 2,064,532 |
| Input | 2,059,860 | 1,815,163 | 2,059,085 |
| Cached input | 1,949,440 | 1,636,224 | 1,958,144 |
| Uncached input | 110,420 | 178,939 | 100,941 |
| Output | 6,789 | 7,840 | 5,447 |
| Reasoning, subset of output | 228 | 318 | 91 |

These are cumulative native accounting values across tool continuations, not
unique context size or billed cost. Different cache behavior prevents a general
efficiency claim from the lower Temper uncached-input count. Tool requests,
execution records, completion markers, and final native usage reconcile for every
completed benchmark turn. Provider HTTP request counts remain unknown.

## Stronger SkillKit configuration check

The primary used the full default installation, including its optional native
libraries. After all primary inference/timing ended, a separate cold npm cache
installed SkillKit `1.24.0` with `--omit=optional` in 9.562 seconds.

| Installed dependency directory | Observed bytes |
|---|---:|
| Default SkillKit | 978,493,665 |
| Optional-free SkillKit | 41,401,583 |
| Native Skills CLI | 4,526,335 |

Ten alternating fresh-profile controls passed: five default and five optional-free,
each checking native recommendation, complete-resource installation, list,
removal and owner-file preservation. Median scripted sequence times were 1.859 s
and 1.844 s respectively; the tiny difference is not an improvement claim.
CLI and core distribution code hashes match between installations.

The optional-free configuration also passed all eight phases of the full
scripted reference journey, with native metadata readers: 74.656 s including
31.516 s fixture setup, 18 commands, zero model turns. Two preliminary supplement
setups were incomplete/failed; one retained traceback identifies expansion of the
outer WSL PATH in our wrapper. A constant isolated PATH fixed the wrapper. The
first attempt's exact terminal error was not retained. Neither invoked inference.

This does not rerun or replace the frozen primary, nor test TUI, embeddings,
reasoning backends, or full feature equivalence. It does show that most of the
default footprint is avoidable for the basics exercised here. Default install
size is consequently a weak basis for claiming a Temper advantage. The
supplementary package and lock files are saved alongside these results.

A post-cleanup replay audit found that the basic probe reused a neutral index
inside an earlier disposable fixture. The final helper rebuilds every neutral
74-skill index through SkillKit's native exports instead. Another ten basic
controls passed from restored dependencies, with zero model turns: 31.000 s total
including 12.768 s of index rebuilding, plus 8.360 s for the optional-free install.
The repeated dependency restoration cost 1.109 s for Skills and 17.906 s for
SkillKit. These diagnostics count as overhead, without replacing earlier timings.

## Development, setup and recovery overhead

- The first instrument omitted a source-level dependency acceptance condition:
  pinned pstack `technical-writing` explicitly requires `unslop`. Native Skills
  and SkillKit selected it anyway. The comparison was stopped between turns,
  during the next fixture preparation, **before any Temper model turn**. Their
  completed receipts/events are retained; no failed Temper primary was removed.
  These two diagnostic turns used 516.703 s before disposal, 56 tools and
  1,956,534 total tokens. They provide no overall v1 comparison result.
- Across all eight completed benchmark turns, recorded usage is 7,910,718 total
  tokens: 7,883,833 input, 7,380,864 cached input, 502,969 uncached input,
  26,885 output, with 1,033 reasoning tokens already included in output.
  Complete journeys used 2,141.673 s before fixture disposal and 2,170.985 s
  including their measured disposal. This excludes other development activity.
- Initial lab manager installations took 1.563 s for Skills and 24.109 s for
  SkillKit. SkillKit's two optional native scripts were initially withheld.
  A version-argument approval attempt failed (0.609 s); scoped lab approval
  succeeded (0.453 s), followed by rebuild (1.828 s), SQLite probe (0.109 s),
  and successful backend-load probe (0.797 s). The earlier backend probe failed
  because our `--input-type=module` invocation propagated into a file-based child.
  No embedding model was loaded and no inference provider was invoked.
- Reference attempts are counted rather than treated as free setup: early
  Windows long-path and Node invocation failures, then two routing failures
  (project language overpowering the documentation goal; an incidental-word
  filler selection). The ranker repairs require independent task-term evidence
  and drop weak trailing candidates. v5 reference flows passed; v6 adds dependency
  closure and an independently audited exact-source dependency check. Their full
  measured completed rows remain in `results.json`; later failed-flow receipts
  remain in private evidence. The first two setup failures' exact terminal
  records and durations were not retained and remain unknown. They are
  development controls, not additional model trials.
- The final live public HEAD/cache probe fetched one real Superpowers revision:
  cold 1.906 s, two HTTP requests and 680,678 archive bytes; warm
  0.234/0.250/0.203/0.203 s, one request each, with tree-integrity checks.
  HEAD did not change. This demonstrates acquisition/reuse, not an unattended
  upstream release transition. An earlier pre-integrity refresh probe is retained.
- The shared, preexisting eight-family public snapshot cache is 133,320,090 bytes
  and remains available. The current three-source registry reuses it. Initial
  research, source approval and existing Windows/WSL/Node/Python/Codex/venv setup
  are prerequisites; their owner/coordinator effort is unknown, not zero.
- The 37 original disposable Windows fixture workspaces were removed in 96.844 s;
  the model-fixture portion is already included in journey totals. Encrypted raw
  model records and receipts remain outside Git and the vault. Shared public
  source caches and preexisting runtimes were preserved.
  Ten additional replay profiles were removed in 0.015 s, making 47 disposed
  workspaces and 96.859 s across all fixture cleanup.
- The dedicated Linux dependency/cache tree (1,743,665,679 bytes) was removed in
  0.542 s. Exact locked dependencies were then restored from a deleted cache:
  Skills 0.938 s, SkillKit 16.922 s, correct versions. The restored SQLite and
  native backend qualification passed in 0.562 s without loading a model.
  The recreated tree (1,449,671,683 bytes) was removed again in 0.575 s.
  After the final replay audit, its new 1,621,353,329-byte dependency/cache tree
  was also removed in 0.718 s.
- A read-only Mac coordination turn took 28.114 s; its tokens and coordinator
  costs are unavailable. No Mac source/runtime or shared state was synchronized.
  Prototype/instrument development, audits, failed setup, reporting and user
  research are not silently converted into product onboarding savings.

## Verification and limits

Focused unit coverage: **46 passed**, covering the prototype, dependency closure,
grader and reused extension/repository lifecycle boundaries. Six representative
grader mutations were detected (app edit, owner policy loss, resource loss,
source/catalog tampering and wrong-scope installation). A separate exact-source
missing-dependency mutation was rejected and restoration passed. An actual abrupt
child exit during publication converged on recovery. Ruff and strict mypy passed
for the new frozen files and the supplementary probe. No stale Git lock files
remained in any of the twelve corrected project trees before disposal.

A broader legacy benchmark-suite attempt had **255 passes and 26 failures** on
Windows, including POSIX permission/getuid/bwrap assumptions and historical
fixture-digest checks. Existing tracked fixtures/source were unchanged at that
point; they were not rewritten or weakened to obtain green results. This is not
an all-green repository run.

Two repetitions of one previously seen journey cannot establish general
superiority, equivalence, human attention savings, security of arbitrary sources,
or coding quality. This is one continuous operator session per journey, not a
longitudinal test across ordinary separately started chats. No clean-machine,
macOS package, signing or release validation was performed. No background service,
arbitrary framework runtime installer, semantic native-policy solver or personal
habit learner was added. Installed app, personal grants/serving, native user
instructions, Foundry quarantine, and frozen habit-learning studies are unchanged.

## Product implication

Keep this as a measured sandbox prototype. The selection/copy/update mechanism
works, but an agent with existing managers already handles this bounded sequence
with little intervention. A useful next iteration should reuse those managers
and test durable source/compatibility state across independent real work sessions:
source watch, project switching, safe update decisions, and rollback without
repeating research. Cache the costly catalog/resource work, then evaluate on new
repositories and actual upstream revisions with owner attention explicitly timed.
That would test the proposed convenience niche directly; this screen cannot.

Machine-readable measurements: [results.json](results.json). Frozen design:
[protocol.json](protocol.json), [cases.json](cases.json), and [README.md](README.md).
No GitHub CI, push, PR, release, app install, website publication or LinkedIn post
was performed.

To replay the post-primary supplement with the declared source/runtime prerequisites
and retained primary receipts (use new private output directories):

```text
.venv\Scripts\python.exe -m scripts.prepare_discovery_maintenance
.venv\Scripts\python.exe -m scripts.probe_skillkit_minimal --output <new-private-basic-controls>
.venv\Scripts\python.exe -m scripts.probe_skillkit_minimal --full-controls-only --output <new-private-full-control>
```

For a fresh checkout that will replay the frozen primary, restore its exact
legacy fixture bytes first (no JSON values change):

```text
.venv\Scripts\python.exe -c "from pathlib import Path; import hashlib; p=Path('development_benchmark_extensions/lifecycle-v1/sources.json'); b=p.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'); assert hashlib.sha256(b).hexdigest()=='ac22624ad1290f7a8f4134023ad560b48c66eb12cd19756d9b5a093342b7c2ad'; p.write_bytes(b)"
```
