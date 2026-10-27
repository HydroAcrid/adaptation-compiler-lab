import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useRef, useState } from "react";
import { engineFailureMessage } from "../engine";
import {
  hubRequest,
  type ConnectionPreview,
  type HubOperation,
  type HubPreview,
  type HubState,
} from "../toolsHub";
import { Button, StatusPill } from "./ui";

type Repository = { id: string; label: string; root: string };
type Review =
  | { type: "permission"; value: HubPreview }
  | { type: "connection"; value: ConnectionPreview }
  | { type: "stop" | "repair" };

export function ToolsHubPanel({ nativeRuntime }: { nativeRuntime: boolean }) {
  const [state, setState] = useState<HubState | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const error = loadError ?? actionError;
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const version = useRef(0);
  const [refreshKey, setRefreshKey] = useState(0);
  const [repositories, setRepositories] = useState<Repository[] | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [review, setReview] = useState<Review | null>(null);
  const reviewTrigger = useRef<HTMLButtonElement | null>(null);
  const panelHeading = useRef<HTMLHeadingElement | null>(null);

  function openReview(value: Review, trigger: HTMLButtonElement) {
    reviewTrigger.current = trigger;
    setReview(value);
  }

  useEffect(() => {
    if (!nativeRuntime) return;
    let live = true;
    const refresh = async () => {
      if (busyRef.current) return;
      const request = ++version.current;
      try {
        const next = await hubRequest<HubState>("status");
        if (live && request === version.current && !busyRef.current) {
          setState(next);
          setLoadError(null);
        }
      } catch (value) {
        if (live && request === version.current && !busyRef.current)
          setLoadError(engineFailureMessage(value));
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [nativeRuntime, refreshKey]);

  async function action(work: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    ++version.current;
    setBusy(true);
    setActionError(null);
    try {
      await work();
    } catch (value) {
      setActionError(engineFailureMessage(value));
    } finally {
      busyRef.current = false;
      setBusy(false);
      setRefreshKey((key) => key + 1);
    }
  }
  async function mutate<T>(
    operation: HubOperation,
    params: object = {},
  ): Promise<T> {
    const current = await hubRequest<HubState>("status");
    return hubRequest<T>(operation, params, current.digest);
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
    } else if (review.type === "repair") await mutate("repair");
    else await mutate("control", { operation: "stop" });
    // Confirmation can remove the opener on the next status refresh.
    reviewTrigger.current = null;
    setReview(null);
  }
  const failed =
    state?.job?.state === "failed" || state?.job?.state === "interrupted";
  const working = state?.job?.state === "running";
  const taskFailed = state?.enabled && state.last_task?.state === "failed";
  const needsAttention =
    state?.projects.some((row) => row.attention || row.pending_recovery) ||
    state?.secure_store_ready === false;

  return (
    <section
      className="tools-hub-panel folio-card"
      aria-labelledby="tools-hub-title"
    >
      <div className="tools-hub-panel__heading">
        <div>
          <h2 id="tools-hub-title" ref={panelHeading} tabIndex={-1}>
            Repository setup
          </h2>
          <p>
            A small set of tools for the task at hand, maintained through
            SkillKit.
          </p>
        </div>
        <StatusPill
          tone={
            error || failed || taskFailed || needsAttention
              ? "attention"
              : state?.enabled
                ? "positive"
                : "neutral"
          }
        >
          {error
            ? "Status unavailable"
            : needsAttention || taskFailed || failed
              ? "Needs attention"
              : !nativeRuntime
                ? "Desktop feature"
                : !state
                  ? "Checking"
                  : state.cleanup_pending
                    ? "Cleanup needs attention"
                    : !state.enabled
                      ? "Not enabled"
                      : state.paused
                        ? "Paused"
                        : working
                          ? "Updating"
                          : state.indexed
                            ? "Ready for tasks"
                            : "Setup needed"}
        </StatusPill>
      </div>
      {error && (
        <p role="alert">
          {error}{" "}
          <button type="button" onClick={() => setRefreshKey((key) => key + 1)}>
            Refresh status
          </button>
        </p>
      )}
      {state?.secure_store_ready === false && (
        <p role="status">
          Unlock the secure store to resume tool changes. Existing permission is
          preserved.
        </p>
      )}
      {!nativeRuntime ? (
        <p>Open the desktop app to choose repositories and connect Codex.</p>
      ) : (
        state && (
          <>
            {!state.enabled && !state.cleanup_pending && !repositories && (
              <>
                <p>
                  Approve repositories and publishers once. Your agent checks
                  what fits each task and leaves unrelated tools off. This
                  permission is separate from chat learning.
                </p>
                <Button
                  disabled={busy || !!loadError}
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
              </>
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
                  disabled={busy || working || !!loadError}
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
            {repositories && (
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
                  {repositories
                    .filter((row) =>
                      `${row.label} ${row.id} ${row.root}`
                        .toLowerCase()
                        .includes(query.toLowerCase()),
                    )
                    .map((row) => (
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
                    disabled={busy || !chosen.length || !sources.length}
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
                  <button type="button" onClick={() => setRepositories(null)}>
                    Cancel
                  </button>
                </div>
              </div>
            )}
            {state.enabled && (
              <>
                <p>
                  {state.project_count}{" "}
                  {state.project_count === 1
                    ? "repository approved"
                    : "repositories approved"}
                  .{" "}
                  {state.bridge_configured
                    ? "Codex connection saved. Start a new chat to load it."
                    : "Connect Codex after setup to let it choose tools during ordinary work."}
                </p>
                {state.last_task?.status === "deferred_incompatible_update" && (
                  <p role="status">
                    The upstream update has unsupported requirements. Your
                    previous working tools are still available.
                  </p>
                )}
                {working && (
                  <p role="status">
                    {state.job?.operation === "cleanup"
                      ? "Removing unchanged Temper-managed files…"
                      : "Preparing approved tools in the background. You can keep using the app."}
                  </p>
                )}
                {(failed || taskFailed) && (
                  <p role="alert">
                    {state.last_task?.state === "failed"
                      ? state.last_task.message
                      : (state.job?.message ??
                        "Setup needs attention. Your existing profile was preserved.")}
                  </p>
                )}
                <div className="tools-hub-actions">
                  {!state.bridge_configured && (
                    <Button
                      disabled={
                        busy || working || !state.indexed || !!loadError
                      }
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
                      Connect Codex
                    </Button>
                  )}
                  <button
                    type="button"
                    disabled={busy || !!loadError}
                    onClick={() =>
                      void action(async () => {
                        await mutate("control", {
                          operation: state.paused ? "resume" : "pause",
                        });
                      })
                    }
                  >
                    {state.paused ? "Resume updates" : "Pause updates"}
                  </button>
                  <button
                    type="button"
                    disabled={busy || working || state.paused || !!loadError}
                    onClick={() =>
                      void action(async () => {
                        await mutate("refresh");
                      })
                    }
                  >
                    Check for updates
                  </button>
                  {(failed || taskFailed) && (
                    <button
                      type="button"
                      disabled={busy || working || state.paused || !!loadError}
                      onClick={(event) =>
                        openReview({ type: "repair" }, event.currentTarget)
                      }
                    >
                      Repair setup
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={busy || !!loadError}
                    onClick={(event) =>
                      openReview({ type: "stop" }, event.currentTarget)
                    }
                  >
                    Stop managing tools
                  </button>
                </div>
                <div
                  className="tools-hub-repositories"
                  aria-label="Managed tool profiles"
                >
                  {state.projects.map((row) => (
                    <div className="tools-hub-project" key={row.id}>
                      <div>
                        <strong>{row.label}</strong>
                        <small>{row.id}</small>
                        <span>
                          {row.pending_recovery
                            ? "Recovery needed"
                            : row.attention
                              ? "Edited files preserved"
                              : row.paused
                                ? "Updates paused"
                                : row.active.length
                                  ? row.active.join(", ")
                                  : "Waiting for a task"}
                        </span>
                        {row.attention && (
                          <small>{row.attention.conflicts.join(", ")}</small>
                        )}
                      </div>
                      <div className="tools-hub-actions">
                        <button
                          type="button"
                          disabled={busy || working || !!loadError}
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
                        </button>
                        <button
                          type="button"
                          disabled={
                            busy || working || !row.can_rollback || !!loadError
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
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
                <p className="subtle">
                  Checks approved sources every six hours. Changed guidance
                  needs the agent’s task check before it replaces a working
                  profile. Setup checks do not show whether a tool helped.
                </p>
              </>
            )}
          </>
        )
      )}
      <Dialog.Root
        open={review !== null}
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
              const trigger = reviewTrigger.current;
              if (trigger?.isConnected && !trigger.disabled) trigger.focus();
              else panelHeading.current?.focus();
            }}
          >
            <Dialog.Title>
              {review?.type === "permission"
                ? "Allow repository tool setup"
                : review?.type === "connection"
                  ? "Connect Codex to repository setup"
                  : review?.type === "repair"
                    ? "Repair the private manager"
                    : "Stop managing repository tools"}
            </Dialog.Title>
            <Dialog.Description>
              {review?.type === "permission"
                ? "Temper may maintain up to two applicable skills per task in these repositories until you stop it. SkillKit handles installation; your agent chooses what applies."
                : review?.type === "connection"
                  ? "Add a dedicated Hub endpoint and a short instruction section. Your other Codex settings and instructions are preserved. New chats load the connection."
                  : review?.type === "repair"
                    ? "Reinstall the pinned private SkillKit copy, discard its downloaded source cache, and fetch approved sources again. Repository profiles and permissions are preserved."
                    : "Stop updates and remove unchanged Temper-managed skill files. Files you edited are preserved and may need your attention."}
            </Dialog.Description>
            {actionError && <p role="alert">{actionError}</p>}
            {review?.type === "permission" && (
              <>
                <ul>
                  {review.value.projects.map((row) => (
                    <li key={row.id}>
                      {row.id}
                      <code>{row.root}/.agents/skills</code>
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
            <div className="tools-hub-actions">
              <Button disabled={busy} onClick={() => void action(confirm)}>
                {busy
                  ? "Saving…"
                  : review?.type === "stop"
                    ? "Stop and clean up"
                    : review?.type === "repair"
                      ? "Repair setup"
                      : "Allow and continue"}
              </Button>
              <button
                type="button"
                disabled={busy}
                onClick={() => setReview(null)}
              >
                Cancel
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  );
}
