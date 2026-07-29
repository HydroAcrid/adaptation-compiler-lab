import shlex


def migration_handoff(source: str, destination: str) -> tuple[str, ...]:
    quoted_source = shlex.quote(source)
    quoted_destination = shlex.quote(destination)
    return (
        "Copy the migration directory to the new location so the migration can be run there.",
        f"test -d {quoted_source}",
        f"cp -R {quoted_source} {quoted_destination}",
    )
