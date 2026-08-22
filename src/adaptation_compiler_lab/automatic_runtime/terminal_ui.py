"""Pure raw-free terminal renderers for Temper's review-mode alpha surface."""

from __future__ import annotations

from io import StringIO
from typing import Literal

from rich import box
from rich.console import Console, Group, RenderableType
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from adaptation_compiler_lab.automatic_runtime.product_dogfood import (
    ActiveAdaptationCard,
    ReviewProposalCard,
    TerminalAlphaSnapshot,
)
from adaptation_compiler_lab.domain import Scope

TerminalView = Literal["status", "review", "adaptations", "history", "health", "gate"]


def _capture(renderable: RenderableType, *, width: int, color: bool) -> str:
    stream = StringIO()
    console = Console(
        file=stream,
        width=max(60, width),
        color_system="standard" if color else None,
        force_terminal=color,
        no_color=not color,
        highlight=False,
        legacy_windows=False,
    )
    console.print(renderable)
    return stream.getvalue()


def _status(value: bool) -> Text:
    return Text("OK" if value else "ACTION", style="green" if value else "yellow")


def _scope_text(scope: Scope) -> str:
    labels = (
        ("subjects", scope.subject_ids),
        ("projects", scope.project_ids),
        ("tasks", scope.task_classes),
        ("targets", scope.target_families),
        ("environments", scope.environment_ids),
        ("when", scope.activation_conditions),
        ("excluding", scope.exclusions),
    )
    parts = [f"{name}={','.join(values)}" for name, values in labels if values]
    return "; ".join(parts) if parts else "global registered scope"


def _progress_table(snapshot: TerminalAlphaSnapshot) -> Table:
    gate = snapshot.review_mode.gate
    table = Table(box=box.SIMPLE, expand=True, show_header=False, pad_edge=False)
    table.add_column("Measure", ratio=3)
    table.add_column("Progress", ratio=2, justify="right")
    table.add_row(
        "Eligible interactions",
        f"{gate.eligible_interaction_count} / {gate.goal_interaction_count}",
    )
    table.add_row("Distinct dates", f"{gate.active_date_count} / {gate.minimum_active_dates}")
    table.add_row(
        "Activation attempts", f"{gate.activation_count} / {gate.minimum_activation_count}"
    )
    table.add_row("Rated activations", str(gate.rated_activation_count))
    table.add_row("Correct activations", str(gate.correct_activation_count))
    table.add_row("Evidence ready", "YES" if gate.evidence_ready else "NO")
    return table


def _allowance_table(snapshot: TerminalAlphaSnapshot) -> Table:
    table = Table(box=box.SIMPLE, expand=True, pad_edge=False)
    table.add_column("Allowance")
    table.add_column("Observed", justify="right")
    table.add_column("State", justify="right")
    labels = {
        "missed_learning": "Missed learning",
        "false_learning": "False learning",
        "false_activation": "False activation",
    }
    for item in snapshot.allowances:
        style = (
            "green" if item.state == "available" else "yellow" if item.state == "used" else "red"
        )
        table.add_row(
            labels[item.name],
            f"{item.observed} / {item.maximum}",
            Text(item.state.upper(), style=style),
        )
    return table


def _inbox_table(snapshot: TerminalAlphaSnapshot) -> Table:
    daily = snapshot.review_mode
    table = Table(box=box.SIMPLE, expand=True, show_header=False, pad_edge=False)
    table.add_column("Inbox", ratio=3)
    table.add_column("Count", justify="right")
    table.add_row("Pending reviews", str(daily.metrics.pending_review_count))
    table.add_row("Awaiting activation feedback", str(daily.metrics.pending_feedback_count))
    table.add_row("Active adaptations", str(daily.active_artifact_count))
    table.add_row(
        "Latest delivered projection",
        f"{snapshot.latest_delivered_projection_utf8_bytes} bytes",
    )
    return table


def dashboard(snapshot: TerminalAlphaSnapshot) -> Group:
    daily = snapshot.review_mode
    all_used = all(item.state == "used" for item in snapshot.allowances)
    exceeded = any(item.state == "exceeded" for item in snapshot.allowances)
    if exceeded:
        attention = "The active product gate has exceeded a frozen error allowance."
        attention_style = "bold red"
    elif all_used:
        attention = "All current error allowances have been used; another incident fails this gate."
        attention_style = "bold yellow"
    else:
        attention = "Review mode is active. Proposed learning remains inactive until approved."
        attention_style = "cyan"
    header = Text()
    header.append("Temper", style="bold cyan")
    header.append(f"  {daily.subject_id} · Codex · review mode\n")
    header.append(
        f"Detector: {daily.detector_mode.value}  Generation: {daily.generation}  "
        f"Projects: {len(snapshot.configured_project_ids)}"
    )
    health = Table(box=box.SIMPLE, expand=True, show_header=False, pad_edge=False)
    health.add_column("Component", ratio=3)
    health.add_column("State", justify="right")
    health.add_row("Local credential", _status(daily.credential_enrolled))
    health.add_row("Background watcher", _status(daily.watcher_active))
    health.add_row("Automatic promotion", Text("OFF", style="green"))
    next_action = "\n".join(f"• {escape(item)}" for item in daily.next_actions)
    footer = Text(
        "Commands: temper poll · temper review · temper adaptations · temper gate · temper health",
        style="dim",
    )
    return Group(
        Panel(header, border_style="cyan"),
        Panel(_progress_table(snapshot), title="Ordinary-use gate", border_style="blue"),
        Panel(_inbox_table(snapshot), title="Today", border_style="blue"),
        Panel(Text(attention, style=attention_style), title="Attention"),
        Panel(_allowance_table(snapshot), title="Error allowances"),
        Panel(health, title="Local health"),
        Panel(next_action, title="Next"),
        footer,
    )


def _proposal_panel(card: ReviewProposalCard, *, number: int) -> Panel:
    body = Table(box=None, show_header=False, pad_edge=False, expand=True)
    body.add_column("Field", style="bold", width=18)
    body.add_column("Value", overflow="fold")
    behavior = f"Revoke {card.affected_artifact_id}" if card.behavior is None else card.behavior
    body.add_row("Behavior", escape(behavior))
    body.add_row("Route", "revocation" if card.route is None else card.route.value)
    body.add_row("Layer", card.layer.value)
    body.add_row("Scope", escape(_scope_text(card.scope)))
    body.add_row("Why", escape("; ".join(card.reasons)))
    body.add_row("Queue", card.queue_id)
    body.add_row("Proposal digest", str(card.proposal_digest))
    body.add_row("Evidence", f"{card.evidence_ref.record_id} ({card.evidence_ref.content_digest})")
    body.add_row("Actions", ", ".join(card.available_actions))
    return Panel(body, title=f"Proposal {number}", border_style="yellow")


def reviews(snapshot: TerminalAlphaSnapshot) -> Group:
    proposals = snapshot.review_mode.proposals
    if not proposals:
        return Group(Panel("No proposed adaptations require review.", title="Review inbox"))
    return Group(
        Panel(
            "Supporting raw text remains encrypted. Approval authorizes future sessions and "
            "therefore requires explicit confirmation.",
            title=f"Review inbox · {len(proposals)} pending",
        ),
        *(_proposal_panel(card, number=index) for index, card in enumerate(proposals, start=1)),
    )


def _adaptation_panel(card: ActiveAdaptationCard, *, number: int) -> Panel:
    body = Table(box=None, show_header=False, pad_edge=False, expand=True)
    body.add_column("Field", style="bold", width=18)
    body.add_column("Value", overflow="fold")
    body.add_row("Intent", escape(card.intent))
    body.add_row("Behavior", escape("; ".join(card.required_behaviors)))
    body.add_row("Type", card.artifact_type)
    body.add_row("Layer", card.layer.value)
    body.add_row("Scope", escape(_scope_text(card.scope)))
    body.add_row("Evidence links", str(card.evidence_count))
    body.add_row("Artifact", f"{card.artifact_id}@{card.artifact_version}")
    return Panel(body, title=f"Active adaptation {number}", border_style="green")


def adaptations(snapshot: TerminalAlphaSnapshot) -> Group:
    active = snapshot.active_adaptations
    if not active:
        return Group(
            Panel(
                "No adaptation is currently active. Fresh sessions receive no Temper behavior.",
                title="Active adaptations",
            )
        )
    return Group(
        *(_adaptation_panel(card, number=index) for index, card in enumerate(active, start=1))
    )


def history(snapshot: TerminalAlphaSnapshot) -> Group:
    notices = snapshot.review_mode.recent_notices
    if not notices:
        return Group(Panel("No learning notices have been recorded.", title="Recent history"))
    table = Table(box=box.SIMPLE, expand=True, pad_edge=False)
    table.add_column("Time", width=20)
    table.add_column("Disposition", width=16)
    table.add_column("Summary", overflow="fold")
    for notice in reversed(notices):
        table.add_row(
            notice.created_at.isoformat().replace("+00:00", "Z"),
            notice.kind.value,
            escape(notice.summary),
        )
    return Group(Panel(table, title="Recent history"))


def health(snapshot: TerminalAlphaSnapshot) -> Group:
    daily = snapshot.review_mode
    table = Table(box=box.SIMPLE, expand=True, pad_edge=False)
    table.add_column("Check")
    table.add_column("State", justify="right")
    table.add_row("Credential enrolled", _status(daily.credential_enrolled))
    table.add_row("Watcher active", _status(daily.watcher_active))
    table.add_row("Automatic promotion", Text("OFF", style="green"))
    table.add_row("Raw payloads exposed", Text("NO", style="green"))
    table.add_row("Unresolved reviews", str(daily.gate.unresolved_review_count))
    table.add_row("Unresolved activations", str(daily.gate.unresolved_activation_count))
    projects = "\n".join(snapshot.configured_project_ids) or "none"
    return Group(Panel(table, title="Local health"), Panel(projects, title="Registered projects"))


def gate(snapshot: TerminalAlphaSnapshot) -> Group:
    report = snapshot.review_mode.gate
    outcomes = Table(box=box.SIMPLE, expand=True, pad_edge=False)
    outcomes.add_column("Metric")
    outcomes.add_column("Value", justify="right")
    outcomes.add_row("Correct learning", str(report.correct_learning_count))
    outcomes.add_row("False learning", str(report.false_learning_count))
    outcomes.add_row("Missed learning", str(report.missed_learning_count))
    outcomes.add_row(
        "Helped / hurt / irrelevant",
        f"{report.helped_count} / {report.hurt_count} / {report.irrelevant_count}",
    )
    outcomes.add_row(
        "Correct / false / missed activation",
        (
            f"{report.correct_activation_count} / {report.false_activation_count} / "
            f"{report.missed_activation_count}"
        ),
    )
    outcomes.add_row("Repeated corrections", str(report.repeated_correction_count))
    outcomes.add_row("Latest delivered bytes", str(snapshot.latest_delivered_projection_utf8_bytes))
    return Group(
        Panel(_progress_table(snapshot), title="Evidence readiness"),
        Panel(_allowance_table(snapshot), title="Error allowances"),
        Panel(outcomes, title="Observed outcomes"),
    )


def render_terminal(
    snapshot: TerminalAlphaSnapshot,
    *,
    view: TerminalView = "status",
    width: int = 88,
    color: bool = False,
) -> str:
    """Render one deterministic terminal view without reading or mutating runtime state."""

    renderables = {
        "status": dashboard,
        "review": reviews,
        "adaptations": adaptations,
        "history": history,
        "health": health,
        "gate": gate,
    }
    return _capture(renderables[view](snapshot), width=width, color=color)


def render_plain(snapshot: TerminalAlphaSnapshot, *, view: TerminalView = "status") -> str:
    """Render stable ANSI-free lines for Codex Remote and narrow terminals."""

    daily = snapshot.review_mode
    report = daily.gate
    if view == "status":
        lines = [
            f"Temper | {daily.subject_id} | Codex | review mode",
            f"Interactions: {report.eligible_interaction_count}/{report.goal_interaction_count}",
            f"Dates: {report.active_date_count}/{report.minimum_active_dates}",
            f"Activation attempts: {report.activation_count}/{report.minimum_activation_count}",
            f"Rated activations: {report.rated_activation_count}",
            f"Pending reviews: {daily.metrics.pending_review_count}",
            f"Awaiting feedback: {daily.metrics.pending_feedback_count}",
            f"Active adaptations: {daily.active_artifact_count}",
            f"Latest delivered projection: {snapshot.latest_delivered_projection_utf8_bytes} bytes",
            f"Credential enrolled: {'yes' if daily.credential_enrolled else 'no'}",
            f"Watcher active: {'yes' if daily.watcher_active else 'no'}",
            f"Evidence ready: {'yes' if report.evidence_ready else 'no'}",
        ]
        lines.extend(
            f"Allowance {item.name}: {item.observed}/{item.maximum} ({item.state})"
            for item in snapshot.allowances
        )
        if any(item.state == "exceeded" for item in snapshot.allowances):
            lines.append("Attention: the active gate has exceeded an error allowance.")
        elif all(item.state == "used" for item in snapshot.allowances):
            lines.append(
                "Attention: all error allowances are used; another incident fails the gate."
            )
        lines.extend(f"Next: {item}" for item in daily.next_actions)
        return "\n".join(lines) + "\n"
    if view == "review":
        lines = [f"Temper review inbox: {len(daily.proposals)} pending"]
        for index, proposal in enumerate(daily.proposals, start=1):
            behavior = proposal.behavior or f"Revoke {proposal.affected_artifact_id}"
            lines.extend(
                (
                    f"[{index}] {behavior}",
                    f"    Queue: {proposal.queue_id}",
                    f"    Digest: {proposal.proposal_digest}",
                    f"    Scope: {_scope_text(proposal.scope)}",
                    (
                        f"    Evidence: {proposal.evidence_ref.record_id} "
                        f"({proposal.evidence_ref.content_digest})"
                    ),
                    f"    Actions: {', '.join(proposal.available_actions)}",
                )
            )
        return "\n".join(lines) + "\n"
    if view == "adaptations":
        lines = [f"Temper active adaptations: {len(snapshot.active_adaptations)}"]
        for index, adaptation in enumerate(snapshot.active_adaptations, start=1):
            lines.extend(
                (
                    f"[{index}] {adaptation.intent}",
                    f"    Behavior: {'; '.join(adaptation.required_behaviors)}",
                    f"    Artifact: {adaptation.artifact_id}@{adaptation.artifact_version}",
                    f"    Scope: {_scope_text(adaptation.scope)}",
                    f"    Evidence links: {adaptation.evidence_count}",
                )
            )
        return "\n".join(lines) + "\n"
    if view == "history":
        lines = [f"Temper recent history: {len(daily.recent_notices)} notices"]
        lines.extend(
            (
                f"{notice.created_at.isoformat().replace('+00:00', 'Z')} | "
                f"{notice.kind.value} | {notice.summary}"
            )
            for notice in reversed(daily.recent_notices)
        )
        return "\n".join(lines) + "\n"
    if view == "health":
        lines = [
            "Temper local health",
            f"Credential enrolled: {'yes' if daily.credential_enrolled else 'no'}",
            f"Watcher active: {'yes' if daily.watcher_active else 'no'}",
            "Automatic promotion: no",
            "Raw payloads exposed: no",
            f"Unresolved reviews: {report.unresolved_review_count}",
            f"Unresolved activations: {report.unresolved_activation_count}",
            "Registered projects: " + (", ".join(snapshot.configured_project_ids) or "none"),
        ]
        return "\n".join(lines) + "\n"
    lines = [
        "Temper longitudinal gate",
        f"Interactions: {report.eligible_interaction_count}/{report.goal_interaction_count}",
        f"Dates: {report.active_date_count}/{report.minimum_active_dates}",
        f"Activation attempts: {report.activation_count}/{report.minimum_activation_count}",
        f"Correct learning: {report.correct_learning_count}",
        f"False learning: {report.false_learning_count}",
        f"Missed learning: {report.missed_learning_count}",
        (
            f"Helped/hurt/irrelevant: {report.helped_count}/{report.hurt_count}/"
            f"{report.irrelevant_count}"
        ),
        (
            "Correct/false/missed activation: "
            f"{report.correct_activation_count}/{report.false_activation_count}/"
            f"{report.missed_activation_count}"
        ),
        f"Repeated corrections: {report.repeated_correction_count}",
        f"Latest delivered projection: {snapshot.latest_delivered_projection_utf8_bytes} bytes",
        f"Evidence ready: {'yes' if report.evidence_ready else 'no'}",
    ]
    lines.extend(
        f"Allowance {item.name}: {item.observed}/{item.maximum} ({item.state})"
        for item in snapshot.allowances
    )
    return "\n".join(lines) + "\n"
