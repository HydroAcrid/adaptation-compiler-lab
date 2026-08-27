import {
  ArrowLeft,
  ArrowRight,
  Bot,
  Check,
  CheckCircle2,
  FolderPlus,
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
import { Button, Toggle } from "./ui";

const steps = ["Welcome", "Privacy", "Agents", "Projects", "Ready"];

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
  const [message, setMessage] = useState<string | null>(null);
  const codex = setupSnapshot?.connections.find(
    (connection) => connection.agent_id === "codex",
  );
  const claude = setupSnapshot?.connections.find(
    (connection) => connection.agent_id === "claude",
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
        setMessage(null);
        try {
          await initializeSetup(
            project.preview_token,
            setupDigest,
            crypto.randomUUID(),
          );
          await onComplete();
        } catch (error: unknown) {
          setMessage(
            error instanceof Error
              ? error.message
              : "Temper could not safely finish setup.",
          );
        } finally {
          setBusy(false);
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
      setProject(await previewSetupProject());
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
      setExisting(await previewExistingInstallation());
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
    setMessage(null);
    try {
      await adoptExistingInstallation(
        existing.preview_token,
        setupDigest,
        crypto.randomUUID(),
      );
      await onComplete();
    } catch (error: unknown) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Temper could not safely use that installation.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="onboarding-shell">
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
            description="Temper learns how you work, turns approved feedback into small scoped adaptations, and carries them between coding agents."
            icon={<Radio size={28} strokeWidth={1.6} />}
            title="Your way of working, wherever you work."
          >
            <div className="onboarding-principles">
              <Principle text="Nothing becomes durable until you approve it." />
              <Principle text="Learning stays scoped, inspectable, and reversible." />
              <Principle text="Your raw evidence remains encrypted on this device." />
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
                  <button
                    className="text-action"
                    disabled={busy}
                    onClick={chooseExisting}
                    type="button"
                  >
                    Already use Temper? Choose your existing configuration
                  </button>
                )}
              </div>
            ) : null}
          </OnboardingPanel>
        ) : null}
        {step === 1 ? (
          <OnboardingPanel
            description="Temper creates a dedicated local identity and encrypts captured evidence. Keys are stored in this device's secure credential store."
            icon={<LockKeyhole size={28} strokeWidth={1.6} />}
            title="Local by design."
          >
            <div className="privacy-card">
              <div>
                <strong>30 days</strong>
                <span>maximum raw retention</span>
              </div>
              <div>
                <strong>Never</strong>
                <span>remote raw storage</span>
              </div>
              <div>
                <strong>Any time</strong>
                <span>revoke or pause</span>
              </div>
            </div>
          </OnboardingPanel>
        ) : null}
        {step === 2 ? (
          <OnboardingPanel
            description="Temper checks what is already installed. Connecting does not share credentials with Temper."
            icon={<Bot size={28} strokeWidth={1.6} />}
            title="Connect your coding agents."
          >
            <div className="setup-list">
              <SetupRow
                detail={codex?.status_summary ?? "Signed in with ChatGPT"}
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
            </div>
          </OnboardingPanel>
        ) : null}
        {step === 3 ? (
          <OnboardingPanel
            description="Temper only learns from projects you choose. Existing history stays out of scope."
            icon={<FolderPlus size={28} strokeWidth={1.6} />}
            title="Choose where Temper is active."
          >
            <div className="project-setup-card">
              <div className="project-monogram">
                {(project?.display_name ?? "Kairn")[0]}
              </div>
              <div>
                <strong>{project?.display_name ?? "Kairn"}</strong>
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
              disabled={busy}
              onClick={chooseProject}
              type="button"
            >
              {project ? "Choose a different project" : "+ Choose a project"}
            </button>
          </OnboardingPanel>
        ) : null}
        {step === 4 ? (
          <OnboardingPanel
            description="Temper will work quietly in the tray and only interrupt when a decision needs you."
            icon={<CheckCircle2 size={28} strokeWidth={1.6} />}
            title="Temper is ready."
          >
            <div className="ready-summary">
              <div>
                <Check size={16} />
                <span>Local identity and secure store will be created</span>
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
                  {project?.display_name ?? "Selected project"} will be
                  registered prospectively
                </span>
              </div>
            </div>
            <Toggle
              checked={consent}
              description="Authorize local construction, promotion, delivery, and audit for 30 days. You can revoke this later."
              label="I agree to local governed learning"
              onCheckedChange={setConsent}
            />
            <p className="connection-dialog-note">
              Learning, automatic promotion, telemetry, and launch at login all
              start off.
            </p>
          </OnboardingPanel>
        ) : null}
        {message ? (
          <p className="connection-dialog-note" role="alert">
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
          {busy
            ? "Finishing…"
            : step === steps.length - 1
              ? "Open Temper"
              : "Continue"}
        </Button>
      </footer>
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
      <button
        className={status === "Ready" ? "setup-status" : "text-action"}
        disabled
        type="button"
      >
        {status}
      </button>
    </div>
  );
}
