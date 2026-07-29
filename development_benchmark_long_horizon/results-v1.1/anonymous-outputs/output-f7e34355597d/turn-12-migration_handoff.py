import shlex


def migration_handoff(source: str, destination: str) -> tuple[str, ...]:
    quoted_source = shlex.quote(source)
    quoted_destination = shlex.quote(destination)
    return (
        "Purpose: Copy the migration directory to the destination.",
        f"test -d {quoted_source}",
        f"cp -R {quoted_source} {quoted_destination}",
    )
