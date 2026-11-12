import {
  useEffect,
  useEffectEvent,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import {
  learningAccessLabel,
  loadAutonomy,
  type AutonomyState,
} from "../autonomy";
import { engineFailureMessage } from "../engine";
import { usePageVisibility } from "../pageVisibility";
import { Button, LoadingStatus, StatusPill } from "./ui";

/** A read-only view of the signed learning registry, separate from task runners. */
export function LearningRepositories() {
  const [status, setStatus] = useState<AutonomyState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [attempt, setAttempt] = useState(0);
  const visible = usePageVisibility();
  const visibleRef = useRef(false);
  const pending = useRef(false);
  const queued = useRef(false);

  useLayoutEffect(() => {
    visibleRef.current = visible;
    return () => {
      visibleRef.current = false;
      queued.current = false;
    };
  }, [visible]);

  const refresh = useEffectEvent(async (queueIfPending = false) => {
    if (!visibleRef.current) return;
    if (pending.current) {
      if (queueIfPending) queued.current = true;
      return;
    }

    pending.current = true;
    try {
      do {
        queued.current = false;
        try {
          const response = await loadAutonomy();
          if (visibleRef.current && !queued.current) {
            setStatus(response.value);
            setError(null);
          }
        } catch (value) {
          if (visibleRef.current && !queued.current) {
            setError(engineFailureMessage(value));
          }
        }
      } while (visibleRef.current && queued.current);
    } finally {
      pending.current = false;
    }
  });

  useEffect(() => {
    if (!visible) return;
    void refresh(true);
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => window.clearInterval(timer);
  }, [attempt, visible]);
  const projects = status?.project_access;
  const authorized = projects?.filter(
    (project) => project.learning_authorized,
  ).length;
  const shown = projects?.filter((project) =>
    `${project.display_name} ${project.project_id}`
      .toLowerCase()
      .includes(query.trim().toLowerCase()),
  );
  return (
    <section
      className="projects-section"
      aria-labelledby="learning-repositories-heading"
    >
      <div className="subsection-heading">
        <div>
          <h2 id="learning-repositories-heading">Chat learning</h2>
          {error ? (
            <p>
              {projects
                ? "Showing the last known repository access."
                : "Temper couldn’t check repository access."}
            </p>
          ) : projects ? (
            <p>
              {authorized} of {projects.length} repositories approved for
              learning.
            </p>
          ) : !status ? (
            <LoadingStatus>Checking repository access…</LoadingStatus>
          ) : null}
        </div>
        <Button tone="quiet" onClick={() => setAttempt((value) => value + 1)}>
          Refresh learning access
        </Button>
      </div>
      {error && <p role="alert">{error}</p>}
      {status && !projects && !error && (
        <p>Repository access is unavailable in this engine version.</p>
      )}
      <p>
        These permissions cover ordinary Codex chats. Open Personalization to
        change them.
      </p>
      {projects && (
        <>
          <div className="project-search">
            <label htmlFor="learning-project-search">
              Find a learning repository
            </label>
            <input
              id="learning-project-search"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search repositories"
            />
          </div>
          <div className="project-list" aria-label="Learning repositories">
            {shown?.map((project) => (
              <div className="project-row" key={project.project_id}>
                <div className="project-monogram">
                  {project.display_name[0]}
                </div>
                <div className="project-row__copy">
                  <strong>{project.display_name}</strong>
                  <span>{project.project_id}</span>
                </div>
                <div className="project-row__status">
                  <StatusPill
                    tone={
                      !error && project.learning_state === "on"
                        ? "positive"
                        : "neutral"
                    }
                  >
                    {error
                      ? `Last known: ${learningAccessLabel(project)}`
                      : learningAccessLabel(project)}
                  </StatusPill>
                  {project.learning_authorized && (
                    <span className="agent-chip">
                      {error ? "Last known: " : ""}
                      {project.personalization_enabled
                        ? status?.automatic_serving_ready &&
                          status.secure_store_ready
                          ? "Personalization on"
                          : "Personalization waiting for checks"
                        : "Personalization off"}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
          {shown?.length === 0 && (
            <p className="project-empty">
              {projects.length
                ? "No repositories match your search."
                : "No learning repositories registered."}
            </p>
          )}
        </>
      )}
    </section>
  );
}
