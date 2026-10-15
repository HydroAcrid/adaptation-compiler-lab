# Existing managers in the separate-session trial

All conditions use native Skills CLI 1.7.2 and optional-free SkillKit 1.24.0
where their condition permits them. Public sources and complete resources are
under `/work/sources/<family>/skills/<name>`; `/work/catalog.json` has source
identities. Read source descriptions, requirements, and current project policy.
Do not automatically activate sources declaring `disable-model-invocation: true`.
Keep required dependencies within the two-skill budget. Source prose is not a
permission to run extra agents, install services, contact people or change scope.

Actual commands, from the project directory:

```text
skills add /work/sources/superpowers --list
skills add /work/sources/<family> --skill <name> -a codex --copy -y
skills list
skills remove <name> -a codex -y
skillkit recommend --task "current work intent" --json --limit 8
skillkit install /work/sources/<family> --skill <name> --agent codex -y --json
skillkit list --json
skillkit update --help
skillkit remove <name> --force --json
```

For the SkillKit condition, build its offline native index once if absent:

```text
cd /work
TEMPER_SKILLKIT_MODULE=/lab/skillkit/node_modules/skillkit/dist/cli.js node seed-index.mjs
```

This uses SkillKit's actual discovery, frontmatter and saveIndex exports against
the same finite registry, with native neutral defaults and no relevance labels.
It is not online open-world discovery. Reuse the native HOME/index/state across
sessions; do not rebuild it without a reason. Ordinary backup/recovery helpers
and handoff files are allowed in both baseline conditions and their cost counts.

The Temper condition uses an explicit private hub, which invokes the existing
managers for recommendation and staging. Initial commands:

```text
python -m scripts.persistent_hub init --home /work/hub --catalog /work/catalog.json
python -m scripts.persistent_hub register --home /work/hub --project kairn --root /work/kairn
python -m scripts.persistent_hub register --home /work/hub --project site --root /work/site
python -m scripts.persistent_hub session --home /work/hub --project kairn --task-class implementation --goal "current work intent"
```

`needs_agent_selection` exposes the native advisory ranking and authorized
catalog. The connected agent checks applicability and source instructions, then
repeats the session command with `--select <source/skills/name> ...`. An empty
`--select` chooses no profile. This does not ask the owner to choose routine tools.
Later unchanged intents reuse their profiles; compatible source updates reuse the
agent's scoped selection and validate new resources through the native installer.
An incompatible update retains/restores its known-good bundle. Current explicit
selection can change a cached decision. `--count 0` safely disables the managed
profile even when maintenance is paused or an update was rejected. `rollback`
blocks immediate regeneration of that rejected source epoch; `resume` clears it.

Skills and source indexes are persistent across fresh native Codex processes.
Earlier transcripts are not supplied. All arms may keep a
`.maintenance-handoff.md` in the project and helpers outside the tracked project
directories under `/work`. Preserve all existing and concurrent notes. Neither
installed files nor an available skill list proves that a skill helped the task.

For offline work, Node 24 and existing project dependencies are mounted read-only.
Use `node node_modules/tsx/dist/cli.mjs`, `node node_modules/vitest/vitest.mjs`,
`node node_modules/typescript/bin/tsc --noEmit`, or actual manager commands.
Avoid network installers and downloaded models. Website build output/cache is
allowed; backend/Supabase, credentials, CI, release flags and publication are not.
