# Persistent hub over existing managers

Experimental implementation and same-day separate-session development study.
This does not replace the installed Temper app or its governed habit learner.
The earlier discovery/maintenance and frozen learning evaluations are unchanged.

The [recorded results](RESULTS.md) separate functional checks, original grading
defects, recorded costs and the still-incomplete participant effort comparison.

Later source defaults new hubs to SkillKit and drops the separate Skills CLI
dependency for that configuration. Legacy saved manager choices remain unchanged.
See [the current product scope](../../TEMPER_SKILLKIT_BASE.md). The frozen run
below used an earlier, explicitly bound candidate; its setup costs and results
must not be relabeled as evidence for this later change.

## Implemented controller

`scripts/persistent_hub.py` persists a scoped public source index, project
registrations, native manager identity, agent-selected profiles, validated native
installation bundles, rollback history, and interrupted-publication journals in
an explicit private SQLite state directory. It uses SkillKit's native parser,
index and advisory recommendation API and Skills or SkillKit for staging complete
resource trees. It does not replace either manager with a bespoke installer.

Native recommendation rank alone cannot authorize a profile: a development
control exposed irrelevant top-ranked suggestions. The connected agent checks
the current work, native policy and source instructions, then supplies eligible
catalog IDs. This is ordinary agent work, not per-item owner approval or a hidden
selector model call. Compatible updates reuse that scoped decision. Different
goals/policy/manager identities require a new decision. Exact native bundles can
be reused across decisions without reinstalling them. Goals are hashed as routing
inputs, never labeled as personal habits or independent human preferences.

Only separately marked, explicitly registered project roots are writable. Manual
content and concurrent notes are preserved; externally edited managed files pause
publication. Complete original resources and detected dependencies remain intact.
Sources declaring explicit-only invocation are excluded from autonomous profiles.
Unknown frameworks, arbitrary semantic policy conflicts, and generic runtime
requirements are not solved by this prototype. The agent must inspect them.

SQLite serializes writers. A durable journal permits recovery after a real child
process exit. Known-good bundles repair missing files even when a new source is
incompatible or unavailable. Rollback prevents immediate regeneration of its
rejected epoch. `--count 0` removes identifiable owned files while preserving
owner notes, including when maintenance is paused or an update is rejected.
Per-file replacement is atomic; this is not a power-loss or whole-filesystem
transaction guarantee. Profile/bundle caches are bounded to 20 entries each and
complete profiles to 8 MB; old active/previous profiles remain separately held.

The optional foreground watcher checks configured public refs every five minutes,
without model calls or project writes. It persists each source's integrity receipt
independently, retries failed acquisitions in a new owned partition, and leaves
failed evidence available. The current controller reserves the intake's full
120 MB expansion ceiling before each source acquisition within a 512 MB file
content budget. This is conservative even on a cache hit. The frozen comparison
candidate checked only before a whole batch and could overshoot; the reservation
fix was qualified separately afterward. This prototype does not yet provide
automatic source-cache compaction. No watcher
or service is installed into the owner's environment by the study.

## Native process and real-work comparison

The owner selected Kairn's forthcoming update and website as the actual work.
The new cases use clean current snapshots of Kairn `99e2416` and site `096eb85`.
Original repositories and unfinished work are preserved. Source visibility is
verified through GitHub metadata; older private-source website text is stale.

Three conditions use the same configured native Codex model/effort:

1. Native agent using Skills CLI and ordinary persistent files/helpers.
2. Native agent using optional-free SkillKit and ordinary persistent files/helpers.
3. Native agent using the persistent Temper hub over those existing managers.

Three fresh native processes/threads per condition, nine primary turns in total:
Kairn task-grouped pilot diagnostics; website source/evidence clarity; Kairn return,
compatible-update/resource-loss recovery, CLI completion and one preregistration.
Repository files, manager HOME/index and permitted handoffs persist. Previous
transcripts are not injected. Baselines can retain and automate their own state.
Condition order is forward, reverse, forward across the three sessions.

The input is the completed 45-pair/15-task research evidence artifact, whose hash
matches the October handoff. It is supplied privately to each operator. The
website's separate unrun placeholder and public evidence gates remain unchanged.
The study does not train a value guard, retune a ranker, reopen a contaminated
holdout, run a Kairn campaign, promote research or publish improvement claims.

Updates/faults in the comparative journey are controlled snapshot replay, not a
real upstream release or a human edit. Separate live public-ref/cache probes
exercise source acquisition and restart reuse; unchanged HEAD is not an update
transition. Small lifecycle controls use fresh CLI processes without inference.

Current native-client loading was checked with separate read-only model probes:
a random response word existed only in project instructions, or only in skill
metadata; the model returned it without a tool call. This supports actual loading
in the tested fresh client, not a claim that running chats reload profiles or that
an available skill was followed/helpful. The exact client reports an empty
`instructionSources` list before the first turn even in these successful probes;
file publication and this metadata field alone are not used as delivery proof.
See [official app-server documentation](https://learn.chatgpt.com/docs/app-server)
and [skill loading documentation](https://learn.chatgpt.com/docs/build-skills).

## Correctness and accounting

Independent behavior checks reject duplicate/non-finite inputs, preserve task
clusters and row-order determinism, validate provenance/output refusal, exercise
stale-source-claim mutations, and preserve unrelated source/evidence/release
files. A zero exit without completed assertion proof is not accepted. Positive
reference implementations, broken references, and pristine failures are admitted
before primary execution. References stay outside operator namespaces.

Record cold dependency acquisition, repository/index setup, native account/model/
capacity admission, every model/tool call, errors/retries, source events, checks,
handoffs, evidence persistence, review, and cleanup. Cache hits and model input,
cached input and output are separate; reasoning is a subset of output. Inner
Linux timings and outer Windows timings are labeled separately, never added to
whole elapsed time. Retain failed controls and all auxiliary/probe turns.

Preexisting Windows/WSL/Python/Node/Codex and project dependencies are prerequisites,
not free new-user setup. Their original setup cost, coordinator tokens/active
time, billing and human research before recording are unknown rather than zero.
Dependencies use exact locks and optional-free SkillKit; all arms receive the same
finite 74-skill approved registry. No open-world discovery/research saving is
established by this source list. No API key, paid fallback, model substitution,
GitHub CI, app install, source synchronization, deployment or public post occurs.

## Actual participant effort

`scripts/persistent_hub_effort.py` serves a loopback-only participant timer. The
owner explicitly records research, setup, project switches, decisions/review,
updates, recovery, measurement overhead and waiting by session and condition.
Shared briefing/measurement setup is recorded separately. Waiting is excluded
from active effort; unfinished/unobserved intervals remain unknown. Agents must
not operate participant controls. Test records use separate temporary databases.
There is no keyboard/screen tracking or assertion of continuous physical attention.
These are self-recorded attention intervals, not agent-runtime proxies.

No owner-effort comparison is complete without participant data across the
conditions. One owner's repeated work has learning/order effects; this is a
development study, not a population or statistically established savings claim.
Routine ratings are not required. Helpful/harmful outcomes stay unknown without
reliable assessment. A brief review after automated runs cannot replace the
unobserved effort of earlier sessions.

## Local commands

The namespace helper requires the declared existing Windows/WSL runtimes and
cached public sources. Private evidence stays outside Git and Obsidian.

The recorded nine-session run used commit `9e4e605` and the immutable
`protocol.json`. Check out that exact candidate for a replay. Later code or README
changes intentionally fail its input-binding checks; do not rewrite the old
protocol hashes to admit them. Freeze a separate study version for another
candidate. Preparation also requires the privately authorized source archives,
completed pilot input and dated project-context snapshots whose hashes are listed
in that protocol; the dependency preparation helper does not export them for you.

```text
.venv\Scripts\python.exe -m scripts.prepare_persistent_hub
.venv\Scripts\python.exe -m scripts.probe_persistent_hub --output <new-private-control> --repeats 5
.venv\Scripts\python.exe -m scripts.run_persistent_hub_screen --output <new-private-run>
.venv\Scripts\python.exe -m scripts.persistent_hub_effort --private-root <private-participant-data>
```

For source monitoring after explicit hub initialization, run
`python -m scripts.persistent_hub_watch --home <private-hub> --once`, or omit
`--once` for a foreground five-minute source loop. It does not publish profiles;
the next authorized agent session makes the applicable publication/recovery call.
