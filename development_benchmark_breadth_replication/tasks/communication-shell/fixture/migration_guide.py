"""Migration command guide."""


def build_copy_guide(
    source_path: str,
    destination_path: str,
    target_shell: str = "zsh",
) -> str:
    return (
        f"Copy-Item -Path {source_path} -Destination {destination_path}\n"
        f"Test-Path {destination_path}\n"
        "Copy the release data and verify the destination."
    )
