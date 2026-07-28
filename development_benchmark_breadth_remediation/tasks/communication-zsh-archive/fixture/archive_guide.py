"""Render an archive-copy handoff without executing it."""


def build_archive_guide(
    source_path: str,
    destination_path: str,
    target_shell: str = "zsh",
) -> str:
    return (
        f"Copy-Item -Path {source_path} -Destination {destination_path}\n"
        f"Test-Path {destination_path}\n"
        "Move the release archive."
    )
