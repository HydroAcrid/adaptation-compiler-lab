import { Check, PackageCheck, X } from "lucide-react";
import { useState } from "react";

import type { PackageReviewItem } from "../types";
import { Button, StatusPill, TemperSelect } from "./ui";

export function PackageReviewQueue({
  items,
  projects,
  busyReviewId,
  onDecision,
}: {
  items: PackageReviewItem[];
  projects: Array<{ id: string; label: string }>;
  busyReviewId: string | null;
  onDecision: (
    item: PackageReviewItem,
    decision: "approved" | "rejected",
    projectIds: string[],
  ) => Promise<void>;
}) {
  const [scopeByReview, setScopeByReview] = useState<Record<string, string>>(
    {},
  );
  const [error, setError] = useState<string | null>(null);
  if (!items.length) return null;

  async function decide(
    item: PackageReviewItem,
    decision: "approved" | "rejected",
    projectIds: string[],
  ) {
    setError(null);
    try {
      await onDecision(item, decision, projectIds);
    } catch (cause: unknown) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Temper could not record that package decision.",
      );
    }
  }

  return (
    <section
      aria-labelledby="package-review-title"
      className="package-review-queue"
    >
      <header>
        <div>
          <span className="folio-kicker">Imported, not yet trusted</span>
          <h2 id="package-review-title">Review imported items</h2>
          <p>
            A valid signature proves who packaged these items. Nothing becomes
            yours until you approve it here.
          </p>
        </div>
        <StatusPill tone="neutral">{items.length} waiting</StatusPill>
      </header>
      <ul>
        {items.map((item) => {
          const selectedScope = scopeByReview[item.review_id] ?? "unselected";
          const projectIds =
            selectedScope === "all"
              ? projects.map((project) => project.id)
              : selectedScope !== "unselected"
                ? [selectedScope]
                : [];
          const behavior = item.package_type === "behavior_pack";
          const needsMapping = Boolean(
            item.requested_scope?.scope_mapping_required,
          );
          const canApprove =
            item.available_actions.includes("approve") &&
            (!behavior || !needsMapping || projectIds.length > 0);
          const busy = busyReviewId === item.review_id;
          return (
            <li key={item.review_id}>
              <div className="package-review-queue__mark" aria-hidden="true">
                <PackageCheck size={18} />
              </div>
              <div className="package-review-queue__copy">
                <span>
                  {item.package_type.replaceAll("_", " ")} ·{" "}
                  {item.publisher_name}
                </span>
                <strong>{item.summary}</strong>
                <small>
                  {item.disposition === "new"
                    ? "Inactive until you approve it"
                    : item.disposition.replaceAll("_", " ")}
                </small>
                {behavior && needsMapping ? (
                  <TemperSelect
                    ariaLabel={`Scope for ${item.summary}`}
                    onValueChange={(value) =>
                      setScopeByReview((current) => ({
                        ...current,
                        [item.review_id]: value,
                      }))
                    }
                    options={[
                      {
                        label: "Choose where this applies",
                        value: "unselected",
                      },
                      { label: "All registered projects", value: "all" },
                      ...projects.map((project) => ({
                        label: project.label,
                        value: project.id,
                      })),
                    ]}
                    portalled={false}
                    value={selectedScope}
                  />
                ) : null}
              </div>
              <div className="package-review-queue__actions">
                {item.available_actions.includes("approve") ? (
                  <Button
                    disabled={!canApprove || busy}
                    icon={<Check aria-hidden="true" size={15} />}
                    onClick={() => void decide(item, "approved", projectIds)}
                    tone="primary"
                  >
                    {behavior ? "Add to Core" : "Add Mode"}
                  </Button>
                ) : null}
                <Button
                  disabled={busy}
                  icon={<X aria-hidden="true" size={15} />}
                  onClick={() => void decide(item, "rejected", [])}
                  tone="quiet"
                >
                  Dismiss
                </Button>
              </div>
            </li>
          );
        })}
      </ul>
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}
