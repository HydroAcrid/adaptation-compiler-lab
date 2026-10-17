import { useEffect, useRef, useState } from "react";
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
  type StyleCategory,
} from "../autonomy";
import { engineFailureMessage, type EngineProject } from "../engine";
import { Button, StatusPill, Toggle } from "./ui";

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
type HabitEvidence = Awaited<ReturnType<typeof explainHabit>>["value"];

export function AutonomousLearningPanel({
  projects,
}: {
  projects: EngineProject[];
}) {
  const [state, setState] = useState<Bound<AutonomyState> | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [selectedCategories, setSelectedCategories] = useState<StyleCategory[]>(
    [],
  );
  const [preview, setPreview] = useState<Bound<GrantPreview> | null>(null);
  const [busy, setBusy] = useState(false);
  const [trustAuthorizedChats, setTrustAuthorizedChats] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<HabitEvidence | null>(null);
  const busyRef = useRef(false);
  const requestVersion = useRef(0);
  const [refreshKey, setRefreshKey] = useState(0);
  useEffect(() => {
    let live = true;
    const refresh = async () => {
      if (busyRef.current) return;
      const version = ++requestVersion.current;
      try {
        const value = await loadAutonomy();
        if (live && version === requestVersion.current && !busyRef.current) {
          setState(value);
          setLoadError(null);
        }
      } catch (value) {
        if (live && version === requestVersion.current && !busyRef.current) {
          setLoadError(engineFailureMessage(value));
        }
      }
    };
    void refresh();
    const interval = window.setInterval(() => void refresh(), 30_000);
    return () => {
      live = false;
      window.clearInterval(interval);
    };
  }, [refreshKey]);

  async function run(operation: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    requestVersion.current += 1;
    setBusy(true);
    setActionError(null);
    try {
      await operation();
    } catch (value) {
      setActionError(engineFailureMessage(value));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }
  const control = (action: AutonomyControl, habitId?: string) =>
    run(async () => {
      if (state) {
        setState(await controlAutonomy(action, state.digest, habitId));
        setEvidence(null);
      }
    });
  const status = state?.value;
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
              ? "On"
              : "Waiting";
  return (
    <section
      className="autonomy-panel"
      aria-labelledby="autonomy-heading"
      aria-busy={busy}
    >
      <header className="autonomy-panel__heading">
        <div className="autonomy-panel__title">
          <h2 id="autonomy-heading">Learning</h2>
          <StatusPill
            tone={
              learningLabel === "On"
                ? "positive"
                : learningLabel === "Needs attention" || loadError
                  ? "attention"
                  : "neutral"
            }
          >
            {learningLabel}
          </StatusPill>
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
      {loadError ? (
        <div className="autonomy-notice" role="alert">
          <strong>Learning status is unavailable.</strong>
          <p>{loadError}</p>
          <Button
            tone="quiet"
            onClick={() => setRefreshKey((value) => value + 1)}
          >
            Try again
          </Button>
        </div>
      ) : !status ? (
        <p className="autonomy-panel__intro" role="status">
          Checking learning status…
        </p>
      ) : null}
      {actionError && (
        <p className="autonomy-notice" role="alert">
          {actionError}
        </p>
      )}
      {status && !status.secure_store_ready && (
        <div className="autonomy-notice" role="alert">
          <strong>Secure storage is unavailable.</strong>
          <p>
            Temper needs access to this device’s saved keys before it can learn
            or change your instructions.
          </p>
        </div>
      )}
      {status?.grant_enabled && status.provenance_state === "unverified" && (
        <div className="autonomy-notice" role="status">
          <strong>Conversation access needs attention.</strong>
          <p>
            Learning is waiting for verified input or permission to trust the
            selected conversations.
          </p>
        </div>
      )}
      {status?.publication_needs_attention && (
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
                {projects.map((project) => (
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
                    <span>{project.display_name}</span>
                  </label>
                ))}
                {projects.length === 0 && (
                  <p>Add a project in Connections first.</p>
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
                  void run(async () =>
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
                          projects.find((project) => project.project_id === id)
                            ?.display_name ?? id,
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
                    void run(async () => {
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
          <p className="autonomy-panel__intro">
            {loadError
              ? "Last known learning state. Refresh to check for changes."
              : !status.secure_store_ready ||
                  status.provenance_state === "unverified" ||
                  (status.learning_enabled && status.capture_state !== "ready")
                ? "Learning is waiting. Your saved habits are still here."
                : status.learning_enabled
                  ? "Temper learns communication habits from new Codex chats in your approved projects."
                  : "New chats aren’t being checked. Your saved habits are still here."}
          </p>
          {status.habits.length === 0 ? (
            <div className="learning-empty">
              <h3>No habits yet</h3>
              <p>
                Habits appear here when a pattern repeats across separate tasks.
              </p>
            </div>
          ) : (
            <ul className="habit-list" aria-label="Learned habits">
              {status.habits.map((habit) => (
                <li className="habit-row" key={habit.habit_id}>
                  <div className="habit-row__heading">
                    <h3>{habit.behavior}</h3>
                    <StatusPill
                      tone={habit.state === "active" ? "positive" : "neutral"}
                    >
                      {habitStates[habit.state]}
                    </StatusPill>
                  </div>
                  <p className="habit-row__scope">
                    {projects.find(
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
                      disabled={busy}
                      aria-expanded={
                        evidence?.habit.habit_id === habit.habit_id
                      }
                      onClick={() => {
                        if (evidence?.habit.habit_id === habit.habit_id) {
                          setEvidence(null);
                          return;
                        }
                        void run(async () =>
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
                      disabled={busy || blocked || habit.state === "retired"}
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
                        {evidence.contradiction_count === 1 ? "task" : "tasks"}
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
                        {evidence.outcome_summary.habit_revision}. A file update
                        alone does not confirm that an agent loaded it or that
                        it helped.
                      </p>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
          <div className="personalization-status">
            <span>Personalization</span>
            <strong>
              {!status.personalization_enabled
                ? "Off"
                : !status.automatic_serving_ready
                  ? "Waiting for checks"
                  : "On"}
            </strong>
            <span>
              {!status.published
                ? "No habits added to agent instructions"
                : status.delivery_confirmed
                  ? "Agent loading confirmed"
                  : "Instructions updated · agent loading unconfirmed"}
            </span>
          </div>
          <details className="learning-details">
            <summary>Learning settings</summary>
            <div className="learning-details__body">
              <Toggle
                label="Personalization"
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
                description="Use eligible habits in new chats. Turning this off removes Temper’s managed profile where it can safely do so."
              />
              {!status.automatic_serving_ready && (
                <p>
                  Learning can continue. Automatic personalization needs
                  compatibility, behavior and instruction checks to pass first.
                </p>
              )}
              <p>
                Pausing learning stops new observation and updates. It does not
                turn off existing personalization.
              </p>
              <dl className="learning-facts">
                <div>
                  <dt>Source</dt>
                  <dd>
                    New eligible Codex chats in approved projects. Older chats
                    are excluded.
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
              <div className="learning-revoke">
                <p>
                  Revoke access to stop learning and personalization. Existing
                  evidence follows the same retention limit.
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
          {status.recent_changes.length > 0 && (
            <details className="learning-details">
              <summary>Recent changes</summary>
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
            </details>
          )}
        </>
      )}
    </section>
  );
}
