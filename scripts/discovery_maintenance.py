"""Experimental declarative skill discovery and maintenance, limited to marked sandboxes.

Not a shipping Temper feature or a general runtime installer. Repository goals are
temporary routing inputs, never personal preference evidence. No upstream code runs.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import tarfile
import tempfile
import time
import urllib.request
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

MARKER = ".temper-discovery-sandbox"
STATE = ".temper-hub-state.json"
STOP = set(
    [
        "a",
        "an",
        "the",
        "of",
        "to",
        "and",
        "or",
        "for",
        "in",
        "with",
        "use",
        "using",
        "when",
        "how",
        "is",
        "are",
        "this",
        "that",
        "your",
        "you",
        "be",
        "on",
        "from",
        "as",
        "at",
        "by",
        "it",
        "can",
        "should",
        "need",
        "must",
        "into",
        "all",
        "not",
        "do",
        "have",
        "has",
        "will",
        "skill",
        "skills",
        "agent",
        "agents",
        "code",
        "project",
        "work",
        "repository",
        "task",
    ]
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def root_path(path: Path) -> Path:
    root = path.resolve()
    if not (root / MARKER).is_file():
        raise ValueError("Only marked disposable projects are supported")
    return root


def safe(root: Path, name: str) -> Path:
    if not name or "\\" in name or name.startswith("/") or ".." in Path(name).parts:
        raise ValueError("Noncanonical relative path")
    target = root / name
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Path escapes permitted root")
    current = target
    while current != root:
        if current.is_symlink():
            raise ValueError("Symlinks are unsupported")
        current = current.parent
    return target


def tokens(value: str) -> Counter[str]:
    result: Counter[str] = Counter()
    for word in re.findall(r"[a-z][a-z0-9]+", value.casefold()):
        if word not in STOP:
            # Small, corpus-independent stemming. No benchmark labels or tool aliases.
            word = re.sub(r"(ing|ments|ment|tion|ed|es|s)$", "", word) if len(word) > 5 else word
            result[word] += 1
    return result


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
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Source symlinks are unsupported")
        if path.is_file() and ".git" not in path.relative_to(root).parts:
            if path.stat().st_size > 2_000_000:
                raise ValueError("Source resource exceeds prototype bound")
            result[path.relative_to(root).as_posix()] = sha(path.read_bytes())
    if len(result) > 256:
        raise ValueError("Source resource count exceeds prototype bound")
    return result


def discover(catalog: Path) -> list[dict[str, Any]]:
    """Rescan authorized local snapshots; records real source/resource identity."""
    config = json.loads(catalog.read_text())
    found = []
    for source in config["sources"]:
        root = Path(source["path"]).resolve()
        for path in sorted(root.rglob("SKILL.md")):
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
                if not link or ":" in link or link.startswith(("/", "..")):
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

    The owner supplies the permitted repositories and refs in the catalog. This
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
            headers={"User-Agent": "Temper-development-discovery-prototype"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            commit = json.load(response)["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Upstream did not return a full revision")
        target = safe(cache, owner + "/" + repo + "/" + commit)
        reused = target.is_dir()
        archive_digest = None
        downloaded = 0
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
            stage = Path(tempfile.mkdtemp(prefix="intake-", dir=cache))
            total = 0
            try:
                with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
                    members = archive.getmembers()
                    if len(members) > 12_000:
                        raise ValueError("Archive exceeds prototype entry bound")
                    for member in members:
                        archive_name = PurePosixPath(member.name)
                        if archive_name.is_absolute() or ".." in archive_name.parts:
                            raise ValueError("Archive contains a noncanonical member path")
                        relative = "/".join(member.name.split("/")[1:])
                        if not relative or member.isdir():
                            continue
                        if not member.isfile():
                            raise ValueError("Archive links and special files are unsupported")
                        total += member.size
                        if total > 120_000_000 or member.size > 20_000_000:
                            raise ValueError("Archive exceeds prototype expanded bound")
                        destination = safe(stage, relative)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        stream = archive.extractfile(member)
                        if stream is None:
                            raise ValueError("Unreadable archive member")
                        destination.write_bytes(stream.read())
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage, target)
            except BaseException:
                # Keep rejected material inside the marked cache for inspection.
                raise
        hashes = {
            p.relative_to(target).as_posix(): sha(p.read_bytes())
            for p in sorted(target.rglob("*"))
            if p.is_file()
        }
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


def recommend(
    root: Path, catalog: Path, goal: str, *, count: int = 2, node: int = 24
) -> dict[str, Any]:
    root = root_path(root)
    corpus = discover(catalog)
    profile = (
        (root / "pyproject.toml").read_text()[:3000] if (root / "pyproject.toml").is_file() else ""
    )
    if (root / "package.json").is_file():
        profile += (root / "package.json").read_text()[:3000]
    positive = re.sub(r"\b(?:not|without|no)\s+[^.;]+", "", goal, flags=re.IGNORECASE)
    query, context = tokens(positive), tokens(profile)
    # A stack name repeated in the goal is still project context. Require an
    # independent task-term match before using stack overlap as a tie-breaker.
    task_terms = query.keys() - context.keys()
    documents = [tokens(row["name"] + " " + row["description"]) for row in corpus]
    frequencies: Counter[str] = Counter()
    for document in documents:
        frequencies.update(document.keys())
    state_path = root / STATE
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    rejected = set(state.get("rejected", []))
    candidates = []
    blocked = []
    for row, document in zip(corpus, documents, strict=True):
        if row["node_min"] > node or row["missing_references"]:
            blocked.append({"id": row["id"], "reason": "runtime_or_missing_reference"})
            continue
        if row["id"] in rejected:
            continue
        matched = task_terms & document.keys()
        score = sum(math.log(1 + len(corpus) / (1 + frequencies[w])) for w in matched)
        score /= math.sqrt(max(1, len(document)))
        score += 0.03 * len(context.keys() & document.keys()) if score else 0
        if score > 0.25:
            candidates.append({**row, "score": round(score, 6), "matched_terms": sorted(matched)})
    candidates.sort(key=lambda x: (-x["score"], x["id"]))
    selected: list[dict[str, Any]] = []
    names: set[str] = set()
    for row in candidates if count else []:
        # count is a ceiling. Weak incidental word overlap must not fill unused
        # slots merely because the caller permits a second skill.
        if row["score"] < .65 * candidates[0]["score"]:
            continue
        slug = row["name"].lower().replace(" ", "-")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,99}", slug) or slug in names:
            continue
        # Do not add a near-duplicate of the same procedure from another source.
        if any(
            len(tokens(row["description"]).keys() & tokens(r["description"]).keys())
            / max(1, len(tokens(row["description"]).keys() | tokens(r["description"]).keys()))
            > 0.65
            for r in selected
        ):
            continue
        selected.append(row)
        names.add(slug)
        if len(selected) == count:
            break
    return {
        "goal": goal,
        "catalog_count": len(corpus),
        "selected": selected,
        "candidates": candidates[:8],
        "selection": "lexical_metadata_v1",
        "blocked": blocked,
        "learned_personal_preferences": False,
    }


def reconcile(root: Path, selection: dict[str, Any]) -> dict[str, Any]:
    root = root_path(root)
    state_path = root / STATE
    old = (
        json.loads(state_path.read_text()) if state_path.exists() else {"files": {}, "rejected": []}
    )
    if any(not name.startswith(".agents/skills/") for name in old["files"]):
        raise ValueError("Managed state contains an out-of-scope path")
    active_ids = {s["id"] for s in old.get("sources", {}).values()}
    blocked_active = [b for b in selection.get("blocked", []) if b["id"] in active_ids]
    if blocked_active and old.get("goal") == selection["goal"]:
        return {
            "status": "deferred_update",
            "blocked": blocked_active,
            "changed": False,
            "retained_previous_profile": True,
        }
    expected: dict[str, bytes] = {}
    sources = {}
    for row in selection["selected"]:
        source = Path(row["path"])
        if resources(source) != row["files"]:
            raise ValueError("Source changed after selection")
        name = row["name"].lower().replace(" ", "-")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,99}", name):
            raise ValueError("Invalid native skill name")
        for relative, digest in row["files"].items():
            data = safe(source, relative).read_bytes()
            if sha(data) != digest:
                raise ValueError("Source changed during preparation")
            expected[f".agents/skills/{name}/{relative}"] = data
        sources[name] = {k: row[k] for k in ("id", "revision", "digest", "source_url")}
    conflicts = []
    for name in sorted(set(old["files"]) | set(expected)):
        path = safe(root, name)
        current = sha(path.read_bytes()) if path.is_file() else None
        previous = old["files"].get(name)
        desired = sha(expected[name]) if name in expected else None
        if current is not None and current not in (previous, desired):
            conflicts.append(name)
    if conflicts:
        return {"status": "paused_external_edit", "conflicts": conflicts, "changed": False}
    # Journal intent before writes. Re-running recovery converges to this same plan.
    transaction = root / ".temper-hub-pending.json"
    save(transaction, {"selection": selection, "before": old})
    written, removed = 0, 0
    for name, data in expected.items():
        path = safe(root, name)
        if not path.is_file() or path.read_bytes() != data:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
            os.replace(temporary, path)
            written += 1
    for name in sorted(set(old["files"]) - set(expected)):
        path = safe(root, name)
        if path.is_file():
            path.unlink()
            removed += 1
    save(
        state_path,
        {
            "files": {p: sha(b) for p, b in expected.items()},
            "sources": sources,
            "goal": selection["goal"],
            "rejected": old.get("rejected", []),
        },
    )
    transaction.unlink(missing_ok=True)
    return {
        "status": "ready",
        "written": written,
        "removed": removed,
        "sources": sources,
        "catalog_count": selection.get("catalog_count"),
        "changed": bool(written or removed),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("refresh", "discover", "recommend", "maintain", "status")
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--goal", default="")
    parser.add_argument("--count", type=int, choices=(0, 1, 2, 3), default=2)
    parser.add_argument("--node", type=int, default=24)
    args = parser.parse_args()
    root = root_path(args.root)
    if args.command == "status":
        path = root / STATE
        value = json.loads(path.read_text()) if path.exists() else {"status": "unconfigured"}
    elif args.catalog is None:
        parser.error("--catalog is required")
    elif args.command == "refresh":
        value = refresh(args.catalog, root)
    elif args.command == "discover":
        value = discover(args.catalog)
        value = [{k: v for k, v in row.items() if k not in ("body", "files")} for row in value]
    else:
        value = recommend(root, args.catalog, args.goal, count=args.count, node=args.node)
        if args.command == "maintain":
            value = reconcile(root, value)
        else:
            value = {
                **value,
                "selected": [
                    {k: v for k, v in row.items() if k not in ("body", "files")}
                    for row in value["selected"]
                ],
                "candidates": [
                    {k: v for k, v in row.items() if k not in ("body", "files")}
                    for row in value["candidates"]
                ],
            }
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
