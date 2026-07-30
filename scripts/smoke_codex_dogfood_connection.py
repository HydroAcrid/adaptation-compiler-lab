"""Read-only Codex dogfood auth/schema/list smoke with a construction cutoff of now."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import (
    CodexDogfoodInteractionSource,
    CodexProjectScope,
    open_codex_dogfood,
)
from adaptation_compiler_lab.connectors.pins import load_dogfood_runtime_pins
from adaptation_compiler_lab.domain import Scope
from adaptation_compiler_lab.serialization import canonical_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--codex-home", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--runtime-pin", type=Path, required=True)
    parser.add_argument("--subject-id", default="local-dogfood-user")
    parser.add_argument("--project-id", default="dogfood-project")
    parser.add_argument("--windows-interop", action="store_true")
    arguments = parser.parse_args()

    cutoff = int(datetime.now(UTC).timestamp())
    pins = load_dogfood_runtime_pins(arguments.runtime_pin)
    with open_codex_dogfood(
        executable=arguments.codex_executable,
        codex_home=arguments.codex_home,
        pin=pins.codex,
        windows_interop=arguments.windows_interop,
    ) as (verified, schemas, rpc):
        source = CodexDogfoodInteractionSource(
            rpc,
            subject_id=arguments.subject_id,
            source_version=verified.version,
            source_schema_digest=verified.schema_bundle_digest,
            schemas=schemas,
            projects=(
                CodexProjectScope(
                    root=arguments.project_root,
                    scope=Scope(
                        subject_ids=(arguments.subject_id,),
                        project_ids=(arguments.project_id,),
                        target_families=("codex",),
                    ),
                ),
            ),
            capture_after_epoch_seconds=cutoff,
        )
        batch = source.poll(after_cursor=None, limit=1)
    print(
        canonical_json(
            {
                "authentication": "saved_chatgpt",
                "eligible_message_count": len(batch.items),
                "provider_billed_calls": 0,
                "schema_bundle_digest": verified.schema_bundle_digest,
                "source_version": verified.version,
            }
        )
    )


if __name__ == "__main__":
    main()
