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

import { BotanicalFlourish } from "./BotanicalFlourish";
import { BrandMark } from "./BrandMark";
import { Button, Toggle } from "./ui";

const steps = ["Welcome", "Privacy", "Agents", "Projects", "Ready"];

export function Onboarding({ onComplete }: { onComplete: () => void }) {
  const [step, setStep] = useState(0);
  const [telemetry, setTelemetry] = useState(false);

  function next() {
    if (step === steps.length - 1) {
      onComplete();
      return;
    }
    setStep((current) => current + 1);
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
                detail="Signed in with ChatGPT"
                label="Codex"
                status="Connected"
              />
              <SetupRow
                detail="Console sign-in; provider-billed"
                label="Claude Code"
                status="Connect"
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
              <div className="project-monogram">K</div>
              <div>
                <strong>Kairn</strong>
                <span>~/projects/kairn</span>
              </div>
              <CheckCircle2 aria-label="Selected" size={20} />
            </div>
            <button className="text-action" type="button">
              + Add another project
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
                <span>Local identity created</span>
              </div>
              <div>
                <Check size={16} />
                <span>Codex connected</span>
              </div>
              <div>
                <Check size={16} />
                <span>Kairn registered prospectively</span>
              </div>
            </div>
            <Toggle
              checked={telemetry}
              description="Send raw-free product health counts. Preview everything before the first upload."
              label="Help improve Temper"
              onCheckedChange={setTelemetry}
            />
          </OnboardingPanel>
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
          icon={<ArrowRight aria-hidden="true" size={16} />}
          onClick={next}
          tone="primary"
        >
          {step === steps.length - 1 ? "Open Temper" : "Continue"}
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
        className={status === "Connected" ? "setup-status" : "text-action"}
        type="button"
      >
        {status}
      </button>
    </div>
  );
}
