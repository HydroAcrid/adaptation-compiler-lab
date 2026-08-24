export type Screen =
  | "onboarding"
  | "today"
  | "suggestion"
  | "core"
  | "connections"
  | "settings"
  | "advanced"
  | "tray";

export type Theme = "light" | "dark" | "system";
export type FeedbackValue = "helped" | "hurt" | "irrelevant";
export type ProjectName = "Kairn" | "Green Meadow";
export type EvidenceStrength = "strong" | "promising" | "developing";
export type AutomationDisposition =
  "eligible" | "review-required" | "collect-more";
export type SuggestionDecision = "suggested" | "project" | "ignore";

export interface Suggestion {
  id: string;
  behavior: string;
  explanation: string;
  suggestedScope: string;
  projectScope: string;
  sourceCount: number;
  authority: string;
  capturedAt: string;
  digest: string;
  evidenceStrength: EvidenceStrength;
  confidenceReason: string;
  automationDisposition: AutomationDisposition;
  automationReason: string;
}

export type CoreKind = "preference" | "memory" | "procedure" | "skill";
export type CoreScope = "Everywhere" | "Kairn" | "Green Meadow";

export interface CoreItem {
  id: string;
  kind: CoreKind;
  title: string;
  description: string;
  scope: CoreScope;
  sourceSummary: string;
}

export interface AgentConnection {
  id: "codex" | "claude";
  name: string;
  status: "connected" | "available" | "attention";
  sourceCapability: string;
  targetCapability: string;
  authDescription: string;
  costDescription: string;
}

export interface RegisteredProject {
  id: string;
  name: string;
  pathLabel: string;
  connectedAgents: string[];
}
