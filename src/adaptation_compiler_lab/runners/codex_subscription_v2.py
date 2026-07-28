"""Versioned Codex subscription runner without visible workspace control surfaces."""

from __future__ import annotations

from pathlib import Path

from adaptation_compiler_lab.runners.codex_subscription import (
    _OUTER_BWRAP,
    _OUTER_CODEX,
    _OUTER_CODEX_HOME,
    _OUTER_RUNTIME_ROOT,
    _OUTER_WORKSPACE,
    _WSL_RESOLV_CONF,
    CodexSubscriptionError,
    CodexSubscriptionRunner,
)


class CodexSubscriptionRunnerV2(CodexSubscriptionRunner):
    """Keep agent control surfaces absent while preserving registered source writes."""

    def _outer_sandbox_command(
        self,
        *,
        inner_command: list[str],
        codex_home: Path,
        workspace: Path,
        allowed_change_paths: tuple[str, ...],
    ) -> list[str]:
        if self._bubblewrap is None:
            return inner_command
        writable_files = tuple(
            sorted(
                {
                    (
                        (workspace / value).resolve(),
                        _OUTER_WORKSPACE / value,
                    )
                    for value in allowed_change_paths
                }
            )
        )
        if not writable_files:
            raise CodexSubscriptionError("outer target sandbox requires an allowed file")
        if any(
            not host_path.is_file()
            or not host_path.is_relative_to(workspace)
            or not sandbox_path.is_relative_to(_OUTER_WORKSPACE)
            for host_path, sandbox_path in writable_files
        ):
            raise CodexSubscriptionError("outer target writable file is unsafe")
        writable_args = [
            value
            for host_path, sandbox_path in writable_files
            for value in ("--bind", str(host_path), str(sandbox_path))
        ]
        return [
            str(self._bubblewrap),
            "--unshare-all",
            "--share-net",
            "--die-with-parent",
            "--new-session",
            "--ro-bind",
            "/usr",
            "/usr",
            "--symlink",
            "usr/bin",
            "/bin",
            "--symlink",
            "usr/lib",
            "/lib",
            "--symlink",
            "usr/lib64",
            "/lib64",
            "--symlink",
            "usr/sbin",
            "/sbin",
            "--ro-bind",
            "/etc",
            "/etc",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--dir",
            "/mnt",
            "--dir",
            str(_WSL_RESOLV_CONF.parent),
            "--ro-bind",
            str(_WSL_RESOLV_CONF),
            str(_WSL_RESOLV_CONF),
            "--dir",
            "/opt",
            "--dir",
            str(_OUTER_RUNTIME_ROOT),
            "--dir",
            str(_OUTER_CODEX_HOME),
            "--dir",
            str(_OUTER_WORKSPACE),
            "--ro-bind",
            str(self._executable),
            str(_OUTER_CODEX),
            "--ro-bind",
            str(self._bubblewrap),
            str(_OUTER_BWRAP),
            "--bind",
            str(codex_home),
            str(_OUTER_CODEX_HOME),
            "--ro-bind",
            str(workspace),
            str(_OUTER_WORKSPACE),
            *writable_args,
            "--chdir",
            str(_OUTER_WORKSPACE),
            "--",
            *inner_command,
        ]
