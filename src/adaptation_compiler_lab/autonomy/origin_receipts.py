"""Attribute input only from exact, trusted producer receipts, never a role label."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Literal

from adaptation_compiler_lab.autonomy.models import InputOrigin
from adaptation_compiler_lab.domain import FrozenModel, Identifier, Sha256Digest
from adaptation_compiler_lab.governance.models import SignatureEnvelope
from adaptation_compiler_lab.governance.signing import verify_detached_envelope
from adaptation_compiler_lab.serialization import canonical_digest


class OriginReceiptV1(FrozenModel):
    receipt_version: Literal["1.0.0"] = "1.0.0"
    producer_id: Identifier
    source_client: Identifier
    client_version: str
    client_binary_digest: Sha256Digest
    project_id: Identifier
    task_id: Identifier
    message_id: Identifier
    text_digest: Sha256Digest
    origin: InputOrigin
    observed_at: datetime
    signature: SignatureEnvelope

    @property
    def unsigned(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})


class AdmittedOriginProducerV1(FrozenModel):
    producer_id: Identifier
    source_client: Identifier
    client_version: str
    client_binary_digest: Sha256Digest
    public_key_base64: str
    human_fixture_passed: bool = False
    automated_fixture_passed: bool = False
    project_ids: tuple[Identifier, ...]


def attribute_verified_input(
    *,
    receipt: OriginReceiptV1 | None,
    producers: Mapping[str, AdmittedOriginProducerV1],
    source_client: str,
    client_version: str,
    binary_digest: str,
    project_id: str,
    task_id: str,
    message_id: str,
    text: str,
) -> InputOrigin:
    if receipt is None:
        return InputOrigin.UNKNOWN
    producer = producers.get(receipt.producer_id)
    if producer is None or not producer.automated_fixture_passed:
        return InputOrigin.UNKNOWN
    expected = (
        source_client,
        client_version,
        binary_digest,
        project_id,
        task_id,
        message_id,
        str(canonical_digest({"text": text})),
    )
    observed = (
        receipt.source_client,
        receipt.client_version,
        receipt.client_binary_digest,
        receipt.project_id,
        receipt.task_id,
        receipt.message_id,
        receipt.text_digest,
    )
    if (
        expected != observed
        or project_id not in producer.project_ids
        or (producer.source_client, producer.client_version, producer.client_binary_digest)
        != (source_client, client_version, binary_digest)
    ):
        return InputOrigin.UNKNOWN
    try:
        verify_detached_envelope(
            receipt.unsigned,
            receipt.signature,
            public_key_base64=producer.public_key_base64,
            expected_purpose="temper_input_origin",
        )
    except ValueError:
        return InputOrigin.UNKNOWN
    if receipt.origin is InputOrigin.HUMAN and not producer.human_fixture_passed:
        return InputOrigin.UNKNOWN
    return receipt.origin
