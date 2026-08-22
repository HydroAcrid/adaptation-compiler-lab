"""Product-facing terminal entry point over the governed automatic runtime."""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from enum import StrEnum
from io import TextIOWrapper
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
    execute_codex_feedback_poll,
    execute_fresh_codex_task,
    load_terminal_alpha_snapshot,
    resolve_codex_dogfood_review,
    revoke_active_codex_adaptation,
    save_codex_activation_feedback,
)
from adaptation_compiler_lab.automatic_runtime.models import (
    RuntimeFeedbackOutcome,
)
from adaptation_compiler_lab.automatic_runtime.product_dogfood import TerminalAlphaSnapshot
from adaptation_compiler_lab.automatic_runtime.terminal_ui import (
    TerminalView,
    render_plain,
    render_terminal,
)
from adaptation_compiler_lab.connectors.pins import RuntimeConformanceError
from adaptation_compiler_lab.domain import ApprovalDecision
from adaptation_compiler_lab.serialization import canonical_json


class OutputFormat(StrEnum):
    AUTO = "auto"
    TERMINAL = "terminal"
    PLAIN = "plain"
    JSON = "json"


@dataclass(frozen=True, slots=True)
class TemperCliSettings:
    config_path: Path
    predecessor_config_path: Path | None
    output_format: OutputFormat
    width: int


app = typer.Typer(
    name="temper",
    help="Review, deliver, measure, and undo governed AI adaptations locally.",
    invoke_without_command=True,
    no_args_is_help=False,
    pretty_exceptions_enable=False,
)


def _fail(message: str) -> NoReturn:
    typer.echo(f"Temper could not continue: {message}", err=True)
    raise typer.Exit(code=1)


def _validated_path(
    path: Path | None,
    *,
    label: str,
    option: str,
    envvar: str,
    required: bool,
) -> Path | None:
    if path is None:
        if required:
            _fail(f"{label} is required; pass {option} or set {envvar}")
        return None
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        _fail(f"{label} does not name an existing file")
    return resolved


@app.callback()
def main(
    ctx: typer.Context,
    config_path: Annotated[
        Path | None,
        typer.Option(
            "--config",
            envvar="TEMPER_CONFIG_PATH",
            help="Local no-secret Temper configuration outside every Git repository.",
        ),
    ] = None,
    predecessor_config_path: Annotated[
        Path | None,
        typer.Option(
            "--predecessor-config",
            envvar="TEMPER_PREDECESSOR_CONFIG_PATH",
            help="Preserved predecessor required for a signed successor lineage.",
        ),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option(
            "--format",
            help="Terminal, plain phone-friendly text, canonical JSON, or automatic selection.",
        ),
    ] = OutputFormat.AUTO,
    width: Annotated[int, typer.Option("--width", min=60, max=240)] = 88,
) -> None:
    """Show the read-only dashboard when no subcommand is supplied."""

    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")
    checked_config = _validated_path(
        config_path,
        label="local configuration",
        option="--config",
        envvar="TEMPER_CONFIG_PATH",
        required=True,
    )
    assert checked_config is not None
    settings = TemperCliSettings(
        config_path=checked_config,
        predecessor_config_path=_validated_path(
            predecessor_config_path,
            label="predecessor configuration",
            option="--predecessor-config",
            envvar="TEMPER_PREDECESSOR_CONFIG_PATH",
            required=False,
        ),
        output_format=output_format,
        width=width,
    )
    ctx.obj = settings
    if ctx.invoked_subcommand is None:
        _show(settings, view="status")


def _settings(ctx: typer.Context) -> TemperCliSettings:
    value = ctx.obj
    if not isinstance(value, TemperCliSettings):
        raise RuntimeError("Temper CLI settings are unavailable")
    return value


def _load(settings: TemperCliSettings) -> TerminalAlphaSnapshot:
    snapshot, _pickup = load_terminal_alpha_snapshot(
        settings.config_path,
        predecessor_config_path=settings.predecessor_config_path,
    )
    return snapshot


def _effective_format(settings: TemperCliSettings) -> OutputFormat:
    if settings.output_format is not OutputFormat.AUTO:
        return settings.output_format
    return OutputFormat.TERMINAL if sys.stdout.isatty() else OutputFormat.PLAIN


def _emit(
    snapshot: TerminalAlphaSnapshot,
    *,
    settings: TemperCliSettings,
    view: TerminalView,
) -> None:
    output_format = _effective_format(settings)
    if output_format is OutputFormat.JSON:
        typer.echo(canonical_json(snapshot))
    elif output_format is OutputFormat.PLAIN:
        typer.echo(render_plain(snapshot, view=view), nl=False)
    else:
        typer.echo(
            render_terminal(snapshot, view=view, width=settings.width, color=True),
            nl=False,
        )


def _show(settings: TemperCliSettings, *, view: TerminalView) -> None:
    try:
        snapshot = _load(settings)
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    _emit(snapshot, settings=settings, view=view)


def _action_result(settings: TemperCliSettings, payload: dict[str, object], message: str) -> None:
    if _effective_format(settings) is OutputFormat.JSON:
        typer.echo(canonical_json(payload))
        return
    typer.echo(message)


@app.command("status")
def status(ctx: typer.Context) -> None:
    """Show the raw-free product dashboard without polling or changing state."""

    _show(_settings(ctx), view="status")


@app.command("review")
def review(ctx: typer.Context) -> None:
    """Show normalized pending proposals and their exact decision digests."""

    _show(_settings(ctx), view="review")


@app.command("adaptations")
def adaptations(ctx: typer.Context) -> None:
    """Show active scoped behavior and provenance counts without raw evidence."""

    _show(_settings(ctx), view="adaptations")


@app.command("history")
def history(ctx: typer.Context) -> None:
    """Show recent immutable learning notices."""

    _show(_settings(ctx), view="history")


@app.command("health")
def health(ctx: typer.Context) -> None:
    """Show local credentials, watcher, governance, and unresolved-work health."""

    _show(_settings(ctx), view="health")


@app.command("gate")
def gate(ctx: typer.Context) -> None:
    """Show longitudinal evidence readiness separately from product success."""

    _show(_settings(ctx), view="gate")


@app.command("poll")
def poll(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 25,
) -> None:
    """Run one explicit bounded pickup, then show the updated dashboard."""

    settings = _settings(ctx)
    try:
        receipt = execute_codex_feedback_poll(settings.config_path, limit=limit)
        snapshot = _load(settings)
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    if _effective_format(settings) is OutputFormat.JSON:
        typer.echo(
            canonical_json(
                {
                    "pickup": asdict(receipt),
                    "snapshot": snapshot.model_dump(mode="json", round_trip=True),
                    "snapshot_digest": str(snapshot.content_digest),
                }
            )
        )
        return
    typer.echo(
        "Pickup complete: "
        f"{receipt.appended_count} new, {receipt.replayed_count} replayed, "
        f"{receipt.review_count} review proposal(s)."
    )
    _emit(snapshot, settings=settings, view="status")


@app.command("approve")
def approve(
    ctx: typer.Context,
    queue_id: Annotated[str, typer.Argument(help="Exact queue ID shown by `temper review`.")],
    proposal_digest: Annotated[str, typer.Option("--proposal-digest")],
    confirm_future_use: Annotated[
        bool,
        typer.Option(
            "--confirm-future-use",
            help="Explicitly authorize this behavior to influence future sessions.",
        ),
    ] = False,
    task_class: Annotated[list[str] | None, typer.Option("--task-class")] = None,
    environment_id: Annotated[list[str] | None, typer.Option("--environment-id")] = None,
    activation_condition: Annotated[
        list[str] | None, typer.Option("--activation-condition")
    ] = None,
    exclusion: Annotated[list[str] | None, typer.Option("--exclusion")] = None,
) -> None:
    """Approve one exact proposal, optionally narrowing its scope."""

    settings = _settings(ctx)
    try:
        result = resolve_codex_dogfood_review(
            settings.config_path,
            queue_id=queue_id,
            decision=ApprovalDecision.APPROVED,
            proposal_digest=proposal_digest,
            confirm_future_use=confirm_future_use,
            refine_task_class=task_class,
            refine_environment_id=environment_id,
            refine_activation_condition=activation_condition,
            refine_exclusion=exclusion,
        )
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    _action_result(
        settings,
        result,
        f"Approved {queue_id} for future use. Runtime generation: {result['generation']}.",
    )


@app.command("reject")
def reject(
    ctx: typer.Context,
    queue_id: Annotated[str, typer.Argument(help="Exact queue ID shown by `temper review`.")],
    proposal_digest: Annotated[str, typer.Option("--proposal-digest")],
) -> None:
    """Reject one proposal as not authorized for future sessions."""

    settings = _settings(ctx)
    try:
        result = resolve_codex_dogfood_review(
            settings.config_path,
            queue_id=queue_id,
            decision=ApprovalDecision.REJECTED,
            proposal_digest=proposal_digest,
        )
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    _action_result(settings, result, f"Rejected {queue_id}; no future behavior was authorized.")


@app.command("run")
def run(
    ctx: typer.Context,
    task: Annotated[str, typer.Argument(help="Exact task for one fresh governed Codex session.")],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", exists=True, file_okay=False, resolve_path=True),
    ],
    activation_id: Annotated[str | None, typer.Option("--activation-id")] = None,
) -> None:
    """Deliver the applicable compact projection to one fresh isolated session."""

    settings = _settings(ctx)
    try:
        result = execute_fresh_codex_task(
            settings.config_path,
            task=task,
            workspace=workspace,
            activation_id=activation_id,
        )
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    summary = {
        "activation_id": result.activation_id,
        "material_utf8_bytes": result.material_utf8_bytes,
        "status": result.status,
    }
    _action_result(
        settings,
        summary,
        f"Activation {result.activation_id}: {result.status} "
        f"({result.material_utf8_bytes} projection bytes).",
    )
    if result.final_message:
        typer.echo(result.final_message)
    if result.status != "completed":
        raise typer.Exit(code=1)


@app.command("feedback")
def feedback(
    ctx: typer.Context,
    activation_id: Annotated[str, typer.Argument()],
    outcome: Annotated[RuntimeFeedbackOutcome, typer.Argument()],
    relevant_artifact_id: Annotated[
        list[str] | None, typer.Option("--relevant-artifact-id")
    ] = None,
    correction_key: Annotated[str | None, typer.Option("--correction-key")] = None,
) -> None:
    """Record helped, hurt, or irrelevant feedback for one completed activation."""

    settings = _settings(ctx)
    try:
        result = save_codex_activation_feedback(
            settings.config_path,
            activation_id=activation_id,
            outcome=outcome,
            relevant_artifact_ids=relevant_artifact_id,
            correction_key=correction_key,
        )
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    _action_result(
        settings,
        result.model_dump(mode="json"),
        f"Recorded {outcome.value} feedback for {activation_id}.",
    )


@app.command("undo")
def undo(
    ctx: typer.Context,
    artifact_id: Annotated[str, typer.Argument(help="Exact active artifact ID.")],
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Confirm immediate revocation and release recompilation."),
    ] = False,
) -> None:
    """Immediately revoke one exact active adaptation."""

    if not confirm:
        _fail("undo requires --confirm after reviewing the exact active artifact")
    settings = _settings(ctx)
    try:
        notice = revoke_active_codex_adaptation(
            settings.config_path,
            artifact_id=artifact_id,
        )
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    _action_result(
        settings,
        notice.model_dump(mode="json"),
        f"Revoked {artifact_id}. The next release no longer contains it.",
    )
