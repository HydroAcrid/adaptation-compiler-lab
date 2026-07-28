"""Render an archive-copy handoff without executing it."""

import shlex


def build_archive_guide(
    source_path: str,
    destination_path: str,
    target_shell: str = "zsh",
) -> str:
    if target_shell != "zsh":
        raise ValueError("only zsh handoffs are supported")
    source = shlex.quote(source_path)
    destination = shlex.quote(destination_path)
    return (
        "Copy the release tree while preserving metadata and links, then verify it.\n\n"
        f"cp -a -- {source} {destination}\n"
        f"test -e {destination}"
    )
