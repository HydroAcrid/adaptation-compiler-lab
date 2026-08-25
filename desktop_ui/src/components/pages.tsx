import * as Dialog from "@radix-ui/react-dialog";
import {
  ArrowRight,
  Bell,
  Bot,
  Check,
  CheckCircle2,
  CircleHelp,
  Cloud,
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
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";

import { connections, coreItems, projects } from "../data/demo";
import type {
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
  const selectedSuggestion =
    suggestions.find((item) => item.id === selectedSuggestionId) ??
    suggestions[0];
  const hasSuggestion =
    workspace !== "Green Meadow" && Boolean(selectedSuggestion);
  const isAllProjects = workspace === "all";
  const selectedIndex = selectedSuggestion
    ? suggestions.findIndex((item) => item.id === selectedSuggestion.id)
    : -1;
  const suggestionCount = suggestions.length;
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
        <span>Monday, August 24</span>
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
                {suggestions.map((item, index) => (
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
              <h2>Was Temper useful?</h2>
              <p>One scoped behavior was included in a release handoff.</p>
              {feedback ? (
                <div className="feedback-thanks">
                  <Check aria-hidden="true" size={15} /> Recorded as {feedback}
                </div>
              ) : (
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
              )}
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
}: {
  activeWorkspace: WorkspaceScope;
}) {
  const [items, setItems] = useState(coreItems);
  const [kind, setKind] = useState<CoreKind | "all">("all");
  const [scope, setScope] = useState<ProjectName | "all">(activeWorkspace);
  const [selected, setSelected] = useState<CoreItem | null>(null);
  const [removed, setRemoved] = useState<{
    item: CoreItem;
    index: number;
  } | null>(null);
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
        <div className="core-current-project">
          <span>Workspace view</span>
          <strong>
            {activeWorkspace === "all" ? "All projects" : activeWorkspace}
          </strong>
        </div>
      </header>
      <section className="core-overview" aria-label="Core summary">
        <p>
          {activeWorkspace === "all" ? (
            <>
              <strong>{items.length} approved items</strong> across two
              projects. Shared guidance forms the trunk; project knowledge
              branches only where it applies.
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
            <option value="Kairn">Kairn</option>
            <option value="Green Meadow">Green Meadow</option>
          </select>
        </label>
      </div>
      {removed ? (
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
    </div>
  );
}

function CoreGroup({
  label,
  description,
  items,
  onEdit,
  onRemove,
}: {
  label: string;
  description: string;
  items: CoreItem[];
  onEdit: (item: CoreItem) => void;
  onRemove: (item: CoreItem) => void;
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
              <div className="core-entry__actions">
                <button onClick={() => onEdit(item)} type="button">
                  <Pencil aria-hidden="true" size={13} /> Edit
                </button>
                <button onClick={() => onRemove(item)} type="button">
                  Remove
                </button>
              </div>
            </article>
          </li>
        ))}
      </ul>
    </section>
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

export function ConnectionsPage() {
  const [selectedConnection, setSelectedConnection] =
    useState<AgentConnection | null>(null);
  return (
    <div className="page">
      <header className="page-topline">
        <div />
      </header>
      <SectionHeading
        title="Connections"
        description="Review where Temper can learn and where it can deliver adaptations."
      />
      <div className="native-action-note" role="note">
        <Laptop aria-hidden="true" size={16} />
        <span>
          This browser preview cannot change agent accounts or project folders.
          Those controls become available in the installed desktop app.
        </span>
      </div>
      <section className="connection-list">
        {connections.map((connection) => (
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
              disabled={connection.status !== "connected"}
              onClick={() => setSelectedConnection(connection)}
              tone={connection.status === "connected" ? "quiet" : "primary"}
            >
              {connection.status === "connected"
                ? "View details"
                : "Desktop setup"}
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
          <Button disabled icon={<Plus size={16} />}>
            Add in desktop app
          </Button>
        </div>
        <div className="project-list">
          {projects.map((project) => (
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
            Account changes require the installed desktop app. This preview is
            read-only.
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
}: {
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
  advancedMode: boolean;
  onAdvancedModeChange: (enabled: boolean) => void;
  automaticLearning: boolean;
  onAutomaticLearningChange: (enabled: boolean) => void;
}) {
  const [learning, setLearning] = useState(true);
  const [notifications, setNotifications] = useState(true);
  const [launch, setLaunch] = useState(false);
  const [telemetry, setTelemetry] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
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
          checked={learning}
          description="Notice possible preferences in completed work from registered projects."
          label="Background learning"
          onCheckedChange={setLearning}
        />
        <Toggle
          checked={notifications}
          description="Show a quiet notification when a decision is ready."
          label="Decision notifications"
          onCheckedChange={setNotifications}
        />
        <Toggle
          checked={automaticLearning}
          description="Keep only strong, low-impact project preferences. Temper notifies you and gives you 24 hours to undo."
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
          checked={launch}
          description="Keep Temper available in the tray after you sign in."
          label="Launch at sign-in"
          onCheckedChange={setLaunch}
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
          <Button tone="quiet">View consent</Button>
        </div>
        <Toggle
          checked={telemetry}
          description="Send signed, raw-free product health counts. Off by default."
          label="Help improve Temper"
          onCheckedChange={setTelemetry}
        />
        <div className="settings-links">
          <button onClick={() => setPreviewOpen(true)} type="button">
            Preview exact report
          </button>
          <button type="button">Upload history</button>
          <button className="danger-link" type="button">
            Delete cloud reports
          </button>
        </div>
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
    </div>
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
            <ReportRow label="App version" value="0.3.0a1" />
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

export function AdvancedPage() {
  const [running, setRunning] = useState(false);
  const [showDiff, setShowDiff] = useState(true);
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
          <select id="lab-project">
            <option>Kairn</option>
            <option>Green Meadow</option>
          </select>
        </div>
        <label className="lab-label" htmlFor="lab-task">
          Task
        </label>
        <textarea
          defaultValue="Review the release handoff and fix only the verified blocker."
          id="lab-task"
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
          onClick={() => {
            setRunning((value) => !value);
            setShowDiff(true);
          }}
          tone="primary"
        >
          {running ? "Stop task" : "Run task"}
        </Button>
      </section>
      {showDiff ? (
        <section className="diff-card">
          <div className="diff-heading">
            <div className="card-icon">
              <FileDiff size={18} />
            </div>
            <div>
              <h2>Review before applying</h2>
              <p>2 files changed. Nothing has touched Kairn yet.</p>
            </div>
            <StatusPill tone="positive">Checks passed</StatusPill>
          </div>
          <pre aria-label="Proposed code changes">
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
          </pre>
          <div className="diff-warning">
            <Info size={15} />
            <span>
              Apply succeeds only if the project is still at the reviewed commit
              and independent checks pass again.
            </span>
          </div>
          <div className="diff-actions">
            <Button icon={<Check size={16} />} tone="primary">
              Apply reviewed changes
            </Button>
            <Button onClick={() => setShowDiff(false)} tone="quiet">
              Discard
            </Button>
          </div>
        </section>
      ) : null}
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
