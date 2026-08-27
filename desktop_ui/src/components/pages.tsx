import * as Dialog from "@radix-ui/react-dialog";
import {
  ArrowRight,
  Bell,
  Bot,
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
  MoreHorizontal,
  Pause,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Sun,
  Upload,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";

import { connections, coreItems, projects } from "../data/demo";
import {
  previewProjectRegistration,
  registerProject,
  runModeTask,
  type EngineAgentConnection,
  type EngineProjectPreview,
  type EngineProject,
  type EngineRecentUndo,
  type EngineTaskResult,
  type EngineDiagnostics,
  type EngineDesktopSnapshot,
} from "../engine";
import type {
  CapabilityModeSummary,
  CoreItem,
  CoreKind,
  EvidenceStrength,
  FeedbackValue,
  AgentConnection,
  ProjectName,
  Suggestion,
  Theme,
  WorkspaceScope,
} from "../types";
import { ProfilePortabilityDialog } from "./ProfilePortabilityDialog";
import { Button, Divider, SectionHeading, StatusPill, Toggle } from "./ui";

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
    pendingFeedbackCount: number;
    pendingReviewCount: number;
    projectCount: number;
    message?: string;
  };
}) {
  const applicableSuggestions =
    workspace === "all"
      ? suggestions
      : suggestions.filter(
          (item) =>
            item.suggestedScope === "All projects" ||
            item.suggestedScope.split(", ").includes(workspace),
        );
  const selectedSuggestion =
    applicableSuggestions.find((item) => item.id === selectedSuggestionId) ??
    applicableSuggestions[0];
  const hasSuggestion = Boolean(selectedSuggestion);
  const isAllProjects = workspace === "all";
  const selectedIndex = selectedSuggestion
    ? suggestions.findIndex((item) => item.id === selectedSuggestion.id)
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
  return (
    <div className="page folio-page folio-page--today">
      <header className="folio-page-meta">
        <span>
          {new Intl.DateTimeFormat(undefined, {
            dateStyle: "full",
          }).format(new Date())}
        </span>
        <button
          aria-label="Notifications"
          className="folio-icon-button"
          type="button"
        >
          <Bell aria-hidden="true" size={17} strokeWidth={1.6} />
        </button>
      </header>
      <section className="folio-statement" aria-labelledby="today-heading">
        <div className="folio-statement__line">
          <h1 id="today-heading">
            {isAllProjects
              ? "Temper is active across your work."
              : `Temper is active in ${workspace}.`}
          </h1>
        </div>
        <p>
          {liveSummary
            ? (liveSummary.message ??
              `${liveSummary.activeAdaptationCount} approved adaptation${liveSummary.activeAdaptationCount === 1 ? " is" : "s are"} available across ${liveSummary.projectCount} project${liveSummary.projectCount === 1 ? "" : "s"}.`)
            : isAllProjects
              ? `${suggestionCount} suggestions are ready in Kairn. Green Meadow has nothing waiting.`
              : hasSuggestion
                ? suggestionCount === 1
                  ? "Approved guidance is ready when it is relevant. One suggestion needs your attention."
                  : `${suggestionCount} suggestions are ready. Temper has put the clearest one first.`
                : "Approved guidance is ready when it is relevant. Nothing needs your review."}
        </p>
      </section>
      <div className="folio-divider" aria-hidden="true">
        <span />
      </div>
      <section className="folio-workbench" aria-label="Current thought">
        <article className="folio-proposal">
          {hasSuggestion ? (
            <>
              <span className="folio-kicker">
                {isAllProjects ? "Kairn · " : ""}Suggestion {selectedIndex + 1}{" "}
                of {suggestionCount}
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
              <span className="folio-kicker">Current project</span>
              <h2>
                {liveSummary
                  ? liveSummary.health === "ready"
                    ? `${isAllProjects ? "Your work" : workspace} is ready.`
                    : "Temper needs your attention."
                  : "Green Meadow is ready."}
              </h2>
              {liveSummary ? (
                <p>
                  {liveSummary.pendingReviewCount
                    ? `${liveSummary.pendingReviewCount} suggestion${liveSummary.pendingReviewCount === 1 ? " is" : "s are"} waiting for review.`
                    : "Nothing needs your review right now."}
                </p>
              ) : (
                <>
                  <blockquote>“Use PowerShell 7 for release work.”</blockquote>
                  <p>
                    One project memory and the relevant shared guidance are
                    available here. Kairn-only knowledge stays out.
                  </p>
                </>
              )}
              <button
                className="folio-primary-action"
                onClick={onOpenCore}
                type="button"
              >
                View in Core <ArrowRight aria-hidden="true" size={16} />
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
                    {
                      evidenceStrengthLabels[
                        selectedSuggestion?.evidenceStrength ?? "developing"
                      ]
                    }
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
                      : "Seven approved items"}
                  </dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>
                    {liveSummary
                      ? liveSummary.health === "ready"
                        ? "Ready"
                        : "Needs attention"
                      : "Ready"}
                  </dd>
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
                          {evidenceStrengthLabels[item.evidenceStrength]}
                        </small>
                      </span>
                    </button>
                  </li>
                ))}
              </ol>
            </div>
          ) : (
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
                  <button onClick={() => onFeedback("helped")} type="button">
                    Helped
                  </button>
                  <button onClick={() => onFeedback("hurt")} type="button">
                    Hurt
                  </button>
                  <button
                    onClick={() => onFeedback("irrelevant")}
                    type="button"
                  >
                    Irrelevant
                  </button>
                </div>
              ) : null}
            </div>
          )}
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
    id: "skill",
    label: "Skills",
    description: "Reusable guidance for a kind of work.",
  },
];

export function CorePage({
  activeWorkspace,
  availableWorkspaces,
  initialItems = coreItems,
  nativeRuntime = false,
  snapshotDigest = null,
  onNotice,
  onRevoke,
  recentUndo,
  onUndo,
}: {
  activeWorkspace: WorkspaceScope;
  availableWorkspaces?: ProjectName[];
  initialItems?: CoreItem[];
  nativeRuntime?: boolean;
  snapshotDigest?: string | null;
  onNotice?: (message: string) => void;
  onRevoke?: (artifactId: string) => Promise<void>;
  recentUndo?: EngineRecentUndo;
  onUndo?: () => Promise<void>;
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
  const workspaceChoices = availableWorkspaces ?? ["Kairn", "Green Meadow"];
  const visibleItems = items.filter(
    (item) =>
      (kind === "all" || item.kind === kind) &&
      (scope === "all" || item.scope === "Everywhere" || item.scope === scope),
  );

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
            <button onClick={() => setPortabilityMode("export")} type="button">
              <Download aria-hidden="true" size={14} /> Export
            </button>
            <button onClick={() => setPortabilityMode("import")} type="button">
              <Upload aria-hidden="true" size={14} /> Import
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
                  items.filter(
                    (item) =>
                      item.scope === "Everywhere" ||
                      item.scope === activeWorkspace,
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
        <label className="core-scope-filter">
          <span>Show for</span>
          <select
            onChange={(event) =>
              setScope(event.target.value as ProjectName | "all")
            }
            value={scope}
          >
            <option value="all">All projects</option>
            {workspaceChoices.map((workspace) => (
              <option key={workspace} value={workspace}>
                {workspace}
              </option>
            ))}
          </select>
        </label>
      </div>
      {nativeRuntime && recentUndo ? (
        <div className="undo-banner">
          <span>{recentUndo.summary}</span>
          <button onClick={() => void onUndo?.()} type="button">
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
    </div>
  );
}

function CoreGroup({
  label,
  description,
  items,
  onEdit,
  onRemove,
  onRevoke,
  readOnly,
}: {
  label: string;
  description: string;
  items: CoreItem[];
  onEdit: (item: CoreItem) => void;
  onRemove: (item: CoreItem) => void;
  onRevoke: (item: CoreItem) => void;
  readOnly: boolean;
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
                  <button onClick={() => onRevoke(item)} type="button">
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
                void onConfirm().finally(() => setBusy(false));
              }}
              tone="primary"
            >
              Revoke adaptation
            </Button>
          </div>
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
  snapshotDigest,
}: {
  modes: CapabilityModeSummary[];
  nativeRuntime: boolean;
  loading: boolean;
  error: string | null;
  onOpenCore: () => void;
  onTaskComplete: (message: string) => void;
  projects: Array<{ id: string; label: string }>;
  snapshotDigest: string | null;
}) {
  const [selected, setSelected] = useState<CapabilityModeSummary | null>(null);
  return (
    <div className="page folio-page modes-page">
      <header className="modes-heading">
        <div>
          <span className="folio-kicker">Temporary expertise</span>
          <h1>Modes</h1>
          <p>
            Give an agent a focused way of working for one task. Your permanent
            Core stays yours and stays unchanged.
          </p>
        </div>
        <Compass aria-hidden="true" size={30} strokeWidth={1.25} />
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
                Built-in · v{mode.mode_version}
              </span>
              <h2>{mode.name}</h2>
              <p>{mode.summary}</p>
              <div className="mode-card__facts">
                <span>One task</span>
                <span>{mode.projection_utf8_bytes} bytes</span>
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
          projects={modeProjects}
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
  projects: modeProjects,
  snapshotDigest,
}: {
  mode: CapabilityModeSummary;
  nativeRuntime: boolean;
  onClose: () => void;
  onComplete: (message: string) => void;
  projects: Array<{ id: string; label: string }>;
  snapshotDigest: string | null;
}) {
  const [projectId, setProjectId] = useState(modeProjects[0]?.id ?? "");
  const [task, setTask] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canRun = Boolean(
    nativeRuntime && snapshotDigest && projectId && task.trim() && !busy,
  );

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
      onComplete(
        result.review_available
          ? `${mode.name} finished and was removed. Changes are ready for review.`
          : `${mode.name} finished and was removed.`,
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
              <dt>Life span</dt>
              <dd>One exact managed task, then clean removal</dd>
            </div>
            <div>
              <dt>Works with</dt>
              <dd>{mode.compatible_target_families.join(" and ")}</dd>
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
              <dt>Validation</dt>
              <dd>
                {mode.evaluation_valid
                  ? `${mode.evaluation_case_count} conformance checks passed`
                  : "Needs attention"}
              </dd>
            </div>
          </dl>
          <div className="mode-authority-note">
            Your request, project rules, security constraints, and Core always
            outrank Mode defaults.
          </div>
          <div className="mode-task-form">
            <label className="core-field">
              <span>Project</span>
              <select
                disabled={!nativeRuntime}
                onChange={(event) => setProjectId(event.target.value)}
                value={projectId}
              >
                {modeProjects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="core-field">
              <span>Task</span>
              <textarea
                disabled={!nativeRuntime}
                onChange={(event) => setTask(event.target.value)}
                placeholder="Describe the frontend work for this one managed task"
                rows={3}
                value={task}
              />
            </label>
            <p>
              Uses a fresh isolated Codex session and your saved ChatGPT
              authentication. Changes return for review; the Mode is removed
              whether the task succeeds or fails.
            </p>
            {error ? (
              <div className="portability-error" role="alert">
                {error}
              </div>
            ) : null}
          </div>
          <div className="core-dialog__actions">
            <Button onClick={onClose} tone="quiet">
              Close
            </Button>
            <Button disabled={!canRun} onClick={startTask} tone="primary">
              {busy
                ? "Running isolated task…"
                : nativeRuntime
                  ? "Run with this Mode"
                  : "Available in desktop app"}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function CoreItemDialog({
  item,
  onClose,
  onSave,
}: {
  item: CoreItem;
  onClose: () => void;
  onSave: (item: CoreItem) => void;
}) {
  const [title, setTitle] = useState(item.title);
  const [description, setDescription] = useState(item.description);
  const [scope, setScope] = useState<CoreItem["scope"]>(item.scope);
  const allowedScopes: CoreItem["scope"][] =
    item.scope === "Everywhere"
      ? ["Everywhere", "Kairn", "Green Meadow"]
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
          <label className="core-field">
            <span>Use in</span>
            <select
              onChange={(event) =>
                setScope(event.target.value as CoreItem["scope"])
              }
              value={scope}
            >
              {allowedScopes.map((allowedScope) => (
                <option key={allowedScope} value={allowedScope}>
                  {allowedScope}
                </option>
              ))}
            </select>
          </label>
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
  snapshotDigest = null,
  onProjectRegistered,
}: {
  nativeRuntime?: boolean;
  liveConnections?: EngineAgentConnection[];
  liveProjects?: EngineProject[];
  snapshotDigest?: string | null;
  onProjectRegistered?: (message: string) => void | Promise<void>;
}) {
  const [selectedConnection, setSelectedConnection] =
    useState<AgentConnection | null>(null);
  const [projectPreview, setProjectPreview] =
    useState<EngineProjectPreview | null>(null);
  const [projectBusy, setProjectBusy] = useState(false);
  const [projectMessage, setProjectMessage] = useState<string | null>(null);
  const shownConnections: AgentConnection[] = liveConnections
    ? liveConnections.map((connection) => ({
        authDescription: connection.status_summary,
        costDescription: connection.cost_posture,
        id: connection.agent_id,
        name: connection.display_name,
        sourceCapability: connection.learning_capability,
        status:
          connection.agent_id === "codex" &&
          connection.authentication_state === "signed_in" &&
          connection.conformance_state === "compatible"
            ? "connected"
            : connection.installation_state === "installed"
              ? "attention"
              : "available",
        targetCapability: connection.delivery_capability,
      }))
    : connections;
  const shownProjects = liveProjects
    ? liveProjects.map((project) => ({
        connectedAgents: ["Codex"],
        id: project.project_id,
        name: project.display_name,
        pathLabel: "Prospectively registered",
      }))
    : projects;

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
              <Bot size={22} />
            </div>
            <div className="connection-main">
              <div className="connection-title">
                <h2>{connection.name}</h2>
                <StatusPill
                  tone={
                    connection.status === "connected" ? "positive" : "neutral"
                  }
                >
                  {connection.status === "connected"
                    ? "Connected"
                    : "Available"}
                </StatusPill>
              </div>
              <p>
                {connection.authDescription} · {connection.costDescription}
              </p>
              <div className="capability-list">
                <div>
                  <CheckCircle2 size={15} />
                  <span>{connection.sourceCapability}</span>
                </div>
                <div>
                  <CheckCircle2 size={15} />
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
            <h2>Active projects</h2>
            <p>Only new work after registration is eligible.</p>
          </div>
          <Button
            disabled={!nativeRuntime || !snapshotDigest || projectBusy}
            icon={<Plus size={16} />}
            onClick={chooseProject}
          >
            Add project
          </Button>
        </div>
        <div className="project-list">
          {shownProjects.map((project) => (
            <div className="project-row" key={project.id}>
              <div className="project-monogram">{project.name[0]}</div>
              <div className="project-row__copy">
                <strong>{project.name}</strong>
                <span>{project.pathLabel}</span>
              </div>
              <span className="agent-chip">
                {project.connectedAgents.join(", ")}
              </span>
              <button
                aria-label={`Manage ${project.name}`}
                className="icon-button"
                disabled
                title="Project management requires the installed desktop app"
                type="button"
              >
                <MoreHorizontal size={18} />
              </button>
            </div>
          ))}
        </div>
      </section>
      {selectedConnection ? (
        <ConnectionDetailsDialog
          connection={selectedConnection}
          onClose={() => setSelectedConnection(null)}
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
  onClose,
}: {
  connection: AgentConnection;
  onClose: () => void;
}) {
  return (
    <Dialog.Root onOpenChange={(open) => (open ? undefined : onClose())} open>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="core-dialog connection-dialog">
          <Dialog.Close aria-label="Close" className="dialog-close">
            <X size={18} />
          </Dialog.Close>
          <span className="folio-kicker">Connected agent</span>
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
          </dl>
          <p className="connection-dialog-note">
            {connection.id === "claude"
              ? "Detection does not connect Claude to Temper or authorize provider-billed use."
              : "Temper can learn only from prospectively registered completed work and deliver only to fresh Temper-managed tasks."}
          </p>
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
  onGovernedPreferencesChange,
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
  onGovernedPreferencesChange?: (
    learningEnabled: boolean,
    reportingEnabled: boolean,
    notificationsEnabled: boolean,
    launchAtLoginEnabled: boolean,
  ) => Promise<void>;
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
          description="Notice possible preferences in completed work from registered projects."
          label="Background learning"
          onCheckedChange={(enabled) => {
            setLearning(enabled);
            if (nativeRuntime) {
              void onGovernedPreferencesChange?.(
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
          onCheckedChange={(enabled) => {
            setNotifications(enabled);
            if (nativeRuntime) {
              void onGovernedPreferencesChange?.(
                backgroundLearning,
                telemetryEnabled,
                enabled,
                launchAtLoginEnabled,
              );
            }
          }}
        />
        <Toggle
          checked={automaticLearning}
          description={
            nativeRuntime
              ? "Not enabled in this build. Every proposed adaptation still receives a governed review."
              : "Keep only strong, low-impact project preferences. Temper notifies you and gives you 24 hours to undo."
          }
          disabled={nativeRuntime}
          label="Automatic low-risk learning"
          onCheckedChange={onAutomaticLearningChange}
        />
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
          onCheckedChange={(enabled) => {
            setLaunch(enabled);
            if (nativeRuntime) {
              void onGovernedPreferencesChange?.(
                backgroundLearning,
                telemetryEnabled,
                decisionNotificationsEnabled,
                enabled,
              );
            }
          }}
        />
      </SettingsGroup>
      <SettingsGroup title="Privacy and telemetry">
        <div className="privacy-summary">
          <ShieldCheck size={20} />
          <div>
            <strong>Local evidence, encrypted</strong>
            <span>
              Raw evidence is retained for at most 30 days and is never included
              in telemetry.
            </span>
          </div>
          <Button onClick={() => setConsentOpen(true)} tone="quiet">
            View consent
          </Button>
        </div>
        <Toggle
          checked={nativeRuntime ? telemetryEnabled : telemetry}
          description={
            nativeRuntime
              ? telemetryEnabled
                ? "Permission was enabled previously, but cloud reporting is unavailable in this build. You can turn the permission off; nothing is uploaded."
                : "Cloud reporting is not available in this internal build. Nothing is uploaded."
              : "Send signed, raw-free product health counts. Off by default."
          }
          disabled={nativeRuntime && !telemetryEnabled}
          label="Help improve Temper"
          onCheckedChange={(enabled) => {
            setTelemetry(enabled);
            if (nativeRuntime) {
              void onGovernedPreferencesChange?.(
                backgroundLearning,
                enabled,
                decisionNotificationsEnabled,
                launchAtLoginEnabled,
              );
            }
          }}
        />
        {nativeRuntime ? (
          <p className="settings-availability-note">
            Report preview, history, and deletion will appear only when the
            signed reporting service is enabled in a future build.
          </p>
        ) : (
          <div className="settings-links">
            <button onClick={() => setPreviewOpen(true)} type="button">
              Preview sample report
            </button>
            <span>Browser preview only</span>
          </div>
        )}
      </SettingsGroup>
      <SettingsGroup title="Advanced">
        <Toggle
          checked={advancedMode}
          description="Show diagnostics, provenance metadata, and the governed task lab."
          label="Advanced mode"
          onCheckedChange={onAdvancedModeChange}
        />
      </SettingsGroup>
      <TelemetryDialog onOpenChange={setPreviewOpen} open={previewOpen} />
      <ConsentDialog
        consent={consent}
        nativeRuntime={nativeRuntime}
        onOpenChange={setConsentOpen}
        open={consentOpen}
      />
    </div>
  );
}

function ConsentDialog({
  consent,
  nativeRuntime,
  open,
  onOpenChange,
}: {
  consent: EngineDesktopSnapshot["consent"] | null;
  nativeRuntime: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
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
              value={`${consent?.retention_days ?? 30} days`}
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
            <Button onClick={() => onOpenChange(false)} tone="primary">
              Done
            </Button>
          </div>
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
  taskResult = null,
  diagnostics = null,
  onRun,
  onApply,
  onDiscard,
  onDiagnostics,
}: {
  nativeRuntime?: boolean;
  projects?: Array<{ id: string; label: string }>;
  taskResult?: EngineTaskResult | null;
  diagnostics?: EngineDiagnostics | null;
  onRun?: (projectId: string, task: string) => Promise<void>;
  onApply?: () => Promise<void>;
  onDiscard?: () => Promise<void>;
  onDiagnostics?: () => Promise<void>;
}) {
  const [running, setRunning] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [showDiff, setShowDiff] = useState(true);
  const [task, setTask] = useState(
    "Review the release handoff and fix only the verified blocker.",
  );
  const [projectId, setProjectId] = useState(liveProjects[0]?.id ?? "");
  const [error, setError] = useState<string | null>(null);
  const browserReview = !nativeRuntime && showDiff;
  const review = taskResult?.change_review;
  const selectedProjectId = projectId || liveProjects[0]?.id || "";

  async function run() {
    if (!nativeRuntime) {
      setShowDiff(true);
      return;
    }
    if (!selectedProjectId || !task.trim() || !onRun) return;
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
        title="Governed task lab"
        description="Run one fresh isolated task with the smallest relevant projection. Your project is unchanged until you approve the diff."
      />
      <section className="lab-card">
        <div className="lab-field-row">
          <label htmlFor="lab-project">Project</label>
          <select
            id="lab-project"
            onChange={(event) => setProjectId(event.target.value)}
            value={nativeRuntime ? selectedProjectId : "kairn"}
          >
            {(nativeRuntime
              ? liveProjects
              : [
                  { id: "kairn", label: "Kairn" },
                  { id: "green-meadow", label: "Green Meadow" },
                ]
            ).map((project) => (
              <option key={project.id} value={project.id}>
                {project.label}
              </option>
            ))}
          </select>
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
            running || (nativeRuntime && (!selectedProjectId || !task.trim()))
          }
          onClick={() => void run()}
          tone="primary"
        >
          {running ? "Running…" : "Run task"}
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
                  : "2 files changed. Nothing has touched Kairn yet."}
              </p>
            </div>
            <StatusPill tone={nativeRuntime ? "neutral" : "positive"}>
              {nativeRuntime ? "Review ready" : "Checks passed"}
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
              disabled={resolving}
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
        <Button onClick={() => void onDiagnostics?.()} tone="quiet">
          Refresh diagnostics
        </Button>
      </section>
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
        <button aria-label="Dismiss notification" type="button">
          <X size={15} />
        </button>
      </aside>
      <aside aria-label="Temper tray menu" className="tray-menu">
        <div className="tray-header">
          <span aria-hidden="true" className="tray-brand-mark" />
          <div>
            <strong>Temper</strong>
            <span>
              <i /> Active in Kairn
            </span>
          </div>
        </div>
        <Divider />
        <button onClick={onOpen} type="button">
          <Sparkles size={16} />
          <span>Review suggestion</span>
          <b>1</b>
        </button>
        <button type="button">
          <Pause size={16} />
          <span>Pause Temper</span>
        </button>
        <Divider />
        <button type="button">
          <ExternalLink size={16} />
          <span>Open Temper</span>
        </button>
        <button type="button">
          <CircleHelp size={16} />
          <span>Help</span>
        </button>
        <Divider />
        <button type="button">
          <X size={16} />
          <span>Quit</span>
        </button>
      </aside>
    </>
  );
}
