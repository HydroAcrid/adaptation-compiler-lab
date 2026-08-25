import * as Collapsible from "@radix-ui/react-collapsible";
import * as Dialog from "@radix-ui/react-dialog";
import { Check, ChevronDown, Folder, X } from "lucide-react";
import { useState } from "react";

import type { Suggestion, SuggestionDecision } from "../types";
import { Button } from "./ui";

export function ReviewDialog({
  suggestion,
  open,
  onOpenChange,
  onDecision,
}: {
  suggestion: Suggestion;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDecision: (decision: SuggestionDecision) => void;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const evidenceLabel = {
    strong: "Strong evidence",
    promising: "Promising evidence",
    developing: "Developing evidence",
  }[suggestion.evidenceStrength];
  const automationSummary =
    suggestion.automationDisposition === "eligible"
      ? "Eligible for automatic keeping when you enable it. Temper would notify you and preserve a 24-hour undo window."
      : suggestion.automationDisposition === "review-required"
        ? "Your review stays required because this adaptation could materially guide how an agent works."
        : "Temper will keep gathering support unless you choose to keep this now.";
  const canNarrowToSourceProject = suggestion.suggestedScope === "All projects";
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
          <div className="review-annotations">
            <div>
              <span>Suggested scope</span>
              <strong>{suggestion.suggestedScope}</strong>
            </div>
            <div>
              <span>Based on</span>
              <strong>{suggestion.sourceCount} approved source moments</strong>
            </div>
            <div>
              <span>Evidence</span>
              <strong>{evidenceLabel}</strong>
            </div>
          </div>
          <p className="review-automation-note">
            {automationSummary} {suggestion.automationReason}
          </p>
          <div className="review-actions">
            <Button
              className="review-action--primary"
              icon={<Check aria-hidden="true" size={17} />}
              onClick={() => onDecision("suggested")}
              tone="primary"
            >
              Keep as suggested
            </Button>
            {canNarrowToSourceProject ? (
              <Button
                className="review-action--scope"
                icon={<Folder aria-hidden="true" size={17} />}
                onClick={() => onDecision("project")}
                tone="quiet"
              >
                Only in {suggestion.sourceProject}
              </Button>
            ) : null}
            <Button
              className="review-action--ignore"
              onClick={() => onDecision("ignore")}
              tone="quiet"
            >
              Ignore
            </Button>
          </div>
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
              <dl>
                <div>
                  <dt>Authority</dt>
                  <dd>{suggestion.authority}</dd>
                </div>
                <div>
                  <dt>Support</dt>
                  <dd>{suggestion.sourceCount} approved source moments</dd>
                </div>
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
