def render_transfer(source: str, destination: str) -> tuple[str, ...]:
    return (
        "Copy the release into place.",
        f"test -f {source}",
        f"cp {source} {destination}",
    )
