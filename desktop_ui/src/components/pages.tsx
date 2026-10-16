import * as Dialog from "@radix-ui/react-dialog";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  CircleHelp,
  Cloud,
  Compass,
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
  SectionHeading,
  StatusPill,
  TemperSelect,
  Toggle,
} from "./ui";

export function TodayPage({
  onReview,
  onOpenCore,
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
}: {
  onReview: (suggestionId: string) => void;
  onOpenCore: () => void;
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
  const governedReviewBlocked =
    liveSummary?.health === "consent_expired" ||
    liveSummary?.secureStoreReady === false;
  const hasSuggestion =
    Boolean(selectedSuggestion) && !governedReviewBlocked && !nativeConflict;
  const isAllProjects = workspace === "all";
  const selectedIndex = selectedSuggestion
    ? applicableSuggestions.findIndex(
        (item) => item.id === selectedSuggestion.id,
      )
    : -1;
  const suggestionCount = applicableSuggestions.length;
  const automationStatus = selectedSuggestion
    ? selectedSuggestion.automationDisposition === "eligible"
      ? automaticLearning
        ? "Automatic with 24-hour undo"
        : "Automatic option available"
      : selectedSuggestion.automationDisposition === "review-required"
        ? "Your review is required"
        : "Waiting for more evidence"
    : "";
  const headline = nativeConflict
    ? "An instruction conflict needs review."
    : liveSummary?.health === "consent_expired"
      ? nativeAutonomy
        ? "Reviewed suggestions need renewed permission."
        : "Consent needs renewal."
      : liveSummary?.secureStoreReady === false
        ? "Secure storage needs attention."
        : hasSuggestion
          ? `${suggestionCount} suggestion${suggestionCount === 1 ? "" : "s"} to review.`
          : liveSummary?.pendingFeedbackCount
            ? `${liveSummary.pendingFeedbackCount} rating${liveSummary.pendingFeedbackCount === 1 ? "" : "s"} waiting.`
            : liveSummary?.health === "paused"
              ? nativeAutonomy
                ? "Reviewed suggestions are paused."
                : "Learning is paused."
              : liveSummary?.projectCount === 0
                ? "No projects registered."
                : liveSummary?.health === "needs_attention"
                  ? "Temper needs attention."
                  : liveSummary
                    ? isAllProjects
                      ? "Nothing needs your attention."
                      : `Nothing needs review in ${workspace}.`
                    : `${suggestionCount} suggestion${suggestionCount === 1 ? "" : "s"} to review.`;
  const summary = nativeConflict
    ? "Temper withheld the affected adaptation instead of sending contradictory guidance."
    : liveSummary?.health === "consent_expired"
      ? nativeAutonomy
        ? "Reviewed suggestions and their delivery remain stopped until you renew this permission. Everyday habit learning uses the controls above."
        : `${liveSummary.pendingReviewCount} suggestion${liveSummary.pendingReviewCount === 1 ? " remains" : "s remain"} waiting. Learning, review, and delivery stay stopped until you renew consent.`
      : liveSummary?.secureStoreReady === false
        ? "Temper cannot approve, deliver, or change adaptations until its local keys are available."
        : hasSuggestion
          ? "Review the first suggestion below. Nothing changes until you decide."
          : nativeAutonomy && liveSummary?.health === "paused"
            ? "Capture for reviewed suggestions is paused. Everyday habit learning uses the controls above."
            : (liveSummary?.message ??
              (liveSummary?.health === "paused"
                ? "Temper will not inspect new completed work until you turn background learning on."
                : liveSummary?.projectCount === 0
                  ? "Register a project in Connections to make new work eligible."
                  : liveSummary?.health === "needs_attention"
                    ? "Open Advanced for the exact local requirement."
                    : liveSummary
                      ? `${liveSummary.activeAdaptationCount} approved adaptation${liveSummary.activeAdaptationCount === 1 ? "" : "s"} available for this view.`
                      : "This browser preview uses example product data."));
  const healthLabel = liveSummary
    ? {
        ready: "Ready",
        needs_attention: "Needs attention",
        paused: nativeAutonomy ? "Suggestions paused" : "Learning paused",
        consent_expired: nativeAutonomy
          ? "Suggestion permission expired"
          : "Consent expired",
      }[liveSummary.health]
    : "Preview";
  return (
    <div className="page folio-page folio-page--today">
      {nativeAutonomy && <AutonomousLearningPanel projects={liveProjects} />}
      <header className="folio-page-meta">
        <span>
          {new Intl.DateTimeFormat(undefined, {
            dateStyle: "full",
          }).format(new Date())}
        </span>
      </header>
      <section className="folio-statement" aria-labelledby="today-heading">
        <div className="folio-statement__line">
          <h1 id="today-heading">{headline}</h1>
        </div>
        <p>{summary}</p>
      </section>
      <div className="folio-divider" aria-hidden="true">
        <span />
      </div>
      <section className="folio-workbench" aria-label="Current thought">
        <article className="folio-proposal">
          {nativeConflict ? (
            <>
              <span className="folio-kicker">Existing agent setup</span>
              <h2>{nativeConflict.source_display_path}</h2>
              <p>{nativeConflict.rationale}</p>
              <button
                className="folio-primary-action"
                onClick={onOpenCore}
                type="button"
              >
                Review conflict <ArrowRight aria-hidden="true" size={16} />
              </button>
            </>
          ) : hasSuggestion ? (
            <>
              <span className="folio-kicker">
                {isAllProjects && selectedSuggestion?.sourceProject
                  ? `${selectedSuggestion.sourceProject} · `
                  : ""}
                Suggestion {selectedIndex + 1} of {suggestionCount}
              </span>
              <h2>Temper noticed a pattern worth considering.</h2>
              <blockquote>“{selectedSuggestion?.behavior}”</blockquote>
              <p>{selectedSuggestion?.explanation}</p>
              <button
                className="folio-primary-action"
                onClick={() =>
                  selectedSuggestion ? onReview(selectedSuggestion.id) : null
                }
                type="button"
              >
                Review suggestion <ArrowRight aria-hidden="true" size={16} />
              </button>
            </>
          ) : (
            <>
              <span className="folio-kicker">Current view</span>
              <h2>
                {liveSummary
                  ? liveSummary.pendingFeedbackCount
                    ? "A recent adaptation is ready to rate."
                    : liveSummary.health === "ready"
                      ? "No suggestions to review."
                      : liveSummary.health === "paused"
                        ? nativeAutonomy
                          ? "Capture for reviewed suggestions is paused."
                          : "No new learning is running."
                        : liveSummary.health === "consent_expired"
                          ? nativeAutonomy
                            ? "Reviewed suggestions and their delivery are stopped."
                            : "Learning and delivery are stopped."
                          : "A local requirement is unresolved."
                  : "No suggestion is selected."}
              </h2>
              {liveSummary ? (
                <p>
                  {liveSummary.pendingFeedbackCount
                    ? "Use Helped, Hurt, or Irrelevant to record the outcome."
                    : liveSummary.pendingReviewCount
                      ? `${liveSummary.pendingReviewCount} suggestion${liveSummary.pendingReviewCount === 1 ? " is" : "s are"} waiting for review.`
                      : "No suggestion is waiting in this view."}
                </p>
              ) : (
                <>
                  <p>This browser preview uses example product data.</p>
                </>
              )}
              <button
                className="folio-primary-action"
                onClick={onOpenCore}
                type="button"
              >
                View Core <ArrowRight aria-hidden="true" size={16} />
              </button>
            </>
          )}
        </article>
        <aside className="folio-margin" aria-label="Current workspace notes">
          <dl className="margin-register">
            {hasSuggestion ? (
              <>
                <div>
                  <dt>Evidence</dt>
                  <dd>
                    {selectedSuggestion?.evidenceStrength
                      ? evidenceStrengthLabels[
                          selectedSuggestion.evidenceStrength
                        ]
                      : "Review required"}
                  </dd>
                </div>
                <div>
                  <dt>Suggested scope</dt>
                  <dd>{selectedSuggestion?.suggestedScope}</dd>
                </div>
                <div>
                  <dt>Next step</dt>
                  <dd>{automationStatus}</dd>
                </div>
              </>
            ) : (
              <>
                <div>
                  <dt>Project</dt>
                  <dd>{isAllProjects ? "All projects" : workspace}</dd>
                </div>
                <div>
                  <dt>Available here</dt>
                  <dd>
                    {liveSummary
                      ? `${liveSummary.activeAdaptationCount} approved item${liveSummary.activeAdaptationCount === 1 ? "" : "s"}`
                      : "Example items"}
                  </dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>{healthLabel}</dd>
                </div>
              </>
            )}
          </dl>
          {hasSuggestion && suggestionCount > 1 ? (
            <div className="margin-queue">
              <div className="margin-queue__heading">
                <span className="folio-kicker">Suggestion queue</span>
                <span>{suggestionCount} ready</span>
              </div>
              <ol>
                {applicableSuggestions.map((item, index) => (
                  <li key={item.id}>
                    <button
                      aria-current={
                        item.id === selectedSuggestion?.id ? "true" : undefined
                      }
                      onClick={() => onReview(item.id)}
                      type="button"
                    >
                      <span className="queue-number">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <span className="queue-copy">
                        <strong>{item.behavior}</strong>
                        <small>
                          {item.evidenceStrength
                            ? evidenceStrengthLabels[item.evidenceStrength]
                            : "Review required"}
                        </small>
                      </span>
                    </button>
                  </li>
                ))}
              </ol>
            </div>
          ) : liveSummary?.pendingFeedbackCount || !liveSummary ? (
            <div className="margin-feedback">
              <span className="folio-kicker">Last task</span>
              <h2>
                {liveSummary?.pendingFeedbackCount
                  ? "Was Temper useful?"
                  : "No rating is waiting."}
              </h2>
              <p>
                {liveSummary?.pendingFeedbackCount
                  ? "A completed activation is ready for your feedback."
                  : "Temper will ask after it delivers an approved adaptation."}
              </p>
              {feedback ? (
                <div className="feedback-thanks">
                  <Check aria-hidden="true" size={15} /> Recorded as {feedback}
                </div>
              ) : !liveSummary || liveSummary.pendingFeedbackCount ? (
                <div
                  className="feedback-row feedback-row--folio"
                  aria-label="Rate the recent adaptation"
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
              ) : null}
            </div>
          ) : null}
        </aside>
      </section>
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
  activeWorkspace,
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
}: {
  activeWorkspace: WorkspaceScope;
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
}) {
  const [items, setItems] = useState(initialItems);
  const [kind, setKind] = useState<CoreKind | "all">("all");
  const [scope, setScope] = useState<ProjectName | "all">(activeWorkspace);
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
    if (activeWorkspace === "all") return true;
    return liveProjects.some(
      (project) =>
        project.project_id === environment.project_id &&
        project.display_name === activeWorkspace,
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
      <div aria-hidden="true" className="core-tree" />
      <header className="core-heading">
        <div>
          <span className="folio-kicker">Your working character</span>
          <h1>Core</h1>
          <p>
            What Temper has learned about how you work, and where each part
            belongs.
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
          <div className="core-current-project">
            <span>Workspace view</span>
            <strong>
              {activeWorkspace === "all" ? "All projects" : activeWorkspace}
            </strong>
          </div>
        </div>
      </header>
      <section className="core-overview" aria-label="Core summary">
        <p>
          {activeWorkspace === "all" ? (
            <>
              <strong>{items.length} approved items</strong> across your work.
              Shared guidance forms the trunk; project knowledge branches only
              where it applies.
            </>
          ) : (
            <>
              <strong>
                {
                  items.filter((item) =>
                    appliesToProject(item, activeWorkspace),
                  ).length
                }{" "}
                approved items
              </strong>{" "}
              apply in {activeWorkspace}. Shared guidance is combined with this
              project's branch.
            </>
          )}
        </p>
      </section>
      {nativeRuntime ? (
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
      ) : null}
      <div className="core-toolbar">
        <div aria-label="Filter by knowledge type" className="core-kind-filter">
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
          <span>“{removed.item.title}” was removed from Core.</span>
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
            Nothing in Core matches these filters.
          </div>
        ) : null}
      </div>
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
          <span className="folio-kicker">Also considered</span>
          <h2 id="native-context-title">Existing agent setup</h2>
          <p>
            Temper accounts for these project instructions and skills without
            adding them to your Core.
          </p>
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
                    <dt>Temper Core</dt>
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
      <Dialog.Portal>
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
      </Dialog.Portal>
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
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="core-dialog">
          <Dialog.Title>Remove “{item.title}” from Core?</Dialog.Title>
          <Dialog.Description>
            Temper will record a governed revocation and rebuild future
            projections without this behavior. Its lineage stays available in
            Advanced.
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
      </Dialog.Portal>
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
          <span className="folio-kicker">Curated capability library</span>
          <h1>Modes Hub</h1>
          <p>
            Reviewed workflows from respected open-source sources, compiled into
            bounded one-task capabilities. Core stays unchanged.
          </p>
        </div>
        <div className="modes-heading__actions">
          <button
            disabled={!nativeRuntime || !snapshotDigest}
            onClick={() => setPackageAction({ intent: "import" })}
            type="button"
          >
            <Upload aria-hidden="true" size={14} /> Import package
          </button>
          <Compass aria-hidden="true" size={30} strokeWidth={1.25} />
        </div>
      </header>
      <section className="modes-principle">
        <span>Core</span>
        <strong>+</strong>
        <span>Current project</span>
        <strong>+</strong>
        <span>One Mode</span>
        <strong>→</strong>
        <span>Small task projection</span>
      </section>
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
      {loading ? <div className="modes-empty">Loading local Modes…</div> : null}
      {error ? (
        <div className="modes-empty" role="alert">
          {error}
        </div>
      ) : null}
      <div className="mode-catalog">
        {modes.map((mode) => (
          <article className="mode-card" key={mode.mode_id}>
            <div className="mode-card__mark" aria-hidden="true">
              <Sparkles size={22} strokeWidth={1.4} />
            </div>
            <div className="mode-card__copy">
              <span className="folio-kicker">
                {mode.source_kind === "imported" ? "Imported" : "Curated"} · v
                {mode.mode_version} ·{" "}
                {mode.evaluation_status === "product_evaluated"
                  ? "Tested"
                  : mode.evaluation_status === "failed"
                    ? "Did not pass testing"
                    : mode.evaluation_status === "revoked"
                      ? "Unavailable"
                      : "Evaluation pending"}
              </span>
              <h2>{mode.name}</h2>
              <p>{mode.summary}</p>
              <div className="mode-card__facts">
                <span>One task</span>
                {mode.personalized ? <span>Personalized</span> : null}
                <span>{mode.projection_utf8_bytes} bytes</span>
                <span>
                  {mode.source_count} reviewed source
                  {mode.source_count === 1 ? "" : "s"}
                </span>
                <span>
                  {mode.requested_tools.length
                    ? "Requests tools"
                    : "No new tools"}
                </span>
              </div>
            </div>
            <button
              className="folio-primary-action mode-card__action"
              onClick={() => setSelected(mode)}
              type="button"
            >
              View Mode <ArrowRight aria-hidden="true" size={15} />
            </button>
          </article>
        ))}
      </div>
      {!loading && !error && modes.length === 0 ? (
        <div className="modes-empty">No Modes are available in this build.</div>
      ) : null}
      <footer className="mode-footer">
        <p>
          Modes are temporary capabilities. Preferences, memories, procedures,
          and personal skills belong in Core.
        </p>
        <button onClick={onOpenCore} type="button">
          View Core <ArrowRight aria-hidden="true" size={14} />
        </button>
      </footer>
      {selected ? (
        <ModeDetailsDialog
          mode={selected}
          nativeRuntime={nativeRuntime}
          onClose={() => setSelected(null)}
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
          : "Temper could not create a safe Mode preview.",
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
          : "Temper could not start the managed Mode task.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog.Root onOpenChange={(open) => (open ? undefined : onClose())} open>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="core-dialog mode-dialog">
          <Dialog.Close aria-label="Close" className="dialog-close">
            <X size={18} />
          </Dialog.Close>
          <span className="folio-kicker">
            Temporary Mode · v{mode.mode_version}
          </span>
          <Dialog.Title>{mode.name}</Dialog.Title>
          <Dialog.Description>{mode.summary}</Dialog.Description>
          <dl className="mode-detail-list">
            <div>
              <dt>Catalog status</dt>
              <dd>
                {mode.evaluation_status === "product_evaluated"
                  ? "Product evaluated"
                  : "Curated and reviewed; comparative testing pending"}
              </dd>
            </div>
            <div>
              <dt>Source lineage</dt>
              <dd>
                {detail
                  ? detail.sources
                      .map((source) => source.publisher)
                      .join(" and ")
                  : `${mode.source_count} pinned open-source source${mode.source_count === 1 ? "" : "s"}`}
              </dd>
            </div>
            <div>
              <dt>Life span</dt>
              <dd>
                One exact managed task, up to {mode.task_lease_hours} hours,
                then clean removal
              </dd>
            </div>
            <div>
              <dt>Compatible projection formats</dt>
              <dd>{mode.compatible_target_families.join(" and ")}</dd>
            </div>
            <div>
              <dt>Available now</dt>
              <dd>Fresh Temper-managed Codex tasks</dd>
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
              <dt>Static conformance</dt>
              <dd>
                {mode.evaluation_valid
                  ? `${mode.evaluation_case_count} conformance checks passed`
                  : "Needs attention"}
              </dd>
            </div>
            <div>
              <dt>Effectiveness</dt>
              <dd>
                {mode.effectiveness_evaluated
                  ? "Passed the frozen product comparison"
                  : "Not established — comparative evaluation pending"}
              </dd>
            </div>
            <div>
              <dt>Personal overlay</dt>
              <dd>
                {mode.personalized
                  ? "Your approved overlay is applied for this task only"
                  : "None — this Mode uses its generic defaults"}
              </dd>
            </div>
          </dl>
          {detail ? (
            <section className="mode-source-list" aria-label="Mode sources">
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
            Your request, project rules, security constraints, and Core always
            outrank Mode defaults.
          </div>
          {projectId ? (
            <dl
              className="mode-detail-list"
              aria-label="Native instruction coverage"
            >
              <div>
                <dt>Existing setup considered</dt>
                <dd>
                  {selectedEnvironment
                    ? `${selectedEnvironment.source_count} source${selectedEnvironment.source_count === 1 ? "" : "s"}`
                    : "Not analyzed yet"}
                </dd>
              </div>
              <div>
                <dt>Candidate Mode material</dt>
                <dd>
                  {mode.projection_utf8_bytes} bytes before native deduplication
                </dd>
              </div>
              <div>
                <dt>Blocking conflicts</dt>
                <dd>
                  {selectedEnvironment?.blocking_conflict_count ?? "Unknown"}
                </dd>
              </div>
              <div>
                <dt>Final delta</dt>
                <dd>Rehashed and minimized immediately before launch</dd>
              </div>
            </dl>
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
                placeholder={`Describe the ${mode.name.toLowerCase()} work for this one managed task`}
                rows={3}
                value={task}
              />
            </label>
            <p>
              {runnerReady
                ? "Uses a fresh isolated Codex session with your saved ChatGPT authentication."
                : (runnerUnavailableReason ??
                  "Managed Mode delivery is unavailable in the current state.")}{" "}
              Changes return for review; the Mode is removed whether the task
              succeeds or fails.
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
                    : "This Mode requests additional capabilities."}
                </span>
              </div>
            ) : null}
          </div>
          <div className="core-dialog__actions">
            <Button onClick={onClose} tone="quiet">
              Close
            </Button>
            <Button disabled={!nativeRuntime} onClick={onExport} tone="quiet">
              <Share2 aria-hidden="true" size={14} /> Export package
            </Button>
            <Button
              disabled={!canRun}
              onClick={preview ? startTask : createPreview}
              tone="primary"
            >
              {busy
                ? "Running isolated task…"
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
      </Dialog.Portal>
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
      <Dialog.Portal>
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
      </Dialog.Portal>
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
  const [selectedConnection, setSelectedConnection] =
    useState<AgentConnection | null>(null);
  const [projectPreview, setProjectPreview] =
    useState<EngineProjectPreview | null>(null);
  const [projectBusy, setProjectBusy] = useState(false);
  const [projectMessage, setProjectMessage] = useState<string | null>(null);
  const [refreshBusy, setRefreshBusy] = useState(false);
  const shownConnections: AgentConnection[] = liveConnections
    ? liveConnections.map((connection) => ({
        authDescription: connection.status_summary,
        costDescription: connection.cost_posture,
        id: connection.agent_id,
        name: connection.display_name,
        availableActions: connection.available_actions,
        sourceCapability: connection.learning_capability,
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
        pathLabel: "Prospectively registered",
      }))
    : previewProjects;

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
    return { semanticStatus, skillCount, sourceCount, status };
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
      <header className="page-topline">
        <div />
      </header>
      <SectionHeading
        title="Connections"
        description="Review where Temper can learn and where it can deliver adaptations."
      />
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
            This browser preview cannot change agent accounts or project
            folders. Those controls become available in the installed desktop
            app.
          </span>
        </div>
      ) : null}
      <section className="connection-list">
        {shownConnections.map((connection) => (
          <article className="connection-card" key={connection.id}>
            <div className={`agent-logo agent-logo--${connection.id}`}>
              <AgentBrandMark agent={connection.id} />
            </div>
            <div className="connection-main">
              <div className="connection-title">
                <h2>{connection.name}</h2>
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
              onClick={() => setSelectedConnection(connection)}
              tone="quiet"
            >
              View details
            </Button>
          </article>
        ))}
      </section>
      <section className="projects-section">
        <div className="subsection-heading">
          <div>
            <h2>Registered projects</h2>
            <p>Only new work after registration is eligible.</p>
          </div>
          <Button
            disabled={
              !nativeRuntime ||
              !snapshotDigest ||
              projectBusy ||
              !registrationAvailable
            }
            icon={<Plus size={16} />}
            onClick={chooseProject}
            title={registrationUnavailableReason ?? undefined}
          >
            Add project
          </Button>
        </div>
        {nativeRuntime &&
        !registrationAvailable &&
        registrationUnavailableReason ? (
          <p className="setup-state-message">{registrationUnavailableReason}</p>
        ) : null}
        <div className="project-list">
          {shownProjects.map((project) => {
            const environment = environmentStatus(project.id);
            return (
              <div className="project-row" key={project.id}>
                <div className="project-monogram">{project.name[0]}</div>
                <div className="project-row__copy">
                  <strong>{project.name}</strong>
                  <span>{project.pathLabel}</span>
                  {nativeRuntime ? (
                    <span className="project-row__environment">
                      {environment.sourceCount
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
                      {environment.status === "understood" &&
                      environment.semanticStatus !== "current"
                        ? semanticAnalysisStatusLabel(
                            environment.semanticStatus,
                          )
                        : instructionEnvironmentStatusLabel(environment.status)}
                    </StatusPill>
                  ) : null}
                  <span className="agent-chip">
                    {project.connectedAgents.length
                      ? project.connectedAgents.join(", ")
                      : "Registered · managed tasks unavailable"}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
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
          snapshotDigest={snapshotDigest}
        />
      ) : null}
      {projectPreview ? (
        <Dialog.Root
          onOpenChange={(open) => (open ? undefined : setProjectPreview(null))}
          open
        >
          <Dialog.Portal>
            <Dialog.Overlay className="dialog-overlay" />
            <Dialog.Content className="core-dialog connection-dialog">
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
          </Dialog.Portal>
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
  onInstructionChanged,
  snapshotDigest,
}: {
  connection: AgentConnection;
  instructionEnvironments: EngineInstructionEnvironmentSummary[];
  nativeRuntime: boolean;
  projects: EngineProject[];
  onClose: () => void;
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
      await onInstructionChanged?.(
        `${connection.name} existing instructions were analyzed without promoting them into Core.`,
      );
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
          : `Temper could not preview portable Core for ${connection.name}.`,
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
          ? `${receipt.authorized_artifact_count} Core behavior${receipt.authorized_artifact_count === 1 ? " is" : "s are"} now approved for ${connection.name} in this project.`
          : `${connection.name}-specific Core authority was removed for this project.`,
      );
      onClose();
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Temper could not change portable Core authority.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog.Root onOpenChange={(open) => (open ? undefined : onClose())} open>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="core-dialog connection-dialog">
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
              <dt>Learning</dt>
              <dd>{connection.sourceCapability}</dd>
            </div>
            <div>
              <dt>Delivery</dt>
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
                : "Learning observes eligible completed work in registered projects. Approved suggestions go to fresh Temper-managed tasks. With permission, style defaults can also reach ordinary Codex chats through native instructions or scoped MCP context. Native instruction updates apply to new chats or a supported reload; publication does not confirm delivery."}
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
                <h3 id="portable-core-title">Portable Core</h3>
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
                    <span>
                      No approved Core behaviors apply to this project.
                    </span>
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
                      Apply this exact{" "}
                      {connection.id === "claude" ? "Claude" : connection.name}
                      -specific selection for 30 days. This does not alter Core
                      or affect other agents.
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
                        Review behaviors
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
      </Dialog.Portal>
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
      <header className="page-topline">
        <div />
      </header>
      <SectionHeading
        title="Settings"
        description="Temper stays quiet by default. You decide what it can observe and share."
      />
      <SettingsGroup title="Learning">
        <Toggle
          checked={nativeRuntime ? backgroundLearning : learning}
          description={
            nativeRuntime
              ? "Capture explicit feedback for suggestions you review. Everyday habit learning is controlled on Today."
              : "Notice possible preferences in completed work from registered projects."
          }
          label={
            nativeRuntime
              ? "Capture for reviewed suggestions"
              : "Background learning"
          }
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
          description="Show a quiet notification when a decision is ready."
          label="Decision notifications"
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
        title={nativeRuntime ? "Privacy" : "Privacy and telemetry"}
      >
        <div className="privacy-summary">
          <ShieldCheck size={20} />
          <div>
            <strong>Evidence storage</strong>
            <span>
              {nativeRuntime && !secureStoreReady
                ? "Secure storage needs attention before Temper can learn or deliver."
                : "Evidence stays encrypted on this device for at most 30 days."}
            </span>
          </div>
          <Button onClick={() => setConsentOpen(true)} tone="quiet">
            View consent
          </Button>
        </div>
        {nativeRuntime ? (
          <Toggle
            checked={telemetryEnabled}
            description={
              telemetryEnabled
                ? "Reporting was previously allowed. You can turn it off; this build cannot upload new reports."
                : "Aggregate reporting is unavailable in this build. Nothing is uploaded."
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
            description="Send signed, raw-free product health counts. Off by default."
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
      <SettingsGroup title="Advanced">
        <Toggle
          checked={advancedMode}
          description="Show diagnostics, provenance metadata, and the governed task lab."
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
                Protect your Temper identity, approved learning, and governed
                history with a separate passphrase.
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
  onRenewConsent,
  renewalAvailable,
}: {
  consent: EngineDesktopSnapshot["consent"] | null;
  nativeRuntime: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
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
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="telemetry-dialog">
          <Dialog.Close
            aria-label="Close consent details"
            className="icon-button dialog-close"
          >
            <X size={18} />
          </Dialog.Close>
          <div className="dialog-heading-icon">
            <ShieldCheck size={20} />
          </div>
          <Dialog.Title>Local consent</Dialog.Title>
          <Dialog.Description>
            {nativeRuntime
              ? "This is the current governed consent state reported by your local Temper engine."
              : "This browser preview uses sample consent details and cannot change your local Temper installation."}
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
              label="Raw retention"
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
            <span>
              Evidence content stays encrypted locally. This screen never
              reveals raw prompts, repository paths, or signing material.
            </span>
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
      </Dialog.Portal>
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
      <Dialog.Portal>
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
      </Dialog.Portal>
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
          : "Temper could not run that governed task.",
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
        description="Start one fresh isolated Codex task with the smallest relevant projection. Your project is unchanged until you approve the diff."
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
          <span>
            Fresh Codex session · scoped projection · bounded tools · network
            denied
          </span>
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
            This is untrusted agent output. Review the diff and independent
            checks before applying anything.
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
          <p>Load a raw-free local instrument summary when you need it.</p>
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
