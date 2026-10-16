import type {
  AgentConnection,
  CapabilityModeSummary,
  CoreItem,
  PortableProfilePreview,
  RegisteredProject,
  Suggestion,
} from "../types";
import type { ProfileExportPreview, ProfileImportPreview } from "../engine";

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
    targetCapability:
      "Approved suggestions go to fresh Temper-managed tasks. Authorized style defaults can also reach ordinary Codex chats through native instructions or scoped MCP context.",
    authDescription: "Signed in with ChatGPT",
    costDescription: "Uses your Codex subscription",
  },
  {
    id: "claude",
    name: "Claude Code",
    status: "not_installed",
    sourceCapability: "Not integrated in this Temper build",
    targetCapability: "Not integrated in this Temper build",
    authDescription: "Not installed in this example",
    costDescription: "Future Claude use would be provider-billed",
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

export const modes: CapabilityModeSummary[] = [
  {
    activation_default: "one_task",
    applicable_task_classes: [
      "design_system",
      "frontend_design",
      "frontend_implementation",
    ],
    compatible_target_families: ["claude-code", "codex"],
    effectiveness_evaluated: false,
    evaluation_case_count: 6,
    evaluation_status: "curated_unproven",
    evaluation_valid: true,
    mode_id: "curated-frontend-studio",
    mode_version: "1.0.0",
    mutates_permanent_core: false,
    name: "Frontend Studio",
    auto_activates: false,
    source_kind: "curated",
    catalog_digest: `sha256:${"a".repeat(64)}`,
    source_count: 2,
    known_limitations: [
      "Curated and statically checked; comparative evaluation is pending.",
    ],
    personalized: true,
    publisher: "Temper Foundry",
    projection_utf8_bytes: 1518,
    required_capabilities: [],
    requested_tools: [],
    source_license: "MIT",
    summary:
      "A focused frontend workflow for distinctive, accessible, responsive product interfaces.",
    supports_personal_overlay: true,
    task_lease_hours: 4,
  },
  {
    activation_default: "one_task",
    applicable_task_classes: ["security_review", "threat_review"],
    compatible_target_families: ["claude-code", "codex"],
    effectiveness_evaluated: false,
    evaluation_case_count: 6,
    evaluation_status: "curated_unproven",
    evaluation_valid: true,
    mode_id: "curated-read-only-security-review",
    mode_version: "1.0.0",
    mutates_permanent_core: false,
    name: "Read-only Security Review",
    auto_activates: false,
    source_kind: "curated",
    catalog_digest: `sha256:${"a".repeat(64)}`,
    source_count: 2,
    known_limitations: [
      "Review-only: it grants no exploit or write capability.",
    ],
    personalized: false,
    publisher: "Temper Foundry",
    projection_utf8_bytes: 1374,
    required_capabilities: [],
    requested_tools: [],
    source_license: "MIT and Apache-2.0",
    summary:
      "A bounded, evidence-first review workflow that finds and prioritizes actionable security risks without changing code.",
    supports_personal_overlay: true,
    task_lease_hours: 4,
  },
  {
    activation_default: "one_task",
    applicable_task_classes: [
      "debugging",
      "incident_diagnosis",
      "test_failure",
    ],
    compatible_target_families: ["claude-code", "codex"],
    effectiveness_evaluated: false,
    evaluation_case_count: 6,
    evaluation_status: "curated_unproven",
    evaluation_valid: true,
    mode_id: "curated-systematic-debugger",
    mode_version: "1.0.0",
    mutates_permanent_core: false,
    name: "Systematic Debugger",
    auto_activates: false,
    source_kind: "curated",
    catalog_digest: `sha256:${"a".repeat(64)}`,
    source_count: 1,
    known_limitations: [
      "Optimized for reproducible failures, not open-ended feature work.",
    ],
    personalized: false,
    publisher: "Temper Foundry",
    projection_utf8_bytes: 1288,
    required_capabilities: [],
    requested_tools: [],
    source_license: "MIT",
    summary:
      "A root-cause-first debugging workflow that reproduces failures, tests hypotheses, and verifies the exact fix.",
    supports_personal_overlay: true,
    task_lease_hours: 4,
  },
];

export const workspaceOptions = [
  { id: "Kairn", label: "Kairn", description: "3 suggestions" },
  { id: "Green Meadow", label: "Green Meadow", description: "No suggestions" },
];

export const modeProjects = [
  { id: "kairn", label: "Kairn" },
  { id: "green-meadow", label: "Green Meadow" },
];

export const profileExportPreview: ProfileExportPreview &
  PortableProfilePreview = {
  activates_nothing: true,
  display_name: "Temper Core",
  export_token: "browser-preview",
  item_count: 8,
  items: [
    {
      item_id: "profile-item-0001",
      kind: "preference",
      required_behavior_count: 1,
      scope_mapping_required: false,
      summary: "Make handoffs understandable",
    },
    {
      item_id: "profile-item-0002",
      kind: "procedure",
      required_behavior_count: 2,
      scope_mapping_required: true,
      summary: "Synchronize work safely",
    },
  ],
  package_digest: `sha256:${"a".repeat(64)}`,
  package_id: "temper-core-preview",
  raw_payloads_exposed: false,
  scope_mapping_count: 1,
  source_key_fingerprint: `sha256:${"b".repeat(64)}`,
  source_signature_verified: true,
  warnings: [
    "Raw conversations and private paths are not included.",
    "Project-specific guidance needs a local scope on another installation.",
  ],
};

export const profileImportPreview: ProfileImportPreview &
  PortableProfilePreview = {
  ...profileExportPreview,
  display_name: "Shared Temper profile",
  import_token: "browser-import-preview",
  item_count: 4,
  package_id: "shared-profile-preview",
  warnings: [
    "Imported guidance remains inactive until you review and approve it.",
    "The source signature proves origin; it does not become your instruction authority.",
  ],
};
