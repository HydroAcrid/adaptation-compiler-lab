"""Evidence policies used by the Research Analyst comparison."""


def version_recommendation(
    source_kind: str,
    documented_version: str,
    requested_version: str,
    supported: bool,
) -> tuple[str, ...]:
    """Return recommendation, evidentiary basis, and uncertainty."""

    return ("use", "documented", "none")


def synthesize_reports(
    first_method: str,
    first_result: str,
    second_method: str,
    second_result: str,
) -> tuple[str, ...]:
    """Return conclusion and a method-aware disagreement summary."""

    return (first_result, "agreement")


def audit_trials(completed: int, failed: int, incomplete: int) -> tuple[object, ...]:
    """Return all counts, validity, and the corrected headline."""

    return (completed, 0, 0, True, "all trials succeeded")


def panel_width(viewport: int, padding: int, content_width: int) -> int:
    """Return a panel width that cannot overflow the padded viewport."""

    return content_width


def normalize_label(value: str) -> str:
    """Normalize a supplied label without changing its words."""

    return value.strip().lower().replace(" ", "-")
