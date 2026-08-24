export type Screen =
  | "onboarding"
  | "today"
  | "suggestion"
  | "adaptations"
  | "connections"
  | "settings"
  | "advanced"
  | "tray";

export type Theme = "light" | "dark" | "system";
export type FeedbackValue = "helped" | "hurt" | "irrelevant";

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
}

export interface Adaptation {
  id: string;
  behavior: string;
  scope: string;
  sourceSummary: string;
  status: "active" | "paused";
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
