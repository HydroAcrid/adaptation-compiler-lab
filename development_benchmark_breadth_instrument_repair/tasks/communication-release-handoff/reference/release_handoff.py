"""Render a release handoff without executing it."""

import shlex


def render_release_handoff(
    artifact_path: str,
    destination_path: str,
    target_shell: str = "zsh",
) -> str:
    if target_shell != "zsh":
        raise ValueError("render_release_handoff supports only zsh")
    artifact = shlex.quote(artifact_path)
    destination = shlex.quote(destination_path)
    return (
        "Transfer the signed release artifact to the operator's destination.\n\n"
        f"cp -pPR -- {artifact} {destination}\n"
        f"test -e {destination}"
    )
