import * as Dialog from "@radix-ui/react-dialog";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  CircleHelp,
  Cloud,
  Download,
  ExternalLink,
  FileDiff,
  Info,
  Laptop,
  Moon,
  Pause,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  Share2,
  ShieldCheck,
  Sparkles,
  Sun,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { AgentBrandMark } from "./AgentBrandMark";
import { AutonomousLearningPanel } from "./AutonomousLearningPanel";
import { LearningRepositories } from "./LearningRepositories";
import { ToolsHubPanel } from "./ToolsHubPanel";
import {
  analyzeInstructionEnvironment,
  applyClaudeConnection,
  applyCopilotConnection,
  applyTargetAuthorization,
  applyNativeInstructionChange,
  disablePersonalInstructionSetup,
  enablePersonalInstructionSetup,
  loadCuratedMode,
  previewModeActivation,
  previewNativeInstructionChange,
  previewClaudeConnection,
  previewCopilotConnection,
  previewTargetAuthorization,
  previewPersonalInstructionSetup,
  previewProjectRegistration,
  requestNotificationPermission,
  registerProject,
  rollbackNativeInstructionChange,
  runModeTask,
  type EngineAgentConnection,
  type EngineArtifactRef,
  type EngineConnectionPreview,
  type EngineProjectPreview,
  type EngineProject,
  type EngineTargetAuthorizationPreview,
  type EngineRecentUndo,
  type EngineTaskResult,
  type EngineDiagnostics,
  type EngineDesktopSnapshot,
  type EngineInstructionChangePreview,
  type EngineInstructionChangeReceipt,
  type EngineInstructionEnvironmentSummary,
  type EngineInstructionGlobalPreview,
  type EngineInstructionSourceSummary,
  type EngineLongitudinalGate,
  type EngineNativeTarget,
} from "../engine";
import { usePageVisibility } from "../pageVisibility";
import type {
  CapabilityModeSummary,
  CuratedModeDetail,
  CoreItem,
  CoreKind,
  EvidenceStrength,
  FeedbackValue,
  ModeActivationPreview,
  AgentConnection,
  ProjectName,
  RegisteredProject,
  PackageReviewItem,
  Suggestion,
  Theme,
  WorkspaceScope,
} from "../types";
import { ProfilePortabilityDialog } from "./ProfilePortabilityDialog";
import { RecoveryExportDialog } from "./RecoveryDialog";
import { ShareablePackageDialog } from "./ShareablePackageDialog";
import { PackageReviewQueue } from "./PackageReviewQueue";
import {
  Button,
  Divider,
  LoadingStatus,
  SectionHeading,
  StatusPill,
  TemperSelect,
  Toggle,
} from "./ui";

function PageDialogPortal({ children }: { children: ReactNode }) {
  const pageVisible = usePageVisibility();
  return pageVisible ? <Dialog.Portal>{children}</Dialog.Portal> : null;
}

function restorePageDialogFocus(
  event: Event,
  opener: HTMLButtonElement | null,
) {
  event.preventDefault();
  if (opener?.isConnected && !opener.closest("[hidden], [inert]")) {
    opener.focus();
  }
}

export function TodayPage({
  onReview,
  onOpenCore,
  onOpenTools,
  feedback,
  onFeedback,
  workspace,
  suggestions,
  selectedSuggestionId,
  automaticLearning,
  liveSummary,
  instructionEnvironments = [],
  liveProjects = [],
  nativeAutonomy = false,
  workspaceControl,
}: {
  onReview: (suggestionId: string) => void;
  onOpenCore: () => void;
  onOpenTools: () => void;
  feedback: FeedbackValue | null;
  onFeedback: (value: FeedbackValue) => void;
  workspace: WorkspaceScope;
  suggestions: Suggestion[];
  selectedSuggestionId: string | null;
  automaticLearning: boolean;
  liveSummary?: {
    activeAdaptationCount: number;
    health: "ready" | "needs_attention" | "paused" | "consent_expired";
    feedbackAvailable: boolean;
    pendingFeedbackCount: number;
    pendingReviewCount: number;
    projectCount: number;
    secureStoreReady: boolean;
    message?: string;
  };
  instructionEnvironments?: EngineInstructionEnvironmentSummary[];
  liveProjects?: EngineProject[];
  nativeAutonomy?: boolean;
  workspaceControl?: ReactNode;
}) {
  const applicableEnvironments = instructionEnvironments.filter(
    (environment) =>
      workspace === "all" ||
      liveProjects.some(
        (project) =>
          project.project_id === environment.project_id &&
          project.display_name === workspace,
      ),
  );
  const nativeConflict = applicableEnvironments
    .flatMap((environment) => environment.conflicts ?? [])
    .find(
      (conflict) =>
        conflict.severity === "blocking" &&
        conflict.resolution_state === "unresolved",
    );
  const applicableSuggestions =
    workspace === "all"
      ? suggestions
      : suggestions.filter((item) =>
          item.projectNames
            ? item.isGlobal === true || item.projectNames.includes(workspace)
            : item.suggestedScope === "All projects" ||
              item.suggestedScope.split(", ").includes(workspace),
        );
  const selectedSuggestion =
    applicableSuggestions.find((item) => item.id === selectedSuggestionId) ??
    applicableSuggestions[0];
  const permissionExpired = liveSummary?.health === "consent_expired";
  const storageUnavailable = liveSummary?.secureStoreReady === false;
  const suggestionCount = applicableSuggestions.length;
  const feedbackCount = liveSummary?.pendingFeedbackCount ?? 0;
  const reviewUnavailable = nativeAutonomy && !liveSummary;
  const canRate = liveSummary ? feedbackCount > 0 : !nativeAutonomy;
  const pendingReviewCount =
    workspace === "all"
      ? (liveSummary?.pendingReviewCount ?? suggestionCount)
      : suggestionCount;
  const reviewStatus = reviewUnavailable
    ? "Status unavailable"
    : pendingReviewCount
      ? `${pendingReviewCount} to review`
      : feedbackCount
        ? `${feedbackCount} to rate`
        : "No pending reviews";

  return (
    <div className="page folio-page folio-page--today">
      <header className="today-learning-heading">
        <div>
          <h1>Overview</h1>
          <p>See which workflows Temper can use and what’s ready for review.</p>
        </div>
      </header>
      <ToolsHubPanel nativeRuntime={nativeAutonomy} onOpenTools={onOpenTools} />
      {nativeAutonomy && (
        <AutonomousLearningPanel
          projects={liveProjects}
          onOpenPersonalization={onOpenCore}
        />
      )}
      <details
        className="today-review-summary"
        open={
          !nativeAutonomy ||
          suggestions.length > 0 ||
          feedbackCount > 0 ||
          instructionEnvironments.some(
            (environment) => environment.blocking_conflict_count > 0,
          )
        }
      >
        <summary>
          Reviewed suggestions <span>{reviewStatus}</span>
        </summary>
        <div className="overview-review__body">
          {workspaceControl && (
            <div className="overview-review__heading">{workspaceControl}</div>
          )}
          {nativeConflict ? (
            <div className="folio-proposal">
              <h2>Instruction conflict</h2>
              <p>{nativeConflict.source_display_path}</p>
              <p>{nativeConflict.rationale}</p>
              <Button onClick={onOpenCore}>Review agent setup</Button>
            </div>
          ) : permissionExpired || storageUnavailable ? (
            <div className="folio-proposal">
              <h2>
                {permissionExpired
                  ? "Permission expired"
                  : "Secure storage unavailable"}
              </h2>
              <p>
                {permissionExpired
                  ? "Renew permission in Settings to review suggestions and use approved guidance."
                  : "Access to this device’s saved keys is needed to review and apply suggestions."}
              </p>
            </div>
          ) : reviewUnavailable ? (
            <div className="folio-proposal">
              <h2>Suggestions unavailable</h2>
              <p>Refresh status in Connections to check for suggestions.</p>
            </div>
          ) : selectedSuggestion ? (
            <section className="folio-workbench" aria-label="Suggestions">
              <article className="folio-proposal">
                <h2>{selectedSuggestion.behavior}</h2>
                <p>{selectedSuggestion.explanation}</p>
                <button
                  className="folio-primary-action"
                  onClick={() => onReview(selectedSuggestion.id)}
                  type="button"
                >
                  Review suggestion <ArrowRight aria-hidden="true" size={16} />
                </button>
              </article>
              <aside className="folio-margin" aria-label="Suggestion details">
                <dl className="margin-register">
                  <div>
                    <dt>Evidence</dt>
                    <dd>
                      {selectedSuggestion.evidenceStrength
                        ? evidenceStrengthLabels[
                            selectedSuggestion.evidenceStrength
                          ]
                        : "Review required"}
                    </dd>
                  </div>
                  <div>
                    <dt>Suggested scope</dt>
                    <dd>{selectedSuggestion.suggestedScope}</dd>
                  </div>
                  <div>
                    <dt>Next step</dt>
                    <dd>
                      {selectedSuggestion.automationDisposition === "eligible"
                        ? automaticLearning
                          ? "Automatic with 24-hour undo"
                          : "Automatic option available"
                        : selectedSuggestion.automationDisposition ===
                            "review-required"
                          ? "Your review is required"
                          : "Waiting for more evidence"}
                    </dd>
                  </div>
                </dl>
                {suggestionCount > 1 && (
                  <div className="margin-queue">
                    <div className="margin-queue__heading">
                      <span>Other suggestions</span>
                    </div>
                    <ol>
                      {applicableSuggestions
                        .filter((item) => item.id !== selectedSuggestion.id)
                        .map((item) => (
                          <li key={item.id}>
                            <button
                              onClick={() => onReview(item.id)}
                              type="button"
                            >
                              <span className="queue-copy">
                                <strong>{item.behavior}</strong>
                                {item.evidenceStrength && (
                                  <small>
                                    {
                                      evidenceStrengthLabels[
                                        item.evidenceStrength
                                      ]
                                    }
                                  </small>
                                )}
                              </span>
                            </button>
                          </li>
                        ))}
                    </ol>
                  </div>
                )}
              </aside>
            </section>
          ) : (
            <div className="folio-proposal">
              <h2>No suggestions to review</h2>
              <p>
                {liveSummary?.health === "paused"
                  ? "New suggestions are paused. You can resume them in Settings."
                  : liveSummary?.health === "needs_attention"
                    ? "Check Connections for your agent and project status."
                    : liveSummary?.projectCount === 0
                      ? "Add a task project in Connections to get suggestions for your work."
                      : workspace === "all"
                        ? "Suggestions will appear here when Temper has a change for you to review."
                        : `There are no suggestions for ${workspace}.`}
              </p>
            </div>
          )}
          {(feedback || canRate) && (
            <div className="margin-feedback">
              <h2>Was Temper useful?</h2>
              <p>
                {liveSummary
                  ? "Rate the guidance used in a recent task."
                  : "Try a sample rating."}
              </p>
              {feedback ? (
                <div className="feedback-thanks" role="status">
                  <Check aria-hidden="true" size={15} /> Rating saved
                </div>
              ) : (
                <div
                  className="feedback-row feedback-row--folio"
                  aria-label="Rate recent guidance"
                >
                  <button
                    disabled={liveSummary?.feedbackAvailable === false}
                    onClick={() => onFeedback("helped")}
                    type="button"
                  >
                    Helped
                  </button>
                  <button
                    disabled={liveSummary?.feedbackAvailable === false}
                    onClick={() => onFeedback("hurt")}
                    type="button"
                  >
                    Hurt
                  </button>
                  <button
                    disabled={liveSummary?.feedbackAvailable === false}
                    onClick={() => onFeedback("irrelevant")}
                    type="button"
                  >
                    Irrelevant
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </details>
    </div>
  );
}

const evidenceStrengthLabels: Record<EvidenceStrength, string> = {
  strong: "Strong evidence",
  promising: "Promising evidence",
  developing: "Developing evidence",
};

const coreKinds: Array<{
  id: CoreKind;
  label: string;
  description: string;
}> = [
  {
    id: "preference",
    label: "Preferences",
    description: "Choices you tend to favor.",
  },
  {
    id: "memory",
    label: "Memories",
    description: "Stable context worth carrying forward.",
  },
  {
    id: "procedure",
    label: "Procedures",
    description: "Sequences and safeguards you approved.",
  },
  {
    id: "prompt_rule",
    label: "Rules",
    description: "Direct instructions that govern agent behavior.",
  },
  {
    id: "example",
    label: "Examples",
    description: "Approved examples of what good work looks like.",
  },
  {
    id: "skill",
    label: "Skills",
    description: "Reusable guidance for a kind of work.",
  },
  {
    id: "tool_recommendation",
    label: "Tools",
    description: "Approved recommendations for when a tool is useful.",
  },
];

export function CorePage({
  availableWorkspaces,
  initialItems = [],
  nativeRuntime = false,
  governedMutationsAvailable = true,
  governedMutationUnavailableReason = null,
  snapshotDigest = null,
  onNotice,
  onRevoke,
  recentUndo,
  onUndo,
  instructionEnvironments = [],
  liveProjects = [],
  nativeAutonomy = false,
}: {
  availableWorkspaces?: ProjectName[];
  initialItems?: CoreItem[];
  nativeRuntime?: boolean;
  governedMutationsAvailable?: boolean;
  governedMutationUnavailableReason?: string | null;
  snapshotDigest?: string | null;
  onNotice?: (message: string) => void;
  onRevoke?: (artifactId: string) => Promise<void>;
  recentUndo?: EngineRecentUndo;
  onUndo?: () => Promise<void>;
  instructionEnvironments?: EngineInstructionEnvironmentSummary[];
  liveProjects?: EngineProject[];
  nativeAutonomy?: boolean;
}) {
  const [previewItems, setItems] = useState(initialItems);
  const items = nativeRuntime ? initialItems : previewItems;
  const [kind, setKind] = useState<CoreKind | "all">("all");
  const [scope, setScope] = useState<ProjectName | "all">("all");
  const [selected, setSelected] = useState<CoreItem | null>(null);
  const [revokeSelected, setRevokeSelected] = useState<CoreItem | null>(null);
  const [removed, setRemoved] = useState<{
    item: CoreItem;
    index: number;
  } | null>(null);
  const [portabilityMode, setPortabilityMode] = useState<
    "export" | "import" | null
  >(null);
  const [shareablePackageOpen, setShareablePackageOpen] = useState(false);
  const workspaceChoices = availableWorkspaces ?? [];
  const appliesToProject = (item: CoreItem, project: ProjectName) =>
    item.isGlobal === true ||
    (item.projectNames
      ? item.projectNames.includes(project)
      : item.scope === "Everywhere" || item.scope === project);
  const visibleItems = items.filter(
    (item) =>
      (kind === "all" || item.kind === kind) &&
      (scope === "all" || appliesToProject(item, scope)),
  );
  const visibleEnvironments = instructionEnvironments.filter((environment) => {
    if (scope === "all") return true;
    return liveProjects.some(
      (project) =>
        project.project_id === environment.project_id &&
        project.display_name === scope,
    );
  });

  function removeItem(item: CoreItem) {
    setRemoved({
      item,
      index: items.findIndex((entry) => entry.id === item.id),
    });
    setItems((current) => current.filter((entry) => entry.id !== item.id));
  }

  function restoreItem() {
    if (!removed) return;
    setItems((current) => {
      const restored = [...current];
      restored.splice(removed.index, 0, removed.item);
      return restored;
    });
    setRemoved(null);
  }

  function saveItem(updated: CoreItem) {
    setItems((current) =>
      current.map((item) => (item.id === updated.id ? updated : item)),
    );
    setSelected(null);
  }

  return (
    <div className="page folio-page core-page">
      <header className="core-heading">
        <div>
          <h1>Personalization</h1>
          <p>
            Manage what Temper learns and the guidance you’ve saved for your
            agents.
          </p>
        </div>
        <div className="core-heading__aside">
          <div className="core-portability-actions">
            <button
              disabled={nativeRuntime && !governedMutationsAvailable}
              onClick={() => setPortabilityMode("export")}
              title={governedMutationUnavailableReason ?? undefined}
              type="button"
            >
              <Download aria-hidden="true" size={14} /> Export
            </button>
            <button
              disabled={nativeRuntime && !governedMutationsAvailable}
              onClick={() => setPortabilityMode("import")}
              title={governedMutationUnavailableReason ?? undefined}
              type="button"
            >
              <Upload aria-hidden="true" size={14} /> Import
            </button>
            <button
              disabled={nativeRuntime && !governedMutationsAvailable}
              onClick={() => setShareablePackageOpen(true)}
              title={governedMutationUnavailableReason ?? undefined}
              type="button"
            >
              <Share2 aria-hidden="true" size={14} /> Share pack
            </button>
          </div>
        </div>
      </header>
      {nativeAutonomy && <AutonomousLearningPanel projects={liveProjects} />}
      <section
        className="personalization-library"
        aria-labelledby="saved-guidance-heading"
      >
        <div className="subsection-heading">
          <div>
            <h2 id="saved-guidance-heading">Saved guidance</h2>
            <p>Preferences and instructions you approved or imported.</p>
          </div>
          {(!nativeRuntime || snapshotDigest) && (
            <StatusPill tone="neutral">{visibleItems.length} saved</StatusPill>
          )}
        </div>
        {nativeRuntime && visibleEnvironments.length > 0 ? (
          <details
            className="learning-details"
            open={visibleEnvironments.some(
              (environment) => environment.blocking_conflict_count > 0,
            )}
          >
            <summary>Existing agent setup</summary>
            <InstructionEnvironmentPanel
              environments={visibleEnvironments}
              governedMutationsAvailable={governedMutationsAvailable}
              onComplete={(message) => onNotice?.(message)}
              projectLabel={(projectId) =>
                liveProjects.find((project) => project.project_id === projectId)
                  ?.display_name ?? projectId
              }
              snapshotDigest={snapshotDigest}
            />
          </details>
        ) : null}
        <div className="core-toolbar">
          <div
            aria-label="Filter by knowledge type"
            className="core-kind-filter"
          >
            <button
              aria-pressed={kind === "all"}
              onClick={() => setKind("all")}
              type="button"
            >
              All
            </button>
            {coreKinds.map((entry) => (
              <button
                aria-pressed={kind === entry.id}
                key={entry.id}
                onClick={() => setKind(entry.id)}
                type="button"
              >
                {entry.label}
              </button>
            ))}
          </div>
          <div className="core-scope-filter">
            <span>Show for</span>
            <TemperSelect
              ariaLabel="Show for"
              className="core-scope-select"
              onValueChange={setScope}
              options={[
                { label: "All projects", value: "all" as const },
                ...workspaceChoices.map((workspace) => ({
                  label: workspace,
                  value: workspace,
                })),
              ]}
              value={scope}
            />
          </div>
        </div>
        {nativeRuntime && recentUndo ? (
          <div className="undo-banner">
            <span>{recentUndo.summary}</span>
            <button
              disabled={!governedMutationsAvailable}
              onClick={() => void onUndo?.()}
              title={governedMutationUnavailableReason ?? undefined}
              type="button"
            >
              <RotateCcw size={14} /> Undo
            </button>
          </div>
        ) : removed ? (
          <div className="undo-banner">
            <span>“{removed.item.title}” was removed from saved guidance.</span>
            <button onClick={restoreItem} type="button">
              <RotateCcw size={14} /> Undo
            </button>
          </div>
        ) : null}
        <div className="core-catalog">
          {coreKinds.map((entry) => {
            const groupItems = visibleItems.filter(
              (item) => item.kind === entry.id,
            );
            if (!groupItems.length) return null;
            return (
              <CoreGroup
                description={entry.description}
                items={groupItems}
                key={entry.id}
                label={entry.label}
                onEdit={setSelected}
                onRemove={removeItem}
                onRevoke={setRevokeSelected}
                readOnly={nativeRuntime}
                revokeAvailable={governedMutationsAvailable}
                revokeUnavailableReason={governedMutationUnavailableReason}
              />
            );
          })}
          {visibleItems.length === 0 ? (
            <div className="core-empty">
              {nativeRuntime && !snapshotDigest
                ? "Saved guidance is unavailable. Refresh status in Connections to try again."
                : items.length === 0
                  ? "No saved guidance yet. Approve a suggestion or import guidance to add it here."
                  : "No items match these filters."}
            </div>
          ) : null}
        </div>
      </section>
      {selected ? (
        <CoreItemDialog
          availableScopes={workspaceChoices}
          item={selected}
          key={selected.id}
          onClose={() => setSelected(null)}
          onSave={saveItem}
        />
      ) : null}
      {revokeSelected ? (
        <CoreRevocationDialog
          item={revokeSelected}
          onClose={() => setRevokeSelected(null)}
          onConfirm={async () => {
            await onRevoke?.(revokeSelected.id);
            setRevokeSelected(null);
          }}
        />
      ) : null}
      {portabilityMode ? (
        <ProfilePortabilityDialog
          mode={portabilityMode}
          nativeRuntime={nativeRuntime}
          onClose={() => setPortabilityMode(null)}
          onComplete={(message) => {
            setPortabilityMode(null);
            onNotice?.(message);
          }}
          snapshotDigest={snapshotDigest}
        />
      ) : null}
      {shareablePackageOpen ? (
        <ShareablePackageDialog
          intent="export-behaviors"
          nativeRuntime={nativeRuntime}
          onClose={() => setShareablePackageOpen(false)}
          onComplete={(message) => {
            setShareablePackageOpen(false);
            onNotice?.(message);
          }}
          snapshotDigest={snapshotDigest}
        />
      ) : null}
    </div>
  );
}

type NativeSourceFilter = "all" | "instructions" | "memory" | "skills";

function InstructionEnvironmentPanel({
  environments,
  projectLabel,
  snapshotDigest,
  governedMutationsAvailable,
  onComplete,
}: {
  environments: EngineInstructionEnvironmentSummary[];
  projectLabel: (projectId: string) => string;
  snapshotDigest: string | null;
  governedMutationsAvailable: boolean;
  onComplete: (message: string) => void;
}) {
  const [filter, setFilter] = useState<NativeSourceFilter>("all");
  const [selected, setSelected] = useState<{
    environment: EngineInstructionEnvironmentSummary;
    source: EngineInstructionSourceSummary;
  } | null>(null);
  const sources = environments.flatMap((environment) =>
    environment.sources.map((source) => ({ environment, source })),
  );
  const shown = sources.filter(({ source }) => {
    if (filter === "all") return true;
    if (filter === "skills") return source.skill;
    if (filter === "memory") return source.kind === "personal_memory";
    return !source.skill && source.kind !== "personal_memory";
  });
  const conflictCount = environments.reduce(
    (total, item) => total + item.blocking_conflict_count,
    0,
  );

  return (
    <section className="native-context" aria-labelledby="native-context-title">
      <header className="native-context__heading">
        <div>
          <h3 id="native-context-title">Project instructions and skills</h3>
          <p>Temper checks this setup before applying your saved guidance.</p>
        </div>
        <StatusPill tone={conflictCount ? "neutral" : "positive"}>
          {conflictCount
            ? `${conflictCount} conflict${conflictCount === 1 ? "" : "s"}`
            : `${sources.length} source${sources.length === 1 ? "" : "s"}`}
        </StatusPill>
      </header>
      <div
        aria-label="Filter existing agent setup"
        className="native-context__filters"
      >
        {(
          [
            ["all", "All"],
            ["instructions", "Instructions"],
            ["memory", "Agent memory"],
            ["skills", "Skills"],
          ] as const
        ).map(([value, label]) => (
          <button
            aria-pressed={filter === value}
            key={value}
            onClick={() => setFilter(value)}
            type="button"
          >
            {label}
          </button>
        ))}
      </div>
      {environments.flatMap((environment) => environment.conflicts ?? [])
        .length ? (
        <div
          className="native-context__conflicts"
          aria-label="Instruction conflicts"
        >
          {environments
            .flatMap((environment) => environment.conflicts ?? [])
            .map((conflict) => (
              <article key={conflict.conflict_id}>
                <div>
                  <span className="folio-kicker">Withheld safely</span>
                  <strong>{conflict.source_display_path}</strong>
                </div>
                <dl>
                  <div>
                    <dt>Saved guidance</dt>
                    <dd>{conflict.temper_behavior}</dd>
                  </div>
                  <div>
                    <dt>Existing instruction</dt>
                    <dd>{conflict.native_behavior}</dd>
                  </div>
                </dl>
                <p>{conflict.rationale}</p>
              </article>
            ))}
        </div>
      ) : null}
      {shown.length ? (
        <ul className="native-context__list">
          {shown.map(({ environment, source }) => (
            <li
              key={`${environment.project_id}-${environment.target}-${source.source_id}`}
            >
              <div>
                <strong>{source.display_path}</strong>
                <span>
                  {projectLabel(environment.project_id)} ·{" "}
                  {targetLabel(source.target)} · {source.instruction_count}{" "}
                  instruction
                  {source.instruction_count === 1 ? "" : "s"}
                </span>
              </div>
              <div className="native-context__actions">
                <StatusPill
                  tone={source.status === "ready" ? "positive" : "neutral"}
                >
                  {source.skill
                    ? nativeSkillStatusLabel(source.activation_status)
                    : nativeSourceStatusLabel(source.status)}
                </StatusPill>
                <Button
                  disabled={
                    source.status !== "ready" ||
                    source.kind.startsWith("personal_") ||
                    !snapshotDigest ||
                    !governedMutationsAvailable
                  }
                  onClick={() => setSelected({ environment, source })}
                  tone="quiet"
                >
                  Preview edit
                </Button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="native-context__empty">
          No supported existing sources match this view.
        </p>
      )}
      {selected && snapshotDigest ? (
        <NativeInstructionDialog
          environment={selected.environment}
          onClose={() => setSelected(null)}
          onComplete={(message) => {
            setSelected(null);
            onComplete(message);
          }}
          snapshotDigest={snapshotDigest}
          source={selected.source}
        />
      ) : null}
    </section>
  );
}

function NativeInstructionDialog({
  environment,
  source,
  snapshotDigest,
  onClose,
  onComplete,
}: {
  environment: EngineInstructionEnvironmentSummary;
  source: EngineInstructionSourceSummary;
  snapshotDigest: string;
  onClose: () => void;
  onComplete: (message: string) => void;
}) {
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<EngineInstructionChangePreview | null>(
    null,
  );
  const [receipt, setReceipt] = useState<EngineInstructionChangeReceipt | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const instructionField = useRef<HTMLTextAreaElement>(null);

  async function makePreview() {
    setBusy(true);
    setError(null);
    try {
      setPreview(
        await previewNativeInstructionChange(
          environment,
          source.source_id,
          text,
          snapshotDigest,
        ),
      );
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Temper could not preview that instruction change.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function applyPreview() {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      setReceipt(
        await applyNativeInstructionChange(
          preview,
          snapshotDigest,
          crypto.randomUUID(),
        ),
      );
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Temper refused that native instruction edit.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function rollback() {
    if (!receipt) return;
    setBusy(true);
    setError(null);
    try {
      await rollbackNativeInstructionChange(
        receipt,
        receipt.environment_digest_after,
        snapshotDigest,
        crypto.randomUUID(),
      );
      onComplete("The native instruction file was restored exactly.");
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Temper could not safely restore that source.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog.Root onOpenChange={(open) => (open ? undefined : onClose())} open>
      <PageDialogPortal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content
          className="core-dialog native-instruction-dialog"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            instructionField.current?.focus();
          }}
        >
          <Dialog.Close aria-label="Close" className="dialog-close">
            <X size={18} />
          </Dialog.Close>
          <span className="folio-kicker">Existing project instructions</span>
          <Dialog.Title>{source.display_path}</Dialog.Title>
          <Dialog.Description>
            Temper will only create or update its clearly marked section. You
            will see the exact diff before anything changes.
          </Dialog.Description>
          {!preview && !receipt ? (
            <label className="native-instruction-dialog__field">
              <span>Temper-managed instruction</span>
              <textarea
                onChange={(event) => setText(event.target.value)}
                placeholder="Describe the project instruction to add…"
                ref={instructionField}
                value={text}
              />
            </label>
          ) : null}
          {preview && !receipt ? (
            <pre aria-label="Exact native instruction diff">
              <code>{preview.unified_diff}</code>
            </pre>
          ) : null}
          {receipt ? (
            <div className="native-instruction-dialog__success">
              <CheckCircle2 size={18} />
              <div>
                <strong>Applied and signed</strong>
                <span>An encrypted original is available for 30 days.</span>
              </div>
            </div>
          ) : null}
          {error ? <p role="alert">{error}</p> : null}
          <div className="core-dialog__actions">
            {receipt ? (
              <>
                <Button
                  disabled={busy}
                  onClick={() => void rollback()}
                  tone="quiet"
                >
                  Undo this edit
                </Button>
                <Button
                  disabled={busy}
                  onClick={() =>
                    onComplete("Existing agent instructions were refreshed.")
                  }
                  tone="primary"
                >
                  Done
                </Button>
              </>
            ) : preview ? (
              <>
                <Button
                  disabled={busy}
                  onClick={() => setPreview(null)}
                  tone="quiet"
                >
                  Back
                </Button>
                <Button
                  disabled={busy}
                  onClick={() => void applyPreview()}
                  tone="primary"
                >
                  {busy ? "Applying…" : "Apply exact diff"}
                </Button>
              </>
            ) : (
              <>
                <Button disabled={busy} onClick={onClose} tone="quiet">
                  Cancel
                </Button>
                <Button
                  disabled={busy || !text.trim()}
                  onClick={() => void makePreview()}
                  tone="primary"
                >
                  {busy ? "Preparing…" : "Preview exact diff"}
                </Button>
              </>
            )}
          </div>
        </Dialog.Content>
      </PageDialogPortal>
    </Dialog.Root>
  );
}

function targetLabel(target: EngineNativeTarget): string {
  return { codex: "Codex", claude: "Claude", copilot: "Copilot" }[target];
}

function nativeSourceStatusLabel(
  status: EngineInstructionSourceSummary["status"],
): string {
  return {
    invalid_encoding: "Invalid encoding",
    outside_boundary: "Outside project",
    ready: "Considered",
    too_large: "Too large",
    unreadable: "Unreadable",
    unsupported: "Unsupported",
  }[status];
}

function nativeSkillStatusLabel(
  status: EngineInstructionSourceSummary["activation_status"],
): string {
  return {
    active: "Active",
    available: "Available",
    disabled: "Disabled",
    not_applicable: "Considered",
    unknown: "Availability unknown",
  }[status];
}

function CoreGroup({
  label,
  description,
  items,
  onEdit,
  onRemove,
  onRevoke,
  readOnly,
  revokeAvailable,
  revokeUnavailableReason,
}: {
  label: string;
  description: string;
  items: CoreItem[];
  onEdit: (item: CoreItem) => void;
  onRemove: (item: CoreItem) => void;
  onRevoke: (item: CoreItem) => void;
  readOnly: boolean;
  revokeAvailable: boolean;
  revokeUnavailableReason: string | null;
}) {
  return (
    <section className="core-group">
      <header className="core-group__heading">
        <h2>{label}</h2>
        <p>{description}</p>
      </header>
      <ul className="core-list">
        {items.map((item) => (
          <li key={item.id}>
            <article className="core-entry">
              <div className="core-entry__copy">
                <strong>{item.title}</strong>
                <p>{item.description}</p>
                <span>
                  {item.scope} · {item.sourceSummary}
                </span>
              </div>
              {readOnly ? (
                <div className="core-entry__actions">
                  <span className="core-entry__governed">Approved</span>
                  <button
                    disabled={!revokeAvailable}
                    onClick={() => onRevoke(item)}
                    title={revokeUnavailableReason ?? undefined}
                    type="button"
                  >
                    Revoke
                  </button>
                </div>
              ) : (
                <div className="core-entry__actions">
                  <button onClick={() => onEdit(item)} type="button">
                    <Pencil aria-hidden="true" size={13} /> Edit
                  </button>
                  <button onClick={() => onRemove(item)} type="button">
                    Remove
                  </button>
                </div>
              )}
            </article>
          </li>
        ))}
      </ul>
    </section>
  );
}

function CoreRevocationDialog({
  item,
  onClose,
  onConfirm,
}: {
  item: CoreItem;
  onClose: () => void;
  onConfirm: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Dialog.Root onOpenChange={(open) => (open ? null : onClose())} open>
      <PageDialogPortal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="core-dialog">
          <Dialog.Title>
            Remove “{item.title}” from saved guidance?
          </Dialog.Title>
          <Dialog.Description>
            Future tasks won’t receive this guidance. Its history remains
            available in Advanced.
          </Dialog.Description>
          <div className="core-dialog__actions">
            <Button disabled={busy} onClick={onClose} tone="quiet">
              Keep it
            </Button>
            <Button
              disabled={busy}
              onClick={() => {
                setBusy(true);
                setError(null);
                void onConfirm()
                  .catch((reason: unknown) =>
                    setError(
                      reason instanceof Error
                        ? reason.message
                        : "Temper could not revoke that adaptation.",
                    ),
                  )
                  .finally(() => setBusy(false));
              }}
              tone="primary"
            >
              Revoke adaptation
            </Button>
          </div>
          {error ? <p role="alert">{error}</p> : null}
        </Dialog.Content>
      </PageDialogPortal>
    </Dialog.Root>
  );
}

export function ModesPage({
  modes,
  nativeRuntime,
  loading,
  error,
  onOpenCore,
  onTaskComplete,
  projects: modeProjects,
  reviewProjects = [],
  runnerReady,
  runnerUnavailableReason = null,
  snapshotDigest,
  instructionEnvironments = [],
  packageReviews = [],
  onPackageDecision,
}: {
  modes: CapabilityModeSummary[];
  nativeRuntime: boolean;
  loading: boolean;
  error: string | null;
  onOpenCore: () => void;
  onTaskComplete: (
    message: string,
    result: EngineTaskResult | null,
  ) => void | Promise<void>;
  projects: Array<{ id: string; label: string }>;
  reviewProjects?: Array<{ id: string; label: string }>;
  runnerReady: boolean;
  runnerUnavailableReason?: string | null;
  snapshotDigest: string | null;
  instructionEnvironments?: EngineInstructionEnvironmentSummary[];
  packageReviews?: PackageReviewItem[];
  onPackageDecision?: (
    item: PackageReviewItem,
    decision: "approved" | "rejected",
    projectIds: string[],
  ) => Promise<void>;
}) {
  const [selected, setSelected] = useState<CapabilityModeSummary | null>(null);
  const modeTrigger = useRef<HTMLButtonElement | null>(null);
  const [packageAction, setPackageAction] = useState<{
    intent: "export-mode" | "import";
    mode?: CapabilityModeSummary;
  } | null>(null);
  const [busyPackageReview, setBusyPackageReview] = useState<string | null>(
    null,
  );
  return (
    <div className="page folio-page modes-page">
      <header className="modes-heading">
        <div>
          <h1>Tools &amp; workflows</h1>
        </div>
      </header>
      <ToolsHubPanel nativeRuntime={nativeRuntime} />
      <div className="modes-section-heading">
        <h2 className="modes-section-title">Saved workflows</h2>
        <Button
          type="button"
          tone="quiet"
          disabled={!nativeRuntime || !snapshotDigest}
          onClick={() => setPackageAction({ intent: "import" })}
        >
          <Upload aria-hidden="true" size={14} /> Import package
        </Button>
      </div>
      {nativeRuntime ? (
        <PackageReviewQueue
          busyReviewId={busyPackageReview}
          items={packageReviews}
          onDecision={async (item, decision, projectIds) => {
            if (!onPackageDecision) return;
            setBusyPackageReview(item.review_id);
            try {
              await onPackageDecision(item, decision, projectIds);
            } finally {
              setBusyPackageReview(null);
            }
          }}
          projects={reviewProjects}
        />
      ) : null}
      {loading ? <LoadingStatus>Loading saved workflows…</LoadingStatus> : null}
      {error ? (
        <div className="modes-empty" role="alert">
          {error}
        </div>
      ) : null}
      <div className="mode-catalog">
        {modes.map((mode) => (
          <article className="mode-row" key={mode.mode_id}>
            <div className="mode-row__copy">
              <h3>{mode.name}</h3>
              <p>{mode.summary}</p>
              <p className="mode-row__meta">
                {mode.source_kind === "imported" ? "Imported" : "Curated"} ·{" "}
                {mode.evaluation_status === "product_evaluated"
                  ? "Tested"
                  : mode.evaluation_status === "failed"
                    ? "Did not pass testing"
                    : mode.evaluation_status === "revoked"
                      ? "Unavailable"
                      : "Evaluation pending"}
                {mode.requested_tools.length > 0 && " · Requests tools"}
                {mode.personalized && (
                  <>
                    {" "}
                    · <span>Personalized</span>
                  </>
                )}
              </p>
            </div>
            <Button
              className="mode-row__action"
              onClick={(event) => {
                modeTrigger.current = event.currentTarget;
                setSelected(mode);
              }}
              type="button"
            >
              View workflow <ArrowRight aria-hidden="true" size={15} />
            </Button>
          </article>
        ))}
      </div>
      {!loading && !error && modes.length === 0 ? (
        <div className="modes-empty">
          No saved workflows yet. Import a package to add a workflow.
        </div>
      ) : null}
      <footer className="mode-footer">
        <p>Saved workflows apply to one task at a time.</p>
        <button onClick={onOpenCore} type="button">
          View personalization <ArrowRight aria-hidden="true" size={14} />
        </button>
      </footer>
      {selected ? (
        <ModeDetailsDialog
          mode={selected}
          nativeRuntime={nativeRuntime}
          onClose={() => setSelected(null)}
          onReturnFocus={() => modeTrigger.current?.focus()}
          onComplete={onTaskComplete}
          onExport={() => {
            setPackageAction({ intent: "export-mode", mode: selected });
            setSelected(null);
          }}
          projects={modeProjects}
          runnerReady={runnerReady}
          runnerUnavailableReason={runnerUnavailableReason}
          snapshotDigest={snapshotDigest}
          instructionEnvironments={instructionEnvironments}
        />
      ) : null}
      {packageAction ? (
        <ShareablePackageDialog
          intent={packageAction.intent}
          mode={packageAction.mode}
          nativeRuntime={nativeRuntime}
          onClose={() => setPackageAction(null)}
          onComplete={(message) => {
            setPackageAction(null);
            void onTaskComplete(message, null);
          }}
          snapshotDigest={snapshotDigest}
        />
      ) : null}
    </div>
  );
}

function ModeDetailsDialog({
  mode,
  nativeRuntime,
  onClose,
  onReturnFocus,
  onComplete,
  onExport,
  projects: modeProjects,
  runnerReady,
  runnerUnavailableReason,
  snapshotDigest,
  instructionEnvironments,
}: {
  mode: CapabilityModeSummary;
  nativeRuntime: boolean;
  onClose: () => void;
  onReturnFocus: () => void;
  onComplete: (
    message: string,
    result: EngineTaskResult | null,
  ) => void | Promise<void>;
  onExport: () => void;
  projects: Array<{ id: string; label: string }>;
  runnerReady: boolean;
  runnerUnavailableReason: string | null;
  snapshotDigest: string | null;
  instructionEnvironments: EngineInstructionEnvironmentSummary[];
}) {
  const [projectId, setProjectId] = useState(modeProjects[0]?.id ?? "");
  const restoreFocus = useRef(true);
  const [task, setTask] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<CuratedModeDetail | null>(null);
  const [preview, setPreview] = useState<ModeActivationPreview | null>(null);
  const canRun = Boolean(
    nativeRuntime &&
    runnerReady &&
    snapshotDigest &&
    projectId &&
    task.trim() &&
    !busy,
  );
  const selectedEnvironment = instructionEnvironments.find(
    (environment) =>
      environment.project_id === projectId && environment.target === "codex",
  );

  useEffect(() => {
    if (!nativeRuntime || mode.source_kind !== "curated") return;
    let active = true;
    void loadCuratedMode(mode.mode_id)
      .then((value) => {
        if (active) setDetail(value);
      })
      .catch(() => {
        if (active) setDetail(null);
      });
    return () => {
      active = false;
    };
  }, [mode.mode_id, mode.source_kind, nativeRuntime]);

  async function createPreview() {
    if (!canRun) return;
    setBusy(true);
    setError(null);
    try {
      setPreview(
        await previewModeActivation(mode.mode_id, projectId, task.trim()),
      );
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Temper could not create a workflow preview.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function startTask() {
    if (!canRun || !snapshotDigest) return;
    setBusy(true);
    setError(null);
    try {
      const result = await runModeTask(
        mode.mode_id,
        projectId,
        task,
        snapshotDigest,
        crypto.randomUUID(),
      );
      await onComplete(
        result.review_available
          ? `${mode.name} finished and was removed. Changes are ready for review.`
          : `${mode.name} finished and was removed.`,
        result,
      );
      onClose();
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Temper could not start the workflow.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog.Root onOpenChange={(open) => (open ? undefined : onClose())} open>
      <PageDialogPortal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content
          className="core-dialog mode-dialog"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            if (restoreFocus.current) onReturnFocus();
          }}
        >
          <Dialog.Close aria-label="Close" className="dialog-close">
            <X size={18} />
          </Dialog.Close>
          <span className="folio-kicker">
            Saved workflow · v{mode.mode_version}
          </span>
          <Dialog.Title>{mode.name}</Dialog.Title>
          <Dialog.Description>{mode.summary}</Dialog.Description>
          <dl className="mode-detail-list">
            <div>
              <dt>Evaluation status</dt>
              <dd>
                {mode.evaluation_status === "product_evaluated"
                  ? "Passed effectiveness testing"
                  : "Reviewed. Comparative testing pending."}
              </dd>
            </div>
            <div>
              <dt>Based on</dt>
              <dd>
                {detail
                  ? detail.sources
                      .map((source) => source.publisher)
                      .join(" and ")
                  : `${mode.source_count} pinned open-source source${mode.source_count === 1 ? "" : "s"}`}
              </dd>
            </div>
            <div>
              <dt>Duration</dt>
              <dd>One task, up to {mode.task_lease_hours} hours</dd>
            </div>
            <div>
              <dt>Instruction formats</dt>
              <dd>{mode.compatible_target_families.join(" and ")}</dd>
            </div>
            <div>
              <dt>Available now</dt>
              <dd>New Codex tasks started by Temper</dd>
            </div>
            <div>
              <dt>Added tools</dt>
              <dd>
                {mode.requested_tools.length
                  ? mode.requested_tools.join(", ")
                  : "None"}
              </dd>
            </div>
            <div>
              <dt>Safety and format checks</dt>
              <dd>
                {mode.evaluation_valid
                  ? `${mode.evaluation_case_count} checks passed`
                  : "Needs attention"}
              </dd>
            </div>
            <div>
              <dt>Effectiveness</dt>
              <dd>
                {mode.effectiveness_evaluated
                  ? "Passed comparative testing"
                  : "Comparative evaluation pending"}
              </dd>
            </div>
            <div>
              <dt>Personalization</dt>
              <dd>
                {mode.personalized
                  ? "Uses your approved guidance for this task"
                  : "Uses the workflow’s default guidance"}
              </dd>
            </div>
          </dl>
          {detail ? (
            <section className="mode-source-list" aria-label="Workflow sources">
              <h3>Reviewed sources</h3>
              {detail.sources.map((source) => (
                <div key={`${source.repository_url}:${source.source_path}`}>
                  <span>{source.publisher}</span>
                  <small>
                    {source.repository_url.replace("https://github.com/", "")} ·{" "}
                    {source.license_spdx} · {source.commit_sha.slice(0, 8)}
                    {source.excluded_resource_count
                      ? ` · ${source.excluded_resource_count} executable resource excluded`
                      : ""}
                  </small>
                </div>
              ))}
            </section>
          ) : null}
          <div className="mode-authority-note">
            Your request, project rules, security settings and saved guidance
            take precedence over workflow defaults.
          </div>
          {projectId ? (
            <details className="learning-details">
              <summary>Instruction checks</summary>
              <dl className="mode-detail-list" aria-label="Instruction checks">
                <div>
                  <dt>Existing setup considered</dt>
                  <dd>
                    {selectedEnvironment
                      ? `${selectedEnvironment.source_count} source${selectedEnvironment.source_count === 1 ? "" : "s"}`
                      : "Not analyzed yet"}
                  </dd>
                </div>
                <div>
                  <dt>Workflow instructions</dt>
                  <dd>
                    {mode.projection_utf8_bytes} bytes before duplicate
                    instructions are removed
                  </dd>
                </div>
                <div>
                  <dt>Blocking conflicts</dt>
                  <dd>
                    {selectedEnvironment?.blocking_conflict_count ?? "Unknown"}
                  </dd>
                </div>
              </dl>
            </details>
          ) : null}
          <div className="mode-task-form">
            <div className="core-field">
              <span>Project</span>
              <TemperSelect
                ariaLabel="Project"
                disabled={!nativeRuntime}
                onValueChange={(value) => {
                  setProjectId(value);
                  setPreview(null);
                }}
                options={modeProjects.map((project) => ({
                  label: project.label,
                  value: project.id,
                }))}
                portalled={false}
                value={projectId}
              />
            </div>
            <label className="core-field">
              <span>Task</span>
              <textarea
                disabled={!nativeRuntime}
                onChange={(event) => {
                  setTask(event.target.value);
                  setPreview(null);
                }}
                placeholder="Describe the task you want Codex to run"
                rows={3}
                value={task}
              />
            </label>
            <p>
              {runnerReady
                ? "Runs in a separate Codex session using your connected account."
                : (runnerUnavailableReason ??
                  "This workflow is unavailable right now.")}{" "}
              Review any changes before applying them. The workflow ends when
              the task finishes or fails.
            </p>
            {error ? (
              <div className="portability-error" role="alert">
                {error}
              </div>
            ) : null}
            {preview ? (
              <div className="mode-activation-preview" role="status">
                <strong>Ready for one task</strong>
                <span>
                  {preview.included_clause_count} clauses ·{" "}
                  {preview.projection_utf8_bytes} bytes · {preview.source_count}{" "}
                  sources
                </span>
                <span>
                  {preview.requested_tools.length === 0
                    ? "No tools or permissions are added."
                    : "This workflow requests additional tools."}
                </span>
              </div>
            ) : null}
          </div>
          <div className="core-dialog__actions">
            <Button onClick={onClose} tone="quiet">
              Close
            </Button>
            <Button
              disabled={!nativeRuntime}
              onClick={() => {
                restoreFocus.current = false;
                onExport();
              }}
              tone="quiet"
            >
              <Share2 aria-hidden="true" size={14} /> Export package
            </Button>
            <Button
              disabled={!canRun}
              onClick={preview ? startTask : createPreview}
              tone="primary"
            >
              {busy
                ? "Running task…"
                : nativeRuntime
                  ? runnerReady
                    ? preview
                      ? "Confirm and run"
                      : "Preview for this task"
                    : "Unavailable"
                  : "Available in desktop app"}
            </Button>
          </div>
        </Dialog.Content>
      </PageDialogPortal>
    </Dialog.Root>
  );
}

function CoreItemDialog({
  availableScopes,
  item,
  onClose,
  onSave,
}: {
  availableScopes: ProjectName[];
  item: CoreItem;
  onClose: () => void;
  onSave: (item: CoreItem) => void;
}) {
  const [title, setTitle] = useState(item.title);
  const [description, setDescription] = useState(item.description);
  const [scope, setScope] = useState<CoreItem["scope"]>(item.scope);
  const allowedScopes: CoreItem["scope"][] =
    item.scope === "Everywhere"
      ? ["Everywhere", ...availableScopes]
      : [item.scope];
  const canSave = Boolean(title.trim() && description.trim());
  return (
    <Dialog.Root onOpenChange={(open) => (open ? undefined : onClose())} open>
      <PageDialogPortal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="core-dialog">
          <Dialog.Close aria-label="Close" className="dialog-close">
            <X size={18} />
          </Dialog.Close>
          <span className="folio-kicker">{item.kind}</span>
          <Dialog.Title>Edit {item.title}</Dialog.Title>
          <Dialog.Description>
            Change the wording or narrow where this can be used.
          </Dialog.Description>
          <p className="dialog-preview-note">
            Sample preview · these edits do not change local Temper state.
          </p>
          <label className="core-field">
            <span>Name</span>
            <input
              onChange={(event) => setTitle(event.target.value)}
              required
              value={title}
            />
          </label>
          <label className="core-field">
            <span>What it means</span>
            <textarea
              onChange={(event) => setDescription(event.target.value)}
              required
              rows={3}
              value={description}
            />
          </label>
          <div className="core-field">
            <span>Use in</span>
            <TemperSelect
              ariaLabel="Use in"
              onValueChange={setScope}
              options={allowedScopes.map((allowedScope) => ({
                label: allowedScope,
                value: allowedScope,
              }))}
              portalled={false}
              value={scope}
            />
          </div>
          <div className="core-source-note">
            <span>Based on</span>
            <strong>{item.sourceSummary}</strong>
          </div>
          <div className="core-dialog__actions">
            <Button onClick={onClose} tone="quiet">
              Cancel
            </Button>
            <Button
              disabled={!canSave}
              onClick={() =>
                onSave({
                  ...item,
                  title: title.trim(),
                  description: description.trim(),
                  scope,
                })
              }
              tone="primary"
            >
              Save changes
            </Button>
          </div>
        </Dialog.Content>
      </PageDialogPortal>
    </Dialog.Root>
  );
}

export function ConnectionsPage({
  nativeRuntime = false,
  liveConnections,
  liveProjects,
  instructionEnvironments = [],
  previewConnections = [],
  previewProjects = [],
  registrationAvailable = true,
  registrationUnavailableReason = null,
  snapshotDigest = null,
  onProjectRegistered,
  onInstructionChanged,
  onRefresh,
}: {
  nativeRuntime?: boolean;
  liveConnections?: EngineAgentConnection[];
  liveProjects?: EngineProject[];
  instructionEnvironments?: EngineInstructionEnvironmentSummary[];
  previewConnections?: AgentConnection[];
  previewProjects?: RegisteredProject[];
  registrationAvailable?: boolean;
  registrationUnavailableReason?: string | null;
  snapshotDigest?: string | null;
  onProjectRegistered?: (message: string) => void | Promise<void>;
  onInstructionChanged?: (message: string) => void | Promise<void>;
  onRefresh?: () => Promise<void>;
}) {
  const connectionTrigger = useRef<HTMLButtonElement | null>(null);
  const projectTrigger = useRef<HTMLButtonElement | null>(null);
  const [selectedConnection, setSelectedConnection] =
    useState<AgentConnection | null>(null);
  const [projectPreview, setProjectPreview] =
    useState<EngineProjectPreview | null>(null);
  const [projectBusy, setProjectBusy] = useState(false);
  const [projectMessage, setProjectMessage] = useState<string | null>(null);
  const [refreshBusy, setRefreshBusy] = useState(false);
  const [projectQuery, setProjectQuery] = useState("");
  const shownConnections: AgentConnection[] = liveConnections
    ? liveConnections.map((connection) => ({
        authDescription: connection.status_summary,
        costDescription: connection.cost_posture,
        id: connection.agent_id,
        name: connection.display_name,
        availableActions: connection.available_actions,
        sourceCapability:
          connection.agent_id === "codex"
            ? connection.learning_capability.replace(
                /^Learning\b/,
                "Reviewed-suggestion capture",
              )
            : connection.learning_capability,
        status:
          connection.installation_state === "not_installed"
            ? "not_installed"
            : connection.integration_state === "connected"
              ? "connected"
              : connection.integration_state === "attention"
                ? "attention"
                : connection.conformance_state === "update_required"
                  ? "update_required"
                  : connection.authentication_state === "signed_out"
                    ? "signed_out"
                    : connection.integration_state === "available"
                      ? "available"
                      : connection.agent_id === "codex" &&
                          connection.authentication_state === "signed_in" &&
                          connection.conformance_state === "compatible"
                        ? "connected"
                        : "attention",
        targetCapability: connection.delivery_capability,
      }))
    : previewConnections;
  const shownProjects = liveProjects
    ? liveProjects.map((project) => ({
        connectedAgents: project.task_runner_enabled ? ["Managed tasks"] : [],
        id: project.project_id,
        name: project.display_name,
        pathLabel: "New work only",
      }))
    : previewProjects;

  const filteredProjects = shownProjects.filter((project) =>
    (project.name + " " + project.pathLabel)
      .toLocaleLowerCase()
      .includes(projectQuery.trim().toLocaleLowerCase()),
  );

  function environmentStatus(projectId: string) {
    const environments = instructionEnvironments.filter(
      (environment) => environment.project_id === projectId,
    );
    const sourceCount = environments.reduce(
      (total, environment) => total + environment.source_count,
      0,
    );
    const skillCount = environments.reduce(
      (total, environment) => total + environment.skill_count,
      0,
    );
    const status = worstInstructionEnvironmentStatus(environments);
    const semanticStatus = worstSemanticAnalysisStatus(environments);
    return {
      semanticStatus,
      skillCount,
      sourceCount,
      status,
      checked: environments.length > 0,
    };
  }

  async function chooseProject() {
    setProjectBusy(true);
    setProjectMessage(null);
    try {
      setProjectPreview(await previewProjectRegistration());
    } catch (error: unknown) {
      setProjectMessage(
        error instanceof Error ? error.message : "Nothing was selected.",
      );
    } finally {
      setProjectBusy(false);
    }
  }

  async function confirmProject() {
    if (!projectPreview || !snapshotDigest) return;
    setProjectBusy(true);
    setProjectMessage(null);
    try {
      await registerProject(
        projectPreview.preview_token,
        snapshotDigest,
        crypto.randomUUID(),
      );
      setProjectPreview(null);
      await onProjectRegistered?.(
        `${projectPreview.display_name} is now eligible for new work.`,
      );
    } catch (error: unknown) {
      setProjectMessage(
        error instanceof Error
          ? error.message
          : "Temper could not register that project.",
      );
    } finally {
      setProjectBusy(false);
    }
  }
  return (
    <div className="page">
      <header className="today-learning-heading">
        <div>
          <h1>Connections</h1>
          <p>Manage the agents and projects that Temper can access.</p>
        </div>
      </header>
      {nativeRuntime ? (
        <div className="connections-toolbar">
          <Button
            disabled={refreshBusy}
            onClick={() => {
              if (!onRefresh) return;
              setRefreshBusy(true);
              setProjectMessage(null);
              void onRefresh()
                .catch((error: unknown) =>
                  setProjectMessage(
                    error instanceof Error
                      ? error.message
                      : "Temper could not refresh connection status.",
                  ),
                )
                .finally(() => setRefreshBusy(false));
            }}
            tone="quiet"
          >
            {refreshBusy ? "Checking…" : "Refresh status"}
          </Button>
        </div>
      ) : null}
      {!nativeRuntime ? (
        <div className="native-action-note" role="note">
          <Laptop aria-hidden="true" size={16} />
          <span>
            Use the desktop app to connect agents and add project folders.
          </span>
        </div>
      ) : null}
      <div className="subsection-heading">
        <div>
          <h2>Agent accounts</h2>
          {nativeRuntime ? (
            <p>
              Connect an agent to run workflows and use guidance you’ve
              approved.
            </p>
          ) : null}
        </div>
      </div>
      <section className="connection-list" aria-label="Agent accounts">
        {shownConnections.map((connection) => (
          <article className="connection-card" key={connection.id}>
            <div className={`agent-logo agent-logo--${connection.id}`}>
              <AgentBrandMark agent={connection.id} />
            </div>
            <div className="connection-main">
              <div className="connection-title">
                <h3>{connection.name}</h3>
                <StatusPill
                  tone={
                    connection.status === "connected" ? "positive" : "neutral"
                  }
                >
                  {connectionStatusLabel(connection.status)}
                </StatusPill>
              </div>
              <p>
                {connection.authDescription} · {connection.costDescription}
              </p>
              <div className="capability-list">
                <div>
                  {connection.status === "connected" ? (
                    <CheckCircle2 size={15} />
                  ) : (
                    <Info size={15} />
                  )}
                  <span>{connection.sourceCapability}</span>
                </div>
                <div>
                  {connection.status === "connected" ? (
                    <CheckCircle2 size={15} />
                  ) : (
                    <Info size={15} />
                  )}
                  <span>{connection.targetCapability}</span>
                </div>
              </div>
            </div>
            <Button
              onClick={(event) => {
                connectionTrigger.current = event.currentTarget;
                setSelectedConnection(connection);
              }}
              tone="quiet"
            >
              View details
            </Button>
          </article>
        ))}
      </section>
      {nativeRuntime && <LearningRepositories />}
      <section className="projects-section" aria-label="Task projects">
        <div className="subsection-heading">
          <div>
            <h2>{nativeRuntime ? "Task projects" : "Registered projects"}</h2>
            <p>Choose the folders where Temper can run saved workflows.</p>
          </div>
          <Button
            disabled={
              !nativeRuntime ||
              !snapshotDigest ||
              projectBusy ||
              !registrationAvailable
            }
            icon={<Plus size={16} />}
            onClick={(event) => {
              projectTrigger.current = event.currentTarget;
              void chooseProject();
            }}
            title={registrationUnavailableReason ?? undefined}
          >
            {nativeRuntime ? "Add task project" : "Add project"}
          </Button>
        </div>
        {nativeRuntime &&
        !registrationAvailable &&
        registrationUnavailableReason ? (
          <p className="setup-state-message">{registrationUnavailableReason}</p>
        ) : null}
        {shownProjects.length > 0 && (
          <div className="project-search">
            <label htmlFor="project-search">Find a project</label>
            <input
              id="project-search"
              type="search"
              value={projectQuery}
              onChange={(event) => setProjectQuery(event.target.value)}
              placeholder="Search projects"
            />
          </div>
        )}
        <div className="project-list">
          {filteredProjects.map((project) => {
            const environment = environmentStatus(project.id);
            return (
              <div className="project-row" key={project.id}>
                <div className="project-monogram">{project.name[0]}</div>
                <div className="project-row__copy">
                  <strong>{project.name}</strong>
                  <span>{project.pathLabel}</span>
                  {nativeRuntime ? (
                    <span className="project-row__environment">
                      {!environment.checked
                        ? "Agent instructions not checked"
                        : environment.sourceCount
                          ? `${environment.sourceCount} instruction source${environment.sourceCount === 1 ? "" : "s"} · ${environment.skillCount} skill${environment.skillCount === 1 ? "" : "s"}`
                          : "No supported agent instructions detected"}
                    </span>
                  ) : null}
                </div>
                <div className="project-row__status">
                  {nativeRuntime ? (
                    <StatusPill
                      tone={
                        environment.status === "understood"
                          ? "positive"
                          : "neutral"
                      }
                    >
                      {!environment.checked
                        ? "Not checked"
                        : environment.status === "understood" &&
                            environment.semanticStatus !== "current"
                          ? semanticAnalysisStatusLabel(
                              environment.semanticStatus,
                            )
                          : instructionEnvironmentStatusLabel(
                              environment.status,
                            )}
                    </StatusPill>
                  ) : null}
                  <span className="agent-chip">
                    {project.connectedAgents.length
                      ? project.connectedAgents.join(", ")
                      : "Task runner off"}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
        {filteredProjects.length === 0 && (
          <p className="project-empty">
            {shownProjects.length === 0
              ? "No task projects yet. Add a folder to run a saved workflow."
              : "No projects match your search."}
          </p>
        )}
      </section>
      {selectedConnection ? (
        <ConnectionDetailsDialog
          connection={selectedConnection}
          instructionEnvironments={instructionEnvironments.filter(
            (environment) => environment.target === selectedConnection.id,
          )}
          nativeRuntime={nativeRuntime}
          projects={liveProjects ?? []}
          onClose={() => setSelectedConnection(null)}
          onInstructionChanged={onInstructionChanged}
          onCloseAutoFocus={(event) =>
            restorePageDialogFocus(event, connectionTrigger.current)
          }
          snapshotDigest={snapshotDigest}
        />
      ) : null}
      {projectPreview ? (
        <Dialog.Root
          onOpenChange={(open) => (open ? undefined : setProjectPreview(null))}
          open
        >
          <PageDialogPortal>
            <Dialog.Overlay className="dialog-overlay" />
            <Dialog.Content
              className="core-dialog connection-dialog"
              onCloseAutoFocus={(event) =>
                restorePageDialogFocus(event, projectTrigger.current)
              }
            >
              <Dialog.Close aria-label="Close" className="dialog-close">
                <X size={18} />
              </Dialog.Close>
              <span className="folio-kicker">Prospective project</span>
              <Dialog.Title>{projectPreview.display_name}</Dialog.Title>
              <Dialog.Description>
                Only tasks created after you register this project can become
                eligible. Temper will not modify its repository or existing
                tasks.
              </Dialog.Description>
              {projectMessage ? <p role="alert">{projectMessage}</p> : null}
              <div className="core-dialog__actions">
                <Button
                  disabled={projectBusy}
                  onClick={() => setProjectPreview(null)}
                  tone="quiet"
                >
                  Cancel
                </Button>
                <Button
                  disabled={projectBusy}
                  onClick={confirmProject}
                  tone="primary"
                >
                  {projectBusy ? "Registering…" : "Register new work"}
                </Button>
              </div>
            </Dialog.Content>
          </PageDialogPortal>
        </Dialog.Root>
      ) : null}
      {projectMessage && !projectPreview ? (
        <p className="connection-dialog-note" role="alert">
          {projectMessage}
        </p>
      ) : null}
    </div>
  );
}

function ConnectionDetailsDialog({
  connection,
  instructionEnvironments,
  nativeRuntime,
  projects,
  onClose,
  onCloseAutoFocus,
  onInstructionChanged,
  snapshotDigest,
}: {
  connection: AgentConnection;
  instructionEnvironments: EngineInstructionEnvironmentSummary[];
  nativeRuntime: boolean;
  projects: EngineProject[];
  onClose: () => void;
  onCloseAutoFocus: (event: Event) => void;
  onInstructionChanged?: (message: string) => void | Promise<void>;
  snapshotDigest: string | null;
}) {
  const [preview, setPreview] = useState<EngineInstructionGlobalPreview | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connectionPreview, setConnectionPreview] =
    useState<EngineConnectionPreview | null>(null);
  const [connectionConfirmed, setConnectionConfirmed] = useState(false);
  const connectionHookPreview = connectionPreview
    ? "settings" in connectionPreview
      ? connectionPreview.settings
      : connectionPreview.hook_file
    : null;
  const [targetPreview, setTargetPreview] =
    useState<EngineTargetAuthorizationPreview | null>(null);
  const [selectedTargetRefs, setSelectedTargetRefs] = useState<Set<string>>(
    new Set(),
  );
  const [targetConfirmed, setTargetConfirmed] = useState(false);
  const target: EngineNativeTarget = connection.id;
  const personalSetupEnabled = instructionEnvironments.some(
    (environment) => environment.global_sources_enabled,
  );
  const sourceCount = instructionEnvironments.reduce(
    (total, environment) => total + environment.source_count,
    0,
  );
  const skillCount = instructionEnvironments.reduce(
    (total, environment) => total + environment.skill_count,
    0,
  );
  const lastAnalyzed = instructionEnvironments
    .map((environment) => environment.last_analyzed_at)
    .sort()
    .at(-1);
  const semanticStatus = worstSemanticAnalysisStatus(instructionEnvironments);

  async function analyzeExistingSetup() {
    if (!snapshotDigest || instructionEnvironments.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      for (const environment of instructionEnvironments) {
        await analyzeInstructionEnvironment(
          environment.project_id,
          environment.target,
          snapshotDigest,
          crypto.randomUUID(),
        );
      }
      await onInstructionChanged?.(`${connection.name} instructions checked.`);
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Temper could not analyze that existing setup.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function inspectPersonalSetup() {
    setBusy(true);
    setError(null);
    try {
      setPreview(await previewPersonalInstructionSetup(target));
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Temper could not inspect that personal setup.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function enablePersonalSetup() {
    if (!preview || !snapshotDigest) return;
    setBusy(true);
    setError(null);
    try {
      await enablePersonalInstructionSetup(
        preview.preview_token,
        preview.target,
        snapshotDigest,
        crypto.randomUUID(),
      );
      setPreview(null);
      await onInstructionChanged?.(
        `${connection.name} personal instructions are now considered as observed context.`,
      );
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Temper could not enable personal-setup inspection.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function disablePersonalSetup() {
    if (!snapshotDigest) return;
    setBusy(true);
    setError(null);
    try {
      await disablePersonalInstructionSetup(
        target,
        snapshotDigest,
        crypto.randomUUID(),
      );
      await onInstructionChanged?.(
        `${connection.name} personal instructions are no longer inspected.`,
      );
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Temper could not disable personal-setup inspection.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function previewConnectionChange(operation: "connect" | "disconnect") {
    setBusy(true);
    setError(null);
    setConnectionConfirmed(false);
    try {
      setConnectionPreview(
        connection.id === "copilot"
          ? await previewCopilotConnection(operation)
          : await previewClaudeConnection(operation),
      );
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : `Temper could not preview that ${connection.name} connection change.`,
      );
    } finally {
      setBusy(false);
    }
  }

  async function confirmConnectionChange() {
    if (!connectionPreview || !snapshotDigest || !connectionConfirmed) return;
    setBusy(true);
    setError(null);
    try {
      const receipt =
        connection.id === "copilot" && "hook_file" in connectionPreview
          ? await applyCopilotConnection(
              connectionPreview,
              snapshotDigest,
              crypto.randomUUID(),
            )
          : "settings" in connectionPreview
            ? await applyClaudeConnection(
                connectionPreview,
                snapshotDigest,
                crypto.randomUUID(),
              )
            : null;
      if (!receipt)
        throw new Error("The connection preview no longer matches this agent.");
      setConnectionPreview(null);
      await onInstructionChanged?.(
        receipt.operation === "connect"
          ? `${connection.name} is connected for ${receipt.project_count} registered project${receipt.project_count === 1 ? "" : "s"}.`
          : `${connection.name} is disconnected. Temper-owned hook entries were removed.`,
      );
      onClose();
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : `Temper could not apply that ${connection.name} connection change.`,
      );
    } finally {
      setBusy(false);
    }
  }

  async function reviewPortableCore(projectId: string) {
    setBusy(true);
    setError(null);
    setTargetConfirmed(false);
    try {
      const result = await previewTargetAuthorization(
        projectId,
        connection.id === "copilot" ? "copilot-cli" : "claude-code",
      );
      setTargetPreview(result);
      setSelectedTargetRefs(
        new Set(result.currently_authorized_artifact_refs.map(artifactRefKey)),
      );
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : `Temper could not preview saved guidance for ${connection.name}.`,
      );
    } finally {
      setBusy(false);
    }
  }

  async function confirmPortableCore() {
    if (!targetPreview || !snapshotDigest || !targetConfirmed) return;
    setBusy(true);
    setError(null);
    try {
      const selected = targetPreview.items
        .filter(
          (item) =>
            !item.already_compatible &&
            selectedTargetRefs.has(artifactRefKey(item.artifact_ref)),
        )
        .map((item) => item.artifact_ref);
      const receipt = await applyTargetAuthorization(
        targetPreview,
        selected,
        snapshotDigest,
        crypto.randomUUID(),
      );
      setTargetPreview(null);
      await onInstructionChanged?.(
        receipt.decision === "authorize"
          ? `${receipt.authorized_artifact_count} saved item${receipt.authorized_artifact_count === 1 ? " is" : "s are"} now approved for ${connection.name} in this project.`
          : `${connection.name} can no longer use that guidance in this project.`,
      );
      onClose();
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Temper could not update guidance permissions.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog.Root onOpenChange={(open) => (open ? undefined : onClose())} open>
      <PageDialogPortal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content
          className="core-dialog connection-dialog"
          onCloseAutoFocus={onCloseAutoFocus}
        >
          <Dialog.Close aria-label="Close" className="dialog-close">
            <X size={18} />
          </Dialog.Close>
          <span className="folio-kicker">
            {connectionStatusLabel(connection.status)} agent
          </span>
          <Dialog.Title>{connection.name}</Dialog.Title>
          <Dialog.Description>
            {connection.authDescription}. {connection.costDescription}.
          </Dialog.Description>
          <dl className="connection-detail-list">
            <div>
              <dt>{nativeRuntime ? "Reviewed suggestions" : "Learning"}</dt>
              <dd>{connection.sourceCapability}</dd>
            </div>
            <div>
              <dt>{nativeRuntime ? "Guidance and workflows" : "Delivery"}</dt>
              <dd>{connection.targetCapability}</dd>
            </div>
            {nativeRuntime ? (
              <>
                <div>
                  <dt>Existing setup</dt>
                  <dd>
                    {sourceCount} supported source{sourceCount === 1 ? "" : "s"}
                    ; {skillCount} skill{skillCount === 1 ? "" : "s"}
                  </dd>
                </div>
                <div>
                  <dt>Last checked</dt>
                  <dd>
                    {lastAnalyzed
                      ? formatInstructionCheckTime(lastAnalyzed)
                      : "Not checked"}
                  </dd>
                </div>
                <div>
                  <dt>Semantic comparison</dt>
                  <dd>{semanticAnalysisStatusLabel(semanticStatus)}</dd>
                </div>
              </>
            ) : null}
          </dl>
          <p className="connection-dialog-note">
            {connection.id === "claude"
              ? connection.status === "connected"
                ? "The local hook is active only in registered projects. Connecting Temper does not call Claude; ordinary Claude Code usage remains provider-billed."
                : "Detection alone does not authorize capture or delivery. Connecting changes only Temper-owned entries in your Claude user settings and makes no provider call."
              : connection.id === "copilot"
                ? connection.status === "connected"
                  ? "The local hook delivers only signed cached context in registered Copilot CLI projects. Temper does not capture Copilot prompts in this release."
                  : "Temper understands supported Copilot instruction files. Direct delivery is available only through an explicit Copilot CLI hook; other Copilot surfaces require a reviewed file change."
                : "This connection serves reviewed suggestions and managed tasks. Ordinary Codex chat learning has separate permissions and compatibility checks, shown under Chat learning in Connections."}
          </p>
          {nativeRuntime &&
          (connection.id === "claude" || connection.id === "copilot") ? (
            <section
              aria-labelledby="agent-connection-title"
              className="claude-connection"
            >
              <div>
                <h3 id="agent-connection-title">Temper connection</h3>
                <p>
                  Review the exact local change before anything is installed or
                  removed.
                </p>
              </div>
              {connectionPreview ? (
                <div className="claude-connection__preview">
                  <strong>
                    {connectionPreview.operation === "connect"
                      ? "Connect registered projects"
                      : "Disconnect Claude Code"}
                  </strong>
                  <span>
                    {connectionPreview.project_ids.length} registered project
                    {connectionPreview.project_ids.length === 1 ? "" : "s"} · no
                    provider call
                  </span>
                  <span>
                    {connectionPreview.operation === "connect"
                      ? `Local consent ends ${new Date(connectionPreview.consent_expires_at).toLocaleDateString()}.`
                      : "Only Temper-owned hook entries will be removed."}
                  </span>
                  <details>
                    <summary>Show exact hook change</summary>
                    <pre>{connectionHookPreview?.redacted_diff}</pre>
                  </details>
                  <label className="connection-confirmation">
                    <input
                      checked={connectionConfirmed}
                      onChange={(event) =>
                        setConnectionConfirmed(event.target.checked)
                      }
                      type="checkbox"
                    />
                    <span>
                      {connectionPreview.operation === "connect"
                        ? connection.id === "copilot"
                          ? "Allow Temper to deliver approved adaptations in Copilot CLI for these projects for 30 days. Copilot prompts are not stored."
                          : "Allow Temper to capture authorized prompts and deliver approved adaptations in these projects for 30 days."
                        : `Remove Temper’s ${connection.name} connection now.`}
                    </span>
                  </label>
                  <div className="personal-setup__actions">
                    <Button
                      disabled={busy}
                      onClick={() => setConnectionPreview(null)}
                      tone="quiet"
                    >
                      Cancel
                    </Button>
                    <Button
                      disabled={busy || !connectionConfirmed}
                      onClick={() => void confirmConnectionChange()}
                      tone="primary"
                    >
                      {busy
                        ? "Applying…"
                        : connectionPreview.operation === "connect"
                          ? `Connect ${connection.name}`
                          : "Disconnect"}
                    </Button>
                  </div>
                </div>
              ) : connection.availableActions?.includes("connect") ? (
                <Button
                  disabled={busy || !snapshotDigest}
                  onClick={() => void previewConnectionChange("connect")}
                  tone="primary"
                >
                  {busy ? "Preparing…" : "Review connection"}
                </Button>
              ) : connection.availableActions?.includes("disconnect") ? (
                <Button
                  disabled={busy || !snapshotDigest}
                  onClick={() => void previewConnectionChange("disconnect")}
                  tone="quiet"
                >
                  {busy ? "Preparing…" : `Disconnect ${connection.name}`}
                </Button>
              ) : (
                <p className="connection-dialog-note">
                  No connection action is available in the current state.
                </p>
              )}
            </section>
          ) : null}
          {nativeRuntime &&
          (connection.id === "claude" || connection.id === "copilot") &&
          connection.status === "connected" &&
          projects.length ? (
            <section
              aria-labelledby="portable-core-title"
              className="claude-connection portable-core"
            >
              <div>
                <h3 id="portable-core-title">Share approved guidance</h3>
                <p>
                  Choose which already approved behaviors may also guide{" "}
                  {connection.name}. New learning stays unavailable there until
                  you review it.
                </p>
              </div>
              {targetPreview ? (
                <div className="claude-connection__preview portable-core__preview">
                  <strong>
                    {projects.find(
                      (project) =>
                        project.project_id === targetPreview.project_id,
                    )?.display_name ?? "Selected project"}
                  </strong>
                  {targetPreview.items.length ? (
                    <div className="portable-core__items">
                      {targetPreview.items.map((item, index) => {
                        const key = artifactRefKey(item.artifact_ref);
                        const inputId = `portable-core-item-${index}`;
                        return (
                          <div className="portable-core__item" key={key}>
                            <input
                              checked={
                                item.already_compatible ||
                                selectedTargetRefs.has(key)
                              }
                              id={inputId}
                              disabled={item.already_compatible}
                              onChange={(event) => {
                                setTargetConfirmed(false);
                                setSelectedTargetRefs((current) => {
                                  const next = new Set(current);
                                  if (event.target.checked) next.add(key);
                                  else next.delete(key);
                                  return next;
                                });
                              }}
                              type="checkbox"
                            />
                            <label htmlFor={inputId}>
                              <b>{item.behavior_summary}</b>
                              <small>
                                {item.scope_summary}
                                {item.already_compatible
                                  ? " · already compatible"
                                  : " · needs your approval"}
                              </small>
                            </label>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <span>No approved guidance applies to this project.</span>
                  )}
                  <label className="connection-confirmation">
                    <input
                      checked={targetConfirmed}
                      onChange={(event) =>
                        setTargetConfirmed(event.target.checked)
                      }
                      type="checkbox"
                    />
                    <span>
                      Allow {connection.name} to use only the selected guidance
                      in this project for 30 days.
                    </span>
                  </label>
                  <div className="personal-setup__actions">
                    <Button
                      disabled={busy}
                      onClick={() => setTargetPreview(null)}
                      tone="quiet"
                    >
                      Cancel
                    </Button>
                    <Button
                      disabled={busy || !targetConfirmed}
                      onClick={() => void confirmPortableCore()}
                      tone="primary"
                    >
                      {busy ? "Applying…" : "Apply selection"}
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="portable-core__projects">
                  {projects.map((project) => (
                    <div key={project.project_id}>
                      <span>{project.display_name}</span>
                      <Button
                        disabled={busy || !snapshotDigest}
                        onClick={() =>
                          void reviewPortableCore(project.project_id)
                        }
                        tone="quiet"
                      >
                        Review guidance
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </section>
          ) : null}
          {nativeRuntime && instructionEnvironments.length ? (
            <div className="personal-setup__actions">
              <Button
                disabled={busy || !snapshotDigest}
                onClick={() => void analyzeExistingSetup()}
                tone="quiet"
              >
                {busy ? "Analyzing…" : "Analyze existing setup"}
              </Button>
            </div>
          ) : null}
          {nativeRuntime ? (
            <section
              className="personal-setup"
              aria-labelledby="personal-setup-title"
            >
              <div>
                <h3 id="personal-setup-title">Personal agent setup</h3>
                <p>
                  Optional. Temper reads only the folder you choose and keeps
                  its contents as observed context. This does not approve new
                  learning or modify any files.
                </p>
              </div>
              {preview ? (
                <div className="personal-setup__preview">
                  <strong>Ready to inspect</strong>
                  <span>{preview.categories.join(" · ")}</span>
                  <span>
                    {preview.source_count} supported source
                    {preview.source_count === 1 ? "" : "s"} ·{" "}
                    {preview.skill_count} skill
                    {preview.skill_count === 1 ? "" : "s"}
                  </span>
                </div>
              ) : null}
              {error ? <p role="alert">{error}</p> : null}
              <div className="personal-setup__actions">
                {personalSetupEnabled ? (
                  <Button
                    disabled={busy || !snapshotDigest}
                    onClick={() => void disablePersonalSetup()}
                    tone="quiet"
                  >
                    {busy ? "Updating…" : "Stop inspecting"}
                  </Button>
                ) : preview ? (
                  <>
                    <Button
                      disabled={busy}
                      onClick={() => setPreview(null)}
                      tone="quiet"
                    >
                      Cancel
                    </Button>
                    <Button
                      disabled={busy || !snapshotDigest}
                      onClick={() => void enablePersonalSetup()}
                      tone="primary"
                    >
                      {busy ? "Enabling…" : "Enable read-only inspection"}
                    </Button>
                  </>
                ) : (
                  <Button
                    disabled={busy || !snapshotDigest}
                    onClick={() => void inspectPersonalSetup()}
                    tone="quiet"
                  >
                    {busy ? "Opening…" : "Inspect personal setup"}
                  </Button>
                )}
              </div>
            </section>
          ) : null}
          <div className="core-dialog__actions">
            <Button onClick={onClose} tone="primary">
              Done
            </Button>
          </div>
        </Dialog.Content>
      </PageDialogPortal>
    </Dialog.Root>
  );
}

function worstInstructionEnvironmentStatus(
  environments: EngineInstructionEnvironmentSummary[],
): EngineInstructionEnvironmentSummary["status"] {
  const ranking: Record<EngineInstructionEnvironmentSummary["status"], number> =
    {
      conflicting: 3,
      incomplete: 2,
      changed: 1,
      understood: 0,
    };
  return environments.reduce<EngineInstructionEnvironmentSummary["status"]>(
    (worst, environment) =>
      ranking[environment.status] > ranking[worst] ? environment.status : worst,
    "understood",
  );
}

function instructionEnvironmentStatusLabel(
  status: EngineInstructionEnvironmentSummary["status"],
): string {
  return {
    changed: "Changed · review needed",
    conflicting: "Conflict detected",
    incomplete: "Incomplete",
    understood: "Understood",
  }[status];
}

function worstSemanticAnalysisStatus(
  environments: EngineInstructionEnvironmentSummary[],
): EngineInstructionEnvironmentSummary["semantic_analysis_status"] {
  const ranking: Record<
    EngineInstructionEnvironmentSummary["semantic_analysis_status"],
    number
  > = {
    stale: 3,
    not_requested: 2,
    unavailable: 1,
    current: 0,
  };
  return environments.reduce<
    EngineInstructionEnvironmentSummary["semantic_analysis_status"]
  >(
    (worst, environment) =>
      ranking[environment.semantic_analysis_status] > ranking[worst]
        ? environment.semantic_analysis_status
        : worst,
    "current",
  );
}

function semanticAnalysisStatusLabel(
  status: EngineInstructionEnvironmentSummary["semantic_analysis_status"],
): string {
  return {
    current: "Current",
    not_requested: "Not analyzed yet",
    stale: "Needs reanalysis",
    unavailable: "Unavailable",
  }[status];
}

function artifactRefKey(value: EngineArtifactRef): string {
  return `${value.record_id}:${value.record_version}:${value.content_digest}`;
}

function formatInstructionCheckTime(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf())
    ? "Unavailable"
    : parsed.toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      });
}

function connectionStatusLabel(status: AgentConnection["status"]): string {
  return {
    connected: "Ready",
    available: "Ready to connect",
    attention: "Needs attention",
    not_installed: "Not installed",
    signed_out: "Sign-in required",
    update_required: "Temper update required",
  }[status];
}

export function SettingsPage({
  theme,
  onThemeChange,
  advancedMode,
  onAdvancedModeChange,
  automaticLearning,
  onAutomaticLearningChange,
  nativeRuntime = false,
  backgroundLearning = false,
  telemetryEnabled = false,
  decisionNotificationsEnabled = false,
  launchAtLoginEnabled = false,
  consent = null,
  secureStoreReady = false,
  onGovernedPreferencesChange,
  onRenewConsent,
  snapshotDigest = null,
  onRecoveryCreated,
}: {
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
  advancedMode: boolean;
  onAdvancedModeChange: (enabled: boolean) => void;
  automaticLearning: boolean;
  onAutomaticLearningChange: (enabled: boolean) => void;
  nativeRuntime?: boolean;
  backgroundLearning?: boolean;
  telemetryEnabled?: boolean;
  decisionNotificationsEnabled?: boolean;
  launchAtLoginEnabled?: boolean;
  consent?: EngineDesktopSnapshot["consent"] | null;
  secureStoreReady?: boolean;
  onGovernedPreferencesChange?: (
    learningEnabled: boolean,
    reportingEnabled: boolean,
    notificationsEnabled: boolean,
    launchAtLoginEnabled: boolean,
  ) => Promise<void>;
  onRenewConsent?: () => Promise<void>;
  snapshotDigest?: string | null;
  onRecoveryCreated?: (message: string) => void;
}) {
  const [learning, setLearning] = useState(
    nativeRuntime ? backgroundLearning : true,
  );
  const [notifications, setNotifications] = useState(false);
  const [launch, setLaunch] = useState(false);
  const [telemetry, setTelemetry] = useState(
    nativeRuntime ? telemetryEnabled : false,
  );
  const [previewOpen, setPreviewOpen] = useState(false);
  const [consentOpen, setConsentOpen] = useState(false);
  const consentTrigger = useRef<HTMLButtonElement | null>(null);
  const [preferenceBusy, setPreferenceBusy] = useState(false);
  const [preferenceError, setPreferenceError] = useState<string | null>(null);
  const [recoveryOpen, setRecoveryOpen] = useState(false);

  async function savePreferences(
    nextLearning: boolean,
    nextTelemetry: boolean,
    nextNotifications: boolean,
    nextLaunch: boolean,
  ) {
    if (!nativeRuntime || !onGovernedPreferencesChange) return;
    setPreferenceBusy(true);
    setPreferenceError(null);
    try {
      await onGovernedPreferencesChange(
        nextLearning,
        nextTelemetry,
        nextNotifications,
        nextLaunch,
      );
    } catch (error: unknown) {
      setPreferenceError(
        error instanceof Error
          ? error.message
          : "Temper could not save that setting.",
      );
    } finally {
      setPreferenceBusy(false);
    }
  }

  async function saveNotificationPreference(enabled: boolean) {
    if (!nativeRuntime) {
      setNotifications(enabled);
      return;
    }
    if (enabled) {
      setPreferenceBusy(true);
      setPreferenceError(null);
      try {
        const permission = await requestNotificationPermission();
        if (permission !== "granted") {
          setPreferenceError(
            "Notifications remain off because this device did not grant permission.",
          );
          return;
        }
      } catch {
        setPreferenceError(
          "Temper could not confirm notification permission, so notifications remain off.",
        );
        return;
      } finally {
        setPreferenceBusy(false);
      }
    }
    await savePreferences(
      backgroundLearning,
      telemetryEnabled,
      enabled,
      launchAtLoginEnabled,
    );
  }
  return (
    <div className="page settings-page">
      <header className="today-learning-heading">
        <div>
          <h1>Settings</h1>
          <p>Manage app preferences, privacy and recovery.</p>
        </div>
      </header>
      <SettingsGroup
        title={nativeRuntime ? "Reviewed suggestions" : "Learning"}
      >
        <Toggle
          checked={nativeRuntime ? backgroundLearning : learning}
          description={
            nativeRuntime
              ? "Use new feedback to propose guidance for your review. Manage chat learning in Personalization."
              : "Notice possible preferences in completed work from registered projects."
          }
          label={nativeRuntime ? "Reviewed suggestions" : "Background learning"}
          disabled={preferenceBusy}
          onCheckedChange={(enabled) => {
            setLearning(enabled);
            if (nativeRuntime) {
              void savePreferences(
                enabled,
                telemetryEnabled,
                decisionNotificationsEnabled,
                launchAtLoginEnabled,
              );
            }
          }}
        />
        <Toggle
          checked={nativeRuntime ? decisionNotificationsEnabled : notifications}
          description="Notify me when a suggestion needs review."
          label="Review notifications"
          disabled={preferenceBusy}
          onCheckedChange={(enabled) => {
            void saveNotificationPreference(enabled);
          }}
        />
        {!nativeRuntime ? (
          <Toggle
            checked={automaticLearning}
            description="Keep only strong, low-impact project preferences. Temper notifies you and gives you 24 hours to undo."
            label="Automatic low-risk learning"
            onCheckedChange={onAutomaticLearningChange}
          />
        ) : null}
      </SettingsGroup>
      <SettingsGroup title="Appearance">
        <div className="setting-inline">
          <div>
            <strong>Theme</strong>
            <span>Choose how Temper looks on this device.</span>
          </div>
          <div className="theme-picker" role="group" aria-label="Theme">
            <ThemeButton
              active={theme === "light"}
              icon={<Sun size={15} />}
              label="Light"
              onClick={() => onThemeChange("light")}
            />
            <ThemeButton
              active={theme === "dark"}
              icon={<Moon size={15} />}
              label="Dark"
              onClick={() => onThemeChange("dark")}
            />
            <ThemeButton
              active={theme === "system"}
              icon={<Laptop size={15} />}
              label="System"
              onClick={() => onThemeChange("system")}
            />
          </div>
        </div>
        <Toggle
          checked={nativeRuntime ? launchAtLoginEnabled : launch}
          description="Keep Temper available in the tray after you sign in."
          label="Launch at sign-in"
          disabled={preferenceBusy}
          onCheckedChange={(enabled) => {
            setLaunch(enabled);
            if (nativeRuntime) {
              void savePreferences(
                backgroundLearning,
                telemetryEnabled,
                decisionNotificationsEnabled,
                enabled,
              );
            }
          }}
        />
      </SettingsGroup>
      {preferenceError ? (
        <p className="settings-availability-note" role="alert">
          {preferenceError}
        </p>
      ) : null}
      <SettingsGroup
        title={nativeRuntime ? "Privacy" : "Privacy and reporting"}
      >
        <div className="privacy-summary">
          <ShieldCheck size={20} />
          <div>
            <strong>Evidence storage</strong>
            <span>
              {nativeRuntime && !secureStoreReady
                ? "Secure storage needs attention before Temper can learn or deliver."
                : "Raw evidence is encrypted on this device for up to 30 days. Chat excerpts used for analysis are processed by your connected model."}
            </span>
          </div>
          <Button
            onClick={(event) => {
              consentTrigger.current = event.currentTarget;
              setConsentOpen(true);
            }}
            tone="quiet"
          >
            View permissions
          </Button>
        </div>
        {nativeRuntime ? (
          <Toggle
            checked={telemetryEnabled}
            description={
              telemetryEnabled
                ? "Report uploads are unavailable. Nothing new is uploaded."
                : "Report uploads are unavailable. Nothing is uploaded."
            }
            disabled={preferenceBusy || !telemetryEnabled}
            label="Help improve Temper"
            onCheckedChange={(enabled) => {
              if (enabled) return;
              setTelemetry(false);
              void savePreferences(
                backgroundLearning,
                false,
                decisionNotificationsEnabled,
                launchAtLoginEnabled,
              );
            }}
          />
        ) : (
          <Toggle
            checked={telemetry}
            description="Share product health counts without chat content. Off by default."
            label="Help improve Temper"
            onCheckedChange={setTelemetry}
          />
        )}
        {!nativeRuntime ? (
          <div className="settings-links">
            <button onClick={() => setPreviewOpen(true)} type="button">
              Preview sample report
            </button>
            <span>Browser preview only</span>
          </div>
        ) : null}
      </SettingsGroup>
      <SettingsGroup title="Diagnostics">
        <Toggle
          checked={advancedMode}
          description="Show diagnostics and tools for running tasks."
          label="Advanced mode"
          onCheckedChange={onAdvancedModeChange}
        />
      </SettingsGroup>
      {nativeRuntime ? (
        <SettingsGroup title="Recovery">
          <div className="setting-inline recovery-setting">
            <div>
              <strong>Offline recovery file</strong>
              <span>
                Back up your Temper identity, saved guidance and history with a
                separate passphrase.
              </span>
            </div>
            <Button
              disabled={!snapshotDigest || !secureStoreReady}
              onClick={() => setRecoveryOpen(true)}
              tone="quiet"
            >
              Create recovery file
            </Button>
          </div>
        </SettingsGroup>
      ) : null}
      <TelemetryDialog onOpenChange={setPreviewOpen} open={previewOpen} />
      <ConsentDialog
        consent={consent}
        nativeRuntime={nativeRuntime}
        onRenewConsent={onRenewConsent}
        onOpenChange={setConsentOpen}
        onReturnFocus={() => consentTrigger.current?.focus()}
        open={consentOpen}
        renewalAvailable={secureStoreReady}
      />
      {nativeRuntime && snapshotDigest ? (
        <RecoveryExportDialog
          onComplete={(message) => onRecoveryCreated?.(message)}
          onOpenChange={setRecoveryOpen}
          open={recoveryOpen}
          snapshotDigest={snapshotDigest}
        />
      ) : null}
    </div>
  );
}

function ConsentDialog({
  consent,
  nativeRuntime,
  open,
  onOpenChange,
  onReturnFocus,
  onRenewConsent,
  renewalAvailable,
}: {
  consent: EngineDesktopSnapshot["consent"] | null;
  nativeRuntime: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onReturnFocus: () => void;
  onRenewConsent?: () => Promise<void>;
  renewalAvailable: boolean;
}) {
  const [renewing, setRenewing] = useState(false);
  const [renewalError, setRenewalError] = useState<string | null>(null);
  const expiresAt = consent
    ? new Intl.DateTimeFormat(undefined, { dateStyle: "long" }).format(
        new Date(consent.expires_at),
      )
    : null;
  return (
    <Dialog.Root onOpenChange={onOpenChange} open={open}>
      <PageDialogPortal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content
          className="telemetry-dialog"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            onReturnFocus();
          }}
        >
          <Dialog.Close
            aria-label="Close consent details"
            className="icon-button dialog-close"
          >
            <X size={18} />
          </Dialog.Close>
          <div className="dialog-heading-icon">
            <ShieldCheck size={20} />
          </div>
          <Dialog.Title>Permission for reviewed suggestions</Dialog.Title>
          <Dialog.Description>
            {nativeRuntime
              ? "This permission covers reviewed suggestions. Manage chat learning in Personalization."
              : "These sample permissions are for the browser preview."}
          </Dialog.Description>
          <div className="report-preview">
            <ReportRow
              label="Status"
              value={
                consent
                  ? consent.renewal_required
                    ? "Renewal required"
                    : "Current"
                  : nativeRuntime
                    ? "Unavailable"
                    : "Sample only"
              }
            />
            <ReportRow
              label="Evidence retention"
              value={
                consent
                  ? `${consent.retention_days} days`
                  : nativeRuntime
                    ? "Unavailable"
                    : "30 days"
              }
            />
            <ReportRow label="Expires" value={expiresAt ?? "Not configured"} />
            <ReportRow
              label="Time remaining"
              value={consent ? `${consent.days_remaining} days` : "—"}
            />
          </div>
          <div className="report-retention">
            <Info size={15} />
            <span>Temper encrypts stored evidence on this device.</span>
          </div>
          <div className="dialog-footer">
            {nativeRuntime && consent?.renewal_required ? (
              <Button
                disabled={renewing || !renewalAvailable}
                onClick={() => {
                  if (!onRenewConsent) return;
                  setRenewing(true);
                  setRenewalError(null);
                  void onRenewConsent()
                    .then(() => onOpenChange(false))
                    .catch((error: unknown) =>
                      setRenewalError(
                        error instanceof Error
                          ? error.message
                          : "Temper could not renew consent.",
                      ),
                    )
                    .finally(() => setRenewing(false));
                }}
                tone="primary"
              >
                {renewing
                  ? "Renewing…"
                  : renewalAvailable
                    ? "Renew for 30 days"
                    : "Secure storage required"}
              </Button>
            ) : null}
            <Button onClick={() => onOpenChange(false)} tone="primary">
              Done
            </Button>
          </div>
          {renewalError ? <p role="alert">{renewalError}</p> : null}
        </Dialog.Content>
      </PageDialogPortal>
    </Dialog.Root>
  );
}

function SettingsGroup({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="settings-group">
      <h2>{title}</h2>
      <div className="settings-surface">{children}</div>
    </section>
  );
}
function ThemeButton({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-pressed={active}
      className={active ? "theme-button theme-button--active" : "theme-button"}
      onClick={onClick}
      type="button"
    >
      {icon}
      {label}
    </button>
  );
}

function TelemetryDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog.Root onOpenChange={onOpenChange} open={open}>
      <PageDialogPortal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="telemetry-dialog">
          <Dialog.Close
            aria-label="Close report preview"
            className="icon-button dialog-close"
          >
            <X size={18} />
          </Dialog.Close>
          <div className="dialog-heading-icon">
            <Cloud size={20} />
          </div>
          <Dialog.Title>Exact report preview</Dialog.Title>
          <Dialog.Description>
            These are the only values Temper would upload. There are no prompts,
            paths, project names, or behavior text.
          </Dialog.Description>
          <div className="report-preview">
            <ReportRow label="App version" value="0.3.0a2" />
            <ReportRow label="Platform" value="macOS arm64" />
            <ReportRow label="Eligible interactions" value="13" />
            <ReportRow label="Correct activations" value="1" />
            <ReportRow label="False activations" value="1" />
            <ReportRow label="Pending reviews" value="0" />
          </div>
          <div className="report-retention">
            <Info size={15} />
            <span>
              Signed aggregate reports are retained for 90 days and can be
              deleted here at any time.
            </span>
          </div>
          <div className="dialog-footer">
            <Button onClick={() => onOpenChange(false)} tone="primary">
              Done
            </Button>
          </div>
        </Dialog.Content>
      </PageDialogPortal>
    </Dialog.Root>
  );
}

function ReportRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function AdvancedPage({
  nativeRuntime = false,
  projects: liveProjects = [],
  previewProjects = [],
  runnerReady = false,
  runnerUnavailableReason = null,
  taskResult = null,
  diagnostics = null,
  longitudinalGate = null,
  onRun,
  onApply,
  onDiscard,
  onDiagnostics,
}: {
  nativeRuntime?: boolean;
  projects?: Array<{ id: string; label: string }>;
  previewProjects?: Array<{ id: string; label: string }>;
  runnerReady?: boolean;
  runnerUnavailableReason?: string | null;
  taskResult?: EngineTaskResult | null;
  diagnostics?: EngineDiagnostics | null;
  longitudinalGate?: EngineLongitudinalGate | null;
  onRun?: (projectId: string, task: string) => Promise<void>;
  onApply?: () => Promise<void>;
  onDiscard?: () => Promise<void>;
  onDiagnostics?: () => Promise<void>;
}) {
  const [running, setRunning] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [showDiff, setShowDiff] = useState(true);
  const [task, setTask] = useState("");
  const [projectId, setProjectId] = useState(liveProjects[0]?.id ?? "");
  const [error, setError] = useState<string | null>(null);
  const [diagnosticsError, setDiagnosticsError] = useState<string | null>(null);
  const browserReview = !nativeRuntime && showDiff;
  const review = taskResult?.change_review;
  const visibleProjects = nativeRuntime ? liveProjects : previewProjects;
  const selectedProjectId = projectId || visibleProjects[0]?.id || "";

  async function run() {
    if (!nativeRuntime) {
      setShowDiff(true);
      return;
    }
    if (!runnerReady || !selectedProjectId || !task.trim() || !onRun) return;
    setRunning(true);
    setError(null);
    try {
      await onRun(selectedProjectId, task);
    } catch (caught: unknown) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Temper could not run that task.",
      );
    } finally {
      setRunning(false);
    }
  }
  return (
    <div className="page">
      <header className="page-topline">
        <div />
      </header>
      <SectionHeading
        eyebrow="Advanced"
        title="Run with Temper"
        description="Run a Codex task in a temporary workspace. Review the diff before changing your project."
      />
      <section className="lab-card">
        {nativeRuntime && !runnerReady ? (
          <p className="setup-state-message">
            {runnerUnavailableReason ??
              "Managed Codex tasks are unavailable in the current state."}
          </p>
        ) : null}
        <div className="lab-field-row">
          <label htmlFor="lab-project">Project</label>
          <TemperSelect
            ariaLabel="Project"
            id="lab-project"
            onValueChange={setProjectId}
            options={visibleProjects.map((project) => ({
              label: project.label,
              value: project.id,
            }))}
            value={selectedProjectId}
          />
        </div>
        <label className="lab-label" htmlFor="lab-task">
          Task
        </label>
        <textarea
          id="lab-task"
          onChange={(event) => setTask(event.target.value)}
          value={task}
        />
        <div className="lab-contract">
          <ShieldCheck size={16} />
          <span>Separate workspace · project-scoped guidance · no network</span>
        </div>
        <Button
          icon={running ? <Pause size={16} /> : <Play size={16} />}
          disabled={
            !nativeRuntime ||
            running ||
            !runnerReady ||
            !selectedProjectId ||
            !task.trim()
          }
          onClick={() => void run()}
          tone="primary"
        >
          {running
            ? "Running…"
            : nativeRuntime
              ? "Run with Temper"
              : "Available in desktop app"}
        </Button>
        {error ? <p role="alert">{error}</p> : null}
      </section>
      {taskResult?.final_message ? (
        <section className="settings-group">
          <h2>Agent report</h2>
          <p>
            Review the proposed changes and test results before applying them.
          </p>
          <p>{taskResult.final_message}</p>
        </section>
      ) : null}
      {review || browserReview ? (
        <section className="diff-card">
          <div className="diff-heading">
            <div className="card-icon">
              <FileDiff size={18} />
            </div>
            <div>
              <h2>Review before applying</h2>
              <p>
                {review
                  ? `${review.changed_files.length} files changed. Nothing has touched the project yet.`
                  : "Sample diff for 2 files. No local project is connected."}
              </p>
            </div>
            <StatusPill tone={nativeRuntime ? "neutral" : "positive"}>
              {nativeRuntime ? "Review ready" : "Sample diff"}
            </StatusPill>
          </div>
          <pre aria-label="Proposed code changes">
            {review ? (
              <code>{review.diff_text}</code>
            ) : (
              <code>
                <span className="diff-line diff-line--muted">
                  @@ release/checks.py:18 @@
                </span>
                {"\n"}
                <span className="diff-line diff-line--remove">
                  - return note.status == "ready"
                </span>
                {"\n"}
                <span className="diff-line diff-line--add">
                  + return note.status == "ready" and note.verified
                </span>
                {"\n"}
                <span className="diff-line diff-line--muted">
                  @@ tests/test_checks.py:41 @@
                </span>
                {"\n"}
                <span className="diff-line diff-line--add">
                  + assert not can_release(unverified_note)
                </span>
              </code>
            )}
          </pre>
          <div className="diff-warning">
            <Info size={15} />
            <span>
              Apply succeeds only if the project is still at the reviewed commit
              and independent checks pass again.
            </span>
          </div>
          <div className="diff-actions">
            <Button
              icon={<Check size={16} />}
              disabled={!nativeRuntime || !onApply || resolving}
              onClick={() => {
                if (!onApply) return;
                setResolving(true);
                setError(null);
                void onApply()
                  .catch((caught: unknown) =>
                    setError(
                      caught instanceof Error
                        ? caught.message
                        : "Temper could not safely apply those changes.",
                    ),
                  )
                  .finally(() => setResolving(false));
              }}
              tone="primary"
            >
              Apply reviewed changes
            </Button>
            <Button
              onClick={() => {
                if (!nativeRuntime) {
                  setShowDiff(false);
                  return;
                }
                if (!onDiscard) return;
                setResolving(true);
                setError(null);
                void onDiscard()
                  .catch((caught: unknown) =>
                    setError(
                      caught instanceof Error
                        ? caught.message
                        : "Temper could not safely discard that review.",
                    ),
                  )
                  .finally(() => setResolving(false));
              }}
              disabled={resolving}
              tone="quiet"
            >
              Discard
            </Button>
          </div>
        </section>
      ) : null}
      {nativeRuntime && longitudinalGate ? (
        <LongitudinalGateCard gate={longitudinalGate} />
      ) : null}
      <section className="settings-group">
        <h2>Instrument status</h2>
        {diagnostics ? (
          <p>
            {diagnostics.project_count} projects ·{" "}
            {diagnostics.active_adaptation_count} active adaptations ·{" "}
            {diagnostics.pending_review_count} reviews · secure store{" "}
            {diagnostics.secure_store_ready ? "ready" : "needs attention"}
          </p>
        ) : (
          <p>Load local diagnostics.</p>
        )}
        {diagnosticsError ? <p role="alert">{diagnosticsError}</p> : null}
        <Button
          disabled={!nativeRuntime || !onDiagnostics}
          onClick={() => {
            if (!onDiagnostics) return;
            setDiagnosticsError(null);
            void onDiagnostics().catch((caught: unknown) =>
              setDiagnosticsError(
                caught instanceof Error
                  ? caught.message
                  : "Temper could not load diagnostics.",
              ),
            );
          }}
          tone="quiet"
        >
          Refresh diagnostics
        </Button>
      </section>
    </div>
  );
}

function LongitudinalGateCard({ gate }: { gate: EngineLongitudinalGate }) {
  const latestPack = gate.pack_bytes_by_activation.at(-1) ?? 0;
  const progress = (current: number, goal: number) =>
    Math.min(100, Math.round((current / goal) * 100));
  return (
    <section aria-labelledby="longitudinal-gate-title" className="gate-card">
      <div className="gate-card__heading">
        <div>
          <span>Genuine learning gate</span>
          <h2 id="longitudinal-gate-title">
            {gate.evidence_ready
              ? "Evidence set complete"
              : "Ordinary use in progress"}
          </h2>
        </div>
        <StatusPill tone={gate.evidence_ready ? "positive" : "neutral"}>
          {gate.evidence_ready
            ? "Assessment complete"
            : `${gate.remaining_interactions} remaining`}
        </StatusPill>
      </div>
      <p>
        Only real post-registration work counts. Synthetic runs never advance
        this record.
      </p>
      <div className="gate-card__measures">
        <GateMeasure
          label="Interactions"
          progress={progress(
            gate.eligible_interaction_count,
            gate.goal_interaction_count,
          )}
          value={`${gate.eligible_interaction_count} / ${gate.goal_interaction_count}`}
        />
        <GateMeasure
          label="Active dates"
          progress={progress(gate.active_date_count, gate.minimum_active_dates)}
          value={`${gate.active_date_count} / ${gate.minimum_active_dates}`}
        />
        <GateMeasure
          label="Activations"
          progress={progress(
            gate.activation_count,
            gate.minimum_activation_count,
          )}
          value={`${gate.activation_count} / ${gate.minimum_activation_count}`}
        />
      </div>
      <dl className="gate-card__facts">
        <div>
          <dt>Rated</dt>
          <dd>{gate.rated_activation_count}</dd>
        </div>
        <div>
          <dt>Helped / hurt</dt>
          <dd>
            {gate.helped_count} / {gate.hurt_count}
          </dd>
        </div>
        <div>
          <dt>False learning</dt>
          <dd>{gate.false_learning_count}</dd>
        </div>
        <div>
          <dt>False activation</dt>
          <dd>{gate.false_activation_count}</dd>
        </div>
        <div>
          <dt>Repeated corrections</dt>
          <dd>{gate.repeated_correction_count}</dd>
        </div>
        <div>
          <dt>Latest projection</dt>
          <dd>{latestPack.toLocaleString()} bytes</dd>
        </div>
      </dl>
    </section>
  );
}

function GateMeasure({
  label,
  value,
  progress,
}: {
  label: string;
  value: string;
  progress: number;
}) {
  return (
    <div>
      <span>
        {label} <strong>{value}</strong>
      </span>
      <div aria-hidden="true" className="gate-card__track">
        <i style={{ width: `${progress}%` }} />
      </div>
    </div>
  );
}

export function TrayPreview({ onOpen }: { onOpen: () => void }) {
  return (
    <>
      <aside aria-label="Temper notification" className="native-notification">
        <div className="notification-mark">
          <Sparkles size={17} />
        </div>
        <div>
          <strong>Temper noticed something</strong>
          <span>A possible preference is ready to review.</span>
        </div>
        <button
          aria-label="Dismiss notification (preview only)"
          disabled
          type="button"
        >
          <X size={15} />
        </button>
      </aside>
      <aside aria-label="Temper tray menu" className="tray-menu">
        <div className="tray-header">
          <span aria-hidden="true" className="tray-brand-mark" />
          <div>
            <strong>Temper</strong>
            <span>
              <i /> Sample state
            </span>
          </div>
        </div>
        <Divider />
        <button onClick={onOpen} type="button">
          <Sparkles size={16} />
          <span>Review suggestion</span>
          <b>1</b>
        </button>
        <button disabled type="button">
          <Pause size={16} />
          <span>Pause Temper</span>
        </button>
        <Divider />
        <button disabled type="button">
          <ExternalLink size={16} />
          <span>Open Temper</span>
        </button>
        <button disabled type="button">
          <CircleHelp size={16} />
          <span>Help</span>
        </button>
        <Divider />
        <button disabled type="button">
          <X size={16} />
          <span>Quit</span>
        </button>
      </aside>
    </>
  );
}
