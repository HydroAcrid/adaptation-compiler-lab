# Manager commands available to every condition

This experiment uses the actual native Skills 1.7.2 and SkillKit 1.24.0 CLIs.
All source choices are yours. The same finite public snapshot registry is under
`/work/sources`. Native README files remain in the earlier public source cache
under `/public-sources/<family>/README.md`. `/work/catalog.json` declares the
available source revisions, roots, and minimum Node version. Its initial values
come from the pinned public repositories; subsequent v2/v3 edits are explicitly
controlled release replays. No live upstream update is being asserted.

The host uses SkillKit's exported `discoverSkills`, `extractFrontmatter` and
`saveIndex` APIs to seed its normal HOME index from exactly these snapshots.
Compatibility/tags are parsed from native frontmatter, popularity is zero, and
quality is the native fetcher's neutral default 50. No benchmark relevance labels
are present. This is an offline registry replay, not SkillKit's default online
index build. Setup/seeding overhead is measured and supplied to every condition.
Do not edit the replay index, source trees or catalog. Do not ask another provider
to perform reasoning, generate embeddings or run a nested model. Your configured
Codex agent supplies semantic judgment in every arm.

Use the actual `--help` when needed. Useful native command shapes:

```text
skills add /work/sources/<family> --list
skills add /work/sources/<family> --skill <name> -a codex --copy -y
skills list
skills remove <name> -a codex -y
skillkit recommend --task "natural work goal" --json --limit 8
skillkit install /work/sources/<family> --list
skillkit install /work/sources/<family> --skill <name> --agent codex -y --json
skillkit init --agent codex --quiet
skillkit list --json
skillkit update --help
skillkit disable <name> --json
skillkit remove <name> --force --json
skillkit sync --agent codex --yes --json
skillkit doctor --json
```

Run native manager commands from the actual project directory. Both `.agents/skills`
and `.codex/skills` are inspected, along with other declared native skill paths.
Native metadata discovery is separately checked through the actual Codex
`skills/list` RPC. Installing/discovering a skill does not prove a current chat
loaded or followed it. Preserve complete source resources, manual notes and owner
policy. If a manager lacks safe handling, ordinary helpers/backups are allowed in
the native and SkillKit arms and count toward their effort.

The experimental Temper CLI is available only for the Temper condition:

```text
python /tools/temper-hub.py discover --root /work/python --catalog /work/catalog.json
python /tools/temper-hub.py recommend --root /work/python --catalog /work/catalog.json --goal "natural work goal" --count 2
python /tools/temper-hub.py maintain --root /work/python --catalog /work/catalog.json --goal "natural work goal" --count 2
python /tools/temper-hub.py status --root /work/python
python /tools/temper-hub.py maintain --root /work/python --catalog /work/catalog.json --goal "No workflow needed" --count 0
```

This prototype scans source metadata, lexically ranks the current goal with a
small repository-stack tie-breaker, checks declared runtime requirements and
missing local Markdown references, and reconciles exact complete resources to a
project-scoped profile. It preserves untracked owner files, pauses on edited
managed files, and defers incompatible updates to an unchanged task. It does not
execute source scripts, provision external runtimes, transform skill procedures,
infer personal habits, or resolve arbitrary semantic instruction conflicts.

Its `refresh` command can fetch owner-configured public GitHub repositories into
a marked disposable cache. Live acquisition is probed separately and is not run
inside the offline comparison. Candidate scope is an existing permission; the
prototype cannot make a new publisher trusted on its own.

## Dependency-aware repair

The v2 Temper CLI expands strong named skill requirements within the authorized source. Its two-skill ceiling includes dependency closure. It blocks incomplete profiles that cannot fit the budget and reports source invocation restrictions without changing source bytes or claiming delivery. This does not interpret every conditional instruction or framework runtime dependency. All conditions must inspect upstream requirements and preserve required dependencies.
