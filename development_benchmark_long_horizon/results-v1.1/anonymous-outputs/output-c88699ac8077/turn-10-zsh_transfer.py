import shlex


def render_transfer(source: str, destination: str) -> tuple[str, ...]:
    quoted_source = shlex.quote(source)
    quoted_destination = shlex.quote(destination)
    return (
        "On macOS, copy the supplied file into the release location.",
        f"test -f {quoted_source}",
        f"cp {quoted_source} {quoted_destination}",
    )
