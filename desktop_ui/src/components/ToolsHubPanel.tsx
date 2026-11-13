import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useId, useRef, useState } from "react";
import { engineFailureMessage } from "../engine";
import { usePageVisibility } from "../pageVisibility";
import {
  hubRequest,
  type ConnectionPreview,
  type ContinuityPreview,
  type HubOperation,
  type HubPreview,
  type HubProject,
  type HubState,
  type RuntimePreview,
} from "../toolsHub";
import { Button, LoadingStatus } from "./ui";
import { ContinuingWork, type ContinuingWorkAction } from "./ContinuingWork";
import { PortableSetupPanel } from "./PortableSetupPanel";
import { connectionReadiness } from "./RepositoryReadiness";
import "./ToolsHubPanel.css";

type Repository = { id: string; label: string; root: string };
type Review =
  | { type: "permission"; value: HubPreview }
  | { type: "connection"; value: ConnectionPreview }
  | { type: "runtime"; value: RuntimePreview }
  | { type: "continuity"; value: ContinuityPreview; label: string }
  | {
      type: "clear_checkpoint";
      projectId: string;
      checkpointId: string;
      label: string;
    }
  | { type: "stop" | "repair" };

const taskOutcomes: Record<string, string> = {
  ready: "Check complete",
  needs_agent_selection: "Selection requested",
  paused: "Repository updates paused",
  paused_owner_edit: "Edited files need attention",
  rejected_update: "Previously undone guidance skipped",
  deferred_incompatible_update: "Incompatible update deferred",
};

const jobLabels: Record<string, string> = {
  setup: "Publisher setup",
  maintenance: "Publisher check",
  repair: "Setup repair",
  cleanup: "File cleanup",
  prepare: "Task preparation",
  selection: "Guide selection",
};

const jobStates = {
  running: "In progress",
  complete: "Complete",
  failed: "Failed",
  interrupted: "Interrupted",
};

function TaskActivity({
  task,
  projects,
}: {
  task: NonNullable<HubState["last_task"]>;
  projects: HubProject[];
}) {
  const repository =
    projects.find((row) => row.id === task.project_id)?.label ??
    task.project_id;
  const outcome =
    task.state === "failed"
      ? "Failed"
      : (taskOutcomes[task.status ?? ""] ?? "Checked");
  return (
    <>
      {repository} · {outcome}
    </>
  );
}

function PublisherCheck({ timestamp }: { timestamp: number | null }) {
  const checked = timestamp === null ? null : new Date(timestamp * 1000);
  if (!checked || !Number.isFinite(checked.getTime())) {
    return <>No successful check recorded</>;
  }
  return (
    <time dateTime={checked.toISOString()}>
      {checked.toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })}
    </time>
  );
}

function CodexTrustStep() {
  return (
    <p className="tools-hub-guidance">
      Before using automatic workflows, review and trust Temper with{" "}
      <code>/hooks</code> in Codex, then open a new chat.
    </p>
  );
}

function WorkflowLifecycle() {
  return (
    <details className="tools-hub-details">
      <summary>How automatic workflows work</summary>
      <ul className="tools-hub-lifecycle">
        <li>
          <strong>Choose</strong>
          <span>Codex picks up to two guides for the task.</span>
        </li>
        <li>
          <strong>Keep current</strong>
          <span>
            Temper checks approved publishers for updates every six hours.
          </span>
        </li>
        <li>
          <strong>Switch</strong>
          <span>Temper switches guidance as tasks change.</span>
        </li>
        <li>
          <strong>Clean up</strong>
          <span>Temper removes its unchanged copies when a task ends.</span>
        </li>
      </ul>
    </details>
  );
}

function RepositoryGuidance({
  rows,
  stale,
}: {
  rows: HubProject[];
  stale: boolean;
}) {
  return (
    <div className="tools-hub-repositories">
      {rows.map((row) => (
        <div className="tools-hub-project" key={row.id}>
          <div>
            <strong>{row.label}</strong>
            {row.pending_recovery && <span>Recovery needed</span>}
            {row.attention && (
              <span>
                {row.attention.status === "task_cleanup_blocked"
                  ? "Task cleanup needs attention"
                  : "Edited files need attention"}
              </span>
            )}
            {row.paused && <span>Updates paused</span>}
            {row.active.length ? (
              <span className="tools-hub-guidance">
                {stale ? "Last known guidance" : "Available guidance"} ·{" "}
                {row.active.join(", ")}
              </span>
            ) : (
              <span>
                {stale
                  ? "No guidance at the last check"
                  : "No guidance installed"}
              </span>
            )}
          </div>
        </div>
      ))}
      {!rows.length && <p>No repositories to show.</p>}
    </div>
  );
}

export function ToolsHubPanel({
  nativeRuntime,
  onOpenTools,
  showRepositorySetup = false,
}: {
  nativeRuntime: boolean;
  onOpenTools?: () => void;
  showRepositorySetup?: boolean;
}) {
  const headingId = useId();
  const [state, setState] = useState<HubState | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<{
    message: string;
    scope: "panel" | "runtime";
  } | null>(null);
  const [busyScope, setBusyScope] = useState<"panel" | "runtime" | null>(null);
  const busy = busyScope !== null;
  const busyRef = useRef(false);
  const pageVisible = usePageVisibility();
  const statusRequest = useRef<Promise<HubState> | null>(null);
  const [statusPending, setStatusPending] = useState(false);
  const [awaitingActionStatus, setAwaitingActionStatus] = useState(false);
  const [continuityNotice, setContinuityNotice] = useState<string | null>(null);
  const [preparingContinuityReview, setPreparingContinuityReview] =
    useState(false);
  const actionsUnavailable =
    busy ||
    awaitingActionStatus ||
    !!loadError ||
    state?.secure_store_ready === false;
  const [refreshKey, setRefreshKey] = useState(0);
  const [setupRevision, setSetupRevision] = useState(0);
  const continuingWork = useRef<HTMLDetailsElement>(null);
  const continuingSummary = useRef<HTMLElement>(null);
  const [repositories, setRepositories] = useState<Repository[] | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [runtimePaths, setRuntimePaths] = useState({
    node: "",
    node_modules: "",
    browser: "",
  });
  const [review, setReview] = useState<Review | null>(null);
  const reviewTrigger = useRef<HTMLButtonElement | null>(null);
  const panelHeading = useRef<HTMLHeadingElement | null>(null);
  const remotionSummary = useRef<HTMLElement | null>(null);

  function openReview(value: Review, trigger: HTMLButtonElement) {
    reviewTrigger.current = trigger;
    setReview(value);
  }

  useEffect(() => {
    if (!nativeRuntime || !pageVisible) return;
    let live = true;
    let timer: number | undefined;

    async function refresh() {
      if (!live || document.hidden || busyRef.current) return;
      // An earlier visibility or retry cycle may still have a request in flight.
      await statusRequest.current?.catch(() => undefined);
      if (!live || document.hidden || busyRef.current) return;

      setStatusPending(true);
      const request = hubRequest<HubState>("status");
      statusRequest.current = request;
      try {
        const next = await request;
        if (live && !document.hidden && !busyRef.current) {
          setState(next);
          setLoadError(null);
        }
      } catch (value) {
        if (live && !document.hidden && !busyRef.current)
          setLoadError(engineFailureMessage(value));
      } finally {
        if (statusRequest.current === request) statusRequest.current = null;
        if (live && !busyRef.current) {
          setStatusPending(false);
          setAwaitingActionStatus(false);
          if (!document.hidden)
            timer = window.setTimeout(() => void refresh(), 3000);
        }
      }
    }

    function onVisibilityChange() {
      window.clearTimeout(timer);
      if (!document.hidden) setRefreshKey((key) => key + 1);
    }

    void refresh();
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      live = false;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [nativeRuntime, pageVisible, refreshKey]);

  async function action(work: () => Promise<void>, recovery?: string) {
    if (busyRef.current || actionsUnavailable) return;
    busyRef.current = true;
    setBusyScope(recovery ? "runtime" : "panel");
    setActionError(null);
    try {
      await work();
    } catch (value) {
      setActionError({
        message: recovery ?? engineFailureMessage(value),
        scope: recovery ? "runtime" : "panel",
      });
    } finally {
      busyRef.current = false;
      setBusyScope(null);
      setRefreshKey((key) => key + 1);
    }
  }
  async function mutate<T>(
    operation: HubOperation,
    params: object = {},
  ): Promise<T> {
    await statusRequest.current?.catch(() => undefined);
    if (!operation.endsWith("_preview")) setAwaitingActionStatus(true);
    const current = await hubRequest<HubState>("status");
    const result = await hubRequest<T>(operation, params, current.digest);
    if (!operation.endsWith("_preview"))
      setSetupRevision((revision) => revision + 1);
    return result;
  }
  function toggle(
    value: string,
    values: string[],
    update: (next: string[]) => void,
  ) {
    update(
      values.includes(value)
        ? values.filter((item) => item !== value)
        : [...values, value],
    );
  }
  async function confirm() {
    if (!review) return;
    if (review.type === "permission") {
      await mutate("permission_enable", {
        preview_id: review.value.preview_id,
      });
      setRepositories(null);
    } else if (review.type === "connection") {
      await mutate("connection_apply", { preview_id: review.value.preview_id });
    } else if (review.type === "runtime") {
      await mutate("runtime_enable", { preview_id: review.value.preview_id });
    } else if (review.type === "continuity") {
      await mutate("continuity_apply", { preview_id: review.value.preview_id });
      setContinuityNotice(
        review.value.reset
          ? "Saved work was reset. Continuing work is off."
          : review.value.enabled
            ? "Continuing work is on."
            : "Continuing work is off.",
      );
    } else if (review.type === "clear_checkpoint") {
      await mutate("continuity_clear", {
        project_id: review.projectId,
        checkpoint_id: review.checkpointId,
      });
      setContinuityNotice("Checkpoint removed.");
    } else if (review.type === "repair") await mutate("repair");
    else await mutate("control", { operation: "stop" });
    // Confirmation can remove the opener on the next status refresh.
    reviewTrigger.current = null;
    setReview(null);
  }

  function reviewContinuity(
    intent: ContinuingWorkAction,
    trigger: HTMLButtonElement,
  ) {
    setContinuityNotice(null);
    setActionError(null);
    const { project } = intent;
    if (intent.type === "clear") {
      openReview(
        {
          type: "clear_checkpoint",
          projectId: project.id,
          checkpointId: intent.checkpoint.checkpoint_id,
          label: project.label,
        },
        trigger,
      );
      return;
    }
    void action(async () => {
      setPreparingContinuityReview(true);
      try {
        const reset = intent.type === "reset";
        const value = await mutate<ContinuityPreview>("continuity_preview", {
          project_id: project.id,
          enabled: !reset && !project.continuity_enabled,
          ...(reset ? { reset: true } : {}),
        });
        if (Boolean(value.reset) !== reset) {
          throw new Error("Saved work status changed. Review it again.");
        }
        openReview(
          { type: "continuity", value, label: project.label },
          trigger,
        );
      } finally {
        setPreparingContinuityReview(false);
      }
    });
  }
  const failed =
    state?.job?.state === "failed" || state?.job?.state === "interrupted";
  const working = state?.job?.state === "running";
  const taskFailed = state?.enabled && state.last_task?.state === "failed";
  const needsAttention =
    state?.projects.some((row) => row.attention || row.pending_recovery) ||
    state?.secure_store_ready === false;

  const matchingRepositories = (repositories ?? []).filter((row) =>
    `${row.label} ${row.id} ${row.root}`
      .toLowerCase()
      .includes(query.trim().toLowerCase()),
  );
  const attention = needsAttention || taskFailed || failed;
  const connection = state ? connectionReadiness(state) : null;
  const ready = connection === "configured";
  const status = !nativeRuntime
    ? "Desktop feature"
    : loadError
      ? state
        ? "Status out of date"
        : "Status unavailable"
      : !state
        ? "Checking workflow status…"
        : state.cleanup_pending
          ? "Cleanup needed"
          : attention
            ? "Needs attention"
            : !state.enabled
              ? "Setup available"
              : working
                ? "Updating"
                : state.paused
                  ? "Paused"
                  : ready
                    ? "Codex connection configured"
                    : connection === "preparing"
                      ? "Preparing repository tools"
                      : "Codex setup needed";

  const checking = nativeRuntime && !state && !loadError;
  const checkpointChanged =
    review?.type === "clear_checkpoint" &&
    state?.projects.find((project) => project.id === review.projectId)
      ?.continuity?.checkpoint_id !== review.checkpointId;
  const publishers = state?.sources.filter((source) => source.approved) ?? [];
  const stateTone =
    loadError || attention || state?.cleanup_pending
      ? "attention"
      : state?.enabled && ready && !state.paused && !working
        ? "positive"
        : "neutral";
  const showCodexTrustStep =
    state?.enabled &&
    ready &&
    !state.paused &&
    !working &&
    !attention &&
    !state.cleanup_pending &&
    !loadError;
  if (onOpenTools) {
    const relevantRepositories = (
      state?.enabled || state?.cleanup_pending ? state.projects : []
    ).filter(
      (row) =>
        row.active.length ||
        row.attention ||
        row.pending_recovery ||
        row.paused,
    );
    const shownRepositories = relevantRepositories.slice(0, 2);
    const remaining = (state?.project_count ?? 0) - shownRepositories.length;
    const setupAvailable = state && !state.enabled && !state.cleanup_pending;
    return (
      <section
        className="tools-hub-panel tools-hub-panel--overview"
        aria-labelledby={headingId}
      >
        <div className="tools-hub-panel__heading">
          <h2 id={headingId}>Automatic workflows</h2>
          <Button onClick={onOpenTools}>
            {setupAvailable && !loadError
              ? "Set up automatic workflows"
              : "View automatic workflows"}
          </Button>
        </div>
        {checking ? (
          <LoadingStatus>{status}</LoadingStatus>
        ) : (
          <div className="tools-hub-status-row">
            <strong className="tools-hub-state" data-tone={stateTone}>
              {status}
            </strong>
            {state && !setupAvailable && remaining > 0 && (
              <span>
                {remaining} {shownRepositories.length ? "more " : ""}
                {remaining === 1 ? "repository" : "repositories"}
              </span>
            )}
          </div>
        )}
        {loadError && (
          <div className="tools-hub-notice" role="alert">
            <p>
              {state
                ? "Showing the last known workflow status."
                : "Temper couldn’t check workflow status."}
            </p>
            <Button
              type="button"
              disabled={statusPending}
              onClick={() => setRefreshKey((key) => key + 1)}
            >
              {statusPending ? "Refreshing…" : "Retry workflow status"}
            </Button>
          </div>
        )}
        {state?.enabled && !loadError && connection === "connection_needed" && (
          <p className="tools-hub-guidance">
            Connect Codex in Tools to use automatic workflows.
          </p>
        )}
        {showCodexTrustStep && <CodexTrustStep />}
        {shownRepositories.length > 0 && (
          <RepositoryGuidance rows={shownRepositories} stale={!!loadError} />
        )}
        {state?.enabled && state.last_task && (
          <p className="tools-hub-guidance">
            {loadError ? "Last known task check" : "Latest task check"} ·{" "}
            <TaskActivity task={state.last_task} projects={state.projects} />
          </p>
        )}
        {state?.enabled &&
          ready &&
          !state.last_task &&
          !shownRepositories.length &&
          !loadError && (
            <p className="tools-hub-guidance">No task activity recorded.</p>
          )}
        {state ? (
          <ContinuingWork
            compact
            state={state}
            stale={!!loadError}
            pending={statusPending}
            actionsUnavailable={actionsUnavailable}
            onRefresh={() => setRefreshKey((key) => key + 1)}
          />
        ) : null}
      </section>
    );
  }

  return (
    <section className="tools-hub-panel" aria-labelledby={headingId}>
      <div className="tools-hub-panel__heading">
        <h2 id={headingId} ref={panelHeading} tabIndex={-1}>
          Automatic workflows
        </h2>
      </div>
      {checking ? (
        <LoadingStatus>{status}</LoadingStatus>
      ) : (
        <div className="tools-hub-status-row">
          <strong className="tools-hub-state" data-tone={stateTone}>
            {status}
          </strong>
        </div>
      )}
      {loadError && !review && (
        <div className="tools-hub-notice" role="alert">
          <p>
            {state
              ? "Showing the last known status. Refresh status to make changes."
              : "Temper couldn’t check tool status."}
          </p>
          <details className="learning-details">
            <summary>Technical details</summary>
            <p>{loadError}</p>
          </details>
          <Button
            type="button"
            disabled={statusPending || busy}
            onClick={() => setRefreshKey((key) => key + 1)}
          >
            {statusPending ? "Refreshing…" : "Refresh status"}
          </Button>
        </div>
      )}
      {!review && actionError?.scope === "panel" && (
        <p className="tools-hub-notice" role="alert">
          {actionError.message}
        </p>
      )}
      {state?.secure_store_ready === false && (
        <p role="status">Unlock your secure store to make changes.</p>
      )}
      {showCodexTrustStep && <CodexTrustStep />}
      {showRepositorySetup && (
        <PortableSetupPanel
          nativeRuntime={nativeRuntime}
          status={{
            state,
            pending: checking || busy || awaitingActionStatus,
            failed: Boolean(loadError),
            revision: setupRevision,
            refresh: () => setRefreshKey((key) => key + 1),
          }}
          onContinue={
            state?.projects.some(
              (project) => project.continuity_enabled !== undefined,
            )
              ? () => {
                  if (continuingWork.current)
                    continuingWork.current.open = true;
                  continuingSummary.current?.focus();
                }
              : undefined
          }
        />
      )}
      {!nativeRuntime ? (
        <p>Open the desktop app to choose repositories and connect Codex.</p>
      ) : (
        state && (
          <>
            {!state.enabled && !state.cleanup_pending && !repositories && (
              <div className="tools-hub-primary">
                <p>
                  Choose where Temper can manage tools and which publishers
                  Codex can use. Tool setup has its own permissions, separate
                  from chat learning.
                </p>
                <Button
                  disabled={actionsUnavailable}
                  onClick={() =>
                    void action(async () => {
                      const result = await hubRequest<{
                        projects: Repository[];
                      }>("inventory");
                      setRepositories(result.projects);
                    })
                  }
                >
                  Set up repository tools
                </Button>
              </div>
            )}
            {state.cleanup_pending && !state.enabled && (
              <div className="tools-hub-cleanup" role="status">
                <h3>Tool updates have stopped</h3>
                <p>
                  Some managed files still need cleanup. Edited files are
                  preserved; they can remain visible to Codex until you remove
                  them or restore their saved version.
                </p>
                {state.job?.message && <p>{state.job.message}</p>}
                <ul>
                  {state.projects
                    .filter((row) => row.active.length || row.pending_recovery)
                    .map((row) => (
                      <li key={row.id}>
                        {row.label} ({row.id}):{" "}
                        {row.active.join(", ") || "Interrupted update"}
                      </li>
                    ))}
                </ul>
                <ul>
                  {state.job?.result?.projects
                    ?.filter((row) => row.conflicts?.length)
                    .map((row) => (
                      <li key={row.project_id}>
                        {row.project_id}: {row.conflicts?.join(", ")}
                      </li>
                    ))}
                </ul>
                <Button
                  disabled={actionsUnavailable || working}
                  onClick={() =>
                    void action(async () => {
                      await mutate("control", { operation: "stop" });
                    })
                  }
                >
                  {working ? "Cleaning up…" : "Retry safe cleanup"}
                </Button>
              </div>
            )}
            {repositories && !state.enabled && !state.cleanup_pending && (
              <div className="tools-hub-setup">
                <h3>Where should Temper manage tools?</h3>
                <label>
                  Find a repository
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    type="search"
                  />
                </label>
                <div
                  className="tools-hub-repositories"
                  role="group"
                  aria-label="Repositories for tool setup"
                >
                  {matchingRepositories.map((row) => (
                    <label key={row.id}>
                      <input
                        type="checkbox"
                        aria-label={`${row.label} · ${row.id}`}
                        checked={chosen.includes(row.id)}
                        onChange={() => toggle(row.id, chosen, setChosen)}
                      />
                      <span>
                        {row.label}
                        <small>{row.id}</small>
                        <small>{row.root}</small>
                      </span>
                    </label>
                  ))}
                </div>
                {!matchingRepositories.length && (
                  <p role="status">
                    {repositories.length
                      ? "No repositories match your search."
                      : "Add a repository in Temper to continue."}
                  </p>
                )}
                <fieldset>
                  <legend>Publishers to keep available</legend>
                  {state.sources.map((source) => (
                    <label key={source.id}>
                      <input
                        type="checkbox"
                        checked={sources.includes(source.id)}
                        onChange={() => toggle(source.id, sources, setSources)}
                      />
                      {source.label}
                    </label>
                  ))}
                </fieldset>
                <div className="tools-hub-actions">
                  <Button
                    disabled={
                      actionsUnavailable || !chosen.length || !sources.length
                    }
                    onClick={(event) => {
                      const trigger = event.currentTarget;
                      void action(async () => {
                        openReview(
                          {
                            type: "permission",
                            value: await mutate<HubPreview>(
                              "permission_preview",
                              { project_ids: chosen, source_ids: sources },
                            ),
                          },
                          trigger,
                        );
                      });
                    }}
                  >
                    Review setup
                  </Button>
                  <Button type="button" onClick={() => setRepositories(null)}>
                    Cancel
                  </Button>
                </div>
              </div>
            )}
            {state.enabled && (
              <>
                <div className="tools-hub-activity">
                  <h3>
                    {loadError ? "Last known activity" : "Workflow activity"}
                  </h3>
                  <dl>
                    <dt>Latest task check</dt>
                    <dd>
                      {state.last_task ? (
                        <TaskActivity
                          task={state.last_task}
                          projects={state.projects}
                        />
                      ) : (
                        "No task activity recorded"
                      )}
                    </dd>
                    <dt>Approved publishers</dt>
                    <dd>
                      {publishers.map((source) => source.label).join(", ") ||
                        "None"}
                    </dd>
                    <dt>Last successful publisher check</dt>
                    <dd>
                      <PublisherCheck timestamp={state.last_checked} />
                    </dd>
                    {state.job && (
                      <>
                        <dt>
                          {jobLabels[state.job.operation] ?? "Tool operation"}
                        </dt>
                        <dd>{jobStates[state.job.state]}</dd>
                      </>
                    )}
                  </dl>
                </div>
                {!showRepositorySetup && (
                  <div className="tools-hub-overview">
                    <h3>
                      {loadError
                        ? "Last known repositories"
                        : "Approved repositories"}
                    </h3>
                    <RepositoryGuidance
                      rows={state.projects}
                      stale={!!loadError}
                    />
                  </div>
                )}
                <div className="tools-hub-actions">
                  {state.paused ? (
                    <Button
                      disabled={actionsUnavailable}
                      onClick={() =>
                        void action(async () => {
                          await mutate("control", { operation: "resume" });
                        })
                      }
                    >
                      Resume updates
                    </Button>
                  ) : connection === "connection_needed" && !working ? (
                    <Button
                      disabled={actionsUnavailable}
                      onClick={(event) => {
                        const trigger = event.currentTarget;
                        void action(async () =>
                          openReview(
                            {
                              type: "connection",
                              value:
                                await mutate<ConnectionPreview>(
                                  "connection_preview",
                                ),
                            },
                            trigger,
                          ),
                        );
                      }}
                    >
                      {state.bridge_configured
                        ? "Update Codex connection"
                        : "Connect Codex"}
                    </Button>
                  ) : attention && (failed || taskFailed) && !working ? (
                    <Button
                      disabled={actionsUnavailable}
                      onClick={(event) =>
                        openReview({ type: "repair" }, event.currentTarget)
                      }
                    >
                      Repair setup
                    </Button>
                  ) : null}
                  <Button
                    type="button"
                    disabled={actionsUnavailable || working || state.paused}
                    onClick={() =>
                      void action(async () => {
                        await mutate("refresh");
                      })
                    }
                  >
                    Check for updates
                  </Button>
                </div>

                {working && !loadError && (
                  <LoadingStatus>
                    {state.job?.operation === "cleanup"
                      ? "Removing unchanged Temper-managed files…"
                      : `${jobLabels[state.job?.operation ?? ""] ?? "Tool operation"} in progress…`}
                  </LoadingStatus>
                )}
                {(failed || taskFailed) && (
                  <p role="alert">
                    {state.last_task?.state === "failed"
                      ? (state.last_task.message ??
                        "The latest task check failed.")
                      : (state.job?.message ??
                        "The latest tool operation needs attention.")}
                  </p>
                )}
                <details className="tools-hub-settings">
                  <summary>Tool settings</summary>
                  <div className="tools-hub-actions">
                    {!state.paused && (
                      <Button
                        type="button"
                        disabled={actionsUnavailable}
                        onClick={() =>
                          void action(async () => {
                            await mutate("control", { operation: "pause" });
                          })
                        }
                      >
                        Pause updates
                      </Button>
                    )}
                    {(failed || taskFailed) &&
                      !state.paused &&
                      (connection === "connection_needed" || working) && (
                        <Button
                          type="button"
                          disabled={
                            actionsUnavailable || working || state.paused
                          }
                          onClick={(event) =>
                            openReview({ type: "repair" }, event.currentTarget)
                          }
                        >
                          Repair setup
                        </Button>
                      )}
                    <Button
                      type="button"
                      disabled={actionsUnavailable}
                      onClick={(event) =>
                        openReview({ type: "stop" }, event.currentTarget)
                      }
                    >
                      Stop managing tools
                    </Button>
                  </div>
                  <div
                    className="tools-hub-repositories"
                    aria-label="Repository settings"
                  >
                    {state.projects.map((row) => (
                      <div className="tools-hub-project" key={row.id}>
                        <div>
                          <strong>{row.label}</strong>
                          <small>{row.root}</small>
                          {row.attention && (
                            <small>{row.attention.conflicts.join(", ")}</small>
                          )}
                        </div>
                        <div className="tools-hub-actions">
                          <Button
                            type="button"
                            disabled={actionsUnavailable || working}
                            onClick={() =>
                              void action(async () => {
                                await mutate("control", {
                                  operation: row.paused ? "resume" : "pause",
                                  project_id: row.id,
                                });
                              })
                            }
                          >
                            {row.paused ? "Resume" : "Pause"}
                          </Button>
                          <Button
                            type="button"
                            disabled={
                              actionsUnavailable || working || !row.can_rollback
                            }
                            onClick={() =>
                              void action(async () => {
                                await mutate("control", {
                                  operation: "rollback",
                                  project_id: row.id,
                                });
                              })
                            }
                          >
                            Undo last change
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                  {state.remotion_available && (
                    <details>
                      <summary ref={remotionSummary}>
                        Remotion video rendering
                      </summary>
                      <p>
                        Allow the agent to render short videos with an installed
                        Remotion toolchain on Windows x64. This requires a
                        separate approval for these repositories.
                      </p>
                      {state.remotion_enabled ? (
                        <Button
                          type="button"
                          disabled={actionsUnavailable}
                          onClick={() =>
                            void action(async () => {
                              await mutate("runtime_revoke");
                              remotionSummary.current?.focus();
                            })
                          }
                        >
                          Disable Remotion
                        </Button>
                      ) : (
                        <div className="tools-hub-setup">
                          <p>
                            Enter the full Windows paths to Node.js 24, the
                            Remotion 4.0.542 node_modules directory, and Chrome
                            Headless Shell.
                          </p>
                          {(
                            [
                              ["node", "Node executable"],
                              [
                                "node_modules",
                                "Remotion node_modules directory",
                              ],
                              ["browser", "Chrome Headless Shell executable"],
                            ] as const
                          ).map(([key, label]) => (
                            <label key={key}>
                              {label}
                              <input
                                value={runtimePaths[key]}
                                onChange={(event) => {
                                  if (actionError?.scope === "runtime")
                                    setActionError(null);
                                  setRuntimePaths({
                                    ...runtimePaths,
                                    [key]: event.currentTarget.value,
                                  });
                                }}
                              />
                            </label>
                          ))}
                          <Button
                            disabled={
                              actionsUnavailable ||
                              working ||
                              state.paused ||
                              Object.values(runtimePaths).some(
                                (path) => !path.trim(),
                              )
                            }
                            onClick={(event) => {
                              const trigger = event.currentTarget;
                              void action(
                                async () =>
                                  openReview(
                                    {
                                      type: "runtime",
                                      value: await mutate<RuntimePreview>(
                                        "runtime_preview",
                                        runtimePaths,
                                      ),
                                    },
                                    trigger,
                                  ),
                                "Remotion setup could not be checked. Verify all three paths and versions, then review setup again.",
                              );
                            }}
                          >
                            Review Remotion setup
                          </Button>
                          {!review && busyScope === "runtime" && (
                            <p role="status">
                              Checking the installed toolchain…
                            </p>
                          )}
                          {!review && actionError?.scope === "runtime" && (
                            <p role="alert">{actionError.message}</p>
                          )}
                        </div>
                      )}
                    </details>
                  )}
                </details>
              </>
            )}
          </>
        )
      )}
      {state?.projects.some(
        (project) => project.continuity_enabled !== undefined,
      ) ? (
        <details
          className="tools-hub-details"
          ref={continuingWork}
          open={!showRepositorySetup}
        >
          <summary ref={continuingSummary}>Saved work</summary>
          <ContinuingWork
            state={state}
            stale={!!loadError}
            pending={statusPending}
            actionsUnavailable={actionsUnavailable}
            notice={continuityNotice}
            preparingReview={preparingContinuityReview}
            onRefresh={() => setRefreshKey((key) => key + 1)}
            onAction={reviewContinuity}
          />
        </details>
      ) : null}
      {nativeRuntime && <WorkflowLifecycle />}
      <Dialog.Root
        open={pageVisible && review !== null}
        onOpenChange={(open) => {
          if (!open && !busy) setReview(null);
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content
            className="review-dialog tools-hub-review"
            onCloseAutoFocus={(event) => {
              event.preventDefault();
              const heading = panelHeading.current;
              // Radix may finish closing after the cached page becomes hidden.
              if (
                !pageVisible ||
                !heading ||
                heading.closest("[hidden], [inert]")
              )
                return;
              const trigger = reviewTrigger.current;
              if (trigger?.isConnected && !trigger.disabled) trigger.focus();
              else heading.focus();
            }}
          >
            <Dialog.Title>
              {review?.type === "permission"
                ? "Allow repository tool setup"
                : review?.type === "connection"
                  ? "Connect Codex to repository setup"
                  : review?.type === "runtime"
                    ? "Allow Remotion video rendering"
                    : review?.type === "repair"
                      ? "Repair the private manager"
                      : review?.type === "continuity"
                        ? review.value.reset
                          ? "Reset saved work"
                          : `${review.value.enabled ? "Turn on" : "Turn off"} continuing work`
                        : review?.type === "clear_checkpoint"
                          ? "Remove saved checkpoint"
                          : "Stop managing repository tools"}
            </Dialog.Title>
            <Dialog.Description>
              {review?.type === "permission"
                ? "Temper may maintain up to two applicable skills per task in these repositories until you stop it. SkillKit handles installation; your agent chooses what applies."
                : review?.type === "connection"
                  ? "Allow Codex to automatically prepare tasks, select tools, render with a separately approved runtime, and finish tasks in approved repositories. Review and trust the lifecycle hooks in Codex before starting a new chat."
                  : review?.type === "runtime"
                    ? "Allow short MP4 renders with this exact local toolchain during active tasks in these repositories."
                    : review?.type === "repair"
                      ? "Reinstall the pinned private SkillKit copy, discard its downloaded source cache, and fetch approved sources again. Repository profiles and permissions are preserved."
                      : review?.type === "continuity"
                        ? review.value.reset
                          ? `Remove the unreadable saved work for ${review.label} and turn off continuing work. You can turn it on again to save a new checkpoint.`
                          : review.value.enabled
                            ? `Allow Codex to save a brief checkpoint for ${review.label} on this device and retrieve it in a later chat in the same repository.`
                            : review.value.removes_checkpoint
                              ? `Stop saving checkpoints for ${review.label} and remove the saved checkpoint.`
                              : `Stop saving checkpoints for ${review.label}.`
                        : review?.type === "clear_checkpoint"
                          ? `Remove the saved checkpoint for ${review.label}. Codex can save a new checkpoint when you work in this repository again.`
                          : "Stop updates and remove unchanged Temper-managed skill files. Files you edited are preserved and may need your attention."}
            </Dialog.Description>
            {checkpointChanged ? (
              <p role="alert">
                This checkpoint has changed. Close this review to see the latest
                saved work.
              </p>
            ) : actionError ? (
              <p role="alert">{actionError.message}</p>
            ) : null}
            {state?.secure_store_ready === false && (
              <p role="status">Unlock your secure store to make changes.</p>
            )}
            {loadError && (
              <div className="tools-hub-notice" role="alert">
                <p>Tool status is out of date. Refresh status to continue.</p>
                <Button
                  type="button"
                  disabled={statusPending || busy}
                  onClick={() => setRefreshKey((key) => key + 1)}
                >
                  {statusPending ? "Refreshing…" : "Refresh status"}
                </Button>
              </div>
            )}
            {review?.type === "permission" && (
              <>
                <ul>
                  {review.value.projects.map((row) => (
                    <li key={row.id}>
                      {row.id}
                      <code>{row.root}</code>
                    </li>
                  ))}
                </ul>
                <p>Where Temper will write guidance</p>
                <ul>
                  {review.value.destinations.map((destination) => (
                    <li key={destination}>
                      <code>{destination}</code>
                    </li>
                  ))}
                </ul>
                <p>
                  A small .temper-hub-project registration file is added to each
                  selected repository. No repository policy file is replaced.
                </p>
                <ul>
                  {review.value.source_specs?.map((source) => (
                    <li key={source.id}>
                      {source.id}
                      <code>
                        {source.url} · {source.ref} · {source.roots.join(", ")}
                      </code>
                    </li>
                  ))}
                </ul>
                <p>
                  Private manager:{" "}
                  <code>{review.value.manager_destination}</code>
                </p>
                <p>
                  Requires Node.js 24. Uses pinned SkillKit 1.24.0 without
                  optional dependencies or install scripts. Hub storage uses a 1
                  GB budget, including a 512 MB source cache.
                </p>
                <p>
                  This does not authorize chat learning, extra agents, paid
                  services or publishing.
                </p>
              </>
            )}
            {review?.type === "connection" && (
              <ul>
                {review.value.files.map((file) => (
                  <li key={file.path}>
                    <code>{file.path}</code>
                    <pre
                      role="region"
                      aria-label={`Proposed ${file.path.replaceAll("\\", "/").split("/").at(-1)} section`}
                      // A scroll region needs focus for native keyboard scrolling.
                      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
                      tabIndex={0}
                    >
                      {file.block}
                    </pre>
                  </li>
                ))}
              </ul>
            )}
            {review?.type === "runtime" && (
              <>
                <p>Remotion {review.value.admission.version}</p>
                <ul>
                  {review.value.paths.map((path, index) => (
                    <li key={path}>
                      <code>{path}</code>
                      <code>
                        {
                          [
                            review.value.admission.node_digest,
                            review.value.admission.module_tree_digest,
                            review.value.admission.browser_tree_digest,
                          ][index]
                        }
                      </code>
                    </li>
                  ))}
                </ul>
                <p>Repositories {review.value.projects.join(", ")}</p>
              </>
            )}
            <div className="tools-hub-actions">
              <Button
                disabled={actionsUnavailable || checkpointChanged}
                onClick={() =>
                  void action(
                    confirm,
                    review?.type === "runtime"
                      ? "Remotion setup could not be approved. Close this review and check the installed paths and versions again."
                      : undefined,
                  )
                }
              >
                {busy
                  ? review?.type === "runtime"
                    ? "Checking and saving…"
                    : "Saving…"
                  : review?.type === "stop"
                    ? "Stop and clean up"
                    : review?.type === "repair"
                      ? "Repair setup"
                      : review?.type === "continuity"
                        ? review.value.reset
                          ? "Reset saved work"
                          : review.value.enabled
                            ? "Turn on"
                            : "Turn off"
                        : review?.type === "clear_checkpoint"
                          ? "Remove checkpoint"
                          : "Allow and continue"}
              </Button>
              <Button
                type="button"
                disabled={busy}
                onClick={() => setReview(null)}
              >
                Cancel
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  );
}
