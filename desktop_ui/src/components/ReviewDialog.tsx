import * as Collapsible from "@radix-ui/react-collapsible";
import * as Dialog from "@radix-ui/react-dialog";
import { Check, ChevronDown, Folder, X } from "lucide-react";
import { useState } from "react";

import type { Suggestion, SuggestionDecision } from "../types";
import { Button, TemperSelect } from "./ui";

export function ReviewDialog({
  suggestion,
  availableProjects = [],
  open,
  previewMode = false,
  onOpenChange,
  onDecision,
}: {
  suggestion: Suggestion;
  availableProjects?: string[];
  open: boolean;
  previewMode?: boolean;
  onOpenChange: (open: boolean) => void;
  onDecision: (
    decision: SuggestionDecision,
    projectNames?: string[],
  ) => void | Promise<void>;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const projectChoices =
    suggestion.projectNames?.length && !suggestion.isGlobal
      ? suggestion.projectNames
      : availableProjects.length
        ? availableProjects
        : suggestion.sourceProject
          ? [suggestion.sourceProject]
          : [];
  const [selectedProject, setSelectedProject] = useState(
    suggestion.sourceProject ?? projectChoices[0] ?? "",
  );
  const [narrowedProjects, setNarrowedProjects] = useState<string[]>(
    suggestion.projectNames?.length
      ? projectChoices
      : selectedProject
        ? [selectedProject]
        : [],
  );
  const availableDecisions = suggestion.availableDecisions ?? [
    "suggested",
    "project",
    "narrowed",
    "ignore",
  ];
  const evidenceLabel = suggestion.evidenceStrength
    ? {
        strong: "Strong evidence",
        promising: "Promising evidence",
        developing: "Developing evidence",
      }[suggestion.evidenceStrength]
    : null;
  const automationSummary =
    suggestion.automationDisposition === "eligible"
      ? "Can be saved automatically when you enable this option, with a notification and 24 hours to undo."
      : suggestion.automationDisposition === "review-required"
        ? "Your review is required because this change affects how an agent works."
        : "Temper will keep gathering support unless you choose to keep this now.";
  const alreadyProjectScoped =
    Boolean(suggestion.projectNames?.length) ||
    (Boolean(suggestion.sourceProject) &&
      suggestion.isGlobal !== true &&
      suggestion.suggestedScope !== "All projects" &&
      suggestion.suggestedScope !== "All registered projects");
  const canKeepProject =
    !suggestion.isRevocation &&
    !alreadyProjectScoped &&
    availableDecisions.includes("project") &&
    projectChoices.length > 0;
  const canKeepNarrowed =
    !suggestion.isRevocation &&
    availableDecisions.includes("narrowed") &&
    projectChoices.length > 1;
  const narrowedSelectionIsStrict =
    suggestion.isGlobal === true ||
    !suggestion.projectNames?.length ||
    narrowedProjects.length < projectChoices.length;
  function submit(decision: SuggestionDecision, projectNames: string[] = []) {
    setBusy(true);
    setDecisionError(null);
    void Promise.resolve(onDecision(decision, projectNames))
      .catch((error: unknown) =>
        setDecisionError(
          error instanceof Error
            ? error.message
            : "Temper could not save that decision.",
        ),
      )
      .finally(() => setBusy(false));
  }
  return (
    <Dialog.Root onOpenChange={onOpenChange} open={open}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content
          aria-describedby="review-description"
          className="review-dialog review-sheet"
        >
          <Dialog.Close
            aria-label="Close review"
            className="icon-button dialog-close"
          >
            <X size={18} />
          </Dialog.Close>
          <span className="folio-kicker">Suggestion</span>
          <Dialog.Title>“{suggestion.behavior}”</Dialog.Title>
          <Dialog.Description id="review-description">
            {suggestion.explanation}
          </Dialog.Description>
          {previewMode ? (
            <p className="dialog-preview-note">
              Sample preview · this decision changes no local Temper state.
            </p>
          ) : null}
          <div className="review-annotations">
            <div>
              <span>Suggested scope</span>
              <strong>{suggestion.suggestedScope}</strong>
            </div>
            {suggestion.sourceCount ? (
              <div>
                <span>Based on</span>
                <strong>{suggestion.sourceCount} saved observations</strong>
              </div>
            ) : null}
            {evidenceLabel ? (
              <div>
                <span>Evidence</span>
                <strong>{evidenceLabel}</strong>
              </div>
            ) : null}
          </div>
          <p className="review-automation-note">
            {automationSummary} {suggestion.automationReason}
          </p>
          <div className="review-actions">
            {availableDecisions.includes("suggested") ? (
              <Button
                className="review-action--primary"
                disabled={busy}
                icon={<Check aria-hidden="true" size={17} />}
                onClick={() => submit("suggested")}
                tone="primary"
              >
                {suggestion.isRevocation
                  ? "Approve removal"
                  : "Keep as suggested"}
              </Button>
            ) : null}
            {canKeepProject ? (
              <div className="review-project-choice">
                <label htmlFor="review-project">Keep only in</label>
                <TemperSelect
                  ariaLabel="Keep only in"
                  id="review-project"
                  onValueChange={(project) => {
                    setSelectedProject(project);
                    setNarrowedProjects([project]);
                  }}
                  options={projectChoices.map((project) => ({
                    label: project,
                    value: project,
                  }))}
                  portalled={false}
                  value={selectedProject}
                />
                <Button
                  className="review-action--scope"
                  disabled={busy || !selectedProject}
                  icon={<Folder aria-hidden="true" size={17} />}
                  onClick={() => submit("project", [selectedProject])}
                  tone="quiet"
                >
                  Only in {selectedProject}
                </Button>
              </div>
            ) : null}
            {availableDecisions.includes("ignore") ? (
              <Button
                className="review-action--ignore"
                disabled={busy}
                onClick={() => submit("ignore")}
                tone="quiet"
              >
                {suggestion.isRevocation ? "Keep adaptation" : "Ignore"}
              </Button>
            ) : null}
          </div>
          {decisionError ? (
            <p className="portability-error" role="alert">
              {decisionError}
            </p>
          ) : null}
          <Collapsible.Root onOpenChange={setDetailsOpen} open={detailsOpen}>
            <Collapsible.Trigger className="details-trigger">
              <span>Why am I seeing this?</span>
              <ChevronDown
                aria-hidden="true"
                className={detailsOpen ? "details-chevron--open" : ""}
                size={16}
              />
            </Collapsible.Trigger>
            <Collapsible.Content className="provenance-detail">
              {canKeepNarrowed ? (
                <fieldset className="review-narrowing">
                  <legend>Use in selected projects</legend>
                  {projectChoices.map((project) => (
                    <label key={project}>
                      <input
                        checked={narrowedProjects.includes(project)}
                        onChange={(event) =>
                          setNarrowedProjects((current) =>
                            event.target.checked
                              ? [...new Set([...current, project])].sort()
                              : current.filter((item) => item !== project),
                          )
                        }
                        type="checkbox"
                      />
                      {project}
                    </label>
                  ))}
                  <Button
                    disabled={
                      busy ||
                      narrowedProjects.length === 0 ||
                      !narrowedSelectionIsStrict
                    }
                    onClick={() => submit("narrowed", narrowedProjects)}
                    tone="quiet"
                  >
                    Keep in selected projects
                  </Button>
                </fieldset>
              ) : null}
              <dl>
                {suggestion.authority ? (
                  <div>
                    <dt>Authority</dt>
                    <dd>{suggestion.authority}</dd>
                  </div>
                ) : null}
                {suggestion.sourceCount ? (
                  <div>
                    <dt>Support</dt>
                    <dd>{suggestion.sourceCount} saved observations</dd>
                  </div>
                ) : null}
                <div>
                  <dt>Evidence assessment</dt>
                  <dd>{suggestion.confidenceReason}</dd>
                </div>
                <div>
                  <dt>Captured</dt>
                  <dd>{suggestion.capturedAt}</dd>
                </div>
                <div>
                  <dt>Proposal</dt>
                  <dd>{suggestion.digest}</dd>
                </div>
              </dl>
              <p>
                Raw conversation content stays encrypted and is not shown here.
              </p>
            </Collapsible.Content>
          </Collapsible.Root>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
