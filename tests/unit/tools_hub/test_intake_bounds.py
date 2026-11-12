from __future__ import annotations

import io
import json
import os
import shutil
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


def _archive_response(
    monkeypatch: pytest.MonkeyPatch, revision: str, member: str, content: bytes
) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        entry = tarfile.TarInfo("fixture/" + member)
        entry.size = len(content)
        archive.addfile(entry, io.BytesIO(content))

    def response(request: Any, **_kwargs: Any) -> io.BytesIO:
        return io.BytesIO(
            buffer.getvalue()
            if isinstance(request, str)
            else json.dumps({"sha": revision}).encode()
        )

    monkeypatch.setattr(urllib.request, "urlopen", response)


def _catalog(cache: Path, catalog: Path) -> None:
    cache.mkdir()
    (cache / intake.MARKER).touch()
    intake.save(
        catalog,
        {
            "sources": [
                {
                    "id": "fictional",
                    "url": "https://github.com/obra/superpowers",
                    "roots": ["skills"],
                }
            ]
        },
    )


@pytest.mark.skipif(os.name != "nt", reason="native Windows cache path boundary")
@pytest.mark.parametrize(("cache_units", "final_units"), [(136, 245), (153, 262)])
def test_native_windows_archive_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cache_units: int, final_units: int
) -> None:
    def units(value: Path | str) -> int:
        return len(str(value).encode("utf-16-le")) // 2

    cache = tmp_path / ("q" * (cache_units - units(tmp_path) - 1))
    catalog = tmp_path / "catalog.json"
    _catalog(cache, catalog)
    old_revision = "a" * 40
    old_member = "skills/ok/SKILL.md"
    old_target = cache / "obra" / "superpowers" / old_revision
    _archive_response(monkeypatch, old_revision, old_member, b"prior skill")
    intake.refresh(catalog, cache)
    before = catalog.read_bytes()
    revision = "b" * 40
    target = cache / "obra" / "superpowers" / revision
    member = "docs/" + "a" * 39 + "\U0001f600" + ".txt"
    content = b"Bounded source-cache control."
    assert units(member) == 50 and len(member) == 49
    assert units(cache / "intake-xxxxxxxx" / member) == final_units - 42
    assert units(target / member) == final_units
    _archive_response(monkeypatch, revision, member, content)

    if final_units == 245:
        receipt = intake.refresh(catalog, cache)
        expected = intake.sha(json.dumps({member: intake.sha(content)}, sort_keys=True).encode())
        assert receipt["sources"][0]["tree_sha256"] == expected
        assert (target / member).read_bytes() == content
    else:
        try:
            with pytest.raises(ValueError, match=r"final archive file.*262.*259"):
                intake.refresh(catalog, cache)
            assert not target.exists()
            assert list(cache.glob("intake-*/docs")) == []
            assert catalog.read_bytes() == before
            assert (old_target / old_member).read_bytes() == b"prior skill"
        finally:
            # Also clean up an overlong payload if this test runs against the old code.
            shutil.rmtree("\\\\?\\" + str(cache), ignore_errors=True)

    if final_units == 245:
        assert (old_target / old_member).read_bytes() == b"prior skill"


def test_manifest_mismatch_does_not_advance_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache, catalog = tmp_path / "cache", tmp_path / "catalog.json"
    _catalog(cache, catalog)
    old_revision = "a" * 40
    member = "skills/ok/SKILL.md"
    _archive_response(monkeypatch, old_revision, member, b"prior skill")
    intake.refresh(catalog, cache)
    before = catalog.read_bytes()
    revision = "b" * 40
    _archive_response(monkeypatch, revision, member, b"new skill")
    target = cache / "obra" / "superpowers" / revision
    replace = os.replace

    def change_promoted_member(source: Path, destination: Path) -> None:
        replace(source, destination)
        if destination == target:
            (target / member).write_bytes(b"different skill")

    monkeypatch.setattr(os, "replace", change_promoted_member)
    with pytest.raises(ValueError, match="promoted source manifest differs"):
        intake.refresh(catalog, cache)
    assert catalog.read_bytes() == before
    assert (target.with_name(old_revision) / member).read_bytes() == b"prior skill"


@pytest.mark.parametrize("reused", [False, True])
def test_inaccessible_snapshot_member_does_not_advance_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reused: bool
) -> None:
    cache, catalog = tmp_path / "cache", tmp_path / "catalog.json"
    _catalog(cache, catalog)
    revision = "a" * 40
    member = "skills/ok/SKILL.md"
    _archive_response(monkeypatch, revision, member, b"skill")
    if reused:
        intake.refresh(catalog, cache)
    before = catalog.read_bytes()
    destination = cache / "obra" / "superpowers" / revision / member
    original = Path.stat

    def unavailable(path: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if path == destination:
            raise FileNotFoundError("injected inaccessible snapshot member")
        return original(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", unavailable)
    operation = "reused" if reused else "promoted"
    with pytest.raises(OSError, match=rf"{operation} source snapshot"):
        intake.refresh(catalog, cache)
    assert catalog.read_bytes() == before


@pytest.mark.skipif(os.name != "nt", reason="native Windows cache path boundary")
def test_reused_snapshot_rejects_over_budget_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache, catalog = tmp_path / "cache", tmp_path / "catalog.json"
    _catalog(cache, catalog)
    revision = "a" * 40
    _archive_response(monkeypatch, revision, "skills/ok/SKILL.md", b"skill")
    intake.refresh(catalog, cache)
    before = catalog.read_bytes()
    target = cache / "obra" / "superpowers" / revision
    padding = 248 - len(str(target).encode("utf-16-le")) // 2 - 1
    directory = Path("\\\\?\\" + str(target / ("d" * padding)))
    directory.mkdir()
    try:
        with pytest.raises(ValueError, match=r"snapshot resource.*directory path uses 248"):
            intake.refresh(catalog, cache)
        assert catalog.read_bytes() == before
    finally:
        directory.rmdir()


@pytest.mark.parametrize("failure", ["extract", "promote"])
def test_filesystem_failure_preserves_original_cause_and_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    cache, catalog = tmp_path / "cache", tmp_path / "catalog.json"
    _catalog(cache, catalog)
    revision = "a" * 40
    member = "skills/ok/SKILL.md"
    target = cache / "obra" / "superpowers" / revision
    _archive_response(monkeypatch, revision, member, b"skill")
    before = catalog.read_bytes()
    original = OSError(0, "injected filesystem failure", None, 3)

    if failure == "extract":

        def write_failure(path: Path, data: bytes) -> int:
            assert path.name == "SKILL.md"
            raise original

        monkeypatch.setattr(Path, "write_bytes", write_failure)
    else:

        def promote_failure(source: Path, destination: Path) -> None:
            assert destination == target
            raise original

        monkeypatch.setattr(os, "replace", promote_failure)
    with pytest.raises(OSError, match=rf"Could not {failure}") as error:
        intake.refresh(catalog, cache)
    assert error.value.__cause__ is original
    assert not target.exists()
    assert catalog.read_bytes() == before
