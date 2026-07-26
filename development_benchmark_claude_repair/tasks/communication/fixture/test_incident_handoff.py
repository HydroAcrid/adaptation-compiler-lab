from __future__ import annotations

import inspect
import shlex
import unittest

from incident_handoff import build_incident_handoff


def _command_lines(handoff: str) -> tuple[str, str]:
    lines = handoff.splitlines()
    command_index = next(
        index for index, line in enumerate(lines) if line.casefold().startswith("commands")
    )
    commands = tuple(line for line in lines[command_index + 1 :] if line.strip())
    if len(commands) != 2:
        raise AssertionError(f"expected exactly two commands, received {commands!r}")
    return commands


class IncidentHandoffTests(unittest.TestCase):
    def test_reason_precedes_commands(self) -> None:
        purpose = "Collect logs before restarting the failed service."
        handoff = build_incident_handoff(
            purpose,
            "/Users/Shared/Service Logs/current.log",
            "/Users/Shared/Incident Bundle/current.log",
        )

        self.assertLess(handoff.index(purpose), handoff.casefold().index("commands"))

    def test_output_is_deterministic_and_signature_is_preserved(self) -> None:
        arguments = (
            "Preserve evidence for the incident review.",
            "/tmp/service.log",
            "/tmp/incident bundle/service.log",
        )

        self.assertEqual(build_incident_handoff(*arguments), build_incident_handoff(*arguments))
        self.assertEqual(
            tuple(inspect.signature(build_incident_handoff).parameters),
            ("purpose", "log_path", "bundle_path"),
        )

    def test_commands_are_zsh_compatible(self) -> None:
        handoff = build_incident_handoff("Collect evidence.", "/tmp/input.log", "/tmp/output.log")
        verify, copy = _command_lines(handoff)
        verify_argv = shlex.split(verify)
        copy_argv = shlex.split(copy)

        self.assertEqual(verify_argv[0], "test")
        self.assertIn(verify_argv[1], ("-e", "-f"))
        self.assertEqual(verify_argv[2:], ["/tmp/input.log"])
        self.assertIn(copy_argv[0], ("cp", "ditto"))
        if copy_argv[0] == "cp" and copy_argv[1:2] == ["--"]:
            copy_argv.pop(1)
        self.assertEqual(copy_argv[1:], ["/tmp/input.log", "/tmp/output.log"])
        self.assertNotIn("Test-Path", handoff)
        self.assertNotIn("Copy-Item", handoff)

    def test_paths_are_rendered_as_shell_literals(self) -> None:
        log_path = "/Users/Shared/O'Brien Logs/$(touch injected).log"
        bundle_path = "/Users/Shared/Incident Bundle/worker; changed 'today'.log"
        handoff = build_incident_handoff("Collect evidence.", log_path, bundle_path)
        verify, copy = _command_lines(handoff)

        self.assertIn(shlex.quote(log_path), verify)
        self.assertIn(shlex.quote(log_path), copy)
        self.assertIn(shlex.quote(bundle_path), copy)
        self.assertEqual(shlex.split(verify)[-1], log_path)
        self.assertEqual(shlex.split(copy)[-2:], [log_path, bundle_path])


if __name__ == "__main__":
    unittest.main()
