"""Approved publisher snapshots, authenticated before the native index can read them."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import intake
from .controller import fingerprint
from .paths import files, remove_owned_tree, safe
from .sealed import Seals

# The existing prototype's publishers; this milestone adds no new catalog.
SOURCES: tuple[dict[str, Any], ...] = (
    {
        "id": "pstack",
        "label": "pstack",
        "url": "https://github.com/backnotprop/pstack",
        "ref": "HEAD",
        "roots": ["skills"],
    },
    {
        "id": "superpowers",
        "label": "Superpowers",
        "url": "https://github.com/obra/superpowers",
        "ref": "HEAD",
        "roots": ["skills"],
    },
    {
        "id": "ponytail",
        "label": "Ponytail",
        "url": "https://github.com/DietrichGebert/ponytail",
        "ref": "HEAD",
        "roots": ["skills"],
    },
)


def specification(source: dict[str, Any]) -> dict[str, Any]:
    return {key: source[key] for key in ("id", "url", "ref", "roots")}


def tree_digest(path: Path) -> str:
    return fingerprint(
        {
            item.relative_to(path).as_posix(): intake.sha(item.read_bytes())
            for item in files(path, maximum_bytes=120_000_000, maximum_entries=12_500)
        }
    )


class SourceSnapshots:
    def __init__(
        self,
        home: Path,
        seals: Seals,
        grant: dict[str, Any],
        *,
        reserve: Callable[[int], None] | None = None,
    ) -> None:
        self.home, self.seals, self.grant = home, seals, grant
        self.cache = safe(home, "source-cache")
        self.catalog = safe(home, "catalog.json")
        self.reserve = reserve or (lambda _size: None)

    def acquire(self) -> dict[str, Any]:
        self.cache.mkdir(exist_ok=True)
        (self.cache / intake.MARKER).touch()
        previous = (
            self.seals.read(self.home / "snapshots.json", "snapshots")
            if (self.home / "snapshots.json").is_file()
            else {"sources": []}
        )
        prior = {
            row["id"]: row for row in previous["sources"] if row["id"] in self.grant["source_ids"]
        }
        rows: list[dict[str, Any]] = []
        for selected in self.grant["source_specs"]:
            self.reserve(120_000_000)
            self.compact(keep=[Path(row["path"]) for row in (*prior.values(), *rows)])
            total = sum(
                p.stat().st_size
                for p in files(self.cache, maximum_bytes=512_000_000, maximum_entries=50_000)
            )
            if total + 120_000_000 > 512_000_000:
                raise ValueError("Source cache is full; the previous working profile is preserved")
            partition = safe(self.cache, selected["id"])
            partition.mkdir(exist_ok=True)
            (partition / intake.MARKER).touch()
            receipt = self.home / (selected["id"] + "-intake.json")
            # Only a verified prior record may supply a cache path/revision/tree binding.
            source = {**specification(selected), **prior.get(selected["id"], {})}
            source.update(specification(selected))
            if "path" in source:
                self.validate(source, previous, allow_prior_grant=True)
            intake.save(receipt, {"sources": [source]})
            intake.refresh(receipt, partition)
            row = json.loads(receipt.read_text())["sources"][0]
            row["license_files"] = {
                p.name: intake.sha(p.read_bytes())
                for p in Path(row["path"]).iterdir()
                if p.is_file() and p.name.upper().startswith(("LICENSE", "COPYING"))
            }
            if not row["license_files"]:
                raise ValueError("A source has no root license record; it was not admitted")
            rows.append(row)
        binding = {"grant_id": self.grant["grant_id"], "sources": rows}
        self.seals.write(self.home / "snapshots.json", binding, "snapshots")
        intake.save(self.catalog, {"sources": rows})
        self.compact(keep=[Path(row["path"]) for row in rows])
        return {"sources": len(rows), "project_files_changed": False}

    def validate(
        self,
        row: dict[str, Any],
        record: dict[str, Any] | None = None,
        *,
        allow_prior_grant: bool = False,
    ) -> None:
        record = record or self.seals.read(self.home / "snapshots.json", "snapshots")
        approved = next(
            (item for item in self.grant["source_specs"] if item["id"] == row.get("id")), None
        )
        if (
            approved is None
            or specification(row) != specification(approved)
            or (not allow_prior_grant and record.get("grant_id") != self.grant["grant_id"])
        ):
            raise ValueError("Source is outside the current Hub permission")
        signed = next((item for item in record["sources"] if item["id"] == row["id"]), None)
        if signed != row or not re.fullmatch(r"[a-f0-9]{40}", row.get("revision", "")):
            raise ValueError("Source snapshot has no matching acquisition receipt")
        relative = (
            row["id"] + "/" + row["url"].removeprefix("https://github.com/") + "/" + row["revision"]
        )
        expected = safe(self.cache, relative)
        if str(expected) != row["path"] or tree_digest(expected) != row["tree_sha256"]:
            raise ValueError("Source snapshot differs from its authenticated acquisition")

    def compact(self, *, keep: list[Path]) -> None:
        """Remove only inactive, completely validated public-cache partitions."""
        if not self.cache.is_dir():
            return
        for family in self.cache.iterdir():
            if not family.is_dir():
                continue
            safe(self.cache, family.name)
            for owner in family.iterdir():
                if not owner.is_dir():
                    continue
                safe(self.cache, owner.relative_to(self.cache).as_posix())
                if owner.name.startswith("intake-"):
                    remove_owned_tree(owner, cache=self.cache, maximum_bytes=120_000_000)
                    continue
                for repository in owner.iterdir():
                    if not repository.is_dir():
                        continue
                    safe(self.cache, repository.relative_to(self.cache).as_posix())
                    for revision in repository.iterdir():
                        if revision not in keep:
                            remove_owned_tree(revision, cache=self.cache, maximum_bytes=120_000_000)
