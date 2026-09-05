"""Clean-runner admission smoke for one target-native Temper macOS candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import plistlib
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Final, Literal

EXPECTED_PROTOCOL: Final = "temper-engine-protocol/v1"
EXPECTED_BUNDLE_ID: Final = "com.hydroacrid.temper"
EXPECTED_MINIMUM_SYSTEM_VERSION: Final = "13.0"
SignaturePolicy = Literal["development", "trusted"]


def _run(
    command: list[str],
    *,
    timeout: int = 30,
    check: bool = True,
    input_text: str | None = None,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
        input=input_text,
        env=environment,
    )


def _arm64_macho(path: Path) -> None:
    if not path.is_file():
        raise ValueError("required macOS package binary is unavailable")
    file_result = _run(["/usr/bin/file", "-b", str(path)])
    arch_result = _run(["/usr/bin/lipo", "-archs", str(path)])
    if "Mach-O" not in file_result.stdout or arch_result.stdout.strip().split() != ["arm64"]:
        raise ValueError("macOS package binaries must be arm64-only Mach-O files")


def _require_developer_id(path: Path, *, deep: bool = False) -> None:
    verify = ["/usr/bin/codesign", "--verify"]
    if deep:
        verify.append("--deep")
    verify.extend(("--strict", "--verbose=4", str(path)))
    _run(verify)
    identity = _run(
        ["/usr/bin/codesign", "--display", "--verbose=4", str(path)],
        check=True,
    )
    details = identity.stdout + identity.stderr
    if "Authority=Developer ID Application:" not in details:
        raise ValueError("trusted policy requires a Developer ID Application identity")


def _verify_signature(app: Path, dmg: Path, *, policy: SignaturePolicy) -> str:
    if policy == "development":
        observed = _run(
            ["/usr/bin/codesign", "--display", "--verbose=2", str(app)],
            check=False,
        )
        return "unsigned" if observed.returncode else "development-signed"
    _require_developer_id(app, deep=True)
    _require_developer_id(app / "Contents" / "MacOS" / "temper-engine")
    _require_developer_id(app / "Contents" / "MacOS" / "temper-hook")
    _require_developer_id(dmg)
    _run(["/usr/sbin/spctl", "--assess", "--type", "execute", "--verbose=4", str(app)])
    _run(
        [
            "/usr/sbin/spctl",
            "--assess",
            "--type",
            "open",
            "--context",
            "context:primary-signature",
            "--verbose=4",
            str(dmg),
        ]
    )
    _run(["/usr/bin/xcrun", "stapler", "validate", str(app)])
    _run(["/usr/bin/xcrun", "stapler", "validate", str(dmg)])
    return "developer-id-notarized"


def _verify_bundle_metadata(app: Path) -> None:
    info_path = app / "Contents" / "Info.plist"
    with info_path.open("rb") as source:
        info = plistlib.load(source)
    if info.get("CFBundleIdentifier") != EXPECTED_BUNDLE_ID:
        raise ValueError("macOS bundle identifier drifted")
    if info.get("LSMinimumSystemVersion") != EXPECTED_MINIMUM_SYSTEM_VERSION:
        raise ValueError("macOS minimum system version drifted")


def _verify_engine(
    sidecar: Path,
    manifest_path: Path,
    *,
    expected_version: str,
) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("engine manifest must be an object")
    actual_digest = hashlib.sha256(sidecar.read_bytes()).hexdigest()
    if (
        manifest.get("target_triple") != "aarch64-apple-darwin"
        or manifest.get("engine_version") != expected_version
        or manifest.get("binary_sha256") != actual_digest
        or manifest.get("minimum_system_version") != EXPECTED_MINIMUM_SYSTEM_VERSION
    ):
        raise ValueError("bundled sidecar does not match its exact Apple manifest")
    requests = (
        {
            "protocol_version": EXPECTED_PROTOCOL,
            "request_id": "apple-package-smoke",
            "method": "system.handshake",
            "params": {},
            "expected_snapshot_digest": None,
            "idempotency_key": None,
        },
        {
            "protocol_version": EXPECTED_PROTOCOL,
            "request_id": "apple-package-smoke-setup",
            "method": "setup.status",
            "params": {},
            "expected_snapshot_digest": None,
            "idempotency_key": None,
        },
    )
    with tempfile.TemporaryDirectory(prefix="temper-apple-engine-") as profile:
        profile_root = Path(profile).resolve()
        environment = os.environ.copy()
        for name in (
            "TEMPER_RUNTIME_CONFIG",
            "TEMPER_PREDECESSOR_CONFIG",
            "CODEX_HOME",
            "CLAUDE_CONFIG_DIR",
            "OPENAI_API_KEY",
            "CODEX_API_KEY",
            "CLAUDE_API_KEY",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_BASE_URL",
            "ANTHROPIC_BEDROCK_BASE_URL",
            "ANTHROPIC_VERTEX_BASE_URL",
            "OPENAI_BASE_URL",
        ):
            environment.pop(name, None)
        environment.update(
            {
                "HOME": str(profile_root),
                "USERPROFILE": str(profile_root),
                "APPDATA": str(profile_root / "AppData" / "Roaming"),
                "LOCALAPPDATA": str(profile_root / "AppData" / "Local"),
                "XDG_CONFIG_HOME": str(profile_root / ".config"),
                "XDG_DATA_HOME": str(profile_root / ".local" / "share"),
            }
        )
        result = _run(
            [str(sidecar)],
            input_text="".join(
                json.dumps(request, separators=(",", ":")) + "\n" for request in requests
            ),
            environment=environment,
            timeout=15,
        )
    lines = result.stdout.splitlines()
    response = json.loads(lines[0]) if len(lines) == 2 else None
    setup_response = json.loads(lines[1]) if len(lines) == 2 else None
    handshake = response.get("result") if isinstance(response, dict) else None
    if (
        not isinstance(response, dict)
        or response.get("ok") is not True
        or response.get("protocol_version") != EXPECTED_PROTOCOL
        or response.get("request_id") != "apple-package-smoke"
        or not isinstance(handshake, dict)
        or handshake.get("engine_version") != expected_version
        or handshake.get("configured") is not False
        or handshake.get("mutation_enabled") is not False
        or handshake.get("snapshot_schema_digest") != manifest.get("snapshot_schema_digest")
    ):
        raise ValueError("bundled sidecar failed the exact unconfigured handshake")
    setup = setup_response.get("result") if isinstance(setup_response, dict) else None
    if (
        not isinstance(setup_response, dict)
        or setup_response.get("ok") is not True
        or setup_response.get("protocol_version") != EXPECTED_PROTOCOL
        or setup_response.get("request_id") != "apple-package-smoke-setup"
        or not isinstance(setup, dict)
        or setup.get("configuration_state") != "unconfigured"
        or setup.get("raw_payloads_exposed") is not False
        or not str(setup_response.get("snapshot_digest", "")).startswith("sha256:")
    ):
        raise ValueError("bundled sidecar failed first-run setup admission")
    return manifest


def _verify_hook(sidecar: Path, manifest_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("hook manifest must be an object")
    actual_digest = hashlib.sha256(sidecar.read_bytes()).hexdigest()
    if (
        manifest.get("protocol_version") != "temper-hook-ipc/v1"
        or manifest.get("target_triple") != "aarch64-apple-darwin"
        or manifest.get("binary_sha256") != actual_digest
        or manifest.get("minimum_system_version") != EXPECTED_MINIMUM_SYSTEM_VERSION
    ):
        raise ValueError("bundled hook helper does not match its exact Apple manifest")
    return manifest


def _verify_dmg(dmg: Path, mountpoint: Path) -> None:
    mounted = False
    mountpoint.mkdir(parents=True)
    try:
        _run(
            [
                "/usr/bin/hdiutil",
                "attach",
                str(dmg),
                "-mountpoint",
                str(mountpoint),
                "-readonly",
                "-nobrowse",
            ],
            timeout=60,
        )
        mounted = True
        if not (mountpoint / "Temper.app").is_dir():
            raise ValueError("DMG does not contain Temper.app")
    finally:
        if mounted:
            _run(["/usr/bin/hdiutil", "detach", str(mountpoint)], check=False, timeout=30)


def _launch_first_run(app: Path, scratch: Path, window_probe: Path) -> None:
    executable = app / "Contents" / "MacOS" / "Temper"
    environment = os.environ.copy()
    environment["HOME"] = str(scratch / "home")
    for name in (
        "TEMPER_RUNTIME_CONFIG",
        "TEMPER_PREDECESSOR_CONFIG",
        "CODEX_HOME",
        "CLAUDE_CONFIG_DIR",
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "CLAUDE_API_KEY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_BEDROCK_BASE_URL",
        "ANTHROPIC_VERTEX_BASE_URL",
        "OPENAI_BASE_URL",
    ):
        environment.pop(name, None)
    Path(environment["HOME"]).mkdir(parents=True)
    process = subprocess.Popen(
        [str(executable)],
        cwd=app.parent,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(6)
        if process.poll() is not None:
            raise ValueError("Temper exited before first-run rendering completed")
        _run(["/usr/bin/swift", str(window_probe), str(process.pid)], timeout=60)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def run_smoke(
    *,
    app: Path,
    dmg: Path,
    manifest: Path,
    hook_manifest: Path,
    expected_version: str,
    signature_policy: SignaturePolicy,
    window_probe: Path,
) -> dict[str, object]:
    if platform.system() != "Darwin" or platform.machine().lower() not in {"arm64", "aarch64"}:
        raise ValueError("Apple package smoke requires a native Apple Silicon runner")
    app = app.expanduser().resolve(strict=True)
    dmg = dmg.expanduser().resolve(strict=True)
    manifest = manifest.expanduser().resolve(strict=True)
    hook_manifest = hook_manifest.expanduser().resolve(strict=True)
    window_probe = window_probe.expanduser().resolve(strict=True)
    main_binary = app / "Contents" / "MacOS" / "Temper"
    sidecar = app / "Contents" / "MacOS" / "temper-engine"
    hook_helper = app / "Contents" / "MacOS" / "temper-hook"
    _arm64_macho(main_binary)
    _arm64_macho(sidecar)
    _arm64_macho(hook_helper)
    _verify_bundle_metadata(app)
    bound_manifest = _verify_engine(sidecar, manifest, expected_version=expected_version)
    bound_hook_manifest = _verify_hook(hook_helper, hook_manifest)
    signature = _verify_signature(app, dmg, policy=signature_policy)
    with tempfile.TemporaryDirectory(prefix="temper-apple-smoke-") as value:
        scratch = Path(value).resolve()
        _verify_dmg(dmg, scratch / "mounted")
        _launch_first_run(app, scratch, window_probe)
    return {
        "status": "passed",
        "architecture": "arm64",
        "app_version": expected_version,
        "engine_sha256": bound_manifest["binary_sha256"],
        "hook_helper_sha256": bound_hook_manifest["binary_sha256"],
        "signature_policy": signature_policy,
        "signature_state": signature,
        "first_run_window_visible": True,
        "temporary_state_removed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--dmg", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--hook-manifest", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument(
        "--signature-policy",
        choices=("development", "trusted"),
        default="trusted",
    )
    parser.add_argument(
        "--window-probe",
        type=Path,
        default=Path(__file__).with_name("window_probe.swift"),
    )
    args = parser.parse_args()
    try:
        receipt = run_smoke(
            app=args.app,
            dmg=args.dmg,
            manifest=args.manifest,
            hook_manifest=args.hook_manifest,
            expected_version=args.expected_version,
            signature_policy=args.signature_policy,
            window_probe=args.window_probe,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
