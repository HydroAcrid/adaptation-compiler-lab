import { useEffect, useState } from "react";
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
import { Button, StatusPill } from "./ui";

const categories: { id: StyleCategory; label: string }[] = [
  { id: "communication_detail", label: "Amount of detail" },
  { id: "presentation_style", label: "Presentation" },
  { id: "suggestion_style", label: "Suggestions" },
];

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
  const [error, setError] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    loadAutonomy()
      .then((value) => {
        if (live) setState(value);
      })
      .catch((value) => {
        if (live) setError(engineFailureMessage(value));
      });
    return () => {
      live = false;
    };
  }, []);

  async function run(operation: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await operation();
    } catch (value) {
      setError(engineFailureMessage(value));
    } finally {
      setBusy(false);
    }
  }
  const control = (action: AutonomyControl, habitId?: string) =>
    run(async () => {
      if (state) setState(await controlAutonomy(action, state.digest, habitId));
    });
  const status = state?.value;
  return (
    <section className="autonomy-panel" aria-labelledby="autonomy-heading">
      <div className="autonomy-panel__heading">
        <h2 id="autonomy-heading">Learning from everyday work</h2>
        <StatusPill>
          {status?.personalization_enabled ? "Personalizing" : "Shadow mode"}
        </StatusPill>
      </div>
      <p>
        Temper looks for communication habits across completed tasks. Shadow
        mode changes no agent behavior.
      </p>
      {status?.provenance_state === "unverified" && (
        <p role="status">
          Capture is blocked: this Codex version cannot yet verify which
          messages came from a person. No conversations are being learned from.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {status?.publication_needs_attention && (
        <p role="alert">
          Instruction publication or cleanup needs attention. Temper preserved
          the file; review its managed section before resuming personalization.
        </p>
      )}
      {status && !status.grant_enabled && (
        <>
          <fieldset disabled={busy || Boolean(preview)}>
            <legend>Projects to learn from</legend>
            {projects.map((project) => (
              <label key={project.project_id}>
                <input
                  type="checkbox"
                  checked={selected.includes(project.project_id)}
                  onChange={(event) =>
                    setSelected(
                      event.target.checked
                        ? [...selected, project.project_id]
                        : selected.filter((id) => id !== project.project_id),
                    )
                  }
                />{" "}
                {project.display_name}
              </label>
            ))}
            {projects.length === 0 && (
              <p>Register a project in Connections first.</p>
            )}
          </fieldset>
          <fieldset disabled={busy || Boolean(preview)}>
            <legend>Habits to learn</legend>
            {categories.map((category) => (
              <label key={category.id}>
                <input
                  type="checkbox"
                  checked={selectedCategories.includes(category.id)}
                  onChange={(event) =>
                    setSelectedCategories(
                      event.target.checked
                        ? [...selectedCategories, category.id]
                        : selectedCategories.filter((id) => id !== category.id),
                    )
                  }
                />{" "}
                {category.label}
              </label>
            ))}
          </fieldset>
          {!preview && (
            <Button
              disabled={busy || !selected.length || !selectedCategories.length}
              onClick={() =>
                void run(async () =>
                  setPreview(
                    await previewLearningGrant(selected, selectedCategories),
                  ),
                )
              }
            >
              Preview permission
            </Button>
          )}
          {preview && (
            <div>
              <p>
                Permission remains active until disabled. Raw evidence stays
                encrypted locally for 30 days. Only new eligible Codex chats in
                the selected projects can be observed.
              </p>
              <p>
                Instruction destination:{" "}
                <code>{preview.value.native_destination}</code>. Temper may
                maintain only its managed style section, after the release
                checks pass. Manually written guidance is preserved. Changes
                apply to newly started chats.
              </p>
              <Button
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    setState(await enableLearningGrant(preview));
                    setPreview(null);
                  })
                }
              >
                Confirm scoped permission
              </Button>
              <Button disabled={busy} onClick={() => setPreview(null)}>
                Cancel
              </Button>
            </div>
          )}
        </>
      )}
      {status?.grant_enabled && (
        <>
          <div className="autonomy-panel__actions">
            <Button
              disabled={busy}
              onClick={() =>
                void control(
                  status.learning_enabled
                    ? "pause_learning"
                    : "resume_learning",
                )
              }
            >
              {status.learning_enabled ? "Pause learning" : "Resume learning"}
            </Button>
            <Button
              disabled={
                busy ||
                (!status.personalization_enabled &&
                  !status.automatic_serving_ready)
              }
              onClick={() =>
                void control(
                  status.personalization_enabled
                    ? "disable_personalization"
                    : "enable_personalization",
                )
              }
            >
              {status.personalization_enabled
                ? "Disable personalization"
                : "Enable personalization"}
            </Button>
            <Button
              disabled={busy}
              onClick={() => void control("revoke_grant")}
            >
              Stop and revoke permission
            </Button>
          </div>
          {!status.automatic_serving_ready && (
            <p>
              Automatic personalization awaits verified source attribution,
              calibration, and instruction conflict checks.
            </p>
          )}
          <p>
            {status.published
              ? "Style profile published."
              : "No style profile published."}{" "}
            {status.delivery_confirmed
              ? "Delivery has been observed."
              : "Delivery and usefulness have not been established."}
          </p>
          <ul>
            {status.habits.map((habit) => (
              <li key={habit.habit_id}>
                <p>
                  {habit.behavior} <StatusPill>{habit.state}</StatusPill>
                </p>
                <p>
                  {projects.find(
                    (project) => project.project_id === habit.project_id,
                  )?.display_name ?? habit.project_id}{" "}
                  · {habit.task_class.replaceAll("_", " ")} ·{" "}
                  {habit.origin === "inferred"
                    ? "Inferred habit"
                    : "Expressed preference"}
                </p>
                <Button
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      const result = await explainHabit(habit.habit_id);
                      setExplanation(
                        `${result.value.support_count} independent supporting tasks; ${result.value.contradiction_count} contradictions. Silence does not count as success.`,
                      );
                    })
                  }
                >
                  Explain evidence
                </Button>
                <Button
                  disabled={busy || habit.state === "retired"}
                  onClick={() => void control("revoke_habit", habit.habit_id)}
                >
                  Undo this habit
                </Button>
              </li>
            ))}
          </ul>
          {explanation && <p role="status">{explanation}</p>}
          <details>
            <summary>Recent learning changes</summary>
            <ul>
              {status.recent_changes.map((change) => (
                <li key={change.digest}>{change.type.replaceAll("_", " ")}</li>
              ))}
            </ul>
          </details>
        </>
      )}
    </section>
  );
}
