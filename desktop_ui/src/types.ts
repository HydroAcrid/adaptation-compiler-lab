export type Screen =
  | "onboarding"
  | "today"
  | "suggestion"
  | "core"
  | "modes"
  | "connections"
  | "settings"
  | "advanced"
  | "tray";

export type Theme = "light" | "dark" | "system";
export type FeedbackValue = "helped" | "hurt" | "irrelevant";
export type ProjectName = string;
export type WorkspaceScope = "all" | ProjectName;
export type EvidenceStrength = "strong" | "promising" | "developing";
export type AutomationDisposition =
  "eligible" | "review-required" | "collect-more";
export type SuggestionDecision =
  "suggested" | "project" | "narrowed" | "ignore";

export interface Suggestion {
  id: string;
  behavior: string;
  explanation: string;
  suggestedScope: string;
  sourceProject: ProjectName | null;
  projectNames?: ProjectName[];
  isGlobal?: boolean;
  availableDecisions?: SuggestionDecision[];
  sourceCount?: number;
  authority?: string;
  capturedAt: string;
  digest: string;
  evidenceStrength?: EvidenceStrength;
  confidenceReason: string;
  automationDisposition: AutomationDisposition;
  automationReason: string;
  isRevocation?: boolean;
}

export type CoreKind =
  | "preference"
  | "memory"
  | "example"
  | "procedure"
  | "prompt_rule"
  | "skill"
  | "tool_recommendation";
export type CoreScope = string;

export interface CoreItem {
  id: string;
  kind: CoreKind;
  title: string;
  description: string;
  scope: CoreScope;
  projectNames?: ProjectName[];
  isGlobal?: boolean;
  sourceSummary: string;
}

export interface PortableProfileItemPreview {
  item_id: string;
  kind: string;
  summary: string;
  required_behavior_count: number;
  scope_mapping_required: boolean;
}

export interface PortableProfilePreview {
  package_id: string;
  display_name: string;
  package_digest: string;
  source_key_fingerprint: string;
  source_signature_verified: true;
  item_count: number;
  items: PortableProfileItemPreview[];
  scope_mapping_count: number;
  warnings: string[];
  activates_nothing: true;
  raw_payloads_exposed: false;
}

export interface CapabilityModeSummary {
  mode_id: string;
  mode_version: string;
  name: string;
  summary: string;
  publisher: string;
  source_license: string;
  activation_default: "one_task";
  task_lease_hours: number;
  supports_personal_overlay: true;
  applicable_task_classes: string[];
  compatible_target_families: string[];
  requested_tools: string[];
  required_capabilities: string[];
  evaluation_status: "experimental" | "product_evaluated" | "failed";
  effectiveness_evaluated: boolean;
  projection_utf8_bytes: number;
  evaluation_valid: boolean;
  evaluation_case_count: number;
  mutates_permanent_core: false;
  auto_activates: false;
}

export interface AgentConnection {
  id: "codex" | "claude";
  name: string;
  status:
    | "connected"
    | "available"
    | "attention"
    | "not_installed"
    | "signed_out"
    | "update_required";
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
