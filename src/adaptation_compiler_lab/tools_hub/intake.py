"""Bounded public source intake reused from the maintenance prototype. No source code executes."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import secrets
import stat
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, cast

from adaptation_compiler_lab.tools_hub.paths import check_root, check_windows_path, files, safe

MARKER = ".temper-discovery-sandbox"


class BoundedArchiveReader:
    """Bound decompressed headers/padding too, before tarfile processes them."""

    def __init__(self, reader: BinaryIO, maximum: int = 144_000_000) -> None:
        self.reader, self.maximum, self.consumed = reader, maximum, 0

    def read(self, size: int = -1) -> bytes:
        limit = self.maximum - self.consumed + 1
        value = self.reader.read(limit if size < 0 else min(size, limit))
        self.consumed += len(value)
        if self.consumed > self.maximum:
            raise ValueError("Archive exceeds its total decompressed stream bound")
        return value


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(path: Path, value: Any) -> None:
    check_root(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                # Windows readers/virus scanners can briefly hold a private
                # receipt without DELETE sharing. Never retry owner publication
                # this way; its digest check belongs immediately before the write.
                time.sleep(0.01 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


def root_path(path: Path) -> Path:
    root = check_root(path)
    if not (root / MARKER).is_file():
        raise ValueError("Only marked disposable projects are supported")
    return root


def metadata(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    fields: dict[str, str] = {}
    current = ""
    for line in text.split("---", 2)[1].splitlines():
        match = re.match(r"^([a-zA-Z_-]+):\s*(.*)$", line)
        if match:
            current, value = match.groups()
            fields[current] = value.strip().strip("\"'")
        elif line.startswith((" ", "\t")) and current:
            fields[current] += " " + line.strip()
    return {**fields, "body": text}


def resources(root: Path) -> dict[str, str]:
    result = {}
    for path in files(root, maximum_bytes=8_000_000, maximum_entries=1024):
        if ".git" in path.relative_to(root).parts:
            continue
        if path.stat().st_size > 2_000_000:
            raise ValueError("Source resource exceeds its bound")
        result[path.relative_to(root).as_posix()] = sha(path.read_bytes())
    if len(result) > 256:
        raise ValueError("Source resource count exceeds its bound")
    return result


def discover(catalog: Path) -> list[dict[str, Any]]:
    """Rescan authorized local snapshots; records real source/resource identity."""
    config = json.loads(catalog.read_text())
    found = []
    for source in config["sources"]:
        root = Path(source["path"]).resolve()
        for path in files(root, maximum_bytes=120_000_000, maximum_entries=12_500):
            if path.name != "SKILL.md":
                continue
            if path.stat().st_size > 64_000:
                continue
            relative = path.parent.relative_to(root).as_posix()
            if source.get("roots") and not any(
                relative == prefix or relative.startswith(prefix.rstrip("/") + "/")
                for prefix in source["roots"]
            ):
                continue
            if any(p in relative.split("/") for p in (".git", "node_modules", "tests", "fixtures")):
                continue
            fields = metadata(path)
            if not fields.get("name") or not fields.get("description"):
                continue
            try:
                hashes = resources(path.parent)
            except ValueError:
                continue
            missing = []
            for link in re.findall(r"\]\(([^\s)]+)\)", fields["body"]):
                link = link.split("#", 1)[0]
                if not link or ":" in link:
                    continue
                if link.startswith(("/", "..")):
                    missing.append(link)
                    continue
                if Path(link).suffix and not (path.parent / link).exists():
                    missing.append(link)
            found.append(
                {
                    "id": source["id"] + "/" + relative,
                    "name": fields["name"],
                    "description": fields["description"],
                    "path": str(path.parent),
                    "source": source["id"],
                    "revision": source["revision"],
                    "source_url": source["url"],
                    "files": hashes,
                    "digest": sha(json.dumps(hashes, sort_keys=True).encode()),
                    "node_min": source.get("node_min", 0),
                    "missing_references": sorted(missing),
                    "body": fields["body"],
                }
            )
    return found


def refresh(catalog: Path, cache: Path) -> dict[str, Any]:
    """Fetch public GitHub heads into a marked cache without executing source code.

    The native authorization supplies permitted repositories and refs in the catalog. This
    discovers revisions and skill metadata, not arbitrary new trusted publishers.
    """
    cache = root_path(cache)
    config = json.loads(catalog.read_text())
    rows = []
    started = time.monotonic()
    for source in config["sources"]:
        match = re.fullmatch(r"https://github.com/([\w.-]+)/([\w.-]+)", source["url"])
        if not match or not re.fullmatch(r"[\w./-]+", source.get("ref", "HEAD")):
            raise ValueError(
                "Only explicitly configured canonical public GitHub sources are supported"
            )
        owner, repo = match.groups()
        identity = owner + "/" + repo
        requests = 1
        request = urllib.request.Request(
            f"https://api.github.com/repos/{identity}/commits/{source.get('ref', 'HEAD')}",
            headers={"User-Agent": "Temper-tools-hub/1"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            commit = json.load(response)["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Upstream did not return a full revision")
        target_relative = owner + "/" + repo + "/" + commit
        if os.name == "nt":
            check_windows_path(
                cache / target_relative,
                directory=True,
                operation="final snapshot",
                relative=target_relative,
            )
        target = safe(cache, target_relative)
        try:
            target_mode = target.lstat().st_mode
        except FileNotFoundError:
            reused = False
        except OSError as error:
            raise OSError("Could not inspect final source snapshot") from error
        else:
            if not stat.S_ISDIR(target_mode):
                raise ValueError("Cached source path must be a directory")
            reused = True
        archive_digest = None
        downloaded = 0
        expected: dict[str, str] = {}
        if not reused:
            with urllib.request.urlopen(
                f"https://codeload.github.com/{identity}/tar.gz/{commit}", timeout=45
            ) as response:
                payload = response.read(20_000_001)
            requests += 1
            downloaded = len(payload)
            if len(payload) > 20_000_000:
                raise ValueError("Archive exceeds prototype download bound")
            archive_digest = sha(payload)
            stage = cache / ("intake-" + secrets.token_urlsafe(6))
            if os.name == "nt":
                check_windows_path(stage, directory=True, operation="staged snapshot")
            try:
                stage.mkdir(mode=0o700)
            except OSError as error:
                raise OSError("Could not create staged source snapshot") from error
            total = 0
            with (
                gzip.GzipFile(fileobj=io.BytesIO(payload)) as uncompressed,
                tarfile.open(
                    fileobj=cast(Any, BoundedArchiveReader(cast(BinaryIO, uncompressed))),
                    mode="r|",
                ) as archive,
            ):
                for number, member in enumerate(archive, 1):
                    if number > 12_000:
                        raise ValueError("Archive exceeds its entry bound")
                    archive_name = PurePosixPath(member.name)
                    if archive_name.is_absolute() or ".." in archive_name.parts:
                        raise ValueError("Archive contains a noncanonical member path")
                    relative = "/".join(member.name.split("/")[1:])
                    if not relative:
                        continue
                    directory = member.isdir()
                    if not directory and not member.isfile():
                        raise ValueError("Archive links and special files are unsupported")
                    if os.name == "nt":
                        kind = "directory" if directory else "file"
                        check_windows_path(
                            stage / relative,
                            directory=directory,
                            operation=f"staged archive {kind}",
                            relative=relative,
                        )
                        check_windows_path(
                            target / relative,
                            directory=directory,
                            operation=f"final archive {kind}",
                            relative=relative,
                        )
                    if directory:
                        continue
                    total += member.size
                    if total > 120_000_000 or member.size > 20_000_000:
                        raise ValueError("Archive exceeds prototype expanded bound")
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise ValueError("Unreadable archive member")
                    content = stream.read()
                    try:
                        destination = safe(stage, relative)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(content)
                    except OSError as error:
                        label = ascii(relative)[:96]
                        raise OSError(f"Could not extract source archive member {label}") from error
                    expected[relative] = sha(content)
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage, target)
            except OSError as error:
                raise OSError("Could not promote staged source snapshot") from error
        try:
            hashes = {
                p.relative_to(target).as_posix(): sha(p.read_bytes())
                for p in files(
                    target,
                    maximum_bytes=120_000_000,
                    maximum_entries=12_500,
                    enforce_windows_budget=True,
                )
            }
        except OSError as error:
            operation = "reused" if reused else "promoted"
            raise OSError(f"Could not verify {operation} source snapshot") from error
        if not reused and hashes != expected:
            raise ValueError("The promoted source manifest differs from the archive")
        tree_digest = sha(json.dumps(hashes, sort_keys=True).encode())
        if reused and source.get("tree_sha256") != tree_digest:
            raise ValueError("Cached source differs or has no recorded integrity binding")
        source.update(path=str(target), revision=commit, tree_sha256=tree_digest)
        if archive_digest is not None:
            source["archive_sha256"] = archive_digest
        rows.append(
            {
                "source": identity,
                "revision": commit,
                "reused": reused,
                "downloaded_bytes": downloaded,
                "archive_sha256": archive_digest,
                "http_requests": requests,
                "tree_sha256": tree_digest,
            }
        )
    save(catalog, config)
    return {
        "sources": rows,
        "seconds": time.monotonic() - started,
        "scope": "owner-configured public repositories only",
    }
