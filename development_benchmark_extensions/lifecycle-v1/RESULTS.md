# Extension setup, compatibility and recovery results

Recorded October 15, 2026. Frozen operator candidate:
`61e8523027ad57e5573d70b9bc0abab421394e0e`.

**No overall effort reduction was demonstrated.** Both selective native use and
the experimental Temper publisher completed all four workflows correctly. Their
aggregate elapsed times were effectively identical. The prototype used fewer tool
calls, more cumulative/output tokens and more observed scratch storage. The two
approaches installed the same requested source resources.

This is a negative screen for a differentiated file-publishing/setup wrapper.
It does not disprove the broader idea of automatically choosing and maintaining
the right tools for each repository. That automatic selection and compatibility
layer was not implemented or validated here.

## Broader tool coverage

Seven workflow families were exercised through real native tools and public
sources: [pstack](https://github.com/backnotprop/pstack),
[Ponytail](https://github.com/DietrichGebert/ponytail),
[Superpowers](https://github.com/obra/superpowers),
[OpenSpec](https://github.com/Fission-AI/OpenSpec),
[Spec Kit](https://github.com/github/spec-kit),
[GSD Core](https://github.com/open-gsd/gsd-core) and
[Pi](https://github.com/earendil-works/pi). The
[native skills CLI](https://github.com/vercel-labs/skills) supplied selective and
temporary installation paths. Exact repository commits and archive digests are
in [sources.json](sources.json). Published npm distributions have separate version,
integrity and gitHead records in [distributions.json](distributions.json).

There were **45 fresh-profile native probes**, five per route. All passed their
defined checks. The table measures project files after setup with preinstalled
runtimes and a shared pinned source cache; it does not measure full product or
clean-machine installation.

| Native route | Project files added | Skill files | Project bytes added | Command seconds, median (range) |
| --- | ---: | ---: | ---: | ---: |
| pstack, full | 133 | 53 | 652,007 | 2.922 (2.812–3.140) |
| pstack, TDD only | 2 | 1 | 3,358 | 0.594 (0.578–0.625) |
| pstack, temporary use | 0 | 0 | 0 | 0.578 (0.562–0.578) |
| Ponytail, main skill only | 2 | 1 | 3,714 | 0.437 (0.437–0.453) |
| Superpowers, systematic debugging | 12 | 1 | 41,079 | 0.547 (0.531–0.547) |
| OpenSpec | 11 | 6 | 96,578 | 1.875 (1.844–1.875) |
| Spec Kit, source-built 1.2.1.dev0 | 30 | 10 | 244,350 | 2.297 (2.282–2.313) |
| GSD Core, Codex local setup | 860 | 72 | 15,747,835 | 16.671 (16.219–16.750) |
| Pi/Ponytail local package registration | 1 | 0 | 55 | 0.453 (0.422–0.453) |

The Pi row is a local package reference; its source/runtime is elsewhere. It is
not a claim that Pi costs 55 bytes to install. GSD additionally wrote two files
in the disposable HOME and generated 64 role configurations and hooks. This
establishes artifact creation, not that native Codex accepts every role/hook or
that GSD improves SWE work. WSL writes into Windows-hosted directories and host
load affect these timings; they do not rank the frameworks' ordinary performance.

Native selective installation already removes most unwanted pstack files for a
TDD-only task. Native temporary use also emits the skill prompt without installing
project skill files. Installed bytes should not be equated with loaded context:
Codex discovers skill metadata separately from full skill content. OpenAI also
documents that excessive or conflicting skill descriptions can hurt routing.
[Current skill/context guidance](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra).

## Compatibility and functionality findings

- **Actual Codex discovery:** the native Windows `skills/list` interface found
  both the project-scoped TDD skill and preserved owner guidance. This is metadata
  discovery, not evidence that an active chat loaded or followed the skill.
- **Runtime mismatch:** the real system Node 18.20.4 could not start `skills`
  1.7.2 because `node:util.styleText` was unavailable. Operator trials used Node
  24.18.0. Neither the current Foundry nor this file publisher supplies an automatic
  framework runtime-compatibility solution.
- **Pi approval:** registration succeeded, but the initial RPC command list did
  not include Ponytail. After explicit project-resource approval in the lab,
  native Pi RPC exposed Ponytail commands and skills. Both RPC probes had zero
  conversation messages and no provider model turn. Installing a package alone
  would have overstated readiness.
- **Supporting code matters:** Superpowers' actual `find-polluter.sh` identified
  the deliberately polluting Node test. Its exit code 1 is the documented result
  when pollution is found. Current Temper Foundry inspection quarantines that
  script. Dropping it would lose the requested helper capability and cannot be
  counted as a successful bloat reduction.
- **Current Temper boundary:** actual Foundry intake accepted five tested skill
  roots and rejected the non-SKILL Spec Kit command/Pi extension forms. Accepted
  OpenSpec/GSD instruction files do not provision their executable runtimes.
  These are intake outcomes, not successful framework installation receipts.

These diagnostics are separate from the frozen operator scores. The initial
unapproved Pi probe and failed `pi list --local` discovery attempt were preserved;
the later approval check does not rewrite the registration-only probe results.

## Real-repository operator comparison

Eight fresh native Codex contexts used full historical Temper/Python and
Kairn/TypeScript repositories. Each condition ran twice per repository. Source
choices were explicit to isolate installation and recovery effort:

- Python: pstack TDD, Ponytail, Superpowers systematic debugging.
- TypeScript: pstack technical writing plus its unslop dependency, Superpowers
  systematic debugging.

The agent had to install the complete requested resources, pass a host checkpoint,
recover a corrupted skill file and missing reference while preserving concurrent
owner notes/policy edits, pass another checkpoint, and uninstall without losing
owner content or leaving stale registry entries. All eleven checks passed in
every run: **88/88 checks, 8/8 completed workflows**. No application source or
unrelated owner configuration changed.

| Four workflows per condition | Selective native use | Temper publishing prototype |
| --- | ---: | ---: |
| Complete workflows | 4/4 | 4/4 |
| Whole-work seconds, sum | 604.610 | 604.390 |
| Whole-work seconds, median (range) | 143.938 (92.110–224.625) | 150.383 (85.484–218.140) |
| Actual tool requests/executed calls | 86 | 73 |
| Nonzero tool results | 10 | 11 |
| Reported cumulative tokens, cached input included | 2,277,021 | 2,562,940 |
| Uncached input tokens | 212,087 | 211,362 |
| Cached input tokens | 2,055,040 | 2,340,224 |
| Output tokens | 9,894 | 11,354 |
| Reasoning, already included in output | 819 | 495 |
| Observed peak scratch bytes, median | 261,409 | 683,940 |
| Observed peak scratch bytes, range | 40,138–1,046,447 | 180,875–995,462 |

The 0.220-second difference in aggregate time has no meaningful interpretation.
This is not evidence of statistical equivalence or a general speed improvement.
Nonzero results include recoverable command mistakes and checks; they are not
failed-workflow counts. Scratch measurements sample after tool calls and miss
transient peaks within commands.

Per-repository whole-work seconds, median (range):

| Repository | Selective native use | Prototype |
| --- | ---: | ---: |
| Temper/Python | 200.875 (177.125–224.625) | 204.468 (190.797–218.140) |
| Kairn/TypeScript | 101.430 (92.110–110.750) | 97.727 (85.484–109.969) |

Both installed the same source trees: setup snapshots contained 47,557 bytes for
the Python case and 55,842 for TypeScript, including the unchanged owner guide.
The prototype does not save installed resources beyond native selection. It
retains full scripts/references and adds staging/journal state.

## What was counted

Whole trials include repository/Git extraction, private HOME/config, fresh native
auth/catalog/model admission, operator reasoning and tools, setup checks, fault
injection, repair, removal, independent final verification, encrypted trace
persistence and safe workspace cleanup. The sequential operator run took
**1,209.031 seconds, or 20.15 minutes**. All eight final usage records match the
durable native journals. No malformed/unaccounted tool requests were found.

Shared setup and development are additional:

- Eight immutable public source snapshots were acquired and retained. Both
  conditions shared those sources; per-project probes did not repeatedly download
  them. Python, Node, WSL and the base repository environments already existed.
- Isolated npm provisioning added 280 packages in 16.343 seconds. Isolated Spec
  Kit/Python provisioning installed 41 packages in 5.437 seconds. This common
  tooling covers all framework probes and is not pstack's installation footprint.
  Two dependency scripts were withheld by npm; version/registration checks do not
  establish full Pi runtime readiness.
- There were **at least 36.36 wall minutes of preparation** before operator
  execution, including research, prototype/instrument development, controls,
  admission fixes and waits. An earlier unrecorded interval and active coordinator
  time/token use are unavailable, not zero. This is study development, not a
  product-onboarding measurement.
- Setup reporting hit a console-encoding error after a successful OpenSpec
  command; an early cleanup guard rejected mixed Windows long-path prefixes.
  Those attempts were retained. Corrected reference workflows passed before the
  freeze. A separate supplemental helper initially had an import-path error.
- The prototype's crash/stale-preview/owner-edit controls plus the existing native
  harness passed 24 tests. All four reference workflows passed the fixed final
  checks before model execution. Ruff and mypy passed. No failed model trial was
  discarded or rerun; there were eight model turns total.
- Actual human onboarding/discovery, production curation/signing, app integration,
  ongoing compatibility maintenance, and provider request counts were not measured.
  No monetary cost is inferred from subscription tokens.

The whole study/reporting interval exceeded 70 minutes at the saved results
checkpoint. Shared and prototype development cannot be allocated reliably to the
two conditions. These unknowns prevent a net ownership-cost savings claim.

After the tests, the isolated prerequisite directory was removed: 903,553,269
apparent file bytes, with 0.581 seconds of deletion work and 2.588 seconds for the
whole cleanup command. Public pinned sources (133,320,090 file bytes) and encrypted
evidence remain for audit. Dependency lock/version records were preserved first.
The lock-based preparation helper was then replayed successfully in 18.207 seconds
without a model turn; that restored prerequisite cache was also removed. This
reproduction check is additional validation overhead.

## Scope and conclusion

The publishing prototype supplies a useful structural property: previewed writes
and safe undo can preserve files that a native reinstall would otherwise replace.
The competent native agent achieved the same final outcome with ordinary backup
and restoration. The wrapper did not demonstrate lower overall effort here.

The remaining hypothesis is **automatic selection and maintenance of a minimal,
compatible repository profile**, including runtime/client checks and clear
permission/recovery behavior. This screen did not test automatic tool selection,
semantic instruction-conflict resolution, natural unexpected failures, human
usability, market demand or downstream SWE improvements. It tested file conflicts
and explicitly requested source sets. Source choice was not a learned preference.

The prototype condition received API usage examples; native use had pinned
upstream docs and help. Familiar human operators were not studied. Two repetitions,
two repositories, WSL/Windows filesystem effects and instrumented timings limit
generalization. GSD/Pi runtime probes do not establish cross-agent equivalence.

The installed Temper app, personal learning grant, native instruction profile,
habit-learning evaluations and Mac applications remain unchanged. The new manager
is benchmark-only and requires a disposable-project marker. It is not a shipping
Temper feature or a validated generic framework integration. No GitHub CI ran.

Evidence: [results.json](results.json), [admission.json](admission.json),
[protocol.json](protocol.json), [cases.json](cases.json), and [README.md](README.md).
The frozen protocol SHA-256 is
`639c0b840aca8ceb64d22d9adfc972023615e5e99ce33d7825912f356c9c8d5e`.
All frozen source/input bindings remained unchanged.
