from adaptation_compiler_lab.benchmark.command_audit import audit_target_commands


def _events(command: str) -> tuple[dict[str, object], ...]:
    return (
        {
            "item": {
                "command": command,
                "type": "command_execution",
            }
        },
    )


def test_command_audit_allows_virtual_workspace_reads() -> None:
    assert audit_target_commands(_events("find /workspace -maxdepth 3 -type f"))[1] == ()


def test_command_audit_rejects_absolute_and_relative_control_surfaces() -> None:
    for command in (
        "find /workspace/.codex -type f",
        "find .agents .codex -type f",
        "find ./.agents -type f",
    ):
        assert audit_target_commands(_events(command))[1] == (
            "ephemeral control surface inspection",
        )


def test_command_audit_rejects_host_and_network_commands() -> None:
    assert audit_target_commands(_events("find / -maxdepth 2"))[1] == (
        "host or parent path access",
    )
    assert audit_target_commands(_events("curl https://example.invalid"))[1] == (
        "forbidden command family",
    )
