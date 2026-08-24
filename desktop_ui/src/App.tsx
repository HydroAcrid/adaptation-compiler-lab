import * as Tooltip from "@radix-ui/react-tooltip";
import { useEffect, useState } from "react";

import { Onboarding } from "./components/Onboarding";
import {
  AdvancedPage,
  ConnectionsPage,
  CorePage,
  SettingsPage,
  TodayPage,
  TrayPreview,
} from "./components/pages";
import { ReviewDialog } from "./components/ReviewDialog";
import { Shell } from "./components/Shell";
import { suggestions } from "./data/demo";
import type {
  FeedbackValue,
  ProjectName,
  Screen,
  Suggestion,
  SuggestionDecision,
  Theme,
} from "./types";

const supportedScreens = new Set<Screen>([
  "onboarding",
  "today",
  "suggestion",
  "core",
  "connections",
  "settings",
  "advanced",
  "tray",
]);

function initialScreen(): Screen {
  const rawValue = new URLSearchParams(window.location.search).get("screen");
  if (rawValue === "adaptations") return "core";
  const value = rawValue as Screen | null;
  return value && supportedScreens.has(value) ? value : "today";
}

function initialProject(): ProjectName {
  return new URLSearchParams(window.location.search).get("project") ===
    "green-meadow"
    ? "Green Meadow"
    : "Kairn";
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
  const [activeProject, setActiveProject] =
    useState<ProjectName>(initialProject);
  const [suggestionQueue, setSuggestionQueue] =
    useState<Suggestion[]>(suggestions);
  const [selectedSuggestionId, setSelectedSuggestionId] = useState(
    suggestions[0]?.id ?? "",
  );
  const [automaticLearning, setAutomaticLearning] = useState(false);
  const [feedback, setFeedback] = useState<FeedbackValue | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const selectedSuggestion =
    suggestionQueue.find((item) => item.id === selectedSuggestionId) ??
    suggestionQueue[0];

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");

    function applyTheme() {
      const resolved =
        theme === "system" ? (media.matches ? "dark" : "light") : theme;
      document.documentElement.dataset.theme = resolved;
      document
        .querySelector<HTMLMetaElement>('meta[name="theme-color"]')
        ?.setAttribute("content", resolved === "dark" ? "#161412" : "#f5f1ea");
    }

    applyTheme();
    if (theme !== "system") return;
    media.addEventListener("change", applyTheme);
    return () => media.removeEventListener("change", applyTheme);
  }, [theme]);

  function navigate(destination: Screen) {
    setScreen(destination);
    if (destination === "suggestion") setReviewOpen(true);
  }

  function reviewSuggestion(suggestionId: string) {
    setSelectedSuggestionId(suggestionId);
    setReviewOpen(true);
  }

  function decide(decision: SuggestionDecision) {
    if (!selectedSuggestion) return;
    const remaining = suggestionQueue.filter(
      (item) => item.id !== selectedSuggestion.id,
    );
    setSuggestionQueue(remaining);
    setSelectedSuggestionId(remaining[0]?.id ?? "");
    setReviewOpen(false);
    setScreen(decision === "ignore" ? "today" : "core");
    const suggestedScope = selectedSuggestion.suggestedScope;
    setToast(
      decision === "suggested"
        ? suggestedScope === "All projects"
          ? "Adaptation kept for all projects."
          : `Adaptation kept for ${suggestedScope}.`
        : decision === "project"
          ? `Adaptation kept for ${activeProject} only.`
          : "Suggestion ignored. Nothing changed.",
    );
  }

  if (screen === "onboarding")
    return <Onboarding onComplete={() => setScreen("today")} />;

  return (
    <Tooltip.Provider delayDuration={500}>
      <Shell
        activeProject={activeProject}
        advancedMode={advancedMode}
        onNavigate={navigate}
        onProjectChange={setActiveProject}
        screen={screen}
      >
        {screen === "today" || screen === "suggestion" || screen === "tray" ? (
          <TodayPage
            automaticLearning={automaticLearning}
            feedback={feedback}
            onFeedback={setFeedback}
            onOpenCore={() => navigate("core")}
            onReview={reviewSuggestion}
            project={activeProject}
            selectedSuggestionId={selectedSuggestion?.id ?? null}
            suggestions={suggestionQueue}
          />
        ) : null}
        {screen === "core" ? <CorePage activeProject={activeProject} /> : null}
        {screen === "connections" ? <ConnectionsPage /> : null}
        {screen === "settings" ? (
          <SettingsPage
            advancedMode={advancedMode}
            automaticLearning={automaticLearning}
            onAdvancedModeChange={setAdvancedMode}
            onAutomaticLearningChange={setAutomaticLearning}
            onThemeChange={setTheme}
            theme={theme}
          />
        ) : null}
        {screen === "advanced" ? <AdvancedPage /> : null}
      </Shell>
      {selectedSuggestion ? (
        <ReviewDialog
          activeProject={activeProject}
          onDecision={decide}
          onOpenChange={setReviewOpen}
          open={reviewOpen}
          suggestion={selectedSuggestion}
        />
      ) : null}
      {screen === "tray" ? (
        <TrayPreview
          onOpen={() =>
            selectedSuggestion
              ? reviewSuggestion(selectedSuggestion.id)
              : undefined
          }
        />
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
