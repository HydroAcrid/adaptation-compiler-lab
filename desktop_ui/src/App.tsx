import * as Tooltip from "@radix-ui/react-tooltip";
import { useEffect, useState } from "react";

import { Onboarding } from "./components/Onboarding";
import {
  AdaptationsPage,
  AdvancedPage,
  ConnectionsPage,
  SettingsPage,
  TodayPage,
  TrayPreview,
} from "./components/pages";
import { ReviewDialog } from "./components/ReviewDialog";
import { Shell } from "./components/Shell";
import { suggestion } from "./data/demo";
import type { FeedbackValue, Screen, Theme } from "./types";

const supportedScreens = new Set<Screen>([
  "onboarding",
  "today",
  "suggestion",
  "adaptations",
  "connections",
  "settings",
  "advanced",
  "tray",
]);

function initialScreen(): Screen {
  const value = new URLSearchParams(window.location.search).get(
    "screen",
  ) as Screen | null;
  return value && supportedScreens.has(value) ? value : "today";
}

function initialTheme(): Theme {
  const value = new URLSearchParams(window.location.search).get("theme");
  return value === "dark" || value === "system" ? value : "light";
}

export default function App() {
  const [firstScreen] = useState(initialScreen);
  const [screen, setScreen] = useState<Screen>(firstScreen);
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [advancedMode, setAdvancedMode] = useState(firstScreen === "advanced");
  const [reviewOpen, setReviewOpen] = useState(firstScreen === "suggestion");
  const [feedback, setFeedback] = useState<FeedbackValue | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    const resolved =
      theme === "system"
        ? window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light"
        : theme;
    document.documentElement.dataset.theme = resolved;
  }, [theme]);

  function navigate(destination: Screen) {
    setScreen(destination);
    if (destination === "suggestion") setReviewOpen(true);
  }
  function decide(decision: "keep" | "project" | "ignore") {
    setReviewOpen(false);
    setScreen(decision === "ignore" ? "today" : "adaptations");
    setToast(
      decision === "keep"
        ? "Adaptation kept for all coding work."
        : decision === "project"
          ? "Adaptation kept for Kairn only."
          : "Suggestion ignored. Nothing changed.",
    );
  }

  if (screen === "onboarding")
    return <Onboarding onComplete={() => setScreen("today")} />;

  return (
    <Tooltip.Provider delayDuration={500}>
      <Shell advancedMode={advancedMode} onNavigate={navigate} screen={screen}>
        {screen === "today" || screen === "suggestion" || screen === "tray" ? (
          <TodayPage
            feedback={feedback}
            onFeedback={setFeedback}
            onReview={() => setReviewOpen(true)}
          />
        ) : null}
        {screen === "adaptations" ? <AdaptationsPage /> : null}
        {screen === "connections" ? <ConnectionsPage /> : null}
        {screen === "settings" ? (
          <SettingsPage
            advancedMode={advancedMode}
            onAdvancedModeChange={setAdvancedMode}
            onThemeChange={setTheme}
            theme={theme}
          />
        ) : null}
        {screen === "advanced" ? <AdvancedPage /> : null}
      </Shell>
      <ReviewDialog
        onDecision={decide}
        onOpenChange={setReviewOpen}
        open={reviewOpen}
        suggestion={suggestion}
      />
      {screen === "tray" ? (
        <TrayPreview onOpen={() => setReviewOpen(true)} />
      ) : null}
      {toast ? (
        <div className="toast" role="status">
          {toast}
          <button
            aria-label="Dismiss message"
            onClick={() => setToast(null)}
            type="button"
          >
            ×
          </button>
        </div>
      ) : null}
    </Tooltip.Provider>
  );
}
