import {
  ArrowLeft,
  ArrowRight,
  Bot,
  Check,
  CheckCircle2,
  FolderPlus,
  LoaderCircle,
  LockKeyhole,
  Radio,
} from "lucide-react";
import { useState, type ReactNode } from "react";

import {
  adoptExistingInstallation,
  initializeSetup,
  previewExistingInstallation,
  previewSetupProject,
  type EngineExistingInstallationPreview,
  type EngineProjectPreview,
  type EngineSetupSnapshot,
} from "../engine";
import { BotanicalFlourish } from "./BotanicalFlourish";
import { BrandMark } from "./BrandMark";
import { RecoveryImportDialog } from "./RecoveryDialog";
import { Button, Toggle } from "./ui";

const steps = ["Welcome", "Privacy", "Agents", "Projects", "Ready"];
type SetupPhase = "idle" | "creating" | "adopting" | "opening";

export function Onboarding({
  onComplete,
  nativeRuntime = false,
  setupSnapshot = null,
  setupDigest = null,
}: {
  onComplete: () => void | Promise<void>;
  nativeRuntime?: boolean;
  setupSnapshot?: EngineSetupSnapshot | null;
  setupDigest?: string | null;
}) {
  const [step, setStep] = useState(0);
  const [consent, setConsent] = useState(false);
  const [project, setProject] = useState<EngineProjectPreview | null>(null);
  const [existing, setExisting] =
    useState<EngineExistingInstallationPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [setupPhase, setSetupPhase] = useState<SetupPhase>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [recoveryOpen, setRecoveryOpen] = useState(false);
  const codex = setupSnapshot?.connections.find(
    (connection) => connection.agent_id === "codex",
  );
  const claude = setupSnapshot?.connections.find(
    (connection) => connection.agent_id === "claude",
  );
  const copilot = setupSnapshot?.connections.find(
    (connection) => connection.agent_id === "copilot",
  );
  const codexReady =
    !nativeRuntime ||
    (codex?.authentication_state === "signed_in" &&
      codex.conformance_state === "compatible");

  async function next() {
    if (step === steps.length - 1) {
      if (nativeRuntime) {
        if (!project || !setupDigest || !consent) return;
        setBusy(true);
        setSetupPhase("creating");
        setMessage(null);
        try {
          await initializeSetup(
            project.preview_token,
            setupDigest,
            crypto.randomUUID(),
          );
          setSetupPhase("opening");
          await onComplete();
        } catch (error: unknown) {
          setMessage(
            error instanceof Error
              ? error.message
              : "Temper could not safely finish setup.",
          );
        } finally {
          setBusy(false);
          setSetupPhase("idle");
        }
      } else {
        await onComplete();
      }
      return;
    }
    setStep((current) => current + 1);
  }

  async function chooseProject() {
    if (!nativeRuntime) return;
    setBusy(true);
    setMessage(null);
    try {
      const preview = await previewSetupProject();
      if (preview) setProject(preview);
    } catch (error: unknown) {
      setMessage(
        error instanceof Error ? error.message : "Nothing was selected.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function chooseExisting() {
    if (!nativeRuntime) return;
    setBusy(true);
    setMessage(null);
    try {
      const preview = await previewExistingInstallation();
      if (preview) setExisting(preview);
    } catch (error: unknown) {
      setMessage(
        error instanceof Error ? error.message : "Nothing was selected.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function adoptExisting() {
    if (!existing || !setupDigest) return;
    setBusy(true);
    setSetupPhase("adopting");
    setMessage(null);
    try {
      await adoptExistingInstallation(
        existing.preview_token,
        setupDigest,
        crypto.randomUUID(),
      );
      setSetupPhase("opening");
      await onComplete();
    } catch (error: unknown) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Temper could not safely use that installation.",
      );
    } finally {
      setBusy(false);
      setSetupPhase("idle");
    }
  }

  if (nativeRuntime && setupPhase !== "idle") {
    return <SetupProgress phase={setupPhase} />;
  }

  return (
    <div
      className={`onboarding-shell ${nativeRuntime ? "" : "onboarding-shell--preview"}`}
    >
      {!nativeRuntime ? (
        <aside
          aria-label="Browser preview notice"
          className="browser-preview-banner"
        >
          Browser preview · sample data · controls do not change your local
          Temper state
        </aside>
      ) : null}
      <BotanicalFlourish placement="onboarding" />
      <header className="onboarding-header">
        <BrandMark />
        <span>
          {step + 1} of {steps.length}
        </span>
      </header>
      <nav
        className="onboarding-progress"
        aria-label={`Setup progress: step ${step + 1} of ${steps.length}`}
      >
        {steps.map((label, index) => (
          <span
            aria-current={index === step ? "step" : undefined}
            className={index <= step ? "onboarding-progress__active" : ""}
            key={label}
          />
        ))}
      </nav>
      <main className="onboarding-content">
        {step === 0 ? (
          <OnboardingPanel
            description="Learn communication habits from Codex chats and manage guidance for your coding agents."
            icon={<Radio size={28} strokeWidth={1.6} />}
            title="Set up Temper"
          >
            <div className="onboarding-principles">
              <Principle text="Choose the projects Temper can learn from." />
              <Principle text="Pause learning or undo a change." />
              <Principle text="Raw evidence is encrypted on this device." />
            </div>
            {nativeRuntime ? (
              <div className="existing-installation-card">
                {existing ? (
                  <>
                    <div>
                      <strong>Existing Temper found</strong>
                      <span>
                        {existing.installation.project_count} registered{" "}
                        {existing.installation.project_count === 1
                          ? "project"
                          : "projects"}
                      </span>
                      <span>
                        Identity{" "}
                        {existing.installation.signer_fingerprint.slice(7, 19)}…
                      </span>
                    </div>
                    <Button
                      disabled={busy}
                      onClick={adoptExisting}
                      tone="quiet"
                    >
                      Continue with this Temper
                    </Button>
                  </>
                ) : (
                  <div className="existing-installation-actions">
                    <button
                      className="text-action"
                      disabled={busy}
                      onClick={chooseExisting}
                      type="button"
                    >
                      Use an existing Temper on this device
                    </button>
                    <button
                      className="text-action"
                      disabled={busy || !setupDigest}
                      onClick={() => setRecoveryOpen(true)}
                      type="button"
                    >
                      Restore from an encrypted recovery file
                    </button>
                  </div>
                )}
              </div>
            ) : null}
          </OnboardingPanel>
        ) : null}
        {step === 1 ? (
          <OnboardingPanel
            description="Chat excerpts used for analysis are sent to your connected model. Temper encrypts raw evidence on this device and keeps its keys in system secure storage."
            icon={<LockKeyhole size={28} strokeWidth={1.6} />}
            title="Data and privacy"
          >
            <div className="privacy-card">
              <div>
                <strong>30 days</strong>
                <span>raw evidence retention</span>
              </div>
              <div>
                <strong>Your model</strong>
                <span>chat analysis</span>
              </div>
              <div>
                <strong>Your choice</strong>
                <span>learning starts off</span>
              </div>
            </div>
          </OnboardingPanel>
        ) : null}
        {step === 2 ? (
          <OnboardingPanel
            description="Temper checks what is already installed. It does not sign in, copy credentials, or change either agent."
            icon={<Bot size={28} strokeWidth={1.6} />}
            title="Check your coding agents."
          >
            <div className="setup-list">
              <SetupRow
                detail={codex?.status_summary ?? "Not checked"}
                label="Codex"
                status={codexReady ? "Ready" : "Needs attention"}
              />
              <SetupRow
                detail={
                  claude?.status_summary ??
                  "Not integrated in this Temper build"
                }
                label="Claude Code"
                status={
                  claude?.installation_state === "installed"
                    ? "Detected"
                    : "Not installed"
                }
              />
              {copilot || nativeRuntime ? (
                <SetupRow
                  detail={
                    copilot?.status_summary ??
                    "Repository instructions can be inspected after setup"
                  }
                  label="GitHub Copilot"
                  status={
                    copilot?.installation_state === "installed"
                      ? "Detected"
                      : "CLI not installed"
                  }
                />
              ) : null}
            </div>
          </OnboardingPanel>
        ) : null}
        {step === 3 ? (
          <OnboardingPanel
            description="Temper only learns from projects you choose. Existing history stays out of scope."
            icon={<FolderPlus size={28} strokeWidth={1.6} />}
            title="Register your first project."
          >
            <div className="project-setup-card">
              <div className="project-monogram">
                {project?.display_name[0] ?? "—"}
              </div>
              <div>
                <strong>
                  {project?.display_name ??
                    (nativeRuntime ? "No project selected" : "Example project")}
                </strong>
                <span>
                  {project
                    ? "Only new work after registration is eligible"
                    : nativeRuntime
                      ? "No project selected"
                      : "Example prospective project"}
                </span>
              </div>
              {project || !nativeRuntime ? (
                <CheckCircle2 aria-label="Selected" size={20} />
              ) : null}
            </div>
            <button
              className="text-action"
              disabled={busy || !nativeRuntime}
              onClick={chooseProject}
              type="button"
            >
              {nativeRuntime
                ? project
                  ? "Choose a different project"
                  : "+ Choose a project"
                : "Project selection is available in the desktop app"}
            </button>
          </OnboardingPanel>
        ) : null}
        {step === 4 ? (
          <OnboardingPanel
            description="Review what Temper will set up. Nothing starts running in the background yet."
            icon={<CheckCircle2 size={28} strokeWidth={1.6} />}
            title="Ready to set up Temper."
          >
            <div className="ready-summary">
              <div>
                <Check size={16} />
                <span>A secure local identity will be created</span>
              </div>
              <div>
                <Check size={16} />
                <span>
                  {codexReady ? "Codex is ready" : "Codex needs attention"}
                </span>
              </div>
              <div>
                <Check size={16} />
                <span>
                  {project?.display_name ?? "Your project"} will start with new
                  work only
                </span>
              </div>
            </div>
            <Toggle
              checked={consent}
              description="Allow new feedback to become suggestions for your review for 30 days. Revoke access at any time. Habit learning is enabled separately on Today."
              label="Allow reviewed suggestions in this project"
              onCheckedChange={setConsent}
            />
            <p className="onboarding-footnote">
              Learning, notifications, telemetry, and launch at sign-in stay off
              until you choose otherwise.
            </p>
          </OnboardingPanel>
        ) : null}
        {message ? (
          <p className="onboarding-message" role="alert">
            {message}
          </p>
        ) : null}
      </main>
      <footer className="onboarding-footer">
        <Button
          disabled={step === 0}
          icon={<ArrowLeft aria-hidden="true" size={16} />}
          onClick={() => setStep((current) => Math.max(0, current - 1))}
          tone="quiet"
        >
          Back
        </Button>
        <Button
          disabled={
            busy ||
            (step === 2 && !codexReady) ||
            (step === 3 && nativeRuntime && !project) ||
            (step === steps.length - 1 && nativeRuntime && !consent)
          }
          icon={<ArrowRight aria-hidden="true" size={16} />}
          onClick={next}
          tone="primary"
        >
          {busy && step === steps.length - 1
            ? "Finishing…"
            : step === steps.length - 1
              ? "Open Temper"
              : "Continue"}
        </Button>
      </footer>
      {nativeRuntime && setupDigest ? (
        <RecoveryImportDialog
          onOpenChange={setRecoveryOpen}
          onRestored={onComplete}
          open={recoveryOpen}
          setupDigest={setupDigest}
        />
      ) : null}
    </div>
  );
}

function SetupProgress({ phase }: { phase: Exclude<SetupPhase, "idle"> }) {
  const opening = phase === "opening";
  const adopting = phase === "adopting";
  const firstStage = adopting
    ? "Link existing Temper"
    : "Create local identity";
  return (
    <div className="setup-progress" aria-busy="true">
      <BotanicalFlourish placement="onboarding" />
      <header className="onboarding-header">
        <BrandMark />
        <span>{opening ? "2 of 2" : "1 of 2"}</span>
      </header>
      <div className="setup-progress__track" aria-hidden="true">
        <span className={opening ? "setup-progress__bar--complete" : ""} />
      </div>
      <main
        aria-live="polite"
        className="setup-progress__content"
        role="status"
      >
        <div className="setup-progress__mark" aria-hidden="true">
          <LoaderCircle className="setup-progress__spinner" size={28} />
        </div>
        <span className="setup-progress__stage">
          Step {opening ? "2" : "1"} of 2
        </span>
        <h1>
          {opening
            ? "Opening Temper"
            : adopting
              ? "Linking your existing Temper"
              : "Creating your Temper"}
        </h1>
        <p>
          {opening
            ? "Loading your project and preferences."
            : adopting
              ? "Reconnecting your existing Temper data."
              : "Setting up secure storage and registering your project."}
        </p>
        <div className="setup-progress__stages" aria-label="Setup stages">
          <div className={opening ? "setup-progress__stage-complete" : ""}>
            {opening ? (
              <Check aria-hidden="true" size={16} />
            ) : (
              <LoaderCircle
                aria-hidden="true"
                className="setup-progress__spinner"
                size={16}
              />
            )}
            <span>{firstStage}</span>
          </div>
          <div className={opening ? "setup-progress__stage-active" : ""}>
            {opening ? (
              <LoaderCircle
                aria-hidden="true"
                className="setup-progress__spinner"
                size={16}
              />
            ) : (
              <span aria-hidden="true" className="setup-progress__dot" />
            )}
            <span>Open your workspace</span>
          </div>
        </div>
        <small>Keep Temper open while setup finishes.</small>
      </main>
    </div>
  );
}

function OnboardingPanel({
  title,
  description,
  icon,
  children,
}: {
  title: string;
  description: string;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="onboarding-panel">
      <div className="onboarding-icon" aria-hidden="true">
        {icon}
      </div>
      <h1>{title}</h1>
      <p className="onboarding-description">{description}</p>
      {children}
    </section>
  );
}

function Principle({ text }: { text: string }) {
  return (
    <div>
      <Check size={16} strokeWidth={2} />
      <span>{text}</span>
    </div>
  );
}

function SetupRow({
  label,
  detail,
  status,
}: {
  label: string;
  detail: string;
  status: string;
}) {
  return (
    <div className="setup-row">
      <div>
        <strong>{label}</strong>
        <span>{detail}</span>
      </div>
      <span className={status === "Ready" ? "setup-status" : "setup-state"}>
        {status}
      </span>
    </div>
  );
}
