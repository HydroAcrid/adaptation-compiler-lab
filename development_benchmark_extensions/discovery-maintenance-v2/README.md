# Dependency-aware discovery/maintenance repair

This is a new version of the [v1 instrument](../discovery-maintenance-v1/README.md),
not a rewrite of its frozen inputs or results. The source audit identified a
missing acceptance condition: pstack's exact pinned `technical-writing` release
explicitly requires `unslop` (SKILL.md line 93 and README dependency table).
Treating the parent alone as complete could create a false footprint/effort win.

The v1 run was stopped between turns after its native-manager and SkillKit
operators completed and before any Temper model turn. Both selected the required
dependency. Their receipts, tokens, wall time, and the partially prepared next
workspace remain recorded as experiment overhead. No failing Temper primary
result was discarded. The v1 comparison has no overall result.

## Repaired prototype and acceptance

`scripts/discovery_maintenance_v2.py` layers a dependency-aware resolver over the
unchanged v1 prototype. It discovers strong named skill requirements and simple
declarative dependency fields within the authorized source, expands transitive
closure, detects cycles and missing requirements, and counts the complete closure
against the profile budget. It blocks incomplete choices instead of dropping
required functionality. This does not interpret every conditional instruction,
arbitrary framework dependency, installer script or runtime requirement.

Source invocation restrictions remain byte-for-byte intact. The CLI reports
`disable-model-invocation` source flags separately and never equates installation
with actual native implicit eligibility, delivery, following, or helpfulness.
Client-specific interpretation remains a separate admission question. Neither
version installs a background scheduler or enables product personalization.

The grader has an independently audited exact-source dependency edge, rather than
using the prototype parser to grade itself. Every condition receives the same
requirement to preserve dependencies; the goal still names no skills. All other
v1 safety, source/resource, owner-edit, update, scope and real native-discovery
checks remain. Reference flows and an explicit missing-dependency mutation must
pass before the revised instrument is frozen.

## Comparison

Six fresh native model turns, two complete journeys per condition, forward then
reverse order, using the same configured model/effort and 600-second/100-tool
budgets. This is an instrument repair on a previously seen development journey,
not unseen-task validation. No result establishes broad superiority or human
time savings. The earlier habit-learning evaluations remain unchanged.

Conditions, full repositories, source snapshots, dependency locks, isolated HOME,
live-refresh diagnostics, measurements and confidentiality rules follow v1.
The repaired sandbox binds both the frozen v1 core and the v2 entry point; it does
not modify installed apps, personal grants, native user instructions or source
permissions. Manager dependencies include default optional packages, reviewed
lab-only native-script approvals, and successful SQLite/backend-load probes; no
embedding model or additional provider is invoked. All extra diagnostics count.

The focused verification and bounded controls are authoritative for these files.
A broader legacy benchmark-suite attempt produced 255 passes and 26 failures on
Windows, including POSIX permission/getuid/sandbox assumptions and old frozen
fixture-digest checks. Existing tracked source/fixtures were unchanged at that
point. Those legacy failures are retained as limitations, not silently repaired
or represented as an all-green repository run.

```text
.venv\Scripts\python.exe -m scripts.prepare_discovery_maintenance
.venv\Scripts\python.exe -m scripts.run_discovery_maintenance_v2_screen --controls --output <new-private-controls>
.venv\Scripts\python.exe -m scripts.run_discovery_maintenance_v2_screen --output <new-private-run>
```

Source cache and preinstalled runtime prerequisites remain required. No GitHub CI,
push, PR, package release, signing or public-download readiness is implied.
