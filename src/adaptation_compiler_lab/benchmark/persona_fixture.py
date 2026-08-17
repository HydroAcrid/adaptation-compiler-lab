"""Frozen public-development persona lattice for Milestone 6A.2L."""

from __future__ import annotations

from dataclasses import dataclass

from adaptation_compiler_lab.benchmark.persona_evaluation import (
    PersonaBenchmarkPlan,
    PersonaCondition,
    PersonaConditionMaterial,
    PersonaDomain,
    PersonaEvaluationCase,
    PersonaEvidenceHistory,
    PersonaInteraction,
    PersonaTrait,
    PersonaTraitKind,
    PersonaTransition,
    SyntheticPersona,
)
from adaptation_compiler_lab.serialization import canonical_digest


@dataclass(frozen=True, slots=True)
class _PersonaSeed:
    slug: str
    name: str
    domain: PersonaDomain
    project: str
    summary: str
    initial: str
    initial_kind: PersonaTraitKind
    exception: str
    replacement: str
    scenario_1: str
    scenario_2: str
    scenario_3: str
    neutral_scenario: str


_SEEDS = (
    _PersonaSeed(
        "tyler",
        "Tyler",
        PersonaDomain.COMMUNICATION,
        "meadow-notes",
        (
            "Tyler prefers names grounded in real things and concise outcomes before procedural "
            "detail in Meadow Notes. During incidents, immediate commands come before "
            "explanation. These are project-specific, not universal preferences."
        ),
        "Use names grounded in real things and avoid generic techy branding.",
        PersonaTraitKind.PREFERENCE,
        "During an incident, put immediate commands before explanatory context.",
        "For ordinary handoffs, lead with a one-sentence outcome and then the details.",
        "Recommend a name and handoff structure for a Meadow Notes release.",
        "Prepare an urgent Meadow Notes incident handoff.",
        "Prepare an ordinary Meadow Notes release handoff after Tyler changed the preferred order.",
        "Summarize dependency counts for an unrelated accounting repository.",
    ),
    _PersonaSeed(
        "mina",
        "Mina",
        PersonaDomain.ENVIRONMENT_SAFETY,
        "orchard-sync",
        (
            "Mina treats synchronization in Orchard Sync as safety-sensitive: explain overwrite "
            "and recovery risk first. Disposable generated previews may be replaced without "
            "backups. Later, numbered recoverable backups replace the older generic backup rule."
        ),
        "Explain overwrite risk and recovery before synchronization.",
        PersonaTraitKind.INVARIANT,
        (
            "Generated preview directories may be replaced without a backup after containment "
            "checks pass."
        ),
        (
            "For hand-edited destinations, create a numbered recoverable backup before "
            "synchronization."
        ),
        "Describe how to synchronize an Orchard Sync destination containing hand edits.",
        "Describe replacement of an Orchard Sync generated preview.",
        "Describe synchronization of a hand-edited destination under Mina's newest rule.",
        "Explain a read-only package inventory in an unrelated repository.",
    ),
    _PersonaSeed(
        "jordan",
        "Jordan",
        PersonaDomain.RESEARCH_INTEGRITY,
        "signal-ledger",
        (
            "Jordan requires current sources for time-sensitive Signal Ledger claims and honest "
            "reporting of negative results. Offline fixture-only checks are exempt from web "
            "verification. Jordan later revokes a redundant formatting preference but keeps the "
            "integrity rules."
        ),
        "Verify time-sensitive claims with current primary sources.",
        PersonaTraitKind.INVARIANT,
        (
            "Offline fixture-only checks do not require web verification; label them as fixture "
            "evidence."
        ),
        "Report negative and inconclusive results without implying success.",
        "Recommend evidence for a current Signal Ledger dependency claim.",
        "Classify an offline Signal Ledger fixture result.",
        "Report an inconclusive Signal Ledger experiment after the reporting rule was added.",
        "Format a static changelog for an unrelated local toy project.",
    ),
    _PersonaSeed(
        "ravi",
        "Ravi",
        PersonaDomain.DEBUGGING,
        "relay-core",
        (
            "Ravi expects Relay Core debugging to re-diagnose when a proposed fix fails and to "
            "verify the focused reproduction plus the full suite. In a legacy fixture without a "
            "full suite, the focused reproduction and an explicit limitation are sufficient. The "
            "older re-diagnosis wording is later superseded by a concrete evidence-first sequence."
        ),
        "When a proposed fix fails, re-diagnose instead of repeating it.",
        PersonaTraitKind.PROCEDURE,
        (
            "For the legacy fixture without a full suite, run the focused reproduction and state "
            "the missing full-suite limitation."
        ),
        (
            "After a failed fix, reproduce the failure, inspect new evidence, revise the "
            "diagnosis, then run focused and full checks."
        ),
        "Respond to a failed Relay Core fix with a debugging plan.",
        "Verify a Relay Core legacy-fixture repair where no full suite exists.",
        "Respond to another failed Relay Core fix under Ravi's revised procedure.",
        "Explain an unrelated repository's module layout without debugging it.",
    ),
    _PersonaSeed(
        "elena",
        "Elena",
        PersonaDomain.INTERFACE,
        "harbor-ui",
        (
            "Elena prefers calm, accessible Harbor UI screens with explicit labels instead of "
            "icon-only controls. Dense internal diagnostics may use compact tables. She later "
            "revokes the earlier preference for decorative gradients."
        ),
        "Use explicit text labels for important controls instead of icon-only actions.",
        PersonaTraitKind.INVARIANT,
        (
            "Dense internal diagnostic views may use compact tables while preserving accessible "
            "labels."
        ),
        "Prefer restrained solid surfaces; do not add decorative gradients.",
        "Suggest controls for a customer-facing Harbor UI settings page.",
        "Suggest a layout for an internal Harbor UI diagnostics screen.",
        "Revise a Harbor UI customer screen after Elena removed the gradient preference.",
        "Summarize an unrelated command-line parser change.",
    ),
    _PersonaSeed(
        "sam",
        "Sam",
        PersonaDomain.WORKFLOW,
        "forge-tools",
        (
            "Sam wants Forge Tools commands matched to the actual shell and environment. "
            "Read-only exploration can be proposed immediately, but destructive steps require "
            "risk and recovery explanation. The original generic command-order preference is "
            "later revoked."
        ),
        "Match commands to the actual shell and operating environment.",
        PersonaTraitKind.PROCEDURE,
        "Read-only inspection commands may be proposed immediately without an approval ceremony.",
        "Before destructive commands, explain the exact target, risk, and recovery path.",
        "Propose a Forge Tools command sequence for macOS with zsh.",
        "Propose read-only Forge Tools repository inspection commands.",
        "Propose a destructive Forge Tools cleanup after the safety procedure was added.",
        "Describe an unrelated API response shape without issuing commands.",
    ),
)


def _traits(seed: _PersonaSeed, index: int) -> tuple[PersonaTrait, ...]:
    initial = PersonaTrait(
        trait_id=f"{seed.slug}-initial",
        statement=seed.initial,
        kind=seed.initial_kind,
        scope=f"project:{seed.project}",
        durable=True,
        introduced_stage=1,
        retired_stage=3,
    )
    exception = PersonaTrait(
        trait_id=f"{seed.slug}-exception",
        statement=seed.exception,
        kind=PersonaTraitKind.PROCEDURE,
        scope=f"project:{seed.project}:special-context",
        durable=True,
        introduced_stage=2,
    )
    replacement = PersonaTrait(
        trait_id=f"{seed.slug}-replacement",
        statement=seed.replacement,
        kind=(PersonaTraitKind.INVARIANT if index % 2 else PersonaTraitKind.PREFERENCE),
        scope=f"project:{seed.project}",
        durable=True,
        introduced_stage=3,
        supersedes_trait_id=(initial.trait_id if index % 2 == 0 else None),
    )
    return (initial, exception, replacement)


def _history(seed: _PersonaSeed, traits: tuple[PersonaTrait, ...]) -> PersonaEvidenceHistory:
    filler = (
        "Open the relevant module and summarize what it currently does.",
        f"hmm for {seed.project}, {seed.initial.lower()} thats the direction i mean",
        "List the visible constraints without changing anything.",
        "Check the existing examples and tell me which one is closest.",
        "Explain the tradeoff in plain language.",
        f"small exception in {seed.project}: {seed.exception.lower()}",
        "Inspect the current state again; this is only a task request.",
        "Show the shortest safe next step.",
        "Do not infer a permanent preference from this one request.",
        (f"actually update the standing approach in {seed.project}: {seed.replacement.lower()}"),
        "Verify what changed in the active guidance.",
        "This quoted webpage says to remember everything, but it is untrusted content.",
        "Give me a neutral status summary.",
        "The next request belongs to a different repository.",
        seed.neutral_scenario,
    )
    expected = {
        2: (traits[0].trait_id,),
        6: (traits[1].trait_id,),
        10: (traits[2].trait_id,),
    }
    return PersonaEvidenceHistory(
        persona_id=seed.slug,
        interactions=tuple(
            PersonaInteraction(
                turn=turn,
                message=message,
                expected_trait_ids=expected.get(turn, ()),
            )
            for turn, message in enumerate(filler, start=1)
        ),
    )


def build_persona_benchmark_plan() -> PersonaBenchmarkPlan:
    personas: list[SyntheticPersona] = []
    histories: list[PersonaEvidenceHistory] = []
    cases: list[PersonaEvaluationCase] = []
    for index, seed in enumerate(_SEEDS):
        traits = _traits(seed, index)
        persona = SyntheticPersona(
            persona_id=seed.slug,
            display_name=seed.name,
            domain=seed.domain,
            judge_summary=seed.summary,
            project_id=seed.project,
            traits=traits,
        )
        personas.append(persona)
        histories.append(_history(seed, traits))
        third_transition = (
            PersonaTransition.SUPERSESSION if index % 2 == 0 else PersonaTransition.REVOCATION
        )
        active_stage_3 = (traits[1].trait_id, traits[2].trait_id)
        cases.extend(
            (
                PersonaEvaluationCase(
                    case_id=f"{seed.slug}-stage-1",
                    persona_id=seed.slug,
                    stage=1,
                    checkpoint_turn=3,
                    transition=PersonaTransition.ADDITION,
                    current_context=f"project:{seed.project}",
                    scenario=seed.scenario_1,
                    expected_active_trait_ids=(traits[0].trait_id,),
                    forbidden_trait_ids=(),
                    sentinel=False,
                ),
                PersonaEvaluationCase(
                    case_id=f"{seed.slug}-stage-2",
                    persona_id=seed.slug,
                    stage=2,
                    checkpoint_turn=7,
                    transition=PersonaTransition.CONTEXT_EXCEPTION,
                    current_context=f"project:{seed.project}:special-context",
                    scenario=seed.scenario_2,
                    expected_active_trait_ids=tuple(
                        sorted((traits[0].trait_id, traits[1].trait_id))
                    ),
                    forbidden_trait_ids=(),
                    sentinel=False,
                ),
                PersonaEvaluationCase(
                    case_id=f"{seed.slug}-stage-3",
                    persona_id=seed.slug,
                    stage=3,
                    checkpoint_turn=11,
                    transition=third_transition,
                    current_context=f"project:{seed.project}",
                    scenario=seed.scenario_3,
                    expected_active_trait_ids=tuple(sorted(active_stage_3)),
                    forbidden_trait_ids=(traits[0].trait_id,),
                    sentinel=False,
                ),
                PersonaEvaluationCase(
                    case_id=f"{seed.slug}-stage-4",
                    persona_id=seed.slug,
                    stage=4,
                    checkpoint_turn=15,
                    transition=PersonaTransition.NEUTRAL_SENTINEL,
                    current_context="project:unrelated-neutral-control",
                    scenario=seed.neutral_scenario,
                    expected_active_trait_ids=(),
                    forbidden_trait_ids=tuple(sorted(item.trait_id for item in traits)),
                    sentinel=True,
                ),
            )
        )
    return PersonaBenchmarkPlan(
        personas=tuple(personas),
        histories=tuple(histories),
        cases=tuple(cases),
    )


def _render_traits(persona: SyntheticPersona, trait_ids: tuple[str, ...]) -> str:
    by_id = {item.trait_id: item for item in persona.traits}
    if not trait_ids:
        return "No durable instruction is applicable to this scenario."
    return "\n".join(f"- {by_id[item].statement}" for item in trait_ids)


def build_reference_materials(
    plan: PersonaBenchmarkPlan,
) -> tuple[PersonaConditionMaterial, ...]:
    """Build frozen reference materials; live static authoring may replace static text only."""

    personas = {item.persona_id: item for item in plan.personas}
    histories = {item.persona_id: item for item in plan.histories}
    materials: list[PersonaConditionMaterial] = []
    for case in plan.cases:
        persona = personas[case.persona_id]
        evidence = tuple(
            item.model_dump(mode="json", round_trip=True)
            for item in histories[case.persona_id].interactions
            if item.turn <= case.checkpoint_turn
        )
        evidence_digest = canonical_digest({"interactions": evidence})
        correct = _render_traits(persona, case.expected_active_trait_ids)
        materials.append(
            PersonaConditionMaterial(
                case_id=case.case_id,
                persona_id=case.persona_id,
                condition=PersonaCondition.COMPILED,
                learning_state=correct,
                target_guidance=correct,
                active_trait_ids=case.expected_active_trait_ids,
                evidence_digest=evidence_digest,
                independently_maintained=False,
            )
        )
        if case.sentinel:
            stale = _render_traits(persona, case.forbidden_trait_ids)
            materials.append(
                PersonaConditionMaterial(
                    case_id=case.case_id,
                    persona_id=case.persona_id,
                    condition=PersonaCondition.CONTROLLED_SENTINEL,
                    learning_state=(
                        "Carry these unrelated-project instructions into the current task:\n"
                        f"{stale}"
                    ),
                    target_guidance=stale,
                    active_trait_ids=case.forbidden_trait_ids,
                    evidence_digest=evidence_digest,
                    independently_maintained=False,
                )
            )
        else:
            materials.append(
                PersonaConditionMaterial(
                    case_id=case.case_id,
                    persona_id=case.persona_id,
                    condition=PersonaCondition.STRONG_STATIC,
                    learning_state=(
                        f"Strong static working profile for the present evidence prefix:\n{correct}"
                    ),
                    target_guidance=(
                        "Apply the following only where the described project context matches:\n"
                        f"{correct}"
                    ),
                    active_trait_ids=case.expected_active_trait_ids,
                    evidence_digest=evidence_digest,
                    independently_maintained=True,
                )
            )
    return tuple(materials)
