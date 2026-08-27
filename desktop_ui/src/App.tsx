import * as Tooltip from "@radix-ui/react-tooltip";
import { useEffect, useState } from "react";

import { Onboarding } from "./components/Onboarding";
import {
  AdvancedPage,
  ConnectionsPage,
  CorePage,
  ModesPage,
  SettingsPage,
  TodayPage,
  TrayPreview,
} from "./components/pages";
import { ReviewDialog } from "./components/ReviewDialog";
import { Shell } from "./components/Shell";
import { suggestions } from "./data/demo";
import {
  isTauriRuntime,
  loadEngineHandshake,
  loadEngineSnapshot,
  loadModes,
  loadSetupSnapshot,
  type EngineDesktopSnapshot,
  type EngineSetupSnapshot,
} from "./engine";
import type {
  CapabilityModeSummary,
  CoreItem,
  CoreKind,
  FeedbackValue,
  Screen,
  Suggestion,
  SuggestionDecision,
  Theme,
  WorkspaceScope,
} from "./types";

const supportedScreens = new Set<Screen>([
  "onboarding",
  "today",
  "suggestion",
  "core",
  "modes",
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

function initialWorkspace(): WorkspaceScope {
  const value = new URLSearchParams(window.location.search).get("project");
  if (value === "green-meadow") return "Green Meadow";
  if (value === "kairn") return "Kairn";
  return "all";
}

function initialTheme(): Theme {
  const value = new URLSearchParams(window.location.search).get("theme");
  return value === "dark" || value === "system" ? value : "light";
}

export default function App() {
  const [nativeRuntime] = useState(isTauriRuntime);
  const [firstScreen] = useState(initialScreen);
  const [screen, setScreen] = useState<Screen>(firstScreen);
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [advancedMode, setAdvancedMode] = useState(firstScreen === "advanced");
  const [reviewOpen, setReviewOpen] = useState(firstScreen === "suggestion");
  const [activeWorkspace, setActiveWorkspace] =
    useState<WorkspaceScope>(initialWorkspace);
  const [suggestionQueue, setSuggestionQueue] = useState<Suggestion[]>(
    nativeRuntime ? [] : suggestions,
  );
  const [selectedSuggestionId, setSelectedSuggestionId] = useState(
    suggestions[0]?.id ?? "",
  );
  const [automaticLearning, setAutomaticLearning] = useState(false);
  const [feedback, setFeedback] = useState<FeedbackValue | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [engineSnapshot, setEngineSnapshot] =
    useState<EngineDesktopSnapshot | null>(null);
  const [snapshotDigest, setSnapshotDigest] = useState<string | null>(null);
  const [setupSnapshot, setSetupSnapshot] =
    useState<EngineSetupSnapshot | null>(null);
  const [setupDigest, setSetupDigest] = useState<string | null>(null);
  const [modeCatalog, setModeCatalog] = useState<CapabilityModeSummary[]>(
    nativeRuntime ? [] : browserModes,
  );
  const [engineError, setEngineError] = useState<string | null>(null);
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

  useEffect(() => {
    if (!nativeRuntime) return;
    let active = true;
    loadEngineHandshake()
      .then(async (handshake) => {
        if (!handshake.configured) {
          const setup = await loadSetupSnapshot();
          if (active) {
            setSetupSnapshot(setup.snapshot);
            setSetupDigest(setup.snapshotDigest);
            setScreen("onboarding");
          }
          return;
        }
        const [{ snapshot, snapshotDigest: digest }, modes, setup] =
          await Promise.all([
            loadEngineSnapshot(),
            loadModes(),
            loadSetupSnapshot(),
          ]);
        if (!active) return;
        setEngineSnapshot(snapshot);
        setSnapshotDigest(digest);
        setModeCatalog(modes);
        setSetupSnapshot(setup.snapshot);
        setSetupDigest(setup.snapshotDigest);
      })
      .catch((error: unknown) => {
        if (active) {
          setEngineError(
            error instanceof Error
              ? error.message
              : "Temper could not load your local state.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [nativeRuntime]);

  async function finishOnboarding() {
    if (!nativeRuntime) {
      setScreen("today");
      return;
    }
    const [{ snapshot, snapshotDigest: digest }, modes, setup] =
      await Promise.all([
        loadEngineSnapshot(),
        loadModes(),
        loadSetupSnapshot(),
      ]);
    setEngineSnapshot(snapshot);
    setSnapshotDigest(digest);
    setModeCatalog(modes);
    setSetupSnapshot(setup.snapshot);
    setSetupDigest(setup.snapshotDigest);
    setEngineError(null);
    setScreen("today");
  }

  const workspaces = engineSnapshot?.projects.map((project) => ({
    id: project.display_name,
    label: project.display_name,
    description: project.registered_prospectively
      ? "Connected"
      : "Needs review",
  }));
  const liveCoreItems = engineSnapshot
    ? engineSnapshot.terminal.active_adaptations.map((item) =>
        coreItemFromEngine(item, engineSnapshot),
      )
    : undefined;

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
          ? `Adaptation kept for ${selectedSuggestion.sourceProject} only.`
          : "Suggestion ignored. Nothing changed.",
    );
  }

  async function refreshAfterNativeAction(message: string) {
    setToast(message);
    if (!nativeRuntime) return;
    try {
      const [{ snapshot, snapshotDigest: digest }, modes, setup] =
        await Promise.all([
          loadEngineSnapshot(),
          loadModes(),
          loadSetupSnapshot(),
        ]);
      setEngineSnapshot(snapshot);
      setSnapshotDigest(digest);
      setModeCatalog(modes);
      setSetupSnapshot(setup.snapshot);
      setSetupDigest(setup.snapshotDigest);
      setEngineError(null);
    } catch (error: unknown) {
      setEngineError(
        error instanceof Error
          ? error.message
          : "Temper could not refresh your local state.",
      );
    }
  }

  if (screen === "onboarding")
    return (
      <Onboarding
        nativeRuntime={nativeRuntime}
        onComplete={finishOnboarding}
        setupDigest={setupDigest}
        setupSnapshot={setupSnapshot}
      />
    );

  return (
    <Tooltip.Provider delayDuration={500}>
      <Shell
        activeWorkspace={activeWorkspace}
        advancedMode={advancedMode}
        onNavigate={navigate}
        onWorkspaceChange={setActiveWorkspace}
        screen={screen}
        workspaces={workspaces}
      >
        {screen === "today" || screen === "suggestion" || screen === "tray" ? (
          <TodayPage
            automaticLearning={automaticLearning}
            feedback={feedback}
            onFeedback={setFeedback}
            onOpenCore={() => navigate("core")}
            onReview={reviewSuggestion}
            workspace={activeWorkspace}
            selectedSuggestionId={selectedSuggestion?.id ?? null}
            suggestions={suggestionQueue}
            liveSummary={
              engineSnapshot
                ? {
                    activeAdaptationCount:
                      engineSnapshot.terminal.review_mode.active_artifact_count,
                    health: engineSnapshot.health,
                    pendingFeedbackCount:
                      engineSnapshot.terminal.review_mode.metrics
                        .pending_feedback_count,
                    pendingReviewCount:
                      engineSnapshot.terminal.review_mode.metrics
                        .pending_review_count,
                    projectCount: engineSnapshot.projects.length,
                  }
                : nativeRuntime
                  ? {
                      activeAdaptationCount: 0,
                      health: engineError ? "needs_attention" : "paused",
                      pendingFeedbackCount: 0,
                      pendingReviewCount: 0,
                      projectCount: 0,
                      message:
                        engineError ?? "Temper is opening your local work…",
                    }
                  : undefined
            }
          />
        ) : null}
        {screen === "core" ? (
          <CorePage
            activeWorkspace={activeWorkspace}
            availableWorkspaces={engineSnapshot?.projects.map(
              (project) => project.display_name,
            )}
            initialItems={liveCoreItems}
            key={`${activeWorkspace}-${snapshotDigest ?? "browser"}`}
            nativeRuntime={nativeRuntime}
            onNotice={setToast}
            snapshotDigest={snapshotDigest}
          />
        ) : null}
        {screen === "modes" ? (
          <ModesPage
            error={nativeRuntime ? engineError : null}
            loading={nativeRuntime && !engineError && !engineSnapshot}
            modes={modeCatalog}
            nativeRuntime={nativeRuntime}
            onOpenCore={() => navigate("core")}
            onTaskComplete={refreshAfterNativeAction}
            projects={
              engineSnapshot?.projects.map((project) => ({
                id: project.project_id,
                label: project.display_name,
              })) ?? [
                { id: "kairn", label: "Kairn" },
                { id: "green-meadow", label: "Green Meadow" },
              ]
            }
            snapshotDigest={snapshotDigest}
          />
        ) : null}
        {screen === "connections" ? (
          <ConnectionsPage
            liveConnections={setupSnapshot?.connections}
            liveProjects={engineSnapshot?.projects}
            nativeRuntime={nativeRuntime}
            onProjectRegistered={refreshAfterNativeAction}
            snapshotDigest={snapshotDigest}
          />
        ) : null}
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

const browserModes: CapabilityModeSummary[] = [
  {
    activation_default: "one_task",
    applicable_task_classes: [
      "design_system",
      "frontend_design",
      "frontend_implementation",
    ],
    compatible_target_families: ["claude-code", "codex"],
    evaluation_case_count: 6,
    evaluation_valid: true,
    mode_id: "frontend-studio",
    mode_version: "1.0.0",
    mutates_permanent_core: false,
    name: "Frontend Studio",
    projection_utf8_bytes: 1128,
    requested_tools: [],
    summary:
      "A focused frontend workflow for distinctive, accessible, responsive product interfaces.",
  },
];

function coreItemFromEngine(
  item: EngineDesktopSnapshot["terminal"]["active_adaptations"][number],
  snapshot: EngineDesktopSnapshot,
): CoreItem {
  const projectNames = item.scope.project_ids.map(
    (projectId) =>
      snapshot.projects.find((project) => project.project_id === projectId)
        ?.display_name ?? projectId,
  );
  return {
    description: item.required_behaviors.join(" "),
    id: item.artifact_id,
    kind: coreKind(item.artifact_type),
    scope: projectNames.length ? projectNames.join(", ") : "Everywhere",
    sourceSummary: `Approved from ${item.evidence_count} supporting source${item.evidence_count === 1 ? "" : "s"}`,
    title: item.intent,
  };
}

function coreKind(value: string): CoreKind {
  if (value === "preference" || value === "memory") return value;
  if (value === "procedure" || value === "prompt_rule") return "procedure";
  return "skill";
}
