"""Strict opt-in aggregate reporting with no free-form user or repository content."""

from __future__ import annotations

import base64
import re
from datetime import datetime
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import Field, StringConstraints, model_validator

from adaptation_compiler_lab.desktop.models import DesktopSnapshot
from adaptation_compiler_lab.domain import FrozenModel, Sha256Digest
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

AppVersion = Annotated[str, StringConstraints(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:a[0-9]+)?$")]
ReportId = Annotated[str, StringConstraints(pattern=r"^report-[a-f0-9]{32}$")]
InstallationId = Annotated[str, StringConstraints(pattern=r"^installation-[a-f0-9]{32}$")]
_SIGNATURE_PATTERN = re.compile(r"^[A-Za-z0-9+/]{86}==$")


class ProjectionSizeSummary(FrozenModel):
    latest_utf8_bytes: int = Field(ge=0, le=12_000)
    maximum_utf8_bytes: int = Field(ge=0, le=12_000)

    @model_validator(mode="after")
    def latest_does_not_exceed_maximum(self) -> Self:
        if self.latest_utf8_bytes > self.maximum_utf8_bytes:
            raise ValueError("latest projection size exceeds the reported maximum")
        return self


class AggregateReport(FrozenModel):
    """Allowlisted numeric/enum preview metrics; arbitrary text is structurally impossible."""

    report_version: Literal["1.0.0"] = "1.0.0"
    report_id: ReportId
    installation_id: InstallationId
    app_version: AppVersion
    platform: Literal["windows", "macos"]
    architecture: Literal["x86_64", "arm64"]
    period_started_at: datetime
    period_ended_at: datetime
    active_days: int = Field(ge=0, le=31)
    eligible_interactions: int = Field(ge=0)
    correct_learning: int = Field(ge=0)
    false_learning: int = Field(ge=0)
    missed_learning: int = Field(ge=0)
    pending_reviews: int = Field(ge=0)
    resolved_reviews: int = Field(ge=0)
    activations: int = Field(ge=0)
    correct_activations: int = Field(ge=0)
    false_activations: int = Field(ge=0)
    helped: int = Field(ge=0)
    hurt: int = Field(ge=0)
    irrelevant: int = Field(ge=0)
    repeated_corrections: int = Field(ge=0)
    maintenance_actions: int = Field(ge=0)
    projection_size: ProjectionSizeSummary

    @model_validator(mode="after")
    def period_and_subtotals_are_coherent(self) -> Self:
        if self.period_ended_at < self.period_started_at:
            raise ValueError("aggregate report period is reversed")
        if self.correct_learning + self.false_learning > self.eligible_interactions:
            raise ValueError("learning subtotals exceed eligible interactions")
        if self.correct_activations + self.false_activations > self.activations:
            raise ValueError("activation subtotals exceed activations")
        if self.helped + self.hurt + self.irrelevant > self.activations:
            raise ValueError("feedback subtotals exceed activations")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SignedAggregateReport(FrozenModel):
    """Device-signed aggregate report for invitation-bound server ingestion."""

    envelope_version: Literal["1.0.0"] = "1.0.0"
    report: AggregateReport
    reporting_key_fingerprint: Sha256Digest
    signature_base64: str

    @model_validator(mode="after")
    def signature_has_canonical_shape(self) -> Self:
        if _SIGNATURE_PATTERN.fullmatch(self.signature_base64) is None:
            raise ValueError("aggregate report signature is malformed")
        return self


def sign_aggregate_report(
    report: AggregateReport,
    private_key: Ed25519PrivateKey,
) -> SignedAggregateReport:
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    fingerprint = canonical_digest(
        {"reporting_public_key": base64.b64encode(public_bytes).decode("ascii")}
    )
    signature = private_key.sign(canonical_json(report).encode("utf-8"))
    return SignedAggregateReport(
        report=report,
        reporting_key_fingerprint=fingerprint,
        signature_base64=base64.b64encode(signature).decode("ascii"),
    )


def verify_aggregate_report(
    envelope: SignedAggregateReport,
    public_key: Ed25519PublicKey,
) -> None:
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    expected = canonical_digest(
        {"reporting_public_key": base64.b64encode(public_bytes).decode("ascii")}
    )
    if expected != envelope.reporting_key_fingerprint:
        raise ValueError("aggregate report key fingerprint changed")
    try:
        public_key.verify(
            base64.b64decode(envelope.signature_base64, validate=True),
            canonical_json(envelope.report).encode("utf-8"),
        )
    except (InvalidSignature, ValueError) as error:
        raise ValueError("aggregate report signature is invalid") from error


def build_aggregate_report(
    snapshot: DesktopSnapshot,
    *,
    report_id: str,
    installation_id: str,
    app_version: str,
    platform: Literal["windows", "macos"],
    architecture: Literal["x86_64", "arm64"],
    period_started_at: datetime,
    active_days: int,
) -> AggregateReport:
    """Derive a report only from the already raw-free governed snapshot."""

    gate = snapshot.terminal.review_mode.gate
    sizes = gate.pack_bytes_by_activation
    return AggregateReport(
        report_id=report_id,
        installation_id=installation_id,
        app_version=app_version,
        platform=platform,
        architecture=architecture,
        period_started_at=period_started_at,
        period_ended_at=snapshot.generated_at,
        active_days=active_days,
        eligible_interactions=gate.eligible_interaction_count,
        correct_learning=gate.correct_learning_count,
        false_learning=gate.false_learning_count,
        missed_learning=gate.missed_learning_count,
        pending_reviews=gate.unresolved_review_count,
        resolved_reviews=gate.resolved_review_count,
        activations=gate.activation_count,
        correct_activations=gate.correct_activation_count,
        false_activations=gate.false_activation_count,
        helped=gate.helped_count,
        hurt=gate.hurt_count,
        irrelevant=gate.irrelevant_count,
        repeated_corrections=gate.repeated_correction_count,
        maintenance_actions=gate.manual_review_touches,
        projection_size=ProjectionSizeSummary(
            latest_utf8_bytes=snapshot.terminal.latest_delivered_projection_utf8_bytes,
            maximum_utf8_bytes=max(sizes, default=0),
        ),
    )
