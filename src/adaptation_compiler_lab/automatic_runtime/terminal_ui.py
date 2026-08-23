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

TerminalView = Literal[
    "status",
    "review",
    "adaptations",
    "activity",
    "history",
    "health",
    "gate",
]


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


def _friendly_scope(scope: Scope) -> str:
    """Describe a governed scope without exposing its storage representation."""

    parts: list[str] = []
    if scope.project_ids:
        label = "Project" if len(scope.project_ids) == 1 else "Projects"
        parts.append(f"{label}: {', '.join(scope.project_ids)}")
    if scope.task_classes:
        parts.append(f"Tasks like: {', '.join(scope.task_classes)}")
    if scope.environment_ids:
        parts.append(f"Environment: {', '.join(scope.environment_ids)}")
    if scope.activation_conditions:
        parts.append(f"When: {', '.join(scope.activation_conditions)}")
    if not parts:
        if scope.target_families == ("codex",):
            parts.append("Your Codex sessions")
        else:
            parts.append("Your registered AI sessions")
    if scope.exclusions:
        parts.append(f"Except: {', '.join(scope.exclusions)}")
    return " · ".join(parts)


def _consumer_status(snapshot: TerminalAlphaSnapshot) -> tuple[str, ...]:
    daily = snapshot.review_mode
    messages: list[str] = []
    if daily.metrics.pending_review_count:
        count = daily.metrics.pending_review_count
        messages.append(f"Temper has {count} suggestion{'s' if count != 1 else ''} for you.")
    if daily.metrics.pending_feedback_count:
        count = daily.metrics.pending_feedback_count
        messages.append(
            f"Temper needs feedback on {count} completed session{'s' if count != 1 else ''}."
        )
    if not daily.credential_enrolled:
        messages.append("Temper needs setup attention before it can make changes.")
    elif not daily.watcher_active:
        messages.append(
            "Automatic listening is off. Poll after ordinary work to check for learning."
        )
    if not messages:
        messages.append("Temper is ready. Nothing needs your attention.")
    return tuple(messages)


def _consumer_next_actions(snapshot: TerminalAlphaSnapshot) -> tuple[str, ...]:
    daily = snapshot.review_mode
    actions: list[str] = []
    if daily.metrics.pending_review_count:
        actions.append("Run `temper review` to approve, adjust, or ignore suggestions.")
    if daily.metrics.pending_feedback_count:
        actions.append("Run `temper activity` to see completed sessions awaiting feedback.")
    if not daily.credential_enrolled:
        actions.append("Run `temper health` to see what needs setup attention.")
    elif not daily.watcher_active:
        actions.append("Run `temper poll` after an ordinary-work conversation.")
    if not actions:
        actions.append("Keep working normally. Temper will surface anything that needs you.")
    return tuple(actions)


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
    """Render the calm consumer home: state, attention, and one next step."""

    daily = snapshot.review_mode
    header = Text()
    header.append("Temper", style="bold cyan")
    header.append("\nYour governed AI behavior layer", style="dim")
    summary = Table(box=box.SIMPLE, expand=True, show_header=False, pad_edge=False)
    summary.add_column("Item", ratio=3)
    summary.add_column("Count", justify="right")
    summary.add_row("Suggestions waiting", str(daily.metrics.pending_review_count))
    summary.add_row("Adaptations active", str(daily.active_artifact_count))
    summary.add_row("Feedback waiting", str(daily.metrics.pending_feedback_count))
    state = "\n".join(_consumer_status(snapshot))
    next_action = "\n".join(f"• {escape(item)}" for item in _consumer_next_actions(snapshot))
    footer = Text(
        "More: temper review · temper activity · temper adaptations · temper advanced",
        style="dim",
    )
    return Group(
        Panel(header, border_style="cyan"),
        Panel(state, title="Status", border_style="blue"),
        Panel(summary, title="At a glance"),
        Panel(next_action, title="Next"),
        footer,
    )


def advanced_dashboard(snapshot: TerminalAlphaSnapshot) -> Group:
    """Render the complete operator and longitudinal-evidence dashboard."""

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


def _advanced_proposal_panel(card: ReviewProposalCard) -> Panel:
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
    return Panel(body, title=f"Suggestion {card.review_number}", border_style="yellow")


def _proposal_panel(card: ReviewProposalCard) -> Panel:
    behavior = (
        f"Stop using adaptation {card.affected_artifact_id}"
        if card.behavior is None
        else card.behavior
    )
    body = Text()
    body.append(f'"{behavior}"\n\n', style="bold")
    body.append(f"Applies to: {_friendly_scope(card.scope)}\n\n")
    body.append(f"Approve:      temper approve {card.review_number}\n", style="green")
    if "refine_scope" in card.available_actions:
        body.append(
            f"Change scope: temper approve {card.review_number} --help\n",
            style="cyan",
        )
    body.append(f"Ignore:       temper reject {card.review_number}", style="dim")
    return Panel(body, title=f"Suggestion #{card.review_number}", border_style="yellow")


def reviews(snapshot: TerminalAlphaSnapshot, *, advanced: bool = False) -> Group:
    proposals = snapshot.review_mode.proposals
    if not proposals:
        return Group(
            Panel(
                "No suggestions are waiting. Temper will ask before anything becomes active.",
                title="Suggestions",
            )
        )
    if advanced:
        return Group(
            Panel(
                "Supporting raw text remains encrypted. Approval authorizes future sessions and "
                "therefore requires explicit confirmation.",
                title=f"Advanced review · {len(proposals)} pending",
            ),
            *(_advanced_proposal_panel(card) for card in proposals),
        )
    return Group(
        Panel(
            "Temper noticed behavior that could help in future work. Nothing becomes active "
            "until you approve it.",
            title=f"Suggestions · {len(proposals)} waiting",
        ),
        *(_proposal_panel(card) for card in proposals),
        Text("Technical lineage: temper review --advanced", style="dim"),
    )


def _advanced_adaptation_panel(card: ActiveAdaptationCard, *, number: int) -> Panel:
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


def _adaptation_panel(card: ActiveAdaptationCard, *, number: int) -> Panel:
    body = Text()
    body.append("\n".join(card.required_behaviors), style="bold")
    body.append(f"\n\nApplies to: {_friendly_scope(card.scope)}")
    return Panel(body, title=f"Adaptation {number}", border_style="green")


def adaptations(snapshot: TerminalAlphaSnapshot, *, advanced: bool = False) -> Group:
    active = snapshot.active_adaptations
    if not active:
        return Group(
            Panel(
                "No adaptation is currently active. Fresh sessions receive no Temper behavior.",
                title="Active adaptations",
            )
        )
    panel = _advanced_adaptation_panel if advanced else _adaptation_panel
    footer = (
        "Exact provenance and undo IDs are shown above."
        if advanced
        else "Technical provenance and undo controls: temper adaptations --advanced"
    )
    return Group(
        *(panel(card, number=index) for index, card in enumerate(active, start=1)),
        Text(footer, style="dim"),
    )


def _friendly_notice(kind: str, summary: str) -> str:
    descriptions = {
        "needs_review": "A possible suggestion was captured for review.",
        "blocked": "Temper could not safely turn one interaction into learning.",
        "ignored": "Nothing was saved from this interaction.",
        "unchanged": "A repeated signal required no change.",
    }
    return descriptions.get(kind, summary)


def activity(snapshot: TerminalAlphaSnapshot) -> Group:
    """Render recent learning in consumer language, with pending feedback first."""

    daily = snapshot.review_mode
    sections: list[RenderableType] = []
    if daily.activation_feedback:
        feedback = "\n".join(
            f"• temper feedback {item.activation_id} helped|hurt|irrelevant"
            for item in daily.activation_feedback
        )
        sections.append(Panel(feedback, title="Waiting for your feedback", border_style="yellow"))
    recent = tuple(reversed(daily.recent_notices[-5:]))
    if recent:
        text = "\n".join(
            f"• {escape(_friendly_notice(item.kind.value, item.summary))}" for item in recent
        )
    else:
        text = "No learning activity has been recorded."
    sections.append(Panel(text, title="Recent learning"))
    sections.append(Text("Exact timestamps and dispositions: temper history", style="dim"))
    return Group(*sections)


def history(snapshot: TerminalAlphaSnapshot) -> Group:
    pending_feedback = snapshot.review_mode.activation_feedback
    notices = snapshot.review_mode.recent_notices
    sections: list[RenderableType] = []
    if pending_feedback:
        feedback = Table(box=box.SIMPLE, expand=True, pad_edge=False)
        feedback.add_column("Completed session")
        feedback.add_column("Tell Temper", overflow="fold")
        for item in pending_feedback:
            feedback.add_row(
                item.activation_id,
                f"temper feedback {item.activation_id} helped|hurt|irrelevant",
            )
        sections.append(Panel(feedback, title="Waiting for your feedback", border_style="yellow"))
    if not notices:
        sections.append(Panel("No learning notices have been recorded.", title="Recent learning"))
        return Group(*sections)
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
    sections.append(Panel(table, title="Recent learning"))
    return Group(*sections)


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
    advanced: bool = False,
    width: int = 88,
    color: bool = False,
) -> str:
    """Render one deterministic terminal view without reading or mutating runtime state."""

    if view == "status":
        renderable = advanced_dashboard(snapshot) if advanced else dashboard(snapshot)
    elif view == "review":
        renderable = reviews(snapshot, advanced=advanced)
    elif view == "adaptations":
        renderable = adaptations(snapshot, advanced=advanced)
    elif view == "activity":
        renderable = activity(snapshot)
    else:
        renderables = {"history": history, "health": health, "gate": gate}
        renderable = renderables[view](snapshot)
    return _capture(renderable, width=width, color=color)


def render_plain(
    snapshot: TerminalAlphaSnapshot,
    *,
    view: TerminalView = "status",
    advanced: bool = False,
) -> str:
    """Render stable ANSI-free lines for Codex Remote and narrow terminals."""

    daily = snapshot.review_mode
    report = daily.gate
    if view == "status":
        if not advanced:
            lines = ["Temper", *_consumer_status(snapshot)]
            lines.extend(
                (
                    f"Suggestions waiting: {daily.metrics.pending_review_count}",
                    f"Adaptations active: {daily.active_artifact_count}",
                    f"Feedback waiting: {daily.metrics.pending_feedback_count}",
                )
            )
            lines.extend(f"Next: {item}" for item in _consumer_next_actions(snapshot))
            lines.append(
                "More: temper review | temper activity | temper adaptations | temper advanced"
            )
            return "\n".join(lines) + "\n"
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
        if not daily.proposals:
            return "Temper suggestions\nNothing is waiting.\n"
        lines = [f"Temper suggestions: {len(daily.proposals)} waiting"]
        for proposal in daily.proposals:
            behavior = proposal.behavior or f"Stop using adaptation {proposal.affected_artifact_id}"
            lines.append(f"[{proposal.review_number}] {behavior}")
            if advanced:
                lines.extend(
                    (
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
            else:
                lines.extend(
                    (
                        f"    Applies to: {_friendly_scope(proposal.scope)}",
                        f"    Approve: temper approve {proposal.review_number}",
                        f"    Ignore: temper reject {proposal.review_number}",
                    )
                )
        if not advanced and daily.proposals:
            lines.append("Technical lineage: temper review --advanced")
        return "\n".join(lines) + "\n"
    if view == "adaptations":
        lines = [f"Temper active adaptations: {len(snapshot.active_adaptations)}"]
        for index, adaptation in enumerate(snapshot.active_adaptations, start=1):
            lines.extend((f"[{index}] {'; '.join(adaptation.required_behaviors)}",))
            if advanced:
                lines.extend(
                    (
                        f"    Intent: {adaptation.intent}",
                        f"    Artifact: {adaptation.artifact_id}@{adaptation.artifact_version}",
                        f"    Scope: {_scope_text(adaptation.scope)}",
                        f"    Evidence links: {adaptation.evidence_count}",
                    )
                )
            else:
                lines.append(f"    Applies to: {_friendly_scope(adaptation.scope)}")
        if not advanced and snapshot.active_adaptations:
            lines.append("Technical provenance and undo controls: temper adaptations --advanced")
        return "\n".join(lines) + "\n"
    if view == "activity":
        lines = ["Temper activity"]
        for item in daily.activation_feedback:
            lines.append(
                f"Feedback waiting: temper feedback {item.activation_id} helped|hurt|irrelevant"
            )
        lines.extend(
            f"- {_friendly_notice(notice.kind.value, notice.summary)}"
            for notice in reversed(daily.recent_notices[-5:])
        )
        if not daily.activation_feedback and not daily.recent_notices:
            lines.append("No learning activity has been recorded.")
        lines.append("Exact timestamps and dispositions: temper history")
        return "\n".join(lines) + "\n"
    if view == "history":
        lines = [f"Temper activity: {len(daily.recent_notices)} learning notices"]
        for item in daily.activation_feedback:
            lines.append(
                f"Feedback waiting: temper feedback {item.activation_id} helped|hurt|irrelevant"
            )
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
