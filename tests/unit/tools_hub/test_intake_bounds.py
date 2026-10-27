from __future__ import annotations

import io
import json
import tarfile
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from adaptation_compiler_lab.tools_hub import intake


def test_archive_rejection_stops_at_first_excess_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz", format=tarfile.USTAR_FORMAT) as archive:
        for index in range(12_100):
            member = tarfile.TarInfo(f"repo/skills/f-{index}")
            member.type = tarfile.DIRTYPE
            archive.addfile(member)
    payload = buffer.getvalue()
    catalog = tmp_path / "catalog.json"
    intake.save(
        catalog,
        {
            "sources": [
                {
                    "id": "fictional",
                    "url": "https://github.com/fixture/source",
                    "ref": "HEAD",
                    "roots": ["skills"],
                }
            ]
        },
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / intake.MARKER).touch()

    def response(request: Any, **_kwargs: Any) -> io.BytesIO:
        return io.BytesIO(
            json.dumps({"sha": "a" * 40}).encode() if not isinstance(request, str) else payload
        )

    monkeypatch.setattr(urllib.request, "urlopen", response)
    count = 0
    original = tarfile.TarInfo.fromtarfile

    def read_header(_cls: Any, stream: Any) -> tarfile.TarInfo:
        nonlocal count
        count += 1
        return original(stream)

    monkeypatch.setattr(tarfile.TarInfo, "fromtarfile", classmethod(read_header))
    with pytest.raises(ValueError, match="entry bound"):
        intake.refresh(catalog, cache)
    assert count <= 12_001, "archive must stop parsing at the first excess member"


def test_decompressed_metadata_is_bounded_before_materialization() -> None:
    underlying = io.BytesIO(b"x" * 100)
    reader = intake.BoundedArchiveReader(underlying, maximum=8)
    with pytest.raises(ValueError, match="decompressed stream"):
        reader.read(1_000_000)
    assert underlying.tell() == 9
