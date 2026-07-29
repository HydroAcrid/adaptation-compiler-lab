import shlex


def render_transfer(source: str, destination: str) -> tuple[str, ...]:
    quoted_source = shlex.quote(source)
    quoted_destination = shlex.quote(destination)
    return (
        "Copy the release into place.",
        f"test -f {quoted_source}",
        f"cp {quoted_source} {quoted_destination}",
    )
