import * as Dialog from "@radix-ui/react-dialog";
import {
  Activity,
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
  LockKeyhole,
  Moon,
  MoreHorizontal,
  Pause,
  Play,
  Plus,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Sun,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";

import { adaptations, connections, projects } from "../data/demo";
import type { FeedbackValue, Theme } from "../types";
import { Button, Divider, SectionHeading, StatusPill, Toggle } from "./ui";

export function TodayPage({
  onReview,
  feedback,
  onFeedback,
}: {
  onReview: () => void;
  feedback: FeedbackValue | null;
  onFeedback: (value: FeedbackValue) => void;
}) {
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
        <span className="folio-kicker">Current state · Kairn</span>
        <div className="folio-statement__line">
          <h1 id="today-heading">Temper is active in Kairn.</h1>
          <div
            className="maker-status"
            aria-label="One approved behavior active"
          >
            <span aria-hidden="true">T</span>
            <span>
              1 behavior
              <br />
              in scope
            </span>
          </div>
        </div>
        <p>
          Your approved way of working is ready for the next relevant Codex
          task. One new preference is waiting for your judgment.
        </p>
      </section>
      <div className="folio-divider" aria-hidden="true">
        <span />
      </div>
      <section className="folio-workbench" aria-label="Current thought">
        <article className="folio-proposal">
          <span className="folio-kicker">Possible adaptation · 01</span>
          <h2>A preference may be taking shape.</h2>
          <blockquote>“Lead with the purpose before setup steps.”</blockquote>
          <p>
            Temper noticed the same direction in two approved corrections. It
            has not changed your profile.
          </p>
          <button
            className="folio-primary-action"
            onClick={onReview}
            type="button"
          >
            Review suggestion <ArrowRight aria-hidden="true" size={16} />
          </button>
        </article>
        <aside className="folio-margin" aria-label="Suggestion notes">
          <dl className="margin-register">
            <div>
              <dt>01 · Scope</dt>
              <dd>Suggested: all coding work</dd>
            </div>
            <div>
              <dt>02 · Source</dt>
              <dd>Two approved corrections</dd>
            </div>
            <div>
              <dt>03 · Delivery</dt>
              <dd>Not delivered</dd>
            </div>
          </dl>
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
                <button onClick={() => onFeedback("irrelevant")} type="button">
                  Irrelevant
                </button>
              </div>
            )}
          </div>
        </aside>
      </section>
      <footer className="projection-register" aria-label="Current projection">
        <span>
          <b>Personal</b> 1
        </span>
        <span>
          <b>Project</b> Kairn
        </span>
        <span>
          <b>Preset</b> none
        </span>
        <span className="projection-register__target">
          <b>Destination</b> Codex
        </span>
        <button className="projection-refresh" type="button">
          <Activity aria-hidden="true" size={14} /> Checked 4 min ago
        </button>
      </footer>
    </div>
  );
}

export function AdaptationsPage() {
  const [revoked, setRevoked] = useState<string[]>([]);
  const active = adaptations.filter((item) => !revoked.includes(item.id));
  const global = active.filter((item) => item.scope === "All coding work");
  const project = active.filter((item) => item.scope !== "All coding work");
  return (
    <div className="page folio-page folio-page--adaptations">
      <header className="folio-page-heading">
        <div>
          <span className="folio-kicker">Behavior folio · 02</span>
          <h1>Adaptations</h1>
          <p>The approved clauses Temper can carry into relevant work.</p>
        </div>
        <Button icon={<Plus size={16} />} tone="quiet">
          Add manually
        </Button>
      </header>
      {revoked.length ? (
        <div className="undo-banner">
          <span>One clause was withdrawn from the active folio.</span>
          <button onClick={() => setRevoked([])} type="button">
            <RotateCcw size={14} /> Undo
          </button>
        </div>
      ) : null}
      <AdaptationGroup
        index="01"
        label="Everywhere"
        items={global}
        onRevoke={(id) => setRevoked((items) => [...items, id])}
      />
      <AdaptationGroup
        index="02"
        label="Kairn only"
        items={project}
        onRevoke={(id) => setRevoked((items) => [...items, id])}
      />
      <footer className="folio-footnote">
        <LockKeyhole aria-hidden="true" size={15} />
        <span>
          Source conversations remain encrypted locally. This folio contains
          only approved behavioral clauses and raw-free lineage summaries.
        </span>
      </footer>
    </div>
  );
}

function AdaptationGroup({
  index,
  label,
  items,
  onRevoke,
}: {
  index: string;
  label: string;
  items: typeof adaptations;
  onRevoke: (id: string) => void;
}) {
  if (!items.length) return null;
  return (
    <section className="adaptation-chapter">
      <header className="adaptation-chapter__heading">
        <span>{index} · Scope</span>
        <h2>{label}</h2>
        <p>
          {items.length} approved {items.length === 1 ? "clause" : "clauses"}
        </p>
      </header>
      <ol className="clause-list">
        {items.map((item, itemIndex) => (
          <li key={item.id}>
            <article className="behavior-clause">
              <span className="clause-number" aria-hidden="true">
                {index}.{itemIndex + 1}
              </span>
              <div className="clause-copy">
                <strong>{item.behavior}</strong>
                <span>
                  <sup>{itemIndex + 1}</sup> {item.sourceSummary}
                </span>
              </div>
              <div className="clause-approval">
                <span aria-hidden="true">T</span>
                Approved
              </div>
              <button
                className="revoke-link"
                onClick={() => onRevoke(item.id)}
                type="button"
              >
                Revoke
              </button>
            </article>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function ConnectionsPage() {
  return (
    <div className="page">
      <header className="page-topline">
        <div />
      </header>
      <SectionHeading
        title="Connections"
        description="Choose where Temper can learn and where it can deliver adaptations."
      />
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
              tone={connection.status === "connected" ? "quiet" : "primary"}
            >
              {connection.status === "connected" ? "Manage" : "Connect"}
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
          <Button icon={<Plus size={16} />}>Add project</Button>
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
                type="button"
              >
                <MoreHorizontal size={18} />
              </button>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export function SettingsPage({
  theme,
  onThemeChange,
  advancedMode,
  onAdvancedModeChange,
}: {
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
  advancedMode: boolean;
  onAdvancedModeChange: (enabled: boolean) => void;
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
          <span className="tray-brand-mark">t</span>
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
