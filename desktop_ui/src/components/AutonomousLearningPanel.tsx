import { useEffect, useId, useRef, useState } from "react";
import {
  controlAutonomy,
  enableLearningGrant,
  explainHabit,
  loadAutonomy,
  previewLearningGrant,
  type AutonomyControl,
  type AutonomyState,
  type Bound,
  type GrantPreview,
  type LearningProjectAccess,
  type StyleCategory,
} from "../autonomy";
import { engineFailureMessage, type EngineProject } from "../engine";
import { usePageVisibility } from "../pageVisibility";
import { Button, LoadingStatus, StatusPill, Toggle } from "./ui";

const categories: { id: StyleCategory; label: string }[] = [
  { id: "communication_detail", label: "Amount of detail" },
  { id: "presentation_style", label: "Presentation" },
  { id: "suggestion_style", label: "Suggestions" },
];
const habitStates = {
  provisional: "Gathering evidence",
  trial: "Trying",
  active: "Active",
  paused: "Paused",
  retired: "Removed",
};
const changeLabels: Record<string, string> = {
  habit: "Habit evidence updated",
  publication: "Agent instructions updated",
  habit_revoked: "Habit removed",
  grant_revoked: "Learning permission revoked",
};
const controlProgress: Record<AutonomyControl, string> = {
  pause_learning: "Pausing learning…",
  resume_learning: "Resuming learning…",
  enable_personalization: "Turning personalization on…",
  disable_personalization: "Turning personalization off…",
  revoke_grant: "Revoking learning access…",
  revoke_habit: "Removing habit…",
};
type HabitEvidence = Awaited<ReturnType<typeof explainHabit>>["value"];

function ApprovedLearningProjects({
  projects,
  stale,
}: {
  projects: LearningProjectAccess[];
  stale: boolean;
}) {
  return (
    <details className="learning-details">
      <summary>
        {stale ? "Last known approved repositories" : "Approved repositories"} (
        {projects.length})
      </summary>
      <div className="learning-details__body">
        <ul className="learning-history">
          {projects.map((project) => (
            <li key={project.project_id}>
              {project.display_name}
              {projects.some(
                (other) =>
                  other.display_name === project.display_name &&
                  other.project_id !== project.project_id,
              ) && ` · ${project.project_id}`}
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}

export function AutonomousLearningPanel({
  projects,
  onOpenPersonalization,
}: {
  projects: EngineProject[];
  onOpenPersonalization?: () => void;
}) {
  const headingId = useId();
  const visible = usePageVisibility();
  const [state, setState] = useState<Bound<AutonomyState> | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [selectedCategories, setSelectedCategories] = useState<StyleCategory[]>(
    [],
  );
  const [preview, setPreview] = useState<Bound<GrantPreview> | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const busy = progress !== null;
  const [trustAuthorizedChats, setTrustAuthorizedChats] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<HabitEvidence | null>(null);
  const habitsHeading = useRef<HTMLHeadingElement>(null);
  const busyRef = useRef(false);
  const requestVersion = useRef(0);
  const pendingRead = useRef<Promise<Bound<AutonomyState>> | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  useEffect(() => {
    if (!visible) return;
    let live = true;
    let refreshing = false;
    const refresh = async () => {
      if (busyRef.current || refreshing) return;
      refreshing = true;
      let version = requestVersion.current;
      let read: Promise<Bound<AutonomyState>> | null = null;
      try {
        if (pendingRead.current)
          await pendingRead.current.catch(() => undefined);
        if (!live || busyRef.current) return;
        version = ++requestVersion.current;
        read = loadAutonomy();
        pendingRead.current = read;
        const value = await read;
        if (live && version === requestVersion.current && !busyRef.current) {
          setState(value);
          setLoadError(null);
        }
      } catch (value) {
        if (live && version === requestVersion.current && !busyRef.current) {
          setLoadError(engineFailureMessage(value));
        }
      } finally {
        if (pendingRead.current === read) pendingRead.current = null;
        refreshing = false;
      }
    };
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    void refresh();
    const interval = window.setInterval(refreshWhenVisible, 30_000);
    window.addEventListener("focus", refreshWhenVisible);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      live = false;
      window.clearInterval(interval);
      window.removeEventListener("focus", refreshWhenVisible);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [refreshKey, visible]);

  async function run(message: string, operation: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    requestVersion.current += 1;
    setProgress(message);
    setActionError(null);
    try {
      await operation();
    } catch (value) {
      setActionError(engineFailureMessage(value));
    } finally {
      busyRef.current = false;
      setProgress(null);
    }
  }
  const control = (action: AutonomyControl, habitId?: string) =>
    run(controlProgress[action], async () => {
      if (state) {
        setState(await controlAutonomy(action, state.digest, habitId));
        setEvidence(null);
        if (action === "revoke_habit") habitsHeading.current?.focus();
      }
    });
  const status = state?.value;
  const learningProjects = status?.project_access;
  const grantProjects = learningProjects ?? projects;
  const approvedProjects = learningProjects?.filter(
    (project) => project.learning_authorized,
  );
  const approvedCount = approvedProjects?.length;
  const currentHabits = status?.habits.filter(
    (habit) => habit.state !== "retired",
  );
  const blocked = Boolean(loadError) || status?.secure_store_ready === false;
  const learningLabel = loadError
    ? "Unavailable"
    : !status
      ? "Checking…"
      : !status.grant_enabled
        ? "Off"
        : !status.secure_store_ready || status.provenance_state === "unverified"
          ? "Needs attention"
          : !status.learning_enabled
            ? "Paused"
            : status.capture_state === "ready"
              ? "Enabled"
              : "Waiting";
  const loading = !status && !loadError;
  const statusNotice = loadError ? (
    <div className="autonomy-notice" role="alert">
      <strong>Learning status is unavailable.</strong>
      <p>
        {status
          ? "The last status could not be refreshed."
          : "Temper couldn’t read your learning settings."}
      </p>
      <div className="autonomy-panel__actions">
        <Button
          tone="quiet"
          onClick={() => setRefreshKey((value) => value + 1)}
        >
          Try again
        </Button>
        <details className="learning-details">
          <summary>Technical details</summary>
          <p>{loadError}</p>
        </details>
      </div>
    </div>
  ) : null;
  const statusTone =
    learningLabel === "Enabled"
      ? "positive"
      : learningLabel === "Needs attention" || loadError
        ? "attention"
        : "neutral";
  const personalizationLabel = loadError
    ? "Status unavailable"
    : !status?.personalization_enabled
      ? "Off"
      : !status.automatic_serving_ready ||
          !status.secure_store_ready ||
          status.publication_needs_attention
        ? "Waiting for checks"
        : "On";
  const publicationLabel = !status?.published
    ? "No habits added to agent instructions"
    : status.delivery_confirmed
      ? "Agent loading recorded"
      : "Instructions updated · agent loading unconfirmed";

  if (onOpenPersonalization) {
    const habitCount = currentHabits?.length;
    const capturedCount = status?.capture_summary?.captured_conversations;
    return (
      <section
        className="autonomy-panel autonomy-panel--overview"
        aria-labelledby={headingId}
      >
        <header className="autonomy-panel__heading">
          <div className="autonomy-panel__title">
            <h2 id={headingId}>Chat learning</h2>
            <StatusPill tone={statusTone}>{learningLabel}</StatusPill>
          </div>
          <Button tone="quiet" onClick={onOpenPersonalization}>
            Manage learning
          </Button>
        </header>
        {statusNotice}
        {loading && <LoadingStatus>Checking learning status…</LoadingStatus>}
        {status && (
          <>
            {!status.grant_enabled && !loadError && (
              <p className="autonomy-panel__intro">
                No projects approved for chat learning.
              </p>
            )}
            {status.grant_enabled && (
              <>
                {loadError && <p>Last known learning coverage</p>}
                <dl className="learning-facts" aria-label="Learning coverage">
                  <div>
                    <dt>Approved projects</dt>
                    <dd>{approvedCount ?? "Unavailable"}</dd>
                  </div>
                  <div>
                    <dt>Conversations captured</dt>
                    <dd>{capturedCount ?? "Unavailable"}</dd>
                  </div>
                  <div>
                    <dt>Habits found</dt>
                    <dd>{habitCount}</dd>
                  </div>
                </dl>
                {!loadError && (
                  <div className="personalization-status">
                    <span>Personalization</span>
                    <strong>{personalizationLabel}</strong>
                    <span>{publicationLabel}</span>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </section>
    );
  }

  return (
    <section
      className="autonomy-panel"
      aria-labelledby={headingId}
      aria-busy={busy || loading}
    >
      <header className="autonomy-panel__heading">
        <div className="autonomy-panel__title">
          <h2 id={headingId}>Chat learning</h2>
          <StatusPill tone={statusTone}>{learningLabel}</StatusPill>
        </div>
        {status?.grant_enabled && (
          <Button
            disabled={busy || blocked}
            onClick={() =>
              void control(
                status.learning_enabled ? "pause_learning" : "resume_learning",
              )
            }
          >
            {status.learning_enabled ? "Pause learning" : "Resume learning"}
          </Button>
        )}
      </header>
      {statusNotice}
      {loading && <LoadingStatus>Checking learning status…</LoadingStatus>}
      {progress && (
        <p className="learning-secondary" role="status">
          {progress}
        </p>
      )}
      {actionError && (
        <div className="autonomy-notice" role="alert">
          <strong>Temper couldn’t complete that action.</strong>
          <details className="learning-details">
            <summary>Technical details</summary>
            <p>{actionError}</p>
          </details>
        </div>
      )}
      {!loadError && status && !status.secure_store_ready && (
        <div className="autonomy-notice" role="alert">
          <strong>Secure storage is unavailable.</strong>
          <p>
            Temper needs access to this device’s saved keys before it can learn
            or change your instructions.
          </p>
        </div>
      )}
      {!loadError &&
        status?.grant_enabled &&
        status.provenance_state === "unverified" && (
          <div className="autonomy-notice" role="status">
            <strong>Conversation access needs attention.</strong>
            <p>
              Temper needs verified conversation access or your permission to
              use the selected conversations.
            </p>
          </div>
        )}
      {!loadError && status?.publication_needs_attention && (
        <div className="autonomy-notice" role="alert">
          <strong>Your agent instructions need review.</strong>
          <p>
            Temper left the file unchanged. Review its Temper section before
            resuming personalization.
          </p>
        </div>
      )}
      {status && !status.grant_enabled && !loadError && (
        <div className="learning-setup">
          <p className="autonomy-panel__intro">
            Choose which projects and communication habits Temper can learn
            from.
          </p>
          <div className="learning-setup__choices">
            <fieldset disabled={busy || Boolean(preview)}>
              <legend>Projects</legend>
              <div className="learning-projects">
                {grantProjects.map((project) => (
                  <label key={project.project_id}>
                    <input
                      type="checkbox"
                      checked={selected.includes(project.project_id)}
                      onChange={(event) =>
                        setSelected((current) =>
                          event.target.checked
                            ? [...current, project.project_id]
                            : current.filter((id) => id !== project.project_id),
                        )
                      }
                    />
                    <span>
                      {project.display_name}
                      {grantProjects.some(
                        (other) =>
                          other.display_name === project.display_name &&
                          other.project_id !== project.project_id,
                      ) && ` · ${project.project_id}`}
                    </span>
                  </label>
                ))}
                {grantProjects.length === 0 && (
                  <p>No repositories are available for chat learning.</p>
                )}
              </div>
            </fieldset>
            <fieldset disabled={busy || Boolean(preview)}>
              <legend>Habits</legend>
              {categories.map((category) => (
                <label key={category.id}>
                  <input
                    type="checkbox"
                    checked={selectedCategories.includes(category.id)}
                    onChange={(event) =>
                      setSelectedCategories((current) =>
                        event.target.checked
                          ? [...current, category.id]
                          : current.filter((id) => id !== category.id),
                      )
                    }
                  />
                  <span>{category.label}</span>
                </label>
              ))}
            </fieldset>
          </div>
          {!preview && (
            <>
              <label className="learning-trust">
                <input
                  type="checkbox"
                  disabled={busy}
                  checked={trustAuthorizedChats}
                  onChange={(event) =>
                    setTrustAuthorizedChats(event.target.checked)
                  }
                />
                <span>
                  Include conversations relayed by agents I authorize.
                  <small>
                    Temper may not be able to tell who wrote each message. It
                    treats patterns as inferred habits.
                  </small>
                </span>
              </label>
              <Button
                disabled={
                  busy ||
                  !selected.length ||
                  !selectedCategories.length ||
                  blocked
                }
                onClick={() =>
                  void run("Preparing learning access for review…", async () =>
                    setPreview(
                      await previewLearningGrant(
                        selected,
                        selectedCategories,
                        trustAuthorizedChats,
                      ),
                    ),
                  )
                }
              >
                Review learning access
              </Button>
            </>
          )}
          {preview && (
            <div
              className="learning-permission"
              aria-label="Review learning access"
            >
              <h3>Allow learning in these projects?</h3>
              <dl className="learning-facts">
                <div>
                  <dt>Projects</dt>
                  <dd>
                    {preview.value.project_ids
                      .map(
                        (id) =>
                          grantProjects.find(
                            (project) => project.project_id === id,
                          )?.display_name ?? id,
                      )
                      .join(", ")}
                  </dd>
                </div>
                <div>
                  <dt>Habits</dt>
                  <dd>
                    {preview.value.categories
                      .map(
                        (id) =>
                          categories.find((category) => category.id === id)
                            ?.label ?? id,
                      )
                      .join(", ")}
                  </dd>
                </div>
                <div>
                  <dt>Access</dt>
                  <dd>
                    Until you revoke it. Only new eligible Codex chats are
                    observed.
                  </dd>
                </div>
                <div>
                  <dt>Analysis</dt>
                  <dd>
                    Chat excerpts are sent to your configured Codex model. Local
                    evidence is encrypted and kept for up to 30 days.
                  </dd>
                </div>
                <div>
                  <dt>Agent instructions</dt>
                  <dd>
                    <code>{preview.value.native_destination}</code>
                    <p>
                      With personalization enabled and the required checks
                      passed, Temper can update only its own section. Your
                      written instructions stay intact. Changes apply to new
                      chats.
                    </p>
                  </dd>
                </div>
              </dl>
              {(preview.value.trust_authorized_chats ??
                trustAuthorizedChats) && (
                <p>
                  Agent-relayed conversations are included. Message authorship
                  may be unknown.
                </p>
              )}
              <div className="autonomy-panel__actions">
                <Button
                  tone="primary"
                  disabled={busy || blocked}
                  onClick={() =>
                    void run("Enabling chat learning…", async () => {
                      setState(await enableLearningGrant(preview));
                      setPreview(null);
                    })
                  }
                >
                  Allow learning
                </Button>
                <Button disabled={busy} onClick={() => setPreview(null)}>
                  Back
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
      {status?.grant_enabled && (
        <>
          <div className="personalization-status">
            <span>Personalization</span>
            <strong>{personalizationLabel}</strong>
            <span>
              {loadError
                ? "The last status could not be refreshed."
                : publicationLabel}
            </span>
          </div>
          <Toggle
            label="Use learned habits in new chats"
            checked={status.personalization_enabled}
            disabled={
              busy ||
              blocked ||
              (!status.personalization_enabled &&
                !status.automatic_serving_ready)
            }
            onCheckedChange={() =>
              void control(
                status.personalization_enabled
                  ? "disable_personalization"
                  : "enable_personalization",
              )
            }
            description={
              status.automatic_serving_ready
                ? "Turning this off removes Temper’s managed profile where it can safely do so."
                : "Learning can continue while Temper waits for compatibility, behavior and instruction checks."
            }
          />
          <div className="learning-empty">
            <h3 ref={habitsHeading} tabIndex={-1}>
              {loadError ? "Last known habits" : "Learned habits"}
            </h3>
            {currentHabits?.length ? (
              <ul className="habit-list">
                {currentHabits.map((habit) => (
                  <li className="habit-row" key={habit.habit_id}>
                    <div className="habit-row__heading">
                      <h4>{habit.behavior}</h4>
                      <StatusPill
                        tone={
                          !loadError && habit.state === "active"
                            ? "positive"
                            : "neutral"
                        }
                      >
                        {habitStates[habit.state]}
                      </StatusPill>
                    </div>
                    <p className="habit-row__scope">
                      {grantProjects.find(
                        (project) => project.project_id === habit.project_id,
                      )?.display_name ?? "Project unavailable"}{" "}
                      · {habit.task_class.replaceAll("_", " ")} ·{" "}
                      {habit.origin === "inferred"
                        ? "Learned from chats"
                        : "Stated preference"}
                    </p>
                    <div className="autonomy-panel__actions">
                      <Button
                        tone="quiet"
                        disabled={busy || Boolean(loadError)}
                        aria-expanded={
                          evidence?.habit.habit_id === habit.habit_id
                        }
                        onClick={() => {
                          if (evidence?.habit.habit_id === habit.habit_id) {
                            setEvidence(null);
                            return;
                          }
                          void run("Loading habit evidence…", async () =>
                            setEvidence(
                              (await explainHabit(habit.habit_id)).value,
                            ),
                          );
                        }}
                      >
                        Why this habit?
                      </Button>
                      <Button
                        tone="quiet"
                        disabled={busy || blocked}
                        onClick={() =>
                          void control("revoke_habit", habit.habit_id)
                        }
                      >
                        Undo habit
                      </Button>
                    </div>
                    {evidence?.habit.habit_id === habit.habit_id && (
                      <div className="habit-evidence">
                        <p>
                          {evidence.support_count} supporting{" "}
                          {evidence.support_count === 1 ? "task" : "tasks"} ·{" "}
                          {evidence.contradiction_count} conflicting{" "}
                          {evidence.contradiction_count === 1
                            ? "task"
                            : "tasks"}
                        </p>
                        <dl className="learning-facts">
                          {(
                            [
                              [
                                "Instructions updated",
                                evidence.outcome_summary.published,
                              ],
                              [
                                "Loaded by an agent",
                                evidence.outcome_summary.delivered,
                              ],
                              [
                                "Behavior followed",
                                evidence.outcome_summary.followed,
                              ],
                              ["Helpful", evidence.outcome_summary.helpful],
                              ["Harmful", evidence.outcome_summary.harmful],
                            ] as const
                          ).map(([label, value]) => (
                            <div key={label}>
                              <dt>{label}</dt>
                              <dd>
                                {value === null
                                  ? "Not measured"
                                  : value
                                    ? "Yes"
                                    : "No"}
                              </dd>
                            </div>
                          ))}
                        </dl>
                        <p className="learning-secondary">
                          Results for version{" "}
                          {evidence.outcome_summary.habit_revision}. Agent
                          loading and usefulness are measured separately.
                        </p>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p>
                No habits yet.
                {!loadError &&
                  learningLabel === "Enabled" &&
                  " Keep working in Codex in an approved repository."}
              </p>
            )}
          </div>
          <div className="learning-details learning-details__body">
            {loadError && <p>Last known activity</p>}
            <dl
              className="learning-facts"
              aria-label={
                loadError ? "Last known activity" : "Learning activity"
              }
            >
              <div>
                <dt>Conversations captured</dt>
                <dd>
                  {status.capture_summary?.captured_conversations ??
                    "Unavailable"}
                </dd>
              </div>
              {status.recent_changes.length > 0 && (
                <div>
                  <dt>Recent changes</dt>
                  <dd>
                    <ul className="learning-history">
                      {status.recent_changes
                        .slice()
                        .reverse()
                        .map((change) => (
                          <li key={change.digest}>
                            {changeLabels[change.type] ?? "Learning updated"}
                          </li>
                        ))}
                    </ul>
                  </dd>
                </div>
              )}
            </dl>
          </div>
          {approvedProjects?.length ? (
            <ApprovedLearningProjects
              projects={approvedProjects}
              stale={Boolean(loadError)}
            />
          ) : (
            <div className="learning-details">
              <p className="learning-secondary">
                {approvedProjects
                  ? "No approved repositories."
                  : "Approved repository list unavailable."}
              </p>
            </div>
          )}
          <details className="learning-details">
            <summary>Learning settings</summary>
            <div className="learning-details__body">
              <div className="learning-revoke">
                <p>
                  Revoke access to stop learning and personalization. Local
                  evidence is kept for up to 30 days.
                </p>
                <Button
                  tone="danger"
                  disabled={busy || blocked}
                  onClick={() => void control("revoke_grant")}
                >
                  Stop and revoke permission
                </Button>
              </div>
            </div>
          </details>
          <details className="learning-details">
            <summary>How chat learning works</summary>
            <div className="learning-details__body">
              <p>
                Repeated patterns across tasks can become habits. Pausing
                learning stops new observation and updates. Existing
                personalization can stay on.
              </p>
              <dl className="learning-facts">
                <div>
                  <dt>Source</dt>
                  <dd>
                    {status.capture_window === "completed_work"
                      ? "Completed work in approved projects, including ongoing Codex chats. Messages before your learning cutoff are excluded."
                      : "New eligible Codex chats in approved projects. Older chats are excluded."}
                    {status.capture_summary?.eligible_since && (
                      <p>
                        Learning cutoff{" "}
                        <time dateTime={status.capture_summary.eligible_since}>
                          {new Date(
                            status.capture_summary.eligible_since,
                          ).toLocaleString()}
                        </time>
                      </p>
                    )}
                  </dd>
                </div>
                <div>
                  <dt>Analysis and storage</dt>
                  <dd>
                    Chat excerpts are sent to your configured Codex model. Local
                    evidence is encrypted and kept for up to 30 days.
                  </dd>
                </div>
                {status.input_policy === "owner_authorized_conversations" && (
                  <div>
                    <dt>Conversation trust</dt>
                    <dd>
                      Your permission includes authorized agent relays. Temper
                      may not know who wrote a message; these patterns are
                      inferred habits.
                    </dd>
                  </div>
                )}
                <div>
                  <dt>Agent instructions</dt>
                  <dd>
                    Temper maintains only its own section. Your current requests
                    and written instructions take precedence. New chats or a
                    supported reload are needed to load changes.
                  </dd>
                </div>
              </dl>
            </div>
          </details>
        </>
      )}
    </section>
  );
}
