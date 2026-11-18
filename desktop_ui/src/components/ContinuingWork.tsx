import { useId, useState } from "react";
import {
  hubRequest,
  type HubCheckpoint,
  type HubCheckpointDetails,
  type HubProject,
  type HubState,
} from "../toolsHub";
import { connectionReadiness } from "./RepositoryReadiness";
import { Button, LoadingStatus } from "./ui";

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
      <summary>View saved notes</summary>
      <div className="continuity-details__body">
        {contents ? (
          <dl>
            <dt>Next step</dt>
            <dd>{contents.next_step}</dd>
            {contents.progress.length ? (
              <>
                <dt>Where you left off</dt>
                <dd>
                  <ul>
                    {contents.progress.map((item, index) => (
                      <li key={index}>{item}</li>
                    ))}
                  </ul>
                </dd>
              </>
            ) : null}
          </dl>
        ) : requestState === "loading" ? (
          <LoadingStatus>Opening saved notes…</LoadingStatus>
        ) : (
          <div className="continuity-details__notice">
            {stale || requestState === "failed" ? (
              <p role="status">
                {stale
                  ? "Refresh status to see what was saved."
                  : "Temper couldn’t open your saved notes."}
              </p>
            ) : null}
            {!stale ? (
              <Button type="button" onClick={() => void readCheckpoint()}>
                {requestState === "failed" ? "Try again" : "Load saved notes"}
              </Button>
            ) : null}
          </div>
        )}
      </div>
    </details>
  );
}

function resumeBlockReason(state: HubState, project: HubProject) {
  if (state.secure_store_ready === false)
    return "Unlock your secure storage to resume.";
  if (project.continuity_issue === "unavailable")
    return "Temper couldn’t read the saved work.";
  if (project.attention || project.pending_recovery || state.cleanup_pending)
    return "Resolve the issue in Tool settings to resume.";
  if (!state.enabled || state.paused || project.paused)
    return "Resume automatic workflows to continue.";
  const connection = connectionReadiness(state);
  if (connection === "preparing")
    return "Temper is preparing repository tools.";
  if (connection === "connection_needed")
    return "Connect Codex to resume saved work.";
  if (!project.continuity_enabled) return "Saving work is off.";
  if (project.continuity_issue === "expired")
    return "Your saved notes have expired.";
  return null;
}

function ResumeMessage({
  project,
  disabled,
}: {
  project: HubProject;
  disabled: boolean;
}) {
  const messageId = useId();
  const [copyState, setCopyState] = useState<
    "idle" | "copying" | "copied" | "manual"
  >("idle");
  const message = `Continue the work Temper saved for this repository. The repository folder is ${project.root}. If this chat is in a different repository, ask me to switch before resuming.`;

  async function copyMessage() {
    setCopyState("copying");
    try {
      await navigator.clipboard.writeText(message);
      setCopyState("copied");
    } catch {
      setCopyState("manual");
    }
  }

  return (
    <div className="continuity-resume">
      <Button
        type="button"
        tone="primary"
        disabled={disabled || copyState === "copying"}
        onClick={() => void copyMessage()}
      >
        Copy resume message
      </Button>
      {copyState === "copied" ? (
        <p role="status">
          Copied. Paste it into a new Codex chat for this repository.
        </p>
      ) : null}
      {copyState === "manual" && !disabled ? (
        <div className="continuity-resume__manual">
          <label htmlFor={messageId} role="status">
            Copy this message into a new Codex chat for this repository.
          </label>
          <textarea
            id={messageId}
            readOnly
            rows={3}
            value={message}
            onFocus={(event) => event.currentTarget.select()}
          />
        </div>
      ) : null}
    </div>
  );
}

export function OverviewSavedWork({
  state,
  unavailable,
  onOpenTools,
}: {
  state: HubState;
  unavailable: boolean;
  onOpenTools: () => void;
}) {
  const saved = state.projects.flatMap((project) =>
    project.continuity ? [{ project, checkpoint: project.continuity }] : [],
  );
  if (!saved.length) return null;

  const resumable = unavailable
    ? undefined
    : saved
        .sort((a, b) => b.checkpoint.saved_at - a.checkpoint.saved_at)
        .find(({ project }) => !resumeBlockReason(state, project));
  return (
    <div className="tools-hub-overview-saved">
      <div>
        <strong>Saved work</strong>
        {resumable && (
          <>
            <span>{resumable.project.label}</span>
            {state.projects.some(
              ({ id, label }) =>
                id !== resumable.project.id &&
                label === resumable.project.label,
            ) && <small>{resumable.project.root}</small>}
          </>
        )}
      </div>
      <div className="tools-hub-actions">
        {resumable && (
          <ResumeMessage
            key={resumable.checkpoint.checkpoint_id}
            project={resumable.project}
            disabled={false}
          />
        )}
        {(!resumable || saved.length > 1) && (
          <Button type="button" onClick={onOpenTools}>
            View saved work
          </Button>
        )}
      </div>
    </div>
  );
}

export type ContinuingWorkAction =
  | { type: "toggle"; project: HubProject }
  | { type: "reset"; project: HubProject }
  | { type: "clear"; project: HubProject; checkpoint: HubCheckpoint };

export function ContinuingWork({
  state,
  stale,
  actionsUnavailable,
  notice,
  preparingReview,
  onAction,
}: {
  state: HubState;
  stale: boolean;
  actionsUnavailable: boolean;
  notice?: string | null;
  preparingReview?: boolean;
  onAction: (action: ContinuingWorkAction, trigger: HTMLButtonElement) => void;
}) {
  const supported = state.projects.filter(
    (project) => project.continuity_enabled !== undefined,
  );
  if (!supported.length) return null;

  const canEnable =
    state.enabled &&
    !state.paused &&
    connectionReadiness(state) === "configured" &&
    !state.cleanup_pending;
  const labelCounts = new Map<string, number>();
  for (const { label } of supported)
    labelCounts.set(label, (labelCounts.get(label) ?? 0) + 1);

  return (
    <section
      className="continuity-section"
      aria-label="Saved work by repository"
    >
      {stale ? (
        <p role="status">
          Refresh status before resuming or changing saved work.
        </p>
      ) : null}
      {preparingReview ? (
        <LoadingStatus>Opening saved work settings…</LoadingStatus>
      ) : null}
      {notice ? <p role="status">{notice}</p> : null}
      {supported.map((project) => {
        const checkpoint = project.continuity;
        const reason = resumeBlockReason(state, project);
        const resetNeeded = project.continuity_issue === "unavailable";
        return (
          <div className="continuity-project" key={project.id}>
            <div className="continuity-project__heading">
              <div>
                <strong>{project.label}</strong>
                {(labelCounts.get(project.label) ?? 0) > 1 && (
                  <small>{project.root}</small>
                )}
              </div>
              {checkpoint ? (
                <span>
                  Saved <CheckpointTime timestamp={checkpoint.saved_at} />
                </span>
              ) : null}
            </div>
            {reason ? (
              <p>{reason}</p>
            ) : !checkpoint ? (
              <p>Nothing saved yet.</p>
            ) : null}
            {checkpoint ? (
              <>
                {!reason && (
                  <ResumeMessage
                    key={`resume-${checkpoint.checkpoint_id}`}
                    project={project}
                    disabled={stale || actionsUnavailable}
                  />
                )}
                <CheckpointContents
                  key={checkpoint.checkpoint_id}
                  projectId={project.id}
                  checkpointId={checkpoint.checkpoint_id}
                  stale={stale}
                />
              </>
            ) : null}
            <div className="continuity-project__actions">
              <Button
                type="button"
                tone={project.continuity_enabled ? "quiet" : "secondary"}
                aria-label={
                  resetNeeded
                    ? `Reset saved work for ${project.label}`
                    : `${project.continuity_enabled ? "Stop saving work" : "Save work"} for ${project.label}`
                }
                disabled={
                  actionsUnavailable ||
                  (!resetNeeded &&
                    !project.continuity_enabled &&
                    (!canEnable ||
                      project.paused ||
                      !!project.attention ||
                      project.pending_recovery))
                }
                onClick={(event) =>
                  onAction(
                    { type: resetNeeded ? "reset" : "toggle", project },
                    event.currentTarget,
                  )
                }
              >
                {resetNeeded
                  ? "Reset saved work"
                  : project.continuity_enabled
                    ? "Stop saving work"
                    : "Save work"}
              </Button>
              {checkpoint && !resetNeeded ? (
                <Button
                  type="button"
                  tone="quiet"
                  aria-label={`Remove saved notes for ${project.label}`}
                  disabled={actionsUnavailable}
                  onClick={(event) =>
                    onAction(
                      { type: "clear", project, checkpoint },
                      event.currentTarget,
                    )
                  }
                >
                  Remove saved notes
                </Button>
              ) : null}
            </div>
          </div>
        );
      })}
    </section>
  );
}
