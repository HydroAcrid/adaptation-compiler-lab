"""Recovery handoff renderer."""


def render_recovery_handoff(purpose: str, commands: tuple[str, ...]) -> str:
    lines = ["Commands:"]
    lines.extend(f"$ {command}" for command in commands)
    lines.extend(("", "Reason:", purpose))
    return "\n".join(lines)
