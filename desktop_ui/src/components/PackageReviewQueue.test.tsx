import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { PackageReviewItem } from "../types";
import { PackageReviewQueue } from "./PackageReviewQueue";

const behaviorReview: PackageReviewItem = {
  review_version: "1.0.0",
  review_id: "package-review-1",
  review_digest: `sha256:${"d".repeat(64)}`,
  import_receipt_id: "import-1",
  import_receipt_digest: `sha256:${"e".repeat(64)}`,
  package_type: "behavior_pack",
  package_id: "clear-handoffs",
  package_digest: `sha256:${"a".repeat(64)}`,
  item_id: "purpose-first",
  item_digest: `sha256:${"b".repeat(64)}`,
  claim_key: "communication.purpose-first",
  publisher_name: "Example publisher",
  publisher_key_fingerprint: `sha256:${"c".repeat(64)}`,
  kind: "preference",
  summary: "Explain purpose before procedural detail",
  disposition: "new",
  requested_scope: {
    project_ids: [],
    task_classes: [],
    target_families: ["codex"],
    environment_ids: [],
    activation_conditions: [],
    exclusions: [],
    scope_mapping_required: true,
  },
  behavioral_contract: {
    intent: "Explain purpose before procedural detail",
    required_behaviors: ["State why a procedure matters before its commands."],
    non_goals: [],
    verification_requirements: ["Confirm that purpose precedes procedure."],
  },
  required_capabilities: [],
  evaluation_status: null,
  available_actions: ["approve", "reject"],
  created_at: "2026-09-05T12:00:00Z",
  starts_inactive: true,
  origin_grants_authority: false,
  raw_payloads_exposed: false,
};

describe("PackageReviewQueue", () => {
  it("requires an explicit recipient-local project mapping before adoption", async () => {
    const user = userEvent.setup();
    const onDecision = vi.fn().mockResolvedValue(undefined);
    render(
      <PackageReviewQueue
        busyReviewId={null}
        items={[behaviorReview]}
        onDecision={onDecision}
        projects={[
          { id: "project-a", label: "Project A" },
          { id: "project-b", label: "Project B" },
        ]}
      />,
    );

    const approve = screen.getByRole("button", { name: /add to core/i });
    expect(approve).toBeDisabled();
    await user.click(
      screen.getByRole("combobox", {
        name: "Scope for Explain purpose before procedural detail",
      }),
    );
    await user.click(screen.getByRole("option", { name: "Project B" }));
    expect(approve).toBeEnabled();
    await user.click(approve);

    expect(onDecision).toHaveBeenCalledWith(behaviorReview, "approved", [
      "project-b",
    ]);
  });

  it("can dismiss a blocked item but never offers approval", async () => {
    const user = userEvent.setup();
    const onDecision = vi.fn().mockResolvedValue(undefined);
    render(
      <PackageReviewQueue
        busyReviewId={null}
        items={[
          {
            ...behaviorReview,
            disposition: "conflict",
            available_actions: ["reject"],
          },
        ]}
        onDecision={onDecision}
        projects={[]}
      />,
    );

    expect(
      screen.queryByRole("button", { name: /add to core/i }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(onDecision).toHaveBeenCalledWith(
      expect.objectContaining({ disposition: "conflict" }),
      "rejected",
      [],
    );
  });
});
