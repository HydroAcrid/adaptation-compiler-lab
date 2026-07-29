def migration_handoff(source: str, destination: str) -> tuple[str, ...]:
    return (
        f"test -d {source}",
        f"cp -R {source} {destination}",
        "This moves the migration bundle.",
    )
