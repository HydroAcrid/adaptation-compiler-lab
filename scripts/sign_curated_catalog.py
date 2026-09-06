"""Sign the bundled curated Mode catalog with an external Ed25519 key."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    load_private_key_from_environment,
)
from adaptation_compiler_lab.modes.curated_catalog import CURATED_CATALOG
from adaptation_compiler_lab.modes.foundry import sign_catalog, verify_catalog


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument("--identity-id", default="temper-foundry-release")
    arguments = parser.parse_args()
    key = load_private_key_from_environment(workspace_root=arguments.workspace_root)
    signed = sign_catalog(
        CURATED_CATALOG,
        signer=GovernanceSigner(
            key,
            identity_id=arguments.identity_id,
            subject_id="temper-curated-modes",
        ),
    )
    verify_catalog(signed)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(signed.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
