import { AlertTriangle, RotateCcw } from "lucide-react";

import type { EngineClientFailure } from "../engine";
import { BrandMark } from "./BrandMark";
import { Button, LoadingStatus } from "./ui";

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
      <header className="native-startup__header">
        <BrandMark />
      </header>
      <main className="native-startup__content">
        {failure ? (
          <AlertTriangle
            aria-hidden="true"
            className="native-startup__mark"
            size={24}
            strokeWidth={1.7}
          />
        ) : null}
        <h1>
          {failure
            ? failureStage === "refresh"
              ? "Temper could not refresh its local state."
              : "Temper could not open its local state."
            : "Opening Temper"}
        </h1>
        {failure ? (
          <>
            <p>{failure.message}</p>
            <Button
              icon={<RotateCcw aria-hidden="true" size={16} />}
              onClick={onRetry}
              tone="primary"
              type="button"
            >
              Try again
            </Button>
          </>
        ) : (
          <LoadingStatus>Loading your projects and preferences…</LoadingStatus>
        )}
      </main>
    </div>
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
