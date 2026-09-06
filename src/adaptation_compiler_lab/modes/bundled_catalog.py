"""Fail-closed loading for the signed catalog bundled with Temper."""

from __future__ import annotations

from importlib.resources import files

from adaptation_compiler_lab.modes.foundry import FoundryIntakeError, verify_catalog
from adaptation_compiler_lab.modes.foundry_models import SignedCuratedCatalogV1


def load_bundled_catalog() -> SignedCuratedCatalogV1:
    resource = files("adaptation_compiler_lab.modes").joinpath(
        "data/curated_catalog_v1.signed.json"
    )
    try:
        value = SignedCuratedCatalogV1.model_validate_json(resource.read_text(encoding="utf-8"))
        verify_catalog(value)
    except (OSError, ValueError) as error:
        raise FoundryIntakeError("the bundled curated Mode catalog failed verification") from error
    return value
