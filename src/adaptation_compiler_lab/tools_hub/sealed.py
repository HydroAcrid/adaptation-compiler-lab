"""Hub authorization and intake receipts use the owner's existing signing identity."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from adaptation_compiler_lab.governance.models import SignatureEnvelope
from adaptation_compiler_lab.governance.signing import GovernanceSigner, verify_detached_envelope

from .intake import save
from .paths import check_root


class Seals:
    def __init__(self, signer: GovernanceSigner) -> None:
        self.signer = signer
        self.public_key = base64.b64encode(
            signer.private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        ).decode()

    def seal(self, payload: dict[str, Any], kind: str) -> dict[str, Any]:
        return {
            "payload": payload,
            "signature": self.signer.envelope(
                payload, purpose="tools_hub/" + kind + "/v1", signed_at=datetime.now(UTC)
            ).model_dump(mode="json"),
        }

    def open(self, value: dict[str, Any], kind: str) -> dict[str, Any]:
        if set(value) != {"payload", "signature"} or not isinstance(value["payload"], dict):
            raise ValueError("Invalid Hub authorization record")
        envelope = SignatureEnvelope.model_validate_json(json.dumps(value["signature"]))
        if (
            envelope.signer_identity_id != self.signer.identity_id
            or envelope.key_fingerprint != self.signer.fingerprint
        ):
            raise ValueError("Hub authorization belongs to a different owner")
        verify_detached_envelope(
            value["payload"],
            envelope,
            public_key_base64=self.public_key,
            expected_purpose="tools_hub/" + kind + "/v1",
        )
        return dict(value["payload"])

    def read(self, path: Path, kind: str) -> dict[str, Any]:
        check_root(path)
        if path.stat().st_size > 2_000_000:
            raise ValueError("Hub receipt exceeds its bound")
        return self.open(json.loads(path.read_text(encoding="utf-8")), kind)

    def write(self, path: Path, payload: dict[str, Any], kind: str) -> None:
        save(path, self.seal(payload, kind))
