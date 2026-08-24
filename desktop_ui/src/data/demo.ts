import type {
  AgentConnection,
  CoreItem,
  RegisteredProject,
  Suggestion,
} from "../types";

export const suggestion: Suggestion = {
  id: "suggestion-019f",
  behavior: "Lead with the purpose before setup steps.",
  explanation:
    "You clarified this in two completed Codex tasks. Temper is suggesting a communication preference—not a hard rule.",
  suggestedScope: "All coding work",
  projectScope: "Kairn only",
  sourceCount: 2,
  authority: "Explicit user correction",
  capturedAt: "August 24, 2026 at 10:42 AM",
  digest: "sha256:0f67…c98a",
};

export const coreItems: CoreItem[] = [
  {
    id: "core-purpose-first",
    kind: "preference",
    title: "Purpose before procedure",
    description: "Explain the purpose plainly before setup steps or commands.",
    scope: "Everywhere",
    sourceSummary: "Approved from 3 explicit corrections",
  },
  {
    id: "core-concrete-names",
    kind: "preference",
    title: "Names that mean something",
    description:
      "Prefer names that represent real things over generic, techy names.",
    scope: "Everywhere",
    sourceSummary: "Approved from 1 direct preference",
  },
  {
    id: "core-kairn-state",
    kind: "memory",
    title: "Kairn notes can lag",
    description:
      "Check the live repository before relying on older notes about Kairn.",
    scope: "Kairn",
    sourceSummary: "Approved from 1 explicit correction",
  },
  {
    id: "core-green-meadow-shell",
    kind: "memory",
    title: "Green Meadow release shell",
    description: "Use PowerShell 7 when preparing Green Meadow releases.",
    scope: "Green Meadow",
    sourceSummary: "Approved from 2 completed tasks",
  },
  {
    id: "core-debug-again",
    kind: "procedure",
    title: "Re-diagnose after a failed fix",
    description:
      "Return to the live failure, form a new diagnosis, then make the next change.",
    scope: "Everywhere",
    sourceSummary: "Approved from 2 explicit corrections",
  },
  {
    id: "core-safe-sync",
    kind: "procedure",
    title: "Safe synchronization",
    description:
      "Explain overwrite risk, create a recoverable backup, then verify the result.",
    scope: "Everywhere",
    sourceSummary: "Approved from 2 completed tasks",
  },
  {
    id: "core-release-handoff",
    kind: "skill",
    title: "Release handoff",
    description:
      "Summarize the outcome, verification, and recovery path for a release.",
    scope: "Everywhere",
    sourceSummary: "Approved from 3 successful handoffs",
  },
  {
    id: "core-current-research",
    kind: "skill",
    title: "Current-source research",
    description:
      "Verify time-sensitive claims with current primary sources before reporting them.",
    scope: "Everywhere",
    sourceSummary: "Approved from 1 explicit correction",
  },
];

export const connections: AgentConnection[] = [
  {
    id: "codex",
    name: "Codex",
    status: "connected",
    sourceCapability: "Learns from completed tasks",
    targetCapability: "Delivers to fresh Temper-managed tasks",
    authDescription: "Signed in with ChatGPT",
    costDescription: "Uses your Codex subscription",
  },
  {
    id: "claude",
    name: "Claude Code",
    status: "available",
    sourceCapability: "Can learn through a local hook",
    targetCapability: "Can deliver scoped adaptations to new prompts",
    authDescription: "Console sign-in required",
    costDescription: "Provider-billed; Temper never stores the credential",
  },
];

export const projects: RegisteredProject[] = [
  {
    id: "project-kairn",
    name: "Kairn",
    pathLabel: "~/projects/kairn",
    connectedAgents: ["Codex"],
  },
  {
    id: "project-green-meadow",
    name: "Green Meadow",
    pathLabel: "~/projects/green-meadow",
    connectedAgents: ["Codex"],
  },
];
