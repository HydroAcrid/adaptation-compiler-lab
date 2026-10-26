import { useEffect, useState } from "react";
import {
  learningAccessLabel,
  loadAutonomy,
  type AutonomyState,
} from "../autonomy";
import { engineFailureMessage } from "../engine";
import { Button, StatusPill } from "./ui";

/** A read-only view of the signed learning registry, separate from task runners. */
export function LearningRepositories() {
  const [status, setStatus] = useState<AutonomyState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    let pending = false;
    const refresh = async () => {
      if (pending) return;
      pending = true;
      try {
        const response = await loadAutonomy();
        if (live) {
          setStatus(response.value);
          setError(null);
        }
      } catch (value) {
        if (live) setError(engineFailureMessage(value));
      } finally {
        pending = false;
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [attempt]);
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
          <p>
            {error
              ? "Repository access could not be refreshed. The list below is last known state."
              : projects
                ? `${authorized} of ${projects.length} repositories approved for learning.`
                : "Checking repository access…"}
          </p>
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
        These permissions cover ordinary Codex chats. Pause learning or
        personalization on Today.
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
