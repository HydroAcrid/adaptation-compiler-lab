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

export interface ShareablePackageItemPreview {
  item_id: string;
  kind: string;
  summary: string;
  disposition: "new" | "exact_duplicate" | "conflict" | "owner_only";
}

export interface ShareablePackagePreview {
  package_type: "behavior_pack" | "capability_mode" | "personal_mode_overlay";
  package_id: string;
  release_version: string;
  package_digest: string;
  display_name: string;
  publisher_name: string;
  publisher_key_fingerprint: string;
  source_license: string;
  origin_signature_verified: true;
  item_count: number;
  items: ShareablePackageItemPreview[];
  duplicate_item_ids: string[];
  conflicting_item_ids: string[];
  requested_scope_mapping_count: number;
  required_capabilities: string[];
  evaluation_status: string | null;
  warnings: string[];
  starts_inactive: true;
  grants_user_authority: false;
  raw_payloads_exposed: false;
}

export interface PackageReviewItem {
  review_version: "1.0.0";
  review_id: string;
  review_digest: string;
  import_receipt_id: string;
  import_receipt_digest: string;
  package_type: "behavior_pack" | "capability_mode" | "personal_mode_overlay";
  package_id: string;
  package_digest: string;
  item_id: string;
  item_digest: string;
  claim_key: string | null;
  publisher_name: string;
  publisher_key_fingerprint: string;
  kind: string;
  summary: string;
  disposition: "new" | "exact_duplicate" | "conflict" | "owner_only";
  requested_scope: {
    project_ids: string[];
    task_classes: string[];
    target_families: string[];
    environment_ids: string[];
    activation_conditions: string[];
    exclusions: string[];
    scope_mapping_required: boolean;
  } | null;
  behavioral_contract: {
    intent: string;
    required_behaviors: string[];
    non_goals: string[];
    verification_requirements: string[];
  } | null;
  required_capabilities: string[];
  evaluation_status: string | null;
  available_actions: Array<"approve" | "reject">;
  created_at: string;
  starts_inactive: true;
  origin_grants_authority: false;
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
  source_kind: "first_party" | "imported";
  personalized: boolean;
}

export interface AgentConnection {
  id: "codex" | "claude" | "copilot";
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
  availableActions?: Array<
    "refresh" | "use_for_setup" | "connect" | "disconnect"
  >;
}

export interface RegisteredProject {
  id: string;
  name: string;
  pathLabel: string;
  connectedAgents: string[];
}
