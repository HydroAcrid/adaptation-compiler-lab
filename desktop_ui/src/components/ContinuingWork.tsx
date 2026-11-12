import { Fragment, useId, useState } from "react";
import {
  hubRequest,
  type HubCheckpoint,
  type HubCheckpointDetails,
  type HubProject,
  type HubState,
} from "../toolsHub";
import { Button, LoadingStatus } from "./ui";

const taskLabels: Record<string, string> = {
  implementation: "Implementation",
  debugging: "Debugging",
  review: "Review",
  documentation: "Documentation",
  planning: "Planning",
};

const checkpointFields = [
  ["progress", "Progress"],
  ["facts", "Facts"],
  ["requirements", "Requirements"],
  ["checks", "Reported checks"],
] as const;

function CheckpointTime({ timestamp }: { timestamp: number }) {
  const date = new Date(timestamp * 1000);
  if (!Number.isFinite(date.getTime())) return null;

  return (
    <time dateTime={date.toISOString()}>
      {date.toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })}
    </time>
  );
}

function CheckpointContents({
  projectId,
  checkpointId,
  stale,
}: {
  projectId: string;
  checkpointId: string;
  stale: boolean;
}) {
  const [contents, setContents] = useState<HubCheckpointDetails | null>(null);
  const [requestState, setRequestState] = useState<
    "idle" | "loading" | "failed"
  >("idle");

  async function readCheckpoint() {
    if (stale || requestState === "loading") return;
    setRequestState("loading");
    try {
      const next = await hubRequest<HubCheckpointDetails>("continuity_read", {
        project_id: projectId,
        checkpoint_id: checkpointId,
      });
      if (next.checkpoint_id !== checkpointId) {
        setRequestState("failed");
        return;
      }
      setContents(next);
      setRequestState("idle");
    } catch {
      setRequestState("failed");
    }
  }

  return (
    <details
      className="continuity-details"
      onToggle={(event) => {
        if (event.currentTarget.open && !contents && requestState === "idle")
          void readCheckpoint();
      }}
    >
      <summary>Saved checkpoint</summary>
      <div className="continuity-details__body">
        {contents ? (
          <dl>
            <dt>Next step</dt>
            <dd>{contents.next_step}</dd>
            {checkpointFields.map(([field, label]) =>
              contents[field].length ? (
                <Fragment key={field}>
                  <dt>{label}</dt>
                  <dd>
                    <ul>
                      {contents[field].map((item, index) => (
                        <li key={index}>{item}</li>
                      ))}
                    </ul>
                  </dd>
                </Fragment>
              ) : null,
            )}
          </dl>
        ) : requestState === "loading" ? (
          <LoadingStatus>Opening checkpoint…</LoadingStatus>
        ) : (
          <div className="continuity-details__notice">
            {stale || requestState === "failed" ? (
              <p role="status">
                {stale
                  ? "Refresh status to see what was saved."
                  : "Temper couldn’t open this checkpoint."}
              </p>
            ) : null}
            {!stale ? (
              <Button type="button" onClick={() => void readCheckpoint()}>
                {requestState === "failed"
                  ? "Retry checkpoint"
                  : "Load checkpoint"}
              </Button>
            ) : null}
          </div>
        )}
      </div>
    </details>
  );
}

function projectStatus(state: HubState, project: HubProject) {
  if (state.secure_store_ready === false) return "Secure storage unavailable";
  if (project.continuity_issue === "unavailable")
    return "Checkpoint unavailable";
  if (project.attention || project.pending_recovery || state.cleanup_pending)
    return "Needs attention";
  if (!project.continuity_enabled) {
    return state.indexed && state.native_hooks_configured
      ? "Off"
      : "Codex setup needed";
  }
  if (!state.enabled || state.paused || project.paused) return "Paused";
  if (
    !state.indexed ||
    !state.bridge_configured ||
    !state.native_hooks_configured
  )
    return "Codex setup needed";
  if (project.continuity?.status === "resumed") return "Retrieved by Codex";
  if (project.continuity_issue === "expired") return "Checkpoint expired";
  return project.continuity ? "Saved for a later chat" : "No checkpoint saved";
}

function CheckpointActivity({ checkpoint }: { checkpoint: HubCheckpoint }) {
  return (
    <dl>
      <dt>Saved</dt>
      <dd>
        {taskLabels[checkpoint.task_class] ?? "Work"} ·{" "}
        <CheckpointTime timestamp={checkpoint.saved_at} />
      </dd>
      {checkpoint.resumed_at !== null ? (
        <>
          <dt>Retrieved</dt>
          <dd>
            <CheckpointTime timestamp={checkpoint.resumed_at} />
          </dd>
        </>
      ) : null}
      <dt>Selected guidance</dt>
      <dd>{checkpoint.guidance.join(", ") || "None selected"}</dd>
    </dl>
  );
}

export type ContinuingWorkAction =
  | { type: "toggle"; project: HubProject }
  | { type: "clear"; project: HubProject; checkpoint: HubCheckpoint };

export function ContinuingWork({
  state,
  compact = false,
  stale,
  pending,
  actionsUnavailable,
  notice,
  preparingReview,
  onRefresh,
  onAction,
}: {
  state: HubState;
  compact?: boolean;
  stale: boolean;
  pending: boolean;
  actionsUnavailable: boolean;
  notice?: string | null;
  preparingReview?: boolean;
  onRefresh: () => void;
  onAction?: (action: ContinuingWorkAction, trigger: HTMLButtonElement) => void;
}) {
  const headingId = useId();
  const supported = state.projects.filter(
    (project) => project.continuity_enabled !== undefined,
  );
  if (!supported.length) return null;

  const latest = supported.reduce<HubProject | null>((current, project) => {
    const savedAt = project.continuity?.saved_at;
    return savedAt !== undefined &&
      savedAt > (current?.continuity?.saved_at ?? -Infinity)
      ? project
      : current;
  }, null);
  const shown = compact ? (latest ? [latest] : []) : supported;
  const enabled = supported.filter((project) => project.continuity_enabled);
  const unavailable = supported.some(
    (project) => project.continuity_issue === "unavailable",
  );
  const canEnable =
    state.enabled &&
    !state.paused &&
    state.bridge_configured &&
    state.indexed &&
    state.native_hooks_configured &&
    !state.cleanup_pending;

  return (
    <section
      className="tools-hub-activity continuity-section"
      aria-labelledby={headingId}
    >
      <h3 id={headingId}>Continuing work</h3>
      {stale ? (
        <div className="continuity-section__stale">
          <p role="status">Showing the last known checkpoint status.</p>
          {compact ? (
            <Button type="button" disabled={pending} onClick={onRefresh}>
              {pending ? "Refreshing…" : "Refresh status"}
            </Button>
          ) : null}
        </div>
      ) : null}
      {preparingReview ? (
        <LoadingStatus>Preparing checkpoint settings…</LoadingStatus>
      ) : null}
      {notice ? <p role="status">{notice}</p> : null}
      {!shown.length ? (
        <p>
          {unavailable
            ? "Some checkpoint statuses are unavailable."
            : enabled.length === 1
              ? projectStatus(state, enabled[0])
              : enabled.length
                ? "No checkpoint saved yet."
                : "Off for all repositories."}
        </p>
      ) : null}
      {shown.map((project) => {
        const checkpoint = project.continuity;
        const status = projectStatus(state, project);
        return (
          <div className="continuity-project" key={project.id}>
            <div className="continuity-project__heading">
              <strong>{project.label}</strong>
              <span>{status}</span>
            </div>
            {checkpoint ? (
              <>
                <CheckpointActivity checkpoint={checkpoint} />
                <CheckpointContents
                  key={checkpoint.checkpoint_id}
                  projectId={project.id}
                  checkpointId={checkpoint.checkpoint_id}
                  stale={stale}
                />
                {!stale && status === "Saved for a later chat" ? (
                  <p className="tools-hub-guidance">
                    Ask Codex to continue saved work in a new chat for this
                    repository.
                  </p>
                ) : null}
              </>
            ) : null}
            {!compact && onAction ? (
              <div className="continuity-project__actions">
                <Button
                  type="button"
                  aria-label={`${project.continuity_enabled ? "Turn off" : "Turn on"} continuing work for ${project.label}`}
                  disabled={
                    actionsUnavailable ||
                    project.continuity_issue === "unavailable" ||
                    (!project.continuity_enabled &&
                      (!canEnable ||
                        project.paused ||
                        !!project.attention ||
                        project.pending_recovery))
                  }
                  onClick={(event) =>
                    onAction({ type: "toggle", project }, event.currentTarget)
                  }
                >
                  {project.continuity_enabled ? "Turn off" : "Turn on"}
                </Button>
                {checkpoint ? (
                  <Button
                    type="button"
                    tone="quiet"
                    aria-label={`Remove checkpoint for ${project.label}`}
                    disabled={
                      actionsUnavailable ||
                      project.continuity_issue === "unavailable"
                    }
                    onClick={(event) =>
                      onAction(
                        { type: "clear", project, checkpoint },
                        event.currentTarget,
                      )
                    }
                  >
                    Remove checkpoint
                  </Button>
                ) : null}
              </div>
            ) : null}
          </div>
        );
      })}
    </section>
  );
}
