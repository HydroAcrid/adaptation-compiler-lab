import { AlertTriangle, LoaderCircle, RotateCcw } from "lucide-react";

import type { EngineClientFailure } from "../engine";
import { BotanicalFlourish } from "./BotanicalFlourish";
import { BrandMark } from "./BrandMark";

export function NativeStartup({
  failure,
  failureStage,
  onRetry,
}: {
  failure: EngineClientFailure | null;
  failureStage: "startup" | "refresh";
  onRetry: () => void;
}) {
  return (
    <div className="native-startup">
      <BotanicalFlourish placement="onboarding" />
      <header className="native-startup__header">
        <BrandMark />
      </header>
      <main className="native-startup__content">
        <div className="native-startup__mark" aria-hidden="true">
          {failure ? (
            <AlertTriangle size={25} strokeWidth={1.6} />
          ) : (
            <LoaderCircle className="native-startup__spinner" size={25} />
          )}
        </div>
        <h1>
          {failure
            ? failureStage === "refresh"
              ? "Temper could not refresh its local state."
              : "Temper could not open its local state."
            : "Opening Temper"}
        </h1>
        <p>
          {failure ? failure.message : "Loading your projects and preferences."}
        </p>
        {failure ? (
          <button
            className="folio-primary-action"
            onClick={onRetry}
            type="button"
          >
            Try again <RotateCcw aria-hidden="true" size={16} />
          </button>
        ) : null}
      </main>
    </div>
  );
}

export function DesktopHostRequired() {
  return (
    <div className="native-startup">
      <BotanicalFlourish placement="onboarding" />
      <header className="native-startup__header">
        <BrandMark />
      </header>
      <main className="native-startup__content">
        <div className="native-startup__mark" aria-hidden="true">
          <AlertTriangle size={25} strokeWidth={1.6} />
        </div>
        <h1>Open the Temper desktop app.</h1>
        <p>This page needs the desktop app to access your local Temper data.</p>
      </main>
    </div>
  );
}
