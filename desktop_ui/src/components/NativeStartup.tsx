import { AlertTriangle, RotateCcw } from "lucide-react";

import type { EngineClientFailure } from "../engine";
import { BrandMark } from "./BrandMark";
import { WorkspaceFrame } from "./Shell";
import { Button, LoadingStatus } from "./ui";

export function NativeStartup({
  advancedMode,
  failure,
  onRetry,
}: {
  advancedMode: boolean;
  failure: EngineClientFailure | null;
  onRetry: () => void;
}) {
  return (
    <WorkspaceFrame advancedMode={advancedMode} page="today">
      <div className="page folio-page folio-page--today">
        <header className="today-learning-heading">
          <h1>
            {failure
              ? "Temper could not open its local state."
              : "Opening Temper"}
          </h1>
        </header>
        {failure ? (
          <section aria-label="Startup error" className="startup-error">
            <p role="alert">{failure.message}</p>
            <Button
              icon={<RotateCcw aria-hidden="true" size={16} />}
              onClick={onRetry}
              tone="primary"
              type="button"
            >
              Try again
            </Button>
          </section>
        ) : (
          <div className="startup-placeholder">
            <div className="startup-placeholder__section">
              <LoadingStatus>
                Loading your projects and preferences…
              </LoadingStatus>
              <div aria-hidden="true" className="startup-placeholder__row">
                <span />
                <span />
              </div>
              <div aria-hidden="true" className="startup-placeholder__row">
                <span />
              </div>
            </div>
            <div aria-hidden="true" className="startup-placeholder__section">
              <span className="startup-placeholder__heading" />
              <div className="startup-placeholder__row">
                <span />
              </div>
            </div>
            <div aria-hidden="true" className="startup-placeholder__section">
              <span className="startup-placeholder__heading" />
            </div>
          </div>
        )}
      </div>
    </WorkspaceFrame>
  );
}

export function DesktopHostRequired() {
  return (
    <div className="native-startup">
      <header className="native-startup__header">
        <BrandMark />
      </header>
      <main className="native-startup__content">
        <AlertTriangle
          aria-hidden="true"
          className="native-startup__mark"
          size={24}
          strokeWidth={1.7}
        />
        <h1>Open the Temper desktop app.</h1>
        <p>This page needs the desktop app to access your local Temper data.</p>
      </main>
    </div>
  );
}
