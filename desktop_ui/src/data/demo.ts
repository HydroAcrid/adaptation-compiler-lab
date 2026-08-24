import type {
  Adaptation,
  AgentConnection,
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

export const adaptations: Adaptation[] = [
  {
    id: "adaptation-purpose-first",
    behavior: "Explain the purpose plainly before procedural detail.",
    scope: "All coding work",
    sourceSummary: "Approved from 3 explicit corrections",
    status: "active",
  },
  {
    id: "adaptation-shell",
    behavior: "Match commands to the actual shell and operating environment.",
    scope: "All coding work",
    sourceSummary: "Approved from 2 completed tasks",
    status: "active",
  },
  {
    id: "adaptation-kairn",
    behavior:
      "When reviewing Kairn, distinguish live repository state from older notes.",
    scope: "Kairn only",
    sourceSummary: "Approved from 1 explicit correction",
    status: "active",
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
