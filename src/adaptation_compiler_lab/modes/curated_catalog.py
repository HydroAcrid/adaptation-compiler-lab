"""Pinned, permissively licensed candidates in Temper's offline curated Modes catalog."""

# ruff: noqa: E501 -- curated behavioral clauses are intentionally readable source records.

from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib.resources import files
from typing import Literal

from adaptation_compiler_lab.modes.foundry_models import (
    CapabilityResourceKind,
    CapabilityResourceV1,
    CatalogEvaluationStatus,
    CuratedCatalogManifestV1,
    CuratedModeReleaseV1,
    CuratedSourceManifestV1,
    ModeComponentV1,
    SourceCapabilityRequirementV1,
    SourceReviewStatus,
    SourceReviewV1,
)
from adaptation_compiler_lab.modes.models import (
    CapabilityMode,
    ModeClause,
    ModeClauseCategory,
    ModeEvaluationStatus,
    ModeTargetCompatibility,
)

_PINNED_AT = datetime(2026, 9, 5, 21, 0, tzinfo=UTC)
_INVENTORY = json.loads(
    files("adaptation_compiler_lab.modes")
    .joinpath("data/source_inventory_v1.json")
    .read_text(encoding="utf-8")
)


def _resource_inventory(source_id: str) -> tuple[CapabilityResourceV1, ...]:
    match = next(
        (item for item in _INVENTORY["verified"] if item["source_id"] == source_id),
        None,
    )
    if match is None:
        raise ValueError("the curated source inventory is incomplete")
    return tuple(
        CapabilityResourceV1.model_validate({**item, "kind": CapabilityResourceKind(item["kind"])})
        for item in match["resources"]
    )


def _source(
    *,
    source_id: str,
    publisher: str,
    repository_url: str,
    commit_sha: str,
    source_path: str,
    source_format: Literal["agent-skill", "codex-plugin-skill", "claude-skill"],
    source_digest: str,
    license_spdx: str,
    license_locator: str,
    license_digest: str,
    requirements: tuple[SourceCapabilityRequirementV1, ...] = (),
) -> CuratedSourceManifestV1:
    return CuratedSourceManifestV1(
        source_id=source_id,
        publisher=publisher,
        repository_url=repository_url,
        commit_sha=commit_sha,
        source_path=source_path,
        source_format=source_format,
        source_digest=f"sha256:{source_digest}",
        license_spdx=license_spdx,
        license_locator=license_locator,
        license_digest=f"sha256:{license_digest}",
        redistribution_permitted=True,
        retrieved_at=_PINNED_AT,
        resources=_resource_inventory(source_id),
        requirements=requirements,
    )


OPENAI_FRONTEND_SOURCE = _source(
    source_id="openai-frontend-app-builder",
    publisher="OpenAI",
    repository_url="https://github.com/openai/plugins",
    commit_sha="1e285826e604f66f7208f7ac4dba0fe8341d1f57",
    source_path="plugins/build-web-apps/skills/frontend-app-builder/SKILL.md",
    source_format="codex-plugin-skill",
    source_digest="9273de02827b29534be28fb2b37154c1571ac38b4e20d3ef5482b7e22af67394",
    license_spdx="MIT",
    license_locator="plugins/build-web-apps/.codex-plugin/plugin.json#license",
    license_digest="7bc0085538adf72c31b5c2b42410fe699e6fe15e382fdc309cfd973c4c5db9a0",
    requirements=(
        SourceCapabilityRequirementV1(
            requirement_id="openai-browser-inspection",
            kind="provider_tool",
            name="Browser inspection",
            required=False,
            portable=False,
            rationale="The upstream workflow can use browser tooling; Temper never grants it.",
        ),
        SourceCapabilityRequirementV1(
            requirement_id="openai-image-generation",
            kind="provider_tool",
            name="Image generation",
            required=False,
            portable=False,
            rationale="The upstream workflow can use image generation; the portable Mode omits it.",
        ),
    ),
)

GITHUB_FRONTEND_SOURCE = _source(
    source_id="github-premium-frontend-ui",
    publisher="GitHub community catalog",
    repository_url="https://github.com/github/awesome-copilot",
    commit_sha="7b1ebe6333397841ca918dec904d24d4695fe953",
    source_path="skills/premium-frontend-ui/SKILL.md",
    source_format="agent-skill",
    source_digest="b7edf35b33931d15ea0c1d271f3c05d469e2b6923ed4df1c955d4da86287d9fb",
    license_spdx="MIT",
    license_locator="LICENSE",
    license_digest="e32449d23085399adc1222f7a17408b730550258e51627c153cb108ca9955823",
)

SUPERPOWERS_DEBUG_SOURCE = _source(
    source_id="superpowers-systematic-debugging",
    publisher="Jesse Vincent / obra",
    repository_url="https://github.com/obra/superpowers",
    commit_sha="b36e0829c6d0140e93cfef2ca599b1b07d4a7797",
    source_path="skills/systematic-debugging/SKILL.md",
    source_format="agent-skill",
    source_digest="808fc5717aa88ad65efff312b11c186294d3e6ee301afb584e2f86599b137787",
    license_spdx="MIT",
    license_locator="LICENSE",
    license_digest="a37e0e9697144819e1d965176ac4ae5bc3fa02d11e7812036bbcadf6dafe2400",
)

SUPERPOWERS_VERIFY_SOURCE = _source(
    source_id="superpowers-verification-before-completion",
    publisher="Jesse Vincent / obra",
    repository_url="https://github.com/obra/superpowers",
    commit_sha="b36e0829c6d0140e93cfef2ca599b1b07d4a7797",
    source_path="skills/verification-before-completion/SKILL.md",
    source_format="agent-skill",
    source_digest="2befe7fc55bcadaa3d97dd9e8efeb633d2561c0ebe74c5a8b17c4d9e7e4520b3",
    license_spdx="MIT",
    license_locator="LICENSE",
    license_digest="a37e0e9697144819e1d965176ac4ae5bc3fa02d11e7812036bbcadf6dafe2400",
)

GITHUB_SECURITY_SOURCE = _source(
    source_id="github-security-review",
    publisher="GitHub community catalog",
    repository_url="https://github.com/github/awesome-copilot",
    commit_sha="7b1ebe6333397841ca918dec904d24d4695fe953",
    source_path="skills/security-review/SKILL.md",
    source_format="agent-skill",
    source_digest="002392d88637b89e4cbc409a0531834970937f3b57c0b448a17e04b5ca6d356c",
    license_spdx="MIT",
    license_locator="LICENSE",
    license_digest="e32449d23085399adc1222f7a17408b730550258e51627c153cb108ca9955823",
)

ANTHROPIC_VULN_SOURCE = _source(
    source_id="anthropic-read-only-vulnerability-scan",
    publisher="Anthropic",
    repository_url="https://github.com/anthropics/defending-code-reference-harness",
    commit_sha="d3bea6b5793b5f3d59a75ebe69a58efa88383145",
    source_path=".claude/skills/vuln-scan/SKILL.md",
    source_format="claude-skill",
    source_digest="49e44d80ef199e695cae11801bb4f38d5efc15bcd7e5b5522116c977c77e2405",
    license_spdx="Apache-2.0",
    license_locator="LICENSE",
    license_digest="c18f8a7d5d8278d44045405023c1465a135f13ae5a4ac3764a8ce42f73ddec81",
    requirements=(
        SourceCapabilityRequirementV1(
            requirement_id="anthropic-parallel-review",
            kind="subagent",
            name="Parallel review agents",
            required=False,
            portable=False,
            rationale="The portable read-only Mode uses one agent and grants no subagent capability.",
        ),
        SourceCapabilityRequirementV1(
            requirement_id="anthropic-report-write",
            kind="filesystem_write",
            name="Finding report output",
            required=False,
            portable=True,
            rationale="Writing a report is optional and remains within the managed task workspace.",
        ),
    ),
)


def _review(source: CuratedSourceManifestV1, review_id: str, *findings: str) -> SourceReviewV1:
    return SourceReviewV1(
        review_id=review_id,
        source_manifest_digest=source.content_digest,
        status=SourceReviewStatus.REVIEWED,
        license_verified=True,
        provenance_verified=True,
        declarative_only=True,
        static_safety_passed=True,
        findings=tuple(findings),
        reviewed_at=_PINNED_AT,
    )


FRONTEND_SOURCE_REVIEWS = (
    _review(
        GITHUB_FRONTEND_SOURCE,
        "review-github-premium-frontend-ui",
        "Universal animation and visual-style mandates were excluded as over-broad defaults.",
    ),
    _review(
        OPENAI_FRONTEND_SOURCE,
        "review-openai-frontend-app-builder",
        "Provider-specific image generation and browser assumptions were excluded.",
        "Credential terminology was observed; every key and provider-setup direction was omitted.",
    ),
)

DEBUG_SOURCE_REVIEWS = (
    _review(
        SUPERPOWERS_DEBUG_SOURCE,
        "review-superpowers-systematic-debugging",
        "Global mandatory orchestration language was narrowed to debugging tasks.",
        "Credential terminology and a script were observed; no credential action or executable resource was admitted.",
    ),
    _review(
        SUPERPOWERS_VERIFY_SOURCE,
        "review-superpowers-verification-before-completion",
        "Verification remains bounded by the task and available execution surface.",
    ),
)

SECURITY_SOURCE_REVIEWS = (
    _review(
        ANTHROPIC_VULN_SOURCE,
        "review-anthropic-read-only-vulnerability-scan",
        "Subagent and command assumptions were removed from the portable projection.",
    ),
    _review(
        GITHUB_SECURITY_SOURCE,
        "review-github-security-review",
        "Patch generation was separated from the default read-only review workflow.",
        "Credential and egress terminology describes risks to identify, not authority to access secrets or transmit data.",
    ),
)


FRONTEND_STUDIO_CURATED_MODE = CapabilityMode(
    mode_schema_version="1.2.0",
    mode_id="curated-frontend-studio",
    mode_version="1.0.0",
    name="Frontend Studio",
    summary="Purpose-led frontend design with responsive implementation and visual verification.",
    publisher="Temper Curated",
    source_revision="catalog-1.0.0",
    source_license="MIT sources; attribution included",
    source_kind="curated",
    applicable_task_classes=("design_system", "frontend_design", "frontend_implementation"),
    compatible_target_families=("claude-code", "codex"),
    target_compatibility=(
        ModeTargetCompatibility(
            target_family="codex",
            version_constraint="0.153.1",
            delivery_surface="temper-managed-task",
        ),
    ),
    clauses=tuple(
        sorted(
            (
                ModeClause(
                    clause_id="curated-frontend-brief",
                    claim_key="frontend.brief",
                    category=ModeClauseCategory.WORKFLOW,
                    text="Derive the interface's audience, primary job, real content, and constraints before choosing a visual direction.",
                    source_component_ids=("frontend-purpose-process",),
                ),
                ModeClause(
                    clause_id="curated-frontend-concept",
                    claim_key="frontend.concept",
                    category=ModeClauseCategory.VISUAL_DIRECTION,
                    text="Choose one subject-specific visual concept and a compact color, type, spacing, and motion system; reject choices that could fit any product.",
                    source_component_ids=("frontend-purpose-process",),
                ),
                ModeClause(
                    clause_id="curated-frontend-hierarchy",
                    claim_key="frontend.hierarchy",
                    category=ModeClauseCategory.DESIGN_SYSTEM,
                    text="Use typography, alignment, density, and structural devices to communicate hierarchy; decoration must encode meaning or be removed.",
                    source_component_ids=("frontend-craft",),
                ),
                ModeClause(
                    clause_id="curated-frontend-product-copy",
                    claim_key="frontend.product-copy",
                    category=ModeClauseCategory.DESIGN_SYSTEM,
                    text="Write interface copy from the user's perspective with plain, truthful action labels and no filler or invented success state.",
                    source_component_ids=("frontend-purpose-process",),
                ),
                ModeClause(
                    clause_id="curated-frontend-responsive",
                    claim_key="frontend.responsive",
                    category=ModeClauseCategory.RESPONSIVE,
                    text="Deliberately verify narrow and wide layouts, overflow, touch targets, content density, and mobile degradation.",
                    source_component_ids=("frontend-craft",),
                ),
                ModeClause(
                    clause_id="curated-frontend-states",
                    claim_key="frontend.states",
                    category=ModeClauseCategory.WORKFLOW,
                    text="Implement only the loading, empty, error, populated, disabled, focus, and success states the real feature can enter.",
                    source_component_ids=("frontend-purpose-process",),
                ),
                ModeClause(
                    clause_id="curated-frontend-accessibility",
                    claim_key="frontend.accessibility",
                    category=ModeClauseCategory.ACCESSIBILITY,
                    text="Keep interactions keyboard reachable, visibly focused, contrast-safe, screen-reader labeled, and respectful of reduced motion.",
                    source_component_ids=("frontend-craft",),
                ),
                ModeClause(
                    clause_id="curated-frontend-verify",
                    claim_key="frontend.verify",
                    category=ModeClauseCategory.VALIDATION,
                    text="Inspect the rendered result at relevant sizes and run bounded checks; distinguish what was observed from what remains unverified.",
                    source_component_ids=("frontend-purpose-process",),
                ),
            ),
            key=lambda item: (item.claim_key, item.clause_id),
        )
    ),
    maximum_projection_utf8_bytes=4_000,
    evaluation_status=ModeEvaluationStatus.CURATED_UNPROVEN,
)


SYSTEMATIC_DEBUGGER_MODE = CapabilityMode(
    mode_schema_version="1.2.0",
    mode_id="curated-systematic-debugger",
    mode_version="1.0.0",
    name="Systematic Debugger",
    summary="Evidence-first debugging that reproduces, isolates, repairs, and verifies the actual failure.",
    publisher="Temper Curated",
    source_revision="catalog-1.0.0",
    source_license="MIT",
    source_kind="curated",
    applicable_task_classes=("debugging", "incident_analysis", "test_failure"),
    compatible_target_families=("claude-code", "codex"),
    target_compatibility=(
        ModeTargetCompatibility(
            target_family="codex",
            version_constraint="0.153.1",
            delivery_surface="temper-managed-task",
        ),
    ),
    clauses=tuple(
        sorted(
            (
                ModeClause(
                    clause_id="debug-reproduce",
                    claim_key="debug.reproduce",
                    category=ModeClauseCategory.FAILURE_HANDLING,
                    text="Reproduce the reported behavior and record the exact observed failure before changing code; if it is intermittent, state that and preserve evidence.",
                    source_component_ids=("debug-root-cause",),
                ),
                ModeClause(
                    clause_id="debug-boundaries",
                    claim_key="debug.boundaries",
                    category=ModeClauseCategory.EVIDENCE,
                    text="Trace inputs and outputs across the smallest relevant component boundaries until the first incorrect state is identified.",
                    source_component_ids=("debug-root-cause",),
                ),
                ModeClause(
                    clause_id="debug-hypothesis",
                    claim_key="debug.hypothesis",
                    category=ModeClauseCategory.WORKFLOW,
                    text="Form one falsifiable root-cause hypothesis from the evidence and test it with the smallest discriminating check.",
                    source_component_ids=("debug-root-cause",),
                ),
                ModeClause(
                    clause_id="debug-one-fix",
                    claim_key="debug.one-fix",
                    category=ModeClauseCategory.WORKFLOW,
                    text="Make one focused repair for the confirmed cause; do not bundle unrelated cleanup or symptom workarounds.",
                    source_component_ids=("debug-root-cause",),
                ),
                ModeClause(
                    clause_id="debug-rediagnose",
                    claim_key="debug.rediagnose",
                    category=ModeClauseCategory.FAILURE_HANDLING,
                    text="If the repair fails, return to the live evidence and revise the diagnosis instead of stacking another speculative fix.",
                    source_component_ids=("debug-root-cause",),
                ),
                ModeClause(
                    clause_id="debug-verify-focused",
                    claim_key="debug.verify-focused",
                    category=ModeClauseCategory.VALIDATION,
                    text="After the repair, rerun the focused reproduction and inspect its current output before claiming the defect is resolved.",
                    source_component_ids=("debug-current-verification",),
                ),
                ModeClause(
                    clause_id="debug-verify-regression",
                    claim_key="debug.verify-regression",
                    category=ModeClauseCategory.VALIDATION,
                    text="Run the bounded regression checks that cover the changed behavior and report failures, blockers, or unavailable checks honestly.",
                    source_component_ids=("debug-current-verification",),
                ),
            ),
            key=lambda item: (item.claim_key, item.clause_id),
        )
    ),
    maximum_projection_utf8_bytes=3_500,
    evaluation_status=ModeEvaluationStatus.CURATED_UNPROVEN,
)


READ_ONLY_SECURITY_REVIEW_MODE = CapabilityMode(
    mode_schema_version="1.2.0",
    mode_id="curated-read-only-security-review",
    mode_version="1.0.0",
    name="Read-only Security Review",
    summary="Bounded source review that traces trust boundaries and reports evidence-backed vulnerability candidates.",
    publisher="Temper Curated",
    source_revision="catalog-1.0.0",
    source_license="MIT and Apache-2.0 sources; attribution included",
    source_kind="curated",
    applicable_task_classes=("security_audit", "security_review", "threat_analysis"),
    compatible_target_families=("claude-code", "codex"),
    target_compatibility=(
        ModeTargetCompatibility(
            target_family="codex",
            version_constraint="0.153.1",
            delivery_surface="temper-managed-task",
        ),
    ),
    clauses=tuple(
        sorted(
            (
                ModeClause(
                    clause_id="security-scope",
                    claim_key="security.scope",
                    category=ModeClauseCategory.THREAT_MODEL,
                    text="Define the review boundary, protected assets, entry points, trust boundaries, and attacker-controlled inputs before listing findings.",
                    source_component_ids=("security-data-flow",),
                ),
                ModeClause(
                    clause_id="security-data-flow",
                    claim_key="security.data-flow",
                    category=ModeClauseCategory.SECURITY,
                    text="Trace untrusted data across files to sensitive sinks, authorization decisions, secret handling, cryptography, and dependency boundaries.",
                    source_component_ids=("security-data-flow",),
                ),
                ModeClause(
                    clause_id="security-read-only",
                    claim_key="security.read-only",
                    category=ModeClauseCategory.DATA_PROTECTION,
                    text="Inspect only the authorized source tree; do not execute target code, access the network, follow escaping symlinks, or modify product files.",
                    source_component_ids=("security-read-only-workflow",),
                ),
                ModeClause(
                    clause_id="security-evidence",
                    claim_key="security.evidence",
                    category=ModeClauseCategory.EVIDENCE,
                    text="Tie each candidate to inspected code and an explicit exploit path; never invent file locations, line numbers, sanitization, or reachability.",
                    source_component_ids=("security-read-only-workflow",),
                ),
                ModeClause(
                    clause_id="security-self-check",
                    claim_key="security.self-check",
                    category=ModeClauseCategory.VALIDATION,
                    text="Recheck each candidate for upstream validation, framework guarantees, unreachable paths, and duplicate root causes before assigning severity.",
                    source_component_ids=("security-data-flow",),
                ),
                ModeClause(
                    clause_id="security-report",
                    claim_key="security.report",
                    category=ModeClauseCategory.ACCURACY,
                    text="Separate verified facts from static-review candidates and report severity, confidence, evidence, impact, and a focused remediation direction.",
                    source_component_ids=("security-read-only-workflow",),
                ),
                ModeClause(
                    clause_id="security-no-autofix",
                    claim_key="security.no-autofix",
                    category=ModeClauseCategory.DATA_PROTECTION,
                    text="Do not apply patches during the review; proposed changes require a separate explicit user request and normal project policy.",
                    source_component_ids=("security-data-flow",),
                ),
            ),
            key=lambda item: (item.claim_key, item.clause_id),
        )
    ),
    maximum_projection_utf8_bytes=3_700,
    evaluation_status=ModeEvaluationStatus.CURATED_UNPROVEN,
)


def _component(
    component_id: str,
    source: CuratedSourceManifestV1,
    locator: str,
    output_clause_ids: tuple[str, ...],
    rationale: str,
    *,
    disposition: Literal["adapted", "adopted", "omitted"] = "adapted",
) -> ModeComponentV1:
    return ModeComponentV1(
        component_id=component_id,
        source_id=source.source_id,
        source_manifest_digest=source.content_digest,
        source_locator=locator,
        disposition=disposition,
        output_clause_ids=output_clause_ids,
        rationale=rationale,
    )


FRONTEND_RELEASE = CuratedModeReleaseV1(
    release_id="release-curated-frontend-studio-1",
    mode=FRONTEND_STUDIO_CURATED_MODE,
    source_manifests=(GITHUB_FRONTEND_SOURCE, OPENAI_FRONTEND_SOURCE),
    source_reviews=FRONTEND_SOURCE_REVIEWS,
    components=(
        _component(
            "frontend-craft",
            GITHUB_FRONTEND_SOURCE,
            "creative foundation, performance, responsive degradation, and accessibility",
            (
                "curated-frontend-accessibility",
                "curated-frontend-hierarchy",
                "curated-frontend-responsive",
            ),
            "Retain useful craft and performance constraints without prescribing one aesthetic.",
        ),
        _component(
            "frontend-purpose-process",
            OPENAI_FRONTEND_SOURCE,
            "core standard, real surface, design system, and browser verification",
            (
                "curated-frontend-brief",
                "curated-frontend-concept",
                "curated-frontend-product-copy",
                "curated-frontend-states",
                "curated-frontend-verify",
            ),
            "Preserve the purpose-led build-and-inspect workflow without provider-specific tools.",
        ),
        _component(
            "frontend-universal-effects-omitted",
            GITHUB_FRONTEND_SOURCE,
            "mandatory preloaders, parallax, custom cursors, glass, and animation libraries",
            (),
            "Universal effects conflict with subject-specific design and can regress accessibility.",
            disposition="omitted",
        ),
    ),
    evaluation_status=CatalogEvaluationStatus.CURATED_UNPROVEN,
    known_limitations=(
        "No image generation or browser tool is granted by this Mode.",
        "Its current status proves curation and conformance, not task-performance uplift.",
    ),
    released_at=_PINNED_AT,
)

DEBUG_RELEASE = CuratedModeReleaseV1(
    release_id="release-curated-systematic-debugger-1",
    mode=SYSTEMATIC_DEBUGGER_MODE,
    source_manifests=(SUPERPOWERS_DEBUG_SOURCE, SUPERPOWERS_VERIFY_SOURCE),
    source_reviews=DEBUG_SOURCE_REVIEWS,
    components=(
        _component(
            "debug-current-verification",
            SUPERPOWERS_VERIFY_SOURCE,
            "fresh evidence before completion claims",
            ("debug-verify-focused", "debug-verify-regression"),
            "Retain current-result verification while keeping the check set task-bounded.",
        ),
        _component(
            "debug-root-cause",
            SUPERPOWERS_DEBUG_SOURCE,
            "root-cause investigation, hypothesis, repair, and re-diagnosis",
            (
                "debug-boundaries",
                "debug-hypothesis",
                "debug-one-fix",
                "debug-rediagnose",
                "debug-reproduce",
            ),
            "Adapt the evidence-first workflow to debugging tasks rather than every interaction.",
        ),
    ),
    evaluation_status=CatalogEvaluationStatus.CURATED_UNPROVEN,
    known_limitations=(
        "The upstream framework's global mandatory orchestration is intentionally excluded.",
        "Its current status proves curation and conformance, not task-performance uplift.",
    ),
    released_at=_PINNED_AT,
)

SECURITY_RELEASE = CuratedModeReleaseV1(
    release_id="release-curated-read-only-security-review-1",
    mode=READ_ONLY_SECURITY_REVIEW_MODE,
    source_manifests=(ANTHROPIC_VULN_SOURCE, GITHUB_SECURITY_SOURCE),
    source_reviews=SECURITY_SOURCE_REVIEWS,
    components=(
        _component(
            "security-data-flow",
            GITHUB_SECURITY_SOURCE,
            "scope, data-flow review, self-verification, and remediation proposals",
            (
                "security-data-flow",
                "security-no-autofix",
                "security-scope",
                "security-self-check",
            ),
            "Keep data-flow reasoning and self-verification while separating patch application.",
        ),
        _component(
            "security-read-only-workflow",
            ANTHROPIC_VULN_SOURCE,
            "read-only constraints, evidence discipline, and candidate reporting",
            ("security-evidence", "security-read-only", "security-report"),
            "Keep bounded static review without subagents, shell execution, or network access.",
        ),
    ),
    evaluation_status=CatalogEvaluationStatus.CURATED_UNPROVEN,
    known_limitations=(
        "Findings are static-review candidates, not exploit-confirmed vulnerabilities.",
        "The portable Mode omits parallel subagents and execution-based validation.",
    ),
    released_at=_PINNED_AT,
)

CURATED_MODE_RELEASES = (FRONTEND_RELEASE, SECURITY_RELEASE, DEBUG_RELEASE)
CURATED_MODE_CATALOG = tuple(item.mode for item in CURATED_MODE_RELEASES)

CURATED_CATALOG = CuratedCatalogManifestV1(
    catalog_id="temper-curated-modes",
    release_version="1.0.0",
    releases=CURATED_MODE_RELEASES,
    generated_at=_PINNED_AT,
)


def curated_release_by_mode_id(mode_id: str) -> CuratedModeReleaseV1 | None:
    return next((item for item in CURATED_MODE_RELEASES if item.mode.mode_id == mode_id), None)
