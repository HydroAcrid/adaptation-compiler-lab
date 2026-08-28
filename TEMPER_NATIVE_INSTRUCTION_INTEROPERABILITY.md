# Temper Native Instruction Environment Interoperability

Status: **implemented and locally verified on 2026-08-28**

## Purpose

Temper must understand the instructions already surrounding an agent before it adds anything. A
repository's `AGENTS.md`, `CLAUDE.md`, Copilot instruction files, and supported `SKILL.md` files are
therefore contextual policy—not automatically personal learning. The compiler resolves:

```text
applicable native instructions + approved Temper Core + project + temporary Mode
    -> native precedence, scope, overlap, contradiction
    -> smallest target-specific Temper delta
```

Detection never promotes a native clause into Core. Imported profile exports omit observed native
context. Adopting a native behavior as a personal rule still requires a new explicit user
attestation and the ordinary governed review path.

## Supported contracts

The initial adapters are version-bound to the behavior documented by their platforms:

- Codex: root-to-working-directory `AGENTS.override.md`/`AGENTS.md` discovery, explicitly configured
  fallback filenames, the 32 KiB default combined instruction ceiling, repository
  `.agents/skills/*/SKILL.md`, opted-in personal instructions/skills, and enabled/disabled skill
  configuration. The managed-task gateway compares this prediction to Codex's returned
  `instructionSources` and refuses a mismatch.
- Claude Code: managed `CLAUDE.md` policy at the documented Windows, macOS, or Linux/WSL location;
  project hierarchy `CLAUDE.md`/`CLAUDE.local.md`, `.claude/CLAUDE.md`, recursive
  `.claude/rules/**/*.md`, and `.claude/skills/*/SKILL.md`; opted-in personal rules, skills, and
  selected memory are observed at their lower/unknown authority. Managed policy is read-only and
  does not require personal-root opt-in. This is discovery-only while the Claude product connector
  remains unavailable.
- GitHub Copilot: `.github/copilot-instructions.md`, path-scoped
  `.github/instructions/**/*.instructions.md`, supported project instruction files, and documented
  project/personal skill roots. This is discovery and analysis only; delivery is not claimed.

Contract versions and the exact native source-chain digest are stored in each environment snapshot
and runtime manifest. Unknown future platform behavior is not silently assumed compatible.

References: [Codex instruction discovery](https://developers.openai.com/codex/guides/agents-md),
[Codex skills](https://developers.openai.com/codex/skills),
[Claude memory and rules](https://code.claude.com/docs/en/memory),
[Claude skills](https://code.claude.com/docs/en/slash-commands), and
[Copilot customization support](https://docs.github.com/en/copilot/reference/custom-instructions-support).

## Trust and privacy boundary

- Registered projects are inspected only at exact documented locations. Personal roots remain off
  until a target-specific preview is explicitly enabled.
- Native instructions retain project-policy, user-configured, managed-policy, or agent-generated
  authority. None is rewritten as user feedback.
- Scripts, commands, hooks, resources, plugins, dependencies, MCP servers, and tools referenced by
  skills are never executed or installed.
- Symlinks must resolve within the registered project or opted-in root. Build outputs, dependency
  trees, VCS internals, caches, and temporary directories are excluded.
- Sources are limited to 256 KiB each and 2 MiB per environment. Invalid, raced, unreadable,
  out-of-boundary, or oversized sources make the affected environment incomplete.
- React receives source labels, bounded relevant clause summaries for a blocking conflict, digests,
  counts, and statuses—never absolute paths, home directories, raw conversations, credentials, or
  unrestricted file contents.
- The deferred Milestone 6 bundle, mappings, tasks, and custody state are not reachable from this
  subsystem.

## Semantic and deterministic resolution

Deterministic parsing first establishes source, target, precedence, scope markers, content digest,
encoding, newline style, and authority. Optional semantic analysis runs only after an explicit
Analyze action or when learning is enabled. The background scheduler analyzes at most one complete,
new or changed environment per bounded poll and does nothing while learning is disabled or consent
is expired. It uses fresh, tool-free, network-denied
`gpt-5.6-luna` Codex contexts through saved ChatGPT authentication. Results are schema-bound,
evidence-bound, and cached encrypted by source, prompt, interpreter, and schema digests.

Exact duplicates are omitted deterministically. Semantic equivalence or contradiction requires two
independent passes to agree at the policy threshold. Disagreement remains unknown. Project-policy
contradictions with approved Temper behavior withhold only the affected Temper clause and surface a
conflict; unknown relations preserve the approved clause but mark the plan not fully optimized.
Skills are observed as capabilities and are not assumed active projection coverage merely because
their `SKILL.md` exists.

The runtime manifest records the target/surface contract, environment and source-chain digests,
included clauses, omitted clauses with native coverage lineage, blocked clauses, relation digests,
and final target-visible size. Managed delivery rehashes native sources and refuses stale deltas.
No model runs in the hook or delivery path.

## Governed native writeback

Native files never change automatically. A write uses the exact source digest, environment digest,
application snapshot digest, target, opaque preview token, and idempotency key. The preview shows an
exact diff. Application uses an atomic replacement, verifies the resulting digest, stores an
encrypted exact-byte backup outside the repository, and appends a signed receipt. Receipt and
idempotency state survive engine restart; tampering fails closed. Rollback is available for 30 days
and restores the original bytes exactly.

Temper writes only a marked Temper-managed Markdown section. It can update or remove only content it
previously wrote. If an exact safe anchor or byte-preserving edit is unavailable, no mutation is
offered. Skill writeback is limited to previewed Markdown/metadata and never creates scripts or
changes permissions, dependencies, hooks, plugins, or MCP configuration.

## Product surfaces

- **Connections** reports source/skill counts and understood, changed, incomplete, or conflicting
  status per registered project and target. Personal inspection has a separate preview/opt-in.
- **Core / Also considered** separates approved Temper knowledge from project instructions,
  agent-native memory, and skills. Skill availability is labeled active, available, disabled, or
  unknown rather than guessed.
- **Today** shows only unresolved blocking native conflicts that need action; ordinary source lists
  stay out of the daily view.
- **Modes** displays the existing source count, candidate Mode bytes, known blocking conflicts, and
  the promise to rehash/minimize the final delta immediately before launch. It does not claim a
  Mode clause is already covered before that comparison exists.
- **All projects** aggregates status rows but never merges clauses, authority, or applicability
  across project boundaries.

## Verification boundary

Unit coverage includes native precedence, empty overrides, configured fallbacks, scoped rules,
disabled skills, build-directory exclusion, source limits, encoding, traversal and symlink escape,
semantic agreement/disagreement, conflict isolation, projection omission lineage, stale delivery,
preview races, signed receipt replay/tampering, atomic restore, CRLF/BOM/frontmatter preservation,
restart-safe rollback, strict protocol methods, and raw-free UI models. Codex predictions are also
checked against live `instructionSources` before any managed task is sent.

Read-only dogfood may inspect Kairn and Green Meadow without changing either repository. Native
writeback is validated only in disposable synthetic repositories until separately enabled for a
registered real project.

The 2026-08-28 read-only audit observed Green Meadow as 1 Codex source/3 clauses, 1 Claude
source/1 clause, and 2 Copilot sources/4 clauses. It observed Kairn as 1 Codex source/24 clauses,
no Claude source, and 1 Copilot source/24 clauses. Every environment was complete, personal roots
were disabled, model-call and native-write counts were zero, and Git status was byte-for-byte
unchanged before and after both audits. These counts validate deterministic discovery only; they
do not claim semantic equivalence or product effectiveness.

Final local verification passed locked Python and frontend dependency synchronization, Ruff
formatting and linting over 781 files, strict mypy over 395 source files, 1,091 Python tests with
two expected platform-specific skips, source/wheel builds, React formatting/lint/typechecking,
64 React unit/component tests, 39 product and visual browser tests, nine Windows WebView2
accessibility/compatibility tests, Rust formatting and Clippy, and 13 Rust unit tests. The
temporary Linux verification environment was removed after the run.

GitHub Actions run
[`33212995804`](https://github.com/HydroAcrid/adaptation-compiler-lab/actions/runs/33212995804)
could not provide independent hosted-runner evidence: every direct job ended without executing a
single step because the account's Actions budget was exhausted, and both dependent clean-runner
smokes were skipped. This is recorded as unavailable instrumentation, not as a passing or failing
product test. The successful local gates above remain the evidence for this milestone.

## Remaining boundary

This milestone does not make native files personal learning, implement ambient delivery into
arbitrary agent chats, install integrations, execute skills, or authorize broad automatic
promotion. Claude and Copilot remain discovery-only where their target delivery is unavailable.
Public installer readiness still depends on the separate clean-machine and signing gates.
