"""Recovery handoff renderer."""


def render_recovery_handoff(purpose: str, commands: tuple[str, ...]) -> str:
    lines = [purpose, "", "Commands:"]
    lines.extend(f"$ {command}" for command in commands)
    return "\n".join(lines)
