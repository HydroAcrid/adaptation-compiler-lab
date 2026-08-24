import * as Collapsible from "@radix-ui/react-collapsible";
import * as Dialog from "@radix-ui/react-dialog";
import { Check, ChevronDown, Folder, Globe2, Sparkles, X } from "lucide-react";
import { useState } from "react";

import type { Suggestion } from "../types";
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
  onDecision: (decision: "keep" | "project" | "ignore") => void;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  return (
    <Dialog.Root onOpenChange={onOpenChange} open={open}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content
          aria-describedby="review-description"
          className="review-dialog"
        >
          <div className="review-icon" aria-hidden="true">
            <Sparkles size={21} strokeWidth={1.8} />
          </div>
          <Dialog.Close
            aria-label="Close review"
            className="icon-button dialog-close"
          >
            <X size={18} />
          </Dialog.Close>
          <span className="eyebrow">Possible adaptation</span>
          <Dialog.Title>{suggestion.behavior}</Dialog.Title>
          <Dialog.Description id="review-description">
            {suggestion.explanation}
          </Dialog.Description>
          <div className="scope-preview">
            <div className="scope-preview__icon" aria-hidden="true">
              <Globe2 size={18} />
            </div>
            <div>
              <span>Suggested scope</span>
              <strong>{suggestion.suggestedScope}</strong>
            </div>
          </div>
          <div className="review-actions">
            <Button
              icon={<Check aria-hidden="true" size={17} />}
              onClick={() => onDecision("keep")}
              tone="primary"
            >
              Keep
            </Button>
            <Button
              icon={<Folder aria-hidden="true" size={17} />}
              onClick={() => onDecision("project")}
            >
              Only in Kairn
            </Button>
            <Button onClick={() => onDecision("ignore")} tone="quiet">
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
