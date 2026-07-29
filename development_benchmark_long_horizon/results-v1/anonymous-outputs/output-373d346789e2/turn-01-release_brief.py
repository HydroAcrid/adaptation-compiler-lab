def build_release_brief(service: str, region: str, command: str) -> tuple[str, ...]:
    return (
        f"Purpose: Release the {service} service in the {region} region.",
        f"Operational step: Run this command: {command}",
        f"Service: {service}",
        f"Region: {region}",
    )
