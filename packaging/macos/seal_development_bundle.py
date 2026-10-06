"""Seal an internal macOS app, then build a DMG from those exact app bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import tempfile
from pathlib import Path


def _run(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=True, timeout=timeout)


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _bound_sidecar(app: Path, name: str, manifest_path: Path) -> str:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sidecar = app / "Contents" / "MacOS" / name
    digest = _digest(sidecar)
    if (
        manifest.get("target_triple") != "aarch64-apple-darwin"
        or manifest.get("binary_sha256") != digest
    ):
        raise ValueError(f"{name} does not match its exact Apple manifest")
    return digest


def _verify_sealed_app(app: Path) -> None:
    seal = app / "Contents" / "_CodeSignature" / "CodeResources"
    if not seal.is_file():
        raise ValueError("development app has no complete bundle resource seal")
    _run(["/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=4", str(app)])
    details = _run(["/usr/bin/codesign", "--display", "--verbose=4", str(app)])
    signature = details.stdout + details.stderr
    if "Signature=adhoc" not in signature or "Sealed Resources version=2" not in signature:
        raise ValueError("development app is not an ad hoc sealed bundle")


def seal_development_bundle(
    *, app: Path, dmg: Path, engine_manifest: Path, hook_manifest: Path
) -> dict[str, str]:
    if platform.system() != "Darwin" or platform.machine().lower() not in {"arm64", "aarch64"}:
        raise ValueError("development sealing requires native Apple Silicon")
    app = app.expanduser().resolve(strict=True)
    dmg = dmg.expanduser().absolute()
    if not app.is_dir() or dmg.exists():
        raise ValueError("development app or fresh DMG destination is unavailable")
    dmg.parent.mkdir(parents=True, exist_ok=True)
    engine_digest = _bound_sidecar(app, "temper-engine", engine_manifest)
    hook_digest = _bound_sidecar(app, "temper-hook", hook_manifest)

    # Do not use --deep or re-sign either manifest-bound sidecar.
    _run(["/usr/bin/codesign", "--force", "--sign", "-", "--timestamp=none", str(app)])
    _verify_sealed_app(app)
    if (
        _digest(app / "Contents" / "MacOS" / "temper-engine") != engine_digest
        or _digest(app / "Contents" / "MacOS" / "temper-hook") != hook_digest
    ):
        raise ValueError("development sealing changed a manifest-bound sidecar")

    with tempfile.TemporaryDirectory(prefix="temper-development-dmg-", dir=dmg.parent) as value:
        temporary = Path(value)
        contents = temporary / "contents"
        contents.mkdir()
        _run(["/usr/bin/ditto", str(app), str(contents / "Temper.app")])
        (contents / "Applications").symlink_to("/Applications")
        candidate = temporary / "Temper.dmg"
        _run(
            [
                "/usr/bin/hdiutil",
                "create",
                "-volname",
                "Temper",
                "-srcfolder",
                str(contents),
                "-format",
                "UDZO",
                "-fs",
                "HFS+",
                str(candidate),
            ],
            timeout=180,
        )
        mountpoint = temporary / "mounted"
        mountpoint.mkdir()
        attached = False
        try:
            _run(
                [
                    "/usr/bin/hdiutil",
                    "attach",
                    str(candidate),
                    "-mountpoint",
                    str(mountpoint),
                    "-readonly",
                    "-nobrowse",
                ],
                timeout=60,
            )
            attached = True
            mounted_app = mountpoint / "Temper.app"
            _verify_sealed_app(mounted_app)
            for relative in (
                "Contents/MacOS/Temper",
                "Contents/MacOS/temper-engine",
                "Contents/MacOS/temper-hook",
                "Contents/Info.plist",
                "Contents/_CodeSignature/CodeResources",
            ):
                if _digest(app / relative) != _digest(mounted_app / relative):
                    raise ValueError(f"DMG copy differs from sealed app: {relative}")
        finally:
            if attached:
                _run(["/usr/bin/hdiutil", "detach", str(mountpoint)], timeout=60)
        os.replace(candidate, dmg)

    return {
        "app_binary_sha256": _digest(app / "Contents" / "MacOS" / "Temper"),
        "engine_sha256": engine_digest,
        "hook_sha256": hook_digest,
        "dmg_sha256": _digest(dmg),
        "signature_state": "development-ad-hoc-sealed",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--dmg", type=Path, required=True)
    parser.add_argument("--engine-manifest", type=Path, required=True)
    parser.add_argument("--hook-manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = seal_development_bundle(
            app=args.app,
            dmg=args.dmg,
            engine_manifest=args.engine_manifest,
            hook_manifest=args.hook_manifest,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
