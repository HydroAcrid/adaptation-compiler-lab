from __future__ import annotations

import base64
from datetime import UTC, datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from adaptation_compiler_lab.autonomy.models import InputOrigin
from adaptation_compiler_lab.autonomy.origin_receipts import (
    AdmittedOriginProducerV1,
    OriginReceiptV1,
    attribute_verified_input,
)
from adaptation_compiler_lab.governance.signing import GovernanceSigner
from adaptation_compiler_lab.serialization import canonical_digest

DIGEST = "sha256:" + "a" * 64


def test_human_input_requires_admitted_producer_signature_and_exact_scope() -> None:
    signer = GovernanceSigner(Ed25519PrivateKey.generate(), "producer", "owner")
    payload = {
        "receipt_version": "1.0.0",
        "producer_id": "native-producer",
        "source_client": "codex",
        "client_version": "fixture-client",
        "client_binary_digest": DIGEST,
        "project_id": "project",
        "task_id": "task",
        "message_id": "message",
        "text_digest": canonical_digest({"text": "Shorten this"}),
        "origin": "human",
        "observed_at": datetime(2026, 10, 8, tzinfo=UTC).isoformat(),
    }
    receipt = OriginReceiptV1.model_validate_json(
        __import__("json").dumps(
            {
                **payload,
                "signature": signer.envelope(
                    payload,
                    purpose="temper_input_origin",
                    signed_at=datetime(2026, 10, 8, tzinfo=UTC),
                ).model_dump(mode="json"),
            }
        )
    )
    # Normalize datetime serialization before signing, just like native producer envelopes.
    receipt = receipt.model_copy(
        update={
            "signature": signer.envelope(
                receipt.unsigned,
                purpose="temper_input_origin",
                signed_at=datetime(2026, 10, 8, tzinfo=UTC),
            )
        }
    )
    producer = AdmittedOriginProducerV1(
        producer_id="native-producer",
        source_client="codex",
        client_version="fixture-client",
        client_binary_digest=DIGEST,
        public_key_base64=base64.b64encode(
            signer.private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        ).decode(),
        human_fixture_passed=True,
        automated_fixture_passed=True,
        project_ids=("project",),
    )
    args = dict(
        receipt=receipt,
        producers={producer.producer_id: producer},
        source_client="codex",
        client_version="fixture-client",
        binary_digest=DIGEST,
        project_id="project",
        task_id="task",
        message_id="message",
        text="Shorten this",
    )
    assert attribute_verified_input(**args) is InputOrigin.HUMAN
    assert attribute_verified_input(**{**args, "text": "Another message"}) is InputOrigin.UNKNOWN
    assert attribute_verified_input(**{**args, "project_id": "unrelated"}) is InputOrigin.UNKNOWN
    assert attribute_verified_input(**{**args, "producers": {}}) is InputOrigin.UNKNOWN
    assert (
        attribute_verified_input(
            **{
                **args,
                "producers": {
                    producer.producer_id: producer.model_copy(
                        update={"human_fixture_passed": False}
                    )
                },
            }
        )
        is InputOrigin.UNKNOWN
    )
    forged = receipt.model_copy(update={"origin": InputOrigin.DELEGATED})
    assert attribute_verified_input(**{**args, "receipt": forged}) is InputOrigin.UNKNOWN
