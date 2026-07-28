"""Migration command guide."""

import shlex


def build_copy_guide(
    source_path: str,
    destination_path: str,
    target_shell: str = "zsh",
) -> str:
    if target_shell != "zsh":
        raise ValueError("unsupported target shell")
    source = shlex.quote(source_path)
    destination = shlex.quote(destination_path)
    return (
        "Copy the release data to the macOS destination and verify it exists.\n\n"
        f"cp -a -- {source} {destination}\n"
        f"test -e {destination}"
    )
