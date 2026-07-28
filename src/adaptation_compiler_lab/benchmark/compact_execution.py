"""Typed execution records for the compact-projection subscription comparison."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from adaptation_compiler_lab.benchmark.codex_development import (
    CodexDevelopmentRunObservation,
)
from adaptation_compiler_lab.benchmark.compact_projection import (
    CompactProjectionComparisonDesign,
)
from adaptation_compiler_lab.benchmark.longitudinal_execution import (
    LongitudinalEvidencePacket,
    validate_static_profile,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.domain import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.serialization import canonical_digest

ProfileText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=40, max_length=12000),
]
RationaleText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=20, max_length=2000),
]


def is_interpreter_generated_path(path: str | None) -> bool:
    """Return whether a changed path is Python bytecode rather than agent work."""

    if path is None:
        return False
    parts = path.replace("\\", "/").split("/")
    return "__pycache__" in parts or path.endswith((".pyc", ".pyo"))


class CompactExecutionContract(FrozenModel):
    """Machine-validated identity and isolation settings frozen before live sessions."""

    contract_version: Literal["1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0", "1.5.0"] = "1.0.0"
    design_digest: Sha256Digest
    execution_protocol_digest: Sha256Digest
    cli_version: Literal["codex-cli 0.145.0"] = "codex-cli 0.145.0"
    cli_digest: Literal[
        "sha256:a2a05dafaa1acb002a45eaec0a462de5b13694fcfcd7bc43305f14781ce7be14"
    ] = "sha256:a2a05dafaa1acb002a45eaec0a462de5b13694fcfcd7bc43305f14781ce7be14"
    model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    reasoning_effort: Literal["medium"] = "medium"
    service_mode: Literal["standard"] = "standard"
    max_seconds: Literal[600] = 600
    authentication: Literal["saved_chatgpt"] = "saved_chatgpt"
    api_keys_allowed: Literal[False] = False
    provider_billed_calls: Literal[0] = 0
    maximum_subscription_sessions: Literal[7, 8, 9] = 9
    profile_author_sessions: Literal[0, 1] = 1
    profile_review_sessions: Literal[0, 1] = 1
    instrument_smoke_sessions: Literal[1] | None = None
    target_sessions: Literal[6] = 6
    judge_sessions: Literal[1] = 1
    target_sandbox: Literal[
        "workspace-write",
        "workspace-write-inside-read-only-outer-mount-namespace",
    ] = "workspace-write"
    target_outer_sandbox_digest: Sha256Digest | None = None
    target_workspace_policy: Literal[
        "workspace-writable",
        "workspace-read-only-except-registered-source-file",
    ] = "workspace-writable"
    target_runner_source_digest: Sha256Digest | None = None
    instrument_smoke_source_digest: Sha256Digest | None = None
    inherited_profile_receipt_digest: Sha256Digest | None = None
    target_web_search: Literal["disabled"] = "disabled"
    target_shell_environment_inherit: Literal["none"] = "none"
    target_ephemeral: Literal[True] = True
    target_user_config_ignored: Literal[True] = True
    target_rules_ignored: Literal[True] = True
    role_tools_allowed: Literal[False] = False
    role_outer_sandbox_digest: Literal[
        "sha256:d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
    ] = "sha256:d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
    sealed_external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def versioned_session_and_sandbox_contract_is_exact(self) -> Self:
        if self.contract_version == "1.0.0":
            if (
                self.maximum_subscription_sessions != 9
                or self.profile_author_sessions != 1
                or self.instrument_smoke_sessions is not None
                or self.target_sandbox != "workspace-write"
                or self.target_outer_sandbox_digest is not None
                or self.target_workspace_policy != "workspace-writable"
                or self.target_runner_source_digest is not None
                or self.instrument_smoke_source_digest is not None
                or self.inherited_profile_receipt_digest is not None
            ):
                raise ValueError("compact execution contract v1.0 settings drifted")
        elif self.contract_version in {"1.1.0", "1.2.0"} and (
            self.maximum_subscription_sessions != 8
            or self.profile_author_sessions != 0
            or self.profile_review_sessions != 1
            or self.instrument_smoke_sessions is not None
            or self.target_sandbox != "workspace-write-inside-read-only-outer-mount-namespace"
            or self.target_outer_sandbox_digest != self.role_outer_sandbox_digest
            or self.target_workspace_policy != "workspace-read-only-except-registered-source-file"
            or self.target_runner_source_digest is not None
            or self.instrument_smoke_source_digest is not None
            or self.inherited_profile_receipt_digest is not None
        ):
            raise ValueError("compact execution contract v1.1-v1.2 settings drifted")
        elif self.contract_version == "1.3.0" and (
            self.maximum_subscription_sessions != 7
            or self.profile_author_sessions != 0
            or self.profile_review_sessions != 0
            or self.instrument_smoke_sessions is not None
            or self.target_sandbox != "workspace-write-inside-read-only-outer-mount-namespace"
            or self.target_outer_sandbox_digest != self.role_outer_sandbox_digest
            or self.target_workspace_policy != "workspace-read-only-except-registered-source-file"
            or self.target_runner_source_digest is None
            or self.instrument_smoke_source_digest is not None
            or self.inherited_profile_receipt_digest is None
        ):
            raise ValueError("compact execution contract v1.3 settings drifted")
        elif self.contract_version == "1.4.0" and (
            self.maximum_subscription_sessions != 8
            or self.profile_author_sessions != 0
            or self.profile_review_sessions != 0
            or self.instrument_smoke_sessions != 1
            or self.target_sandbox != "workspace-write-inside-read-only-outer-mount-namespace"
            or self.target_outer_sandbox_digest != self.role_outer_sandbox_digest
            or self.target_workspace_policy != "workspace-read-only-except-registered-source-file"
            or self.target_runner_source_digest is None
            or self.instrument_smoke_source_digest is not None
            or self.inherited_profile_receipt_digest is None
        ):
            raise ValueError("compact execution contract v1.4 settings drifted")
        elif self.contract_version == "1.5.0" and (
            self.maximum_subscription_sessions != 8
            or self.profile_author_sessions != 0
            or self.profile_review_sessions != 0
            or self.instrument_smoke_sessions != 1
            or self.target_sandbox != "workspace-write-inside-read-only-outer-mount-namespace"
            or self.target_outer_sandbox_digest != self.role_outer_sandbox_digest
            or self.target_workspace_policy != "workspace-read-only-except-registered-source-file"
            or self.target_runner_source_digest is None
            or self.instrument_smoke_source_digest is None
            or self.inherited_profile_receipt_digest is None
        ):
            raise ValueError("compact execution contract v1.5 settings drifted")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        payload = self.model_dump(mode="json", round_trip=True)
        if self.instrument_smoke_sessions is None:
            payload.pop("instrument_smoke_sessions")
        if self.instrument_smoke_source_digest is None:
            payload.pop("instrument_smoke_source_digest")
        return canonical_digest(payload)


def load_compact_execution_contract(
    root: Path,
    *,
    design: CompactProjectionComparisonDesign,
) -> CompactExecutionContract:
    """Load the live contract and bind it to the exact design and protocol bytes."""

    contract_name = {
        "1.12.0": "EXECUTION_CONTRACT-v1.1.json",
        "1.13.0": "EXECUTION_CONTRACT-v1.1.json",
        "1.14.0": "EXECUTION_CONTRACT-v1.2.json",
        "1.15.0": "EXECUTION_CONTRACT-v1.3.json",
        "1.16.0": "EXECUTION_CONTRACT-v1.4.json",
        "1.17.0": "EXECUTION_CONTRACT-v1.5.json",
    }.get(design.design_version, "EXECUTION_CONTRACT-v1.0.json")
    contract = CompactExecutionContract.model_validate_json((root / contract_name).read_bytes())
    if contract.design_digest != design.content_digest:
        raise ValueError("compact execution contract design binding drifted")
    if contract.execution_protocol_digest != sha256_file(root / "EXECUTION_PROTOCOL.md"):
        raise ValueError("compact execution protocol binding drifted")
    if contract.maximum_subscription_sessions != design.maximum_subscription_sessions:
        raise ValueError("compact execution session budget drifted")
    if contract.profile_author_sessions != design.profile_author_sessions:
        raise ValueError("compact profile-author session budget drifted")
    if contract.profile_review_sessions != design.profile_review_sessions:
        raise ValueError("compact profile-review session budget drifted")
    if contract.instrument_smoke_sessions != design.instrument_smoke_sessions:
        raise ValueError("compact instrument-smoke session budget drifted")
    if contract.target_runner_source_digest is not None and (
        contract.target_runner_source_digest
        != sha256_file(
            root.parent / "src" / "adaptation_compiler_lab" / "runners" / "codex_subscription.py"
        )
    ):
        raise ValueError("compact target-runner source binding drifted")
    if contract.instrument_smoke_source_digest is not None and (
        contract.instrument_smoke_source_digest
        != sha256_file(root.parent / "scripts" / "run_compact_projection_live_smoke.py")
    ):
        raise ValueError("compact instrument-smoke source binding drifted")
    if contract.inherited_profile_receipt_digest is not None and (
        contract.inherited_profile_receipt_digest
        != sha256_file(root / "profile-remediation-receipt-v1.14.json")
    ):
        raise ValueError("compact inherited profile receipt binding drifted")
    return contract


class CompactProfileAuthorStage(FrozenModel):
    """One independently authored static profile stage."""

    stage: Annotated[int, Field(ge=1, le=3)]
    evidence_ids: tuple[Identifier, ...]
    profile_text: ProfileText
    change_summary: RationaleText
    intentional_edit_operations: int = Field(ge=1, le=100)

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("profile evidence IDs must be sorted and unique")
        return value


class CompactProfileAuthorOutput(FrozenModel):
    """All three static stages produced in the preregistered single author session."""

    output_version: Literal["1.0.0"] = "1.0.0"
    stages: Annotated[tuple[CompactProfileAuthorStage, ...], Field(min_length=3, max_length=3)]
    overall_strategy: RationaleText

    @model_validator(mode="after")
    def stages_are_exact(self) -> Self:
        if tuple(item.stage for item in self.stages) != (1, 2, 3):
            raise ValueError("profile author output must contain ordered stages 1, 2, and 3")
        return self


class CompactProfileReviewStage(FrozenModel):
    """One independently reviewed static profile stage."""

    stage: Annotated[int, Field(ge=1, le=3)]
    evidence_ids: tuple[Identifier, ...]
    approved_profile_text: ProfileText
    review_summary: RationaleText
    intentional_edit_operations: int = Field(ge=0, le=100)
    unsupported_content_removed: bool

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("review evidence IDs must be sorted and unique")
        return value


class CompactProfileReviewOutput(FrozenModel):
    """All three approved stages produced in the single reviewer session."""

    output_version: Literal["1.0.0"] = "1.0.0"
    stages: Annotated[tuple[CompactProfileReviewStage, ...], Field(min_length=3, max_length=3)]
    overall_review: RationaleText

    @model_validator(mode="after")
    def stages_are_exact(self) -> Self:
        if tuple(item.stage for item in self.stages) != (1, 2, 3):
            raise ValueError("profile review output must contain ordered stages 1, 2, and 3")
        return self


class CompactJudgePair(FrozenModel):
    """One condition-blind pairwise general-quality rating."""

    task_id: Identifier
    ordered_output_ids: tuple[Identifier, Identifier]
    preference: Literal["first_better", "second_better", "tie"]
    preferred_output_id: Identifier | None
    implementation_quality: RationaleText
    instruction_adherence: RationaleText
    blocker_handling: RationaleText
    unsupported_verification_claims: RationaleText
    overall_rationale: RationaleText

    @model_validator(mode="after")
    def preference_matches_output(self) -> Self:
        if len(set(self.ordered_output_ids)) != 2:
            raise ValueError("judge pair requires two distinct output IDs")
        expected = {
            "first_better": self.ordered_output_ids[0],
            "second_better": self.ordered_output_ids[1],
            "tie": None,
        }[self.preference]
        if self.preferred_output_id != expected:
            raise ValueError("judge preference does not match its selected output")
        return self


class CompactJudgeDecision(FrozenModel):
    """Secondary anonymous judgment over the exact three public tasks."""

    decision_version: Literal["1.0.0"] = "1.0.0"
    pair_ratings: Annotated[tuple[CompactJudgePair, ...], Field(min_length=3, max_length=3)]
    overall_assessment: RationaleText
    evaluator_limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=6)]

    @model_validator(mode="after")
    def tasks_are_unique(self) -> Self:
        if len({item.task_id for item in self.pair_ratings}) != 3:
            raise ValueError("compact judge must cover all three unique tasks")
        return self


class CompactProjectionBlindReport(FrozenModel):
    """Complete anonymous six-cell report frozen before judging and unblinding."""

    report_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    execution_protocol_digest: Sha256Digest
    execution_contract_digest: Sha256Digest
    profile_construction_receipt_digest: Sha256Digest
    source_commit: NonEmptyStr
    observations: Annotated[
        tuple[CodexDevelopmentRunObservation, ...],
        Field(min_length=6, max_length=6),
    ]
    created_at: UtcDateTime
    condition_mapping_withheld: Literal[True] = True
    external_validation_accessed: Literal[False] = False
    provider_billed_calls: Literal[0] = 0

    @model_validator(mode="after")
    def report_covers_exact_grid(self) -> Self:
        run_ids = tuple(item.run_id for item in self.observations)
        output_ids = tuple(item.blind_output_id for item in self.observations)
        cells = {(item.task_id, item.blind_condition_id) for item in self.observations}
        if len(run_ids) != len(set(run_ids)) or len(output_ids) != len(set(output_ids)):
            raise ValueError("compact observations must have unique run and output IDs")
        if (
            len({item.task_id for item in self.observations}) != 3
            or len({item.blind_condition_id for item in self.observations}) != 2
            or len(cells) != 6
        ):
            raise ValueError("compact blind report must cover the complete 3 x 2 grid")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def validate_compact_profile_stages(
    *,
    stages: Sequence[CompactProfileAuthorStage | CompactProfileReviewStage],
    packets: tuple[
        LongitudinalEvidencePacket,
        LongitudinalEvidencePacket,
        LongitudinalEvidencePacket,
    ],
) -> None:
    """Validate exact evidence binding and active behavior for all three stages."""

    for stage, packet in zip(stages, packets, strict=True):
        profile_text = (
            stage.profile_text
            if isinstance(stage, CompactProfileAuthorStage)
            else stage.approved_profile_text
        )
        validate_static_profile(
            stage=stage.stage,
            evidence_ids=stage.evidence_ids,
            profile_text=profile_text,
            packet=packet,
        )


def validate_compact_remediated_profile_stages(
    *,
    stages: Sequence[CompactProfileReviewStage],
    packets: tuple[
        LongitudinalEvidencePacket,
        LongitudinalEvidencePacket,
        LongitudinalEvidencePacket,
    ],
) -> None:
    """Apply stage-specific baseline checks before a repaired target run."""

    validate_compact_profile_stages(stages=stages, packets=packets)
    for stage in stages:
        lowered = stage.approved_profile_text.casefold()
        if stage.stage < 3 and not all(
            token in lowered for token in ("verify", "selected", "action")
        ):
            raise ValueError(
                f"remediated profile Stage {stage.stage} omitted selected-action verification"
            )
        if stage.stage >= 2 and not all(
            token in lowered for token in ("project", "generated-cache")
        ):
            raise ValueError(
                f"remediated profile Stage {stage.stage} omitted the exact project scope"
            )
        if stage.stage == 3 and not all(
            token in lowered for token in ("requested", "create", "backup", "before", "replace")
        ):
            raise ValueError(
                "remediated profile Stage 3 omitted requested-backup replacement behavior"
            )


def compact_profile_author_schema() -> dict[str, object]:
    """Return the strict tool-free author response schema."""

    stage = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "stage": {"type": "integer", "minimum": 1, "maximum": 3},
            "evidence_ids": {"type": "array", "items": {"type": "string"}},
            "profile_text": {"type": "string"},
            "change_summary": {"type": "string"},
            "intentional_edit_operations": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
            },
        },
        "required": [
            "stage",
            "evidence_ids",
            "profile_text",
            "change_summary",
            "intentional_edit_operations",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "output_version": {"type": "string", "enum": ["1.0.0"]},
            "stages": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": stage,
            },
            "overall_strategy": {"type": "string"},
        },
        "required": ["output_version", "stages", "overall_strategy"],
    }


def compact_profile_review_schema() -> dict[str, object]:
    """Return the strict tool-free reviewer response schema."""

    stage = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "stage": {"type": "integer", "minimum": 1, "maximum": 3},
            "evidence_ids": {"type": "array", "items": {"type": "string"}},
            "approved_profile_text": {"type": "string"},
            "review_summary": {"type": "string"},
            "intentional_edit_operations": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
            },
            "unsupported_content_removed": {"type": "boolean"},
        },
        "required": [
            "stage",
            "evidence_ids",
            "approved_profile_text",
            "review_summary",
            "intentional_edit_operations",
            "unsupported_content_removed",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "output_version": {"type": "string", "enum": ["1.0.0"]},
            "stages": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": stage,
            },
            "overall_review": {"type": "string"},
        },
        "required": ["output_version", "stages", "overall_review"],
    }


def compact_judge_schema() -> dict[str, object]:
    """Return the strict condition-blind judge response schema."""

    pair = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "task_id": {"type": "string"},
            "ordered_output_ids": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "items": {"type": "string"},
            },
            "preference": {
                "type": "string",
                "enum": ["first_better", "second_better", "tie"],
            },
            "preferred_output_id": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
            },
            "implementation_quality": {"type": "string"},
            "instruction_adherence": {"type": "string"},
            "blocker_handling": {"type": "string"},
            "unsupported_verification_claims": {"type": "string"},
            "overall_rationale": {"type": "string"},
        },
        "required": [
            "task_id",
            "ordered_output_ids",
            "preference",
            "preferred_output_id",
            "implementation_quality",
            "instruction_adherence",
            "blocker_handling",
            "unsupported_verification_claims",
            "overall_rationale",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision_version": {"type": "string", "enum": ["1.0.0"]},
            "pair_ratings": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": pair,
            },
            "overall_assessment": {"type": "string"},
            "evaluator_limitations": {
                "type": "array",
                "minItems": 1,
                "maxItems": 6,
                "items": {"type": "string"},
            },
        },
        "required": [
            "decision_version",
            "pair_ratings",
            "overall_assessment",
            "evaluator_limitations",
        ],
    }
