def build_release_brief(service: str, region: str, command: str) -> tuple[str, ...]:
    return (
        f"Purpose: release {service} in {region}.",
        f"Run this command: {command}",
        f"Service: {service} | Region: {region}",
    )
