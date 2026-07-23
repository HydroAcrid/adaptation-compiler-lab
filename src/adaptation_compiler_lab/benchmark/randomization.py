"""Deterministic secret-seed custody mapping and trial-order construction."""

from __future__ import annotations

import base64
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final, TypeVar

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.benchmark.models import (
    BenchmarkCondition,
    BlindConditionId,
    BlindTaskId,
)
from adaptation_compiler_lab.domain.base import (
    FrozenModel,
    Identifier,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.values import strings_are_sorted_unique
from adaptation_compiler_lab.serialization import canonical_digest

RANDOMIZATION_SEED_FILE_ENV: Final = "ACLAB_RANDOMIZATION_SEED_FILE"
RANDOMIZATION_ALGORITHM: Final = "sha256_counter_shuffle_v1"
_DOMAIN: Final = b"adaptation-compiler-lab/randomization/v1\x00"
_T = TypeVar("_T")


class RandomizationSeedError(ValueError):
    """Secret randomization material is missing, unsafe, or malformed."""


@dataclass(frozen=True, slots=True)
class RandomizationSeed:
    """A separate 256-bit seed that never enters construction-visible records."""

    value: bytes

    def __post_init__(self) -> None:
        if len(self.value) != 32:
            raise RandomizationSeedError("randomization seed must contain exactly 32 bytes")

    @property
    def commitment(self) -> Sha256Digest:
        return f"sha256:{hashlib.sha256(self.value).hexdigest()}"

    @classmethod
    def from_file(cls, path: Path, *, workspace_root: Path) -> RandomizationSeed:
        resolved = path.expanduser().resolve()
        workspace = workspace_root.expanduser().resolve()
        if resolved.is_relative_to(workspace):
            raise RandomizationSeedError(
                "randomization seed must remain outside the compiler workspace"
            )
        if _inside_git_repository(resolved):
            raise RandomizationSeedError("randomization seed must remain outside Git")
        try:
            mode = stat.S_IMODE(resolved.stat().st_mode)
            encoded = resolved.read_text(encoding="ascii").strip()
        except FileNotFoundError as exc:
            raise RandomizationSeedError("randomization seed file is unavailable") from exc
        except (OSError, UnicodeError) as exc:
            raise RandomizationSeedError("randomization seed file cannot be read safely") from exc
        if mode & 0o077:
            raise RandomizationSeedError("randomization seed permissions are too broad")
        try:
            value = base64.b64decode(encoded, validate=True)
        except (UnicodeEncodeError, ValueError) as exc:
            raise RandomizationSeedError("randomization seed must be canonical base64") from exc
        if base64.b64encode(value).decode("ascii") != encoded:
            raise RandomizationSeedError("randomization seed must use canonical base64")
        return cls(value)

    @classmethod
    def from_environment(
        cls,
        *,
        workspace_root: Path,
        environ: dict[str, str] | None = None,
    ) -> RandomizationSeed:
        environment = os.environ if environ is None else environ
        path = environment.get(RANDOMIZATION_SEED_FILE_ENV)
        if not path:
            raise RandomizationSeedError(f"{RANDOMIZATION_SEED_FILE_ENV} is required")
        return cls.from_file(Path(path), workspace_root=workspace_root)

    def blind_id(self, *, prefix: str, domain: str, stable_key: str) -> str:
        if prefix not in {"cond", "family", "output", "task"}:
            raise RandomizationSeedError("unsupported blind-ID prefix")
        digest = hashlib.sha256(
            _DOMAIN + self.value + domain.encode("utf-8") + b"\x00" + stable_key.encode("utf-8")
        ).hexdigest()
        return f"{prefix}-{digest[:24]}"

    def shuffled(self, values: tuple[_T, ...], *, domain: str) -> tuple[_T, ...]:
        """Return a deterministic Fisher-Yates permutation from the committed seed."""

        result = list(values)
        for counter, upper in enumerate(range(len(result) - 1, 0, -1)):
            block = hashlib.sha256(
                _DOMAIN + self.value + domain.encode("utf-8") + b"\x00" + counter.to_bytes(8, "big")
            ).digest()
            selected = int.from_bytes(block, "big") % (upper + 1)
            result[upper], result[selected] = result[selected], result[upper]
        return tuple(result)


class ConditionAssignment(FrozenModel):
    """Secret condition-to-blind-ID mapping; this object is sealed, never constructed-visible."""

    condition: BenchmarkCondition
    blind_condition_id: BlindConditionId


class RandomizedTrialCell(FrozenModel):
    """Condition-blind trial cell supplied to the sealed runner."""

    sequence: int = Field(ge=1, le=32)
    trial_id: Identifier
    blind_task_id: BlindTaskId
    blind_condition_id: BlindConditionId
    repetition: int = Field(ge=1, le=2)


class SoftwareCustodyPlan(FrozenModel):
    """Secret mapping and complete deterministic 32-run order stored only under custody."""

    plan_version: str = "1.0.0"
    benchmark_id: Identifier
    construction_cutoff: UtcDateTime
    randomization_seed_commitment: Sha256Digest
    randomization_algorithm: str = RANDOMIZATION_ALGORITHM
    condition_assignments: Annotated[
        tuple[ConditionAssignment, ...],
        Field(min_length=4, max_length=4),
    ]
    trial_order: Annotated[tuple[RandomizedTrialCell, ...], Field(min_length=32, max_length=32)]
    created_at: UtcDateTime

    @model_validator(mode="after")
    def plan_is_complete(self) -> SoftwareCustodyPlan:
        if tuple(item.condition for item in self.condition_assignments) != tuple(
            BenchmarkCondition
        ):
            raise ValueError("condition assignments must contain every condition in order")
        condition_ids = tuple(item.blind_condition_id for item in self.condition_assignments)
        if len(condition_ids) != len(set(condition_ids)):
            raise ValueError("condition blind IDs must be unique")
        expected_sequences = tuple(range(1, 33))
        if tuple(item.sequence for item in self.trial_order) != expected_sequences:
            raise ValueError("trial sequence must be complete and contiguous")
        cells = {
            (item.blind_task_id, item.blind_condition_id, item.repetition)
            for item in self.trial_order
        }
        if len(cells) != 32:
            raise ValueError("trial order contains duplicate cells")
        task_ids = {item.blind_task_id for item in self.trial_order}
        observed_condition_ids = {item.blind_condition_id for item in self.trial_order}
        if len(task_ids) != 4 or observed_condition_ids != set(condition_ids):
            raise ValueError("trial order must cross four tasks with four conditions")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SoftwareCustodyConstructionView(FrozenModel):
    """Safe public commitment with no condition mapping, seed, task content, or trial order."""

    view_version: str = "1.0.0"
    benchmark_id: Identifier
    construction_cutoff: UtcDateTime
    randomization_seed_commitment: Sha256Digest
    randomization_algorithm: str
    condition_blind_ids: Annotated[tuple[BlindConditionId, ...], Field(min_length=4, max_length=4)]
    software_custody_plan_digest: Sha256Digest

    @field_validator("condition_blind_ids")
    @classmethod
    def condition_ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("construction-view condition IDs must be sorted and unique")
        return value


def build_software_custody_plan(
    *,
    seed: RandomizationSeed,
    benchmark_id: str,
    blind_task_ids: tuple[BlindTaskId, ...],
    construction_cutoff: UtcDateTime,
    created_at: UtcDateTime,
) -> SoftwareCustodyPlan:
    """Construct the secret mapping and randomized order without exposing either."""

    if len(blind_task_ids) != 4 or len(set(blind_task_ids)) != 4:
        raise RandomizationSeedError("software custody requires four unique blind task IDs")
    assignments = tuple(
        ConditionAssignment(
            condition=condition,
            blind_condition_id=seed.blind_id(
                prefix="cond",
                domain=f"{benchmark_id}/condition",
                stable_key=condition.value,
            ),
        )
        for condition in BenchmarkCondition
    )
    cells = tuple(
        (task_id, assignment.blind_condition_id, repetition)
        for task_id in blind_task_ids
        for assignment in assignments
        for repetition in (1, 2)
    )
    shuffled = seed.shuffled(cells, domain=f"{benchmark_id}/trial-order")
    trial_order = tuple(
        RandomizedTrialCell(
            sequence=index,
            trial_id=f"trial-{index:04d}",
            blind_task_id=task_id,
            blind_condition_id=condition_id,
            repetition=repetition,
        )
        for index, (task_id, condition_id, repetition) in enumerate(shuffled, start=1)
    )
    return SoftwareCustodyPlan(
        benchmark_id=benchmark_id,
        construction_cutoff=construction_cutoff,
        randomization_seed_commitment=seed.commitment,
        condition_assignments=assignments,
        trial_order=trial_order,
        created_at=created_at,
    )


def construction_view(plan: SoftwareCustodyPlan) -> SoftwareCustodyConstructionView:
    """Project only values safe to return to adaptation construction."""

    return SoftwareCustodyConstructionView(
        benchmark_id=plan.benchmark_id,
        construction_cutoff=plan.construction_cutoff,
        randomization_seed_commitment=plan.randomization_seed_commitment,
        randomization_algorithm=plan.randomization_algorithm,
        condition_blind_ids=tuple(
            sorted(item.blind_condition_id for item in plan.condition_assignments)
        ),
        software_custody_plan_digest=plan.content_digest,
    )


def _inside_git_repository(path: Path) -> bool:
    candidate = path if path.is_dir() else path.parent
    return any((parent / ".git").exists() for parent in (candidate, *candidate.parents))
