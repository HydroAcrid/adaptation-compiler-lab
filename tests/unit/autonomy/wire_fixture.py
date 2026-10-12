"""Explicit mock responses for the distinct proposal and evidence-review protocols."""

from __future__ import annotations

import json
from typing import Any


def wire_result(payload: dict[str, Any], schema: dict[str, object]) -> str:
    properties = schema.get("properties")
    if isinstance(properties, dict) and "style_reviews" in properties:
        payload = {
            "evaluation_version": payload["evaluation_version"],
            "style_reviews": [
                {
                    "style_key": c["style_key"],
                    "expressed_preference": c["origin"] == "expressed_preference",
                    "evidence": [{**e, "supports_behavior": True} for e in c["evidence"]],
                }
                for c in payload["candidates"]
            ],
            "known_habit_assessments": payload["known_habit_assessments"],
        }
    return json.dumps(payload)
