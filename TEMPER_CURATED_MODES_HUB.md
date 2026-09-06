# Temper Curated Modes Hub

Status: implemented development foundation; first three releases are curated and unproven.

## Purpose

Modes are temporary, task-scoped capabilities assembled from high-quality public agent skills. They are not permanent user memory and never mutate Temper Core. Temper's value is not copying a `SKILL.md`; it is pinning provenance, removing unsafe or irrelevant assumptions, resolving the result against Core and project policy, measuring it, and delivering only the useful delta for one task.

## First catalog

| Mode | Reviewed upstream material | License | Current evidence status |
| --- | --- | --- | --- |
| Frontend Studio | OpenAI `frontend-design`; GitHub `premium-frontend` | MIT | Curated, static conformance passed, comparative evaluation pending |
| Systematic Debugger | obra `systematic-debugging`; obra `verification-before-completion` | MIT | Curated, static conformance passed, comparative evaluation pending |
| Read-only Security Review | GitHub `security-review`; Anthropic `vuln-scan` | MIT and Apache-2.0 | Curated, static conformance passed, comparative evaluation pending |

Every source is bound to a full Git commit SHA, exact `SKILL.md` path, content digest, license digest, review record, and clause-level transformation lineage. The catalog is bundled offline and signed. The current signature is explicitly a development signature; it does not satisfy the future trusted external-release gate.

## Intake policy

The Foundry accepts canonical HTTPS GitHub repositories pinned to a full commit SHA. It reads one explicitly selected skill root and never runs repository code, hooks, setup commands, dependencies, tools, or MCP configuration.

Eligible material:

- Declarative instructions.
- References and examples.
- Static assets when independently useful and license-compatible.

Always quarantined:

- Scripts, hooks, binaries, dependencies, tools, plugins, MCP servers, and install instructions.
- Symlinks escaping the selected skill root.
- Invalid UTF-8 declarative files, oversized resources, or unbounded source trees.
- Provider-specific authority that Temper cannot safely reproduce.

Static scanning records suspicious capability assumptions such as credential access, egress, persistence, privilege, and encoded content. A signature proves origin and integrity, not quality or safety.

## Transformation policy

Upstream skills are source material, not runtime instructions. Each included or omitted component records its source locator and rationale. Temper may narrow an instruction to the Mode's task, remove universal mandates, omit tool assumptions, and preserve the underlying procedure. Every emitted clause must link to one or more exact source components.

Precedence remains:

1. Current user request.
2. Managed and project policy.
3. Approved Temper Core.
4. Personal Mode overlay.
5. Generic Mode defaults.
6. Agent-generated memory.

A Mode adds no permissions. Activation is previewed against one registered project and one task, then expires after that task even on failure. Native-instruction reconciliation may omit duplicate clauses or block conflicts before delivery.

## Catalog statuses

- `candidate`: discovered but not admitted.
- `reviewed`: provenance, license, declarative boundary, and static safety checks passed.
- `curated_unproven`: composed release passes schema and static conformance but has no valid comparative effectiveness result.
- `product_evaluated`: the exact release digest passed the frozen task comparison.
- `failed`: the exact release failed its product gate.
- `revoked`: the release must not activate.

The interface must never translate `curated_unproven` into “best,” “proven,” or “optimized.”

## Evaluation funnel

Evaluation is deliberately staged to avoid another expensive, ambiguous grid:

1. Static intake, license, provenance, size, capability, and projection checks.
2. Synthetic conformance and neutral-control tests.
3. Bounded same-agent screening comparing Core only, uncompiled upstream-safe instructions, and the compiled Mode on two diagnostic tasks plus one neutral control.
4. Only promising exact releases advance to fresh-task blinded comparison and longitudinal dogfood.

No Mode becomes product-evaluated merely because its upstream repository is popular. External popularity is a discovery signal, not Temper evidence. Agent-judged quality is secondary; objective task checks, scope isolation, forbidden-operation checks, and clean deactivation are primary.

Recent agent-skill benchmark results are a reason for the Foundry, not a marketing claim. Public skill repositories contain excellent workflows, but benchmark studies also report that many installed skills produce no improvement and some cause regressions. Temper therefore preserves the source while separately measuring the compiled release.

This milestone does not access or modify the sealed Milestone 6 study. It makes no cross-model transfer claim and uses no provider-billed call.
