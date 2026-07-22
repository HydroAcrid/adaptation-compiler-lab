"""Strict shared primitives for all domain records."""

from datetime import UTC, datetime
from typing import Annotated, ClassVar, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from adaptation_compiler_lab.domain.enums import ActorKind, RecordKind


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SemVer = Annotated[
    str,
    StringConstraints(
        pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?$"
    ),
]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
UtcDateTime = Annotated[datetime, AfterValidator(_as_utc)]
SchemaVersion = Literal["1.0"]


class FrozenModel(BaseModel):
    """Base value object: strict, immutable, and closed to unknown fields."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
    )


class ActorRef(FrozenModel):
    actor_id: Identifier
    kind: ActorKind
    display_name: NonEmptyStr | None = None
    version: SemVer | None = None


class VersionedRecord(FrozenModel):
    """Envelope shared by the eight top-level records."""

    record_id: Identifier
    schema_version: SchemaVersion = "1.0"
    record_version: SemVer
    created_at: UtcDateTime
    created_by: ActorRef
    policy_version: SemVer
    record_type: RecordKind = Field(exclude=False)
