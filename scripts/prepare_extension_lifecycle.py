"""Restore public pinned lifecycle-test sources and disposable runtime prerequisites."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shlex
import subprocess
import tarfile
import urllib.request
from pathlib import PurePosixPath

from scripts.extension_lifecycle_sandbox import LINUX, PRIVATE, REPO, run, wsl
from scripts.run_extension_lifecycle_screen import files

BENCH = REPO / "development_benchmark_extensions/lifecycle-v1"


def prepare(*, sources_only: bool) -> None:
    protocol = json.loads((BENCH / "protocol.json").read_text())
    sources = json.loads((BENCH / "sources.json").read_text())
    for source in sources:
        target = PRIVATE / "sources" / source["id"]
        if not target.exists():
            repository = source["repository"].removeprefix("https://github.com/")
            payload = urllib.request.urlopen(
                "https://codeload.github.com/" + repository + "/tar.gz/" + source["commit"],
                timeout=60,
            ).read()
            if hashlib.sha256(payload).hexdigest() != source["archive_sha256"]:
                raise ValueError("public archive differs from its frozen binding")
            target.mkdir(parents=True)
            with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
                prefix = archive.getmembers()[0].name.split("/")[0] + "/"
                for member in archive.getmembers():
                    if not member.isfile():
                        continue
                    name = PurePosixPath(member.name.removeprefix(prefix))
                    if name.is_absolute() or ".." in name.parts:
                        raise ValueError("source archive contains an escaping path")
                    path = target / str(name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise ValueError("source archive member could not be read")
                    path.write_bytes(stream.read())
        observed = hashlib.sha256(json.dumps(files(target), sort_keys=True).encode()).hexdigest()
        if observed != protocol["source_trees"][source["id"]]:
            raise ValueError("existing source directory differs; preserve and inspect it")
    if sources_only:
        print(json.dumps({"verified_source_trees": len(sources), "dependencies_changed": False}))
        return
    subprocess.run(
        ["wsl", "-d", "Ubuntu", "--", "mkdir", "-p", LINUX + "/tooling", LINUX + "/home"],
        check=True,
    )
    lock_path = BENCH / "runtime-node-package-lock.json"
    lock = json.loads(lock_path.read_text())
    metadata = {"name": "tooling", "dependencies": lock["packages"][""]["dependencies"]}
    package = PRIVATE / "runtime-package.json"
    package.write_text(json.dumps(metadata))
    for source, destination in ((lock_path, "package-lock.json"), (package, "package.json")):
        subprocess.run(
            ["wsl", "-d", "Ubuntu", "--", "cp", wsl(source), LINUX + "/tooling/" + destination],
            check=True,
        )
    result = run(
        "npm ci --prefix /lab/tooling --cache /lab/npm-cache --no-audit --no-fund",
        network=True,
        timeout=240,
    )
    if result["returncode"]:
        raise ValueError("native npm prerequisite restoration failed")
    versions = json.loads((BENCH / "runtime-python-packages.json").read_text())
    requirements = " ".join(
        shlex.quote(name + "==" + version) for name, version in versions if name != "specify-cli"
    )
    result = run(
        "/opt/uv pip install --python /opt/py/bin/python --target /lab/spec-kit "
        "/sources/spec-kit " + requirements,
        network=True,
        timeout=180,
    )
    if result["returncode"]:
        raise ValueError("native Python prerequisite restoration failed")
    print(json.dumps({"verified_source_trees": len(sources), "prerequisites_restored": True}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources-only", action="store_true")
    prepare(sources_only=parser.parse_args().sources_only)
