import type {
  AgentConnection,
  CoreItem,
  RegisteredProject,
  Suggestion,
} from "../types";

export const suggestions: Suggestion[] = [
  {
    id: "suggestion-purpose-first",
    behavior: "Lead with the purpose before setup steps.",
    explanation:
      "You gave the same direction in three completed tasks. Temper reads it as a clear communication preference for Kairn.",
    suggestedScope: "Kairn",
    sourceProject: "Kairn",
    sourceCount: 3,
    authority: "Repeated explicit user corrections",
    capturedAt: "August 24, 2026 at 10:42 AM",
    digest: "sha256:0f67…c98a",
    evidenceStrength: "strong",
    confidenceReason:
      "Repeated explicit corrections agree across three completed tasks.",
    automationDisposition: "eligible",
    automationReason:
      "This is a low-impact, reversible preference with a clear project scope.",
  },
  {
    id: "suggestion-live-state",
    behavior:
      "When notes and the repository disagree, verify the live repository.",
    explanation:
      "Two corrections point to the same verification habit. It is strongly supported, but it would guide a procedure rather than express a simple preference.",
    suggestedScope: "Kairn",
    sourceProject: "Kairn",
    sourceCount: 2,
    authority: "Repeated explicit user corrections",
    capturedAt: "August 24, 2026 at 11:18 AM",
    digest: "sha256:23aa…5f10",
    evidenceStrength: "strong",
    confidenceReason:
      "Two explicit corrections agree and the intended project is clear.",
    automationDisposition: "review-required",
    automationReason:
      "Procedures can materially change how an agent works, so review remains required.",
  },
  {
    id: "suggestion-real-names",
    behavior:
      "Prefer names that represent real things over generic techy names.",
    explanation:
      "You stated this directly once. Temper can preserve it now if you want, or wait for another ordinary-work example.",
    suggestedScope: "All projects",
    sourceProject: "Kairn",
    sourceCount: 1,
    authority: "Direct user preference",
    capturedAt: "August 24, 2026 at 12:03 PM",
    digest: "sha256:54d1…0b9e",
    evidenceStrength: "developing",
    confidenceReason:
      "The wording is explicit, but Temper has seen it in only one context.",
    automationDisposition: "collect-more",
    automationReason:
      "A global preference needs either your decision or another supporting example.",
  },
];

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
