"""Fail-closed runtime, binary, and generated-schema pin verification."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Literal, Self

from pydantic import field_validator, model_validator

from adaptation_compiler_lab.domain.base import (
    FrozenModel,
    NonEmptyStr,
    SemVer,
    Sha256Digest,
)
from adaptation_compiler_lab.domain.values import strings_are_sorted_unique

DEFAULT_RUNTIME_LOCK: Final = Path(__file__).resolve().parent / "runtime_pins" / "milestone_4.json"
DEFAULT_HAIKU_DEVELOPMENT_RUNTIME_LOCK: Final = (
    Path(__file__).resolve().parent / "runtime_pins" / "claude_haiku_development.json"
)
DEFAULT_SOURCE_RUNTIME_LOCK: Final = (
    Path(__file__).resolve().parent / "runtime_pins" / "milestone_5_source.json"
)
DEFAULT_DOGFOOD_RUNTIME_LOCK: Final = (
    Path(__file__).resolve().parent / "runtime_pins" / "milestone_6a2b_codex_dogfood.json"
)
DEFAULT_DOGFOOD_WINDOWS_RUNTIME_LOCK: Final = (
    Path(__file__).resolve().parent / "runtime_pins" / "milestone_6a2b_codex_dogfood_windows.json"
)


def product_codex_runtime_locks(platform_name: str) -> tuple[Path, ...]:
    """Keep native product releases separate from frozen research locks."""

    root = Path(__file__).resolve().parent / "runtime_pins"
    if platform_name == "win32":
        return (root / "desktop_codex_windows_0_160_1.json", DEFAULT_DOGFOOD_WINDOWS_RUNTIME_LOCK)
    if platform_name == "darwin":
        return (root / "desktop_codex_macos_0_157_0.json",)
    return (DEFAULT_DOGFOOD_RUNTIME_LOCK,)


def select_product_codex_runtime_lock(executable: Path, platform_name: str) -> Path:
    """Admit only a checked-in exact binary and its regenerated protocol contract."""

    for path in product_codex_runtime_locks(platform_name):
        try:
            pin = load_dogfood_runtime_pins(path).codex
            verify_codex_runtime(executable, pin)
        except (OSError, RuntimeConformanceError):
            continue
        return path
    raise RuntimeConformanceError("installed Codex has no verified native product runtime lock")


def persistent_codex_runtime_lock_path(source: Path, state_root: Path) -> Path:
    """Bind a runtime to content-addressed data outside onefile extraction paths."""

    load_dogfood_runtime_pins(source)
    digest = sha256_file(source).removeprefix("sha256:")
    return state_root.resolve() / "runtime-pins" / f"{digest}.json"


def persist_codex_runtime_lock(
    source: Path, state_root: Path, *, staging_root: Path | None = None
) -> Path:
    """Copy an immutable pin before config enrollment, optionally into a restore stage."""

    final = persistent_codex_runtime_lock_path(source, state_root)
    destination = (staging_root.resolve() / "runtime-pins" / final.name) if staging_root else final
    if destination.parent.is_symlink():
        raise RuntimeConformanceError("runtime lock directory must not be a symlink")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.is_symlink():
        raise RuntimeConformanceError("persisted runtime lock must not be a symlink")
    if destination.exists():
        if sha256_file(destination) != sha256_file(source):
            raise RuntimeConformanceError("persisted runtime lock content changed")
        return final
    descriptor, temporary_name = tempfile.mkstemp(prefix=".runtime-pin-", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(source.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return final


class RuntimeConformanceError(RuntimeError):
    """A runtime cannot prove that it matches the frozen study contract."""


class ExecutablePin(FrozenModel):
    """One package and exact executable identity."""

    package: NonEmptyStr
    package_version: NonEmptyStr
    package_integrity: NonEmptyStr
    executable_sha256: Sha256Digest
    version_args: tuple[NonEmptyStr, ...]
    version_stdout: NonEmptyStr
    required_help_flags: tuple[NonEmptyStr, ...] = ()

    @field_validator("required_help_flags")
    @classmethod
    def help_flags_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("required help flags must be sorted and unique")
        return value


class CodexAppServerPin(FrozenModel):
    """Codex executable plus its version-generated app-server schema bundle."""

    executable: ExecutablePin
    schema_generation_args: tuple[NonEmptyStr, ...]
    schema_bundle_sha256: Sha256Digest
    schema_file_sha256: dict[str, Sha256Digest]

    @model_validator(mode="after")
    def schema_contract_is_safe(self) -> Self:
        if self.schema_generation_args.count("{output}") != 1:
            raise ValueError("Codex schema command must contain one {output} placeholder")
        if not self.schema_file_sha256:
            raise ValueError("Codex schema pin requires at least one exact file")
        for name in self.schema_file_sha256:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or name != path.as_posix():
                raise ValueError("Codex schema file pins must use safe POSIX-relative paths")
        return self


class ClaudeCodePin(FrozenModel):
    """Claude Code executable and target model identity."""

    executable: ExecutablePin
    model_id: Literal["claude-sonnet-5", "claude-haiku-4-5-20251001"]
    api_base_url: Literal["https://api.anthropic.com"]


class SandboxPin(FrozenModel):
    """Exact locally supplied Linux sandbox helpers."""

    bubblewrap: ExecutablePin
    socat: ExecutablePin


class NodeRuntimePin(FrozenModel):
    """Audited installer runtime used to materialize the npm packages."""

    version: SemVer
    distribution_sha256: Sha256Digest
    distribution_url: NonEmptyStr


class RuntimePinSet(FrozenModel):
    """Machine-readable Milestone 4 runtime lock."""

    lock_version: SemVer
    codex: CodexAppServerPin
    claude_code: ClaudeCodePin
    sandbox: SandboxPin
    node: NodeRuntimePin


class SourceRuntimePinSet(FrozenModel):
    """Machine-readable source-runtime lock added for real Desktop capture."""

    lock_version: SemVer
    codex_desktop: CodexAppServerPin


class DogfoodRuntimePinSet(FrozenModel):
    """Machine-readable current Codex runtime lock for the local product integration."""

    lock_version: SemVer
    codex: CodexAppServerPin


@dataclass(frozen=True)
class VerifiedCodexRuntime:
    """Verified Codex executable ready for an app-server connection."""

    executable: Path
    version: str
    schema_bundle_digest: Sha256Digest
    windows_interop: bool = False


@dataclass(frozen=True)
class VerifiedClaudeRuntime:
    """Verified Claude Code and sandbox helper paths."""

    executable: Path
    bubblewrap: Path
    socat: Path
    sandbox_library_path: Path
    version: str
    model_id: str
    api_base_url: str


def sha256_bytes(value: bytes) -> Sha256Digest:
    """Return a typed SHA-256 digest for bytes."""

    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def sha256_file(path: Path) -> Sha256Digest:
    """Hash an exact regular file without following a caller-controlled directory walk."""

    if not path.is_file():
        raise RuntimeConformanceError(f"required runtime file is unavailable: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def digest_tree(root: Path) -> Sha256Digest:
    """Hash relative names and bytes for every regular file in a generated tree."""

    if not root.is_dir():
        raise RuntimeConformanceError(f"schema bundle directory is unavailable: {root}")
    files = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    if not files:
        raise RuntimeConformanceError("generated schema bundle is empty")
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        raw_content = path.read_bytes()
        if path.suffix == ".json":
            try:
                content = json.dumps(
                    json.loads(raw_content),
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            except (UnicodeError, ValueError, TypeError) as exc:
                raise RuntimeConformanceError(
                    f"generated schema is not canonicalizable JSON: {path.name}"
                ) from exc
        else:
            content = raw_content
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def load_runtime_pins(path: Path = DEFAULT_RUNTIME_LOCK) -> RuntimePinSet:
    """Load the frozen runtime lock using strict, closed models."""

    try:
        return RuntimePinSet.model_validate_json(path.read_text(encoding="utf-8"), strict=True)
    except (OSError, ValueError) as exc:
        raise RuntimeConformanceError(f"invalid runtime pin file: {path}") from exc


def load_source_runtime_pins(
    path: Path = DEFAULT_SOURCE_RUNTIME_LOCK,
) -> SourceRuntimePinSet:
    """Load the separately frozen Desktop source-runtime lock."""

    try:
        return SourceRuntimePinSet.model_validate_json(
            path.read_text(encoding="utf-8"),
            strict=True,
        )
    except (OSError, ValueError) as exc:
        raise RuntimeConformanceError(f"invalid source runtime pin file: {path}") from exc


def load_dogfood_runtime_pins(
    path: Path = DEFAULT_DOGFOOD_RUNTIME_LOCK,
) -> DogfoodRuntimePinSet:
    """Load the separately versioned Codex dogfood runtime lock."""

    try:
        return DogfoodRuntimePinSet.model_validate_json(
            path.read_text(encoding="utf-8"),
            strict=True,
        )
    except (OSError, ValueError) as exc:
        raise RuntimeConformanceError(f"invalid dogfood runtime pin file: {path}") from exc


def _run_checked(
    command: list[str],
    *,
    timeout: float = 30.0,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=timeout,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise RuntimeConformanceError(f"runtime probe failed: {command[0]}") from exc
    if completed.returncode != 0:
        diagnostic = completed.stderr.strip()[:500]
        raise RuntimeConformanceError(
            f"runtime probe exited {completed.returncode}: {command[0]}: {diagnostic}"
        )
    return completed


def verify_executable(path: Path, pin: ExecutablePin) -> None:
    """Verify digest, exact version output, and required CLI flags."""

    resolved = path.expanduser().resolve()
    if not os.access(resolved, os.X_OK):
        raise RuntimeConformanceError(f"runtime executable is not executable: {resolved}")
    actual_digest = sha256_file(resolved)
    if actual_digest != pin.executable_sha256:
        raise RuntimeConformanceError(
            f"{pin.package} executable digest drift: expected {pin.executable_sha256}, "
            f"got {actual_digest}"
        )
    version = _run_checked([str(resolved), *pin.version_args]).stdout.strip()
    if version != pin.version_stdout:
        raise RuntimeConformanceError(
            f"{pin.package} version drift: expected {pin.version_stdout!r}, got {version!r}"
        )
    if pin.required_help_flags:
        help_text = _run_checked([str(resolved), "--help"]).stdout
        missing = [flag for flag in pin.required_help_flags if flag not in help_text]
        if missing:
            raise RuntimeConformanceError(
                f"{pin.package} is missing frozen CLI flags: {', '.join(missing)}"
            )


def _as_windows_interop_path(path: Path) -> str:
    """Convert a resolved WSL DrvFS path without invoking an unpinned helper."""

    resolved = path.expanduser().resolve()
    parts = resolved.parts
    if (
        len(parts) < 4
        or parts[0] != "/"
        or parts[1] != "mnt"
        or len(parts[2]) != 1
        or not parts[2].isalpha()
    ):
        raise RuntimeConformanceError(
            "Windows-interoperable Codex paths must resolve below /mnt/<drive>"
        )
    drive = parts[2].upper()
    remainder = "\\".join(parts[3:])
    return f"{drive}:\\{remainder}"


def verify_codex_runtime(
    path: Path,
    pin: CodexAppServerPin,
    *,
    windows_interop: bool = False,
) -> VerifiedCodexRuntime:
    """Regenerate and verify Codex's complete app-server schema bundle."""

    resolved = path.expanduser().resolve()
    if windows_interop and resolved.suffix.casefold() != ".exe":
        raise RuntimeConformanceError("Windows-interoperable Codex must be an .exe")
    verify_executable(resolved, pin.executable)
    temporary_parent = resolved.parent if windows_interop else None
    with tempfile.TemporaryDirectory(
        prefix="acl-codex-schema-",
        dir=temporary_parent,
    ) as temporary:
        schema_root = Path(temporary) / "schemas"
        output_argument = (
            _as_windows_interop_path(schema_root) if windows_interop else str(schema_root)
        )
        command = [
            str(resolved),
            *[
                output_argument if argument == "{output}" else argument
                for argument in pin.schema_generation_args
            ],
        ]
        _run_checked(command, timeout=60.0)
        actual_bundle = digest_tree(schema_root)
        if actual_bundle != pin.schema_bundle_sha256:
            raise RuntimeConformanceError(
                "Codex generated schema bundle drift: "
                f"expected {pin.schema_bundle_sha256}, got {actual_bundle}"
            )
        for relative, expected in sorted(pin.schema_file_sha256.items()):
            actual = sha256_file(schema_root / PurePosixPath(relative))
            if actual != expected:
                raise RuntimeConformanceError(
                    f"Codex generated schema drift for {relative}: "
                    f"expected {expected}, got {actual}"
                )
    return VerifiedCodexRuntime(
        executable=resolved,
        version=pin.executable.package_version,
        schema_bundle_digest=pin.schema_bundle_sha256,
        windows_interop=windows_interop,
    )


def verify_claude_runtime(
    *,
    executable: Path,
    bubblewrap: Path,
    socat: Path,
    sandbox_library_path: Path,
    pin: ClaudeCodePin,
    sandbox_pin: SandboxPin,
) -> VerifiedClaudeRuntime:
    """Verify Claude Code, helper binaries, and a functional user-namespace sandbox."""

    resolved = executable.expanduser().resolve()
    resolved_bwrap = bubblewrap.expanduser().resolve()
    resolved_socat = socat.expanduser().resolve()
    resolved_library_path = sandbox_library_path.expanduser().resolve()
    if not resolved_library_path.is_dir():
        raise RuntimeConformanceError("sandbox helper library directory is unavailable")
    verify_executable(resolved, pin.executable)
    verify_executable(resolved_bwrap, sandbox_pin.bubblewrap)
    socat_environment = {
        "PATH": os.environ.get("PATH", ""),
        "LD_LIBRARY_PATH": str(resolved_library_path),
    }
    if sha256_file(resolved_socat) != sandbox_pin.socat.executable_sha256:
        raise RuntimeConformanceError("socat executable digest drift")
    socat_version = _run_checked(
        [str(resolved_socat), *sandbox_pin.socat.version_args],
        env=socat_environment,
    ).stdout
    if not socat_version.startswith(sandbox_pin.socat.version_stdout):
        raise RuntimeConformanceError("socat version drift")
    _run_checked(
        [
            str(resolved_bwrap),
            "--ro-bind",
            "/",
            "/",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--unshare-user",
            "--unshare-pid",
            "--die-with-parent",
            "/bin/true",
        ],
        timeout=10.0,
    )
    return VerifiedClaudeRuntime(
        executable=resolved,
        bubblewrap=resolved_bwrap,
        socat=resolved_socat,
        sandbox_library_path=resolved_library_path,
        version=pin.executable.package_version,
        model_id=str(pin.model_id),
        api_base_url=str(pin.api_base_url),
    )
