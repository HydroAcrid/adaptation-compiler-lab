import * as Tooltip from "@radix-ui/react-tooltip";
import { useEffect, useState } from "react";

import { Onboarding } from "./components/Onboarding";
import { DesktopHostRequired, NativeStartup } from "./components/NativeStartup";
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
import {
  connections as demoConnections,
  coreItems as demoCoreItems,
  modeProjects as browserProjects,
  modes as browserModes,
  projects as demoProjects,
  suggestions as demoSuggestions,
  workspaceOptions as browserWorkspaceOptions,
} from "./data/demo";
import {
  isTauriRuntime,
  decideEngineSuggestion,
  loadEngineHandshake,
  loadEngineSnapshot,
  loadInstructionEnvironments,
  loadModes,
  loadSetupSnapshot,
  inspectConnections,
  recordEngineFeedback,
  renewEngineConsent,
  runManagedTask,
  applyManagedTask,
  discardManagedTask,
  loadDiagnostics,
  normalizeEngineFailure,
  revokeEngineAdaptation,
  undoEngineAdaptation,
  updateEnginePreferences,
  type EngineSuggestion,
  type EngineDesktopSnapshot,
  type EngineSetupSnapshot,
  type EngineTaskResult,
  type EngineDiagnostics,
  type EngineClientFailure,
  type EngineInstructionEnvironmentSummary,
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

type NavigationDirection = "backward" | "forward" | "neutral";

const navigationPositions: Partial<Record<Screen, number>> = {
  today: 0,
  suggestion: 0,
  tray: 0,
  core: 1,
  modes: 2,
  connections: 3,
  settings: 4,
  advanced: 5,
};

function navigationPosition(screen: Screen): number | null {
  return navigationPositions[screen] ?? null;
}

function initialScreen(): Screen {
  const rawValue = new URLSearchParams(window.location.search).get("screen");
  if (rawValue === "adaptations") return "core";
  const value = rawValue as Screen | null;
  return value && supportedScreens.has(value) ? value : "today";
}

function initialWorkspace(): WorkspaceScope {
  if (!import.meta.env.DEV) return "all";
  const value = new URLSearchParams(window.location.search).get("project");
  if (value === "green-meadow") return "Green Meadow";
  if (value === "kairn") return "Kairn";
  return "all";
}

function initialTheme(): Theme {
  const value = new URLSearchParams(window.location.search).get("theme");
  if (value === "light" || value === "dark" || value === "system") {
    return value;
  }
  const saved = window.localStorage.getItem("temper.theme");
  return saved === "dark" || saved === "system" ? saved : "light";
}

export default function App() {
  const [nativeRuntime] = useState(isTauriRuntime);
  const browserPreviewRuntime = !nativeRuntime && import.meta.env.DEV;
  const [firstScreen] = useState<Screen>(() =>
    nativeRuntime ? "today" : initialScreen(),
  );
  const [screen, setScreen] = useState<Screen>(firstScreen);
  const [navigationDirection, setNavigationDirection] =
    useState<NavigationDirection>("neutral");
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [advancedMode, setAdvancedMode] = useState(
    firstScreen === "advanced" ||
      window.localStorage.getItem("temper.advanced") === "true",
  );
  const [reviewOpen, setReviewOpen] = useState(firstScreen === "suggestion");
  const [activeWorkspace, setActiveWorkspace] =
    useState<WorkspaceScope>(initialWorkspace);
  const [suggestionQueue, setSuggestionQueue] = useState<Suggestion[]>(
    browserPreviewRuntime ? demoSuggestions : [],
  );
  const [selectedSuggestionId, setSelectedSuggestionId] = useState(
    browserPreviewRuntime ? (demoSuggestions[0]?.id ?? "") : "",
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
    browserPreviewRuntime ? browserModes : [],
  );
  const [bootstrapState, setBootstrapState] = useState<
    "loading" | "onboarding" | "ready" | "error"
  >(nativeRuntime ? "loading" : "ready");
  const [bootstrapAttempt, setBootstrapAttempt] = useState(0);
  const [engineFailure, setEngineFailure] =
    useState<EngineClientFailure | null>(null);
  const [failureStage, setFailureStage] = useState<"startup" | "refresh">(
    "startup",
  );
  const [taskResult, setTaskResult] = useState<EngineTaskResult | null>(null);
  const [diagnostics, setDiagnostics] = useState<EngineDiagnostics | null>(
    null,
  );
  const [instructionEnvironments, setInstructionEnvironments] = useState<
    EngineInstructionEnvironmentSummary[]
  >([]);
  const displayedSuggestions = engineSnapshot
    ? engineSnapshot.suggestions.map((item) =>
        suggestionFromEngine(item, engineSnapshot),
      )
    : suggestionQueue;
  const selectedSuggestion =
    displayedSuggestions.find((item) => item.id === selectedSuggestionId) ??
    displayedSuggestions[0];

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
    window.localStorage.setItem("temper.theme", theme);
    if (theme !== "system") return;
    media.addEventListener("change", applyTheme);
    return () => media.removeEventListener("change", applyTheme);
  }, [theme]);

  useEffect(() => {
    window.localStorage.setItem("temper.advanced", String(advancedMode));
  }, [advancedMode]);

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
            setBootstrapState("onboarding");
          }
          return;
        }
        const [
          { snapshot, snapshotDigest: digest },
          modes,
          setup,
          environments,
        ] = await Promise.all([
          loadEngineSnapshot(),
          loadModes(),
          loadSetupSnapshot(),
          loadInstructionEnvironments(),
        ]);
        if (!active) return;
        setEngineSnapshot(snapshot);
        setSnapshotDigest(digest);
        setModeCatalog(modes);
        setSetupSnapshot(setup.snapshot);
        setSetupDigest(setup.snapshotDigest);
        setInstructionEnvironments(environments);
        setBootstrapState("ready");
      })
      .catch((error: unknown) => {
        if (active) {
          setFailureStage("startup");
          setEngineFailure(
            normalizeEngineFailure(
              error,
              "Temper could not load your local state.",
            ),
          );
          setBootstrapState("error");
        }
      });
    return () => {
      active = false;
    };
  }, [bootstrapAttempt, nativeRuntime]);

  async function finishOnboarding() {
    if (browserPreviewRuntime) {
      setScreen("today");
      return;
    }
    const [{ snapshot, snapshotDigest: digest }, modes, setup, environments] =
      await Promise.all([
        loadEngineSnapshot(),
        loadModes(),
        loadSetupSnapshot(),
        loadInstructionEnvironments(),
      ]);
    setEngineSnapshot(snapshot);
    setSnapshotDigest(digest);
    setModeCatalog(modes);
    setSetupSnapshot(setup.snapshot);
    setSetupDigest(setup.snapshotDigest);
    setInstructionEnvironments(environments);
    setEngineFailure(null);
    setBootstrapState("ready");
    setScreen("today");
  }

  const workspaces = engineSnapshot?.projects.map((project) => ({
    id: project.display_name,
    label: project.display_name,
    description: project.registered_prospectively
      ? "Registered for new work"
      : "Needs review",
  }));
  const liveCoreItems = engineSnapshot
    ? engineSnapshot.adaptations.map((item) =>
        coreItemFromEngine(item, engineSnapshot),
      )
    : undefined;
  const selectedProjectId =
    activeWorkspace === "all"
      ? null
      : (engineSnapshot?.projects.find(
          (project) => project.display_name === activeWorkspace,
        )?.project_id ?? null);
  const scopedAdaptationCount = liveCoreItems
    ? liveCoreItems.filter(
        (item) =>
          activeWorkspace === "all" ||
          item.isGlobal === true ||
          item.projectNames?.includes(activeWorkspace),
      ).length
    : 0;
  const scopedSuggestionCount = displayedSuggestions.filter(
    (item) =>
      activeWorkspace === "all" ||
      item.isGlobal === true ||
      item.projectNames?.includes(activeWorkspace) ||
      item.suggestedScope === "All projects" ||
      item.suggestedScope === "All registered projects",
  ).length;
  const secureStoreReady = setupSnapshot?.secure_store.status === "ready";
  const governedActionsAvailable = Boolean(
    engineSnapshot &&
    engineSnapshot.health !== "consent_expired" &&
    secureStoreReady,
  );
  const governedMutationUnavailableReason = !secureStoreReady
    ? "Secure storage must be available before Temper can save governed changes."
    : engineSnapshot?.health === "consent_expired"
      ? "Renew local consent before Temper can save governed changes."
      : null;
  const taskRunnerProjects =
    engineSnapshot?.projects.filter((project) => project.task_runner_enabled) ??
    [];
  const codexConnectionReady = Boolean(
    setupSnapshot?.connections.some(
      (connection) =>
        connection.agent_id === "codex" &&
        connection.authentication_state === "signed_in" &&
        connection.conformance_state === "compatible",
    ),
  );
  const managedTaskUnavailableReason = !secureStoreReady
    ? "Secure storage must be available before Temper can deliver a managed task."
    : engineSnapshot?.health === "consent_expired"
      ? "Renew local consent before Temper can deliver a managed task."
      : !codexConnectionReady
        ? "A compatible Codex installation signed in with ChatGPT is required."
        : taskRunnerProjects.length === 0
          ? "Register a project that allows managed tasks before running this Mode."
          : null;

  function transitionTo(destination: Screen) {
    if (destination === screen) return;
    const currentPosition = navigationPosition(screen);
    const destinationPosition = navigationPosition(destination);
    setNavigationDirection(
      currentPosition === null ||
        destinationPosition === null ||
        currentPosition === destinationPosition
        ? "neutral"
        : destinationPosition > currentPosition
          ? "forward"
          : "backward",
    );
    setScreen(destination);
  }

  function navigate(destination: Screen) {
    transitionTo(destination);
    if (destination === "suggestion") setReviewOpen(true);
  }

  function reviewSuggestion(suggestionId: string) {
    setSelectedSuggestionId(suggestionId);
    setReviewOpen(true);
  }

  async function decide(
    decision: SuggestionDecision,
    projectNames: string[] = [],
  ) {
    if (!selectedSuggestion) return;
    if (nativeRuntime && engineSnapshot && snapshotDigest) {
      const suggestion = engineSnapshot.suggestions.find(
        (item) => item.queue_id === selectedSuggestion.id,
      );
      if (!suggestion) return;
      const selectedProjectIds = projectNames
        .map(
          (projectName) =>
            engineSnapshot.projects.find(
              (project) => project.display_name === projectName,
            )?.project_id,
        )
        .filter((projectId): projectId is string => Boolean(projectId))
        .sort();
      const projectId =
        selectedProjectIds[0] ??
        projectIdForSuggestion(suggestion, engineSnapshot, activeWorkspace);
      const engineDecision =
        decision === "suggested"
          ? suggestion.signal_kind === "revocation"
            ? "approve_revocation"
            : "keep_suggested"
          : decision === "project"
            ? "keep_project"
            : decision === "narrowed"
              ? "keep_narrowed"
              : suggestion.signal_kind === "revocation"
                ? "reject_revocation"
                : "ignore";
      if (!suggestion.available_actions.includes(engineDecision)) {
        throw new Error("That decision is not available for this suggestion.");
      }
      if (decision === "project" && !projectId) {
        throw new Error("Choose one registered project first.");
      }
      if (decision === "narrowed" && selectedProjectIds.length === 0) {
        throw new Error("Choose at least one registered project first.");
      }
      try {
        const receipt = await decideEngineSuggestion(
          suggestion,
          engineDecision,
          snapshotDigest,
          crypto.randomUUID(),
          decision === "project" && projectId
            ? { projectId }
            : decision === "narrowed"
              ? {
                  refinedScope: {
                    ...suggestion.suggested_scope,
                    project_ids: selectedProjectIds,
                  },
                }
              : {},
        );
        setReviewOpen(false);
        transitionTo(decision === "ignore" ? "today" : "core");
        await refreshAfterNativeAction(receipt.message);
      } catch (error: unknown) {
        const failure = normalizeEngineFailure(
          error,
          "Temper could not safely save that decision.",
        );
        await refreshAfterNativeAction(failure.message);
        throw new Error(failure.message);
      }
      return;
    }
    const remaining = suggestionQueue.filter(
      (item) => item.id !== selectedSuggestion.id,
    );
    setSuggestionQueue(remaining);
    setSelectedSuggestionId(remaining[0]?.id ?? "");
    setReviewOpen(false);
    transitionTo(decision === "ignore" ? "today" : "core");
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

  async function recordFeedback(value: FeedbackValue) {
    if (!nativeRuntime || !engineSnapshot || !snapshotDigest) {
      setFeedback(value);
      return;
    }
    const activation = engineSnapshot.activation_feedback[0];
    if (!activation) return;
    try {
      const receipt = await recordEngineFeedback(
        activation,
        value,
        snapshotDigest,
        crypto.randomUUID(),
      );
      setFeedback(value);
      await refreshAfterNativeAction(receipt.message);
    } catch (error: unknown) {
      await refreshAfterNativeAction(
        error instanceof Error
          ? error.message
          : "Temper could not safely record that feedback.",
      );
    }
  }

  async function revokeAdaptation(artifactId: string) {
    if (!engineSnapshot || !snapshotDigest) return;
    const adaptation = engineSnapshot.adaptations.find(
      (item) => item.artifact_id === artifactId,
    );
    if (!adaptation) return;
    try {
      const receipt = await revokeEngineAdaptation(
        adaptation,
        snapshotDigest,
        crypto.randomUUID(),
      );
      await refreshAfterNativeAction(receipt.message);
    } catch (error: unknown) {
      const failure = normalizeEngineFailure(
        error,
        "Temper could not safely revoke that adaptation.",
      );
      await refreshAfterNativeAction(failure.message);
      throw new Error(failure.message);
    }
  }

  async function undoRecentAdaptation() {
    if (!engineSnapshot || !snapshotDigest) return;
    const undo = engineSnapshot.recent_undos[0];
    if (!undo) return;
    try {
      const receipt = await undoEngineAdaptation(
        undo,
        snapshotDigest,
        crypto.randomUUID(),
      );
      await refreshAfterNativeAction(receipt.message);
    } catch (error: unknown) {
      await refreshAfterNativeAction(
        error instanceof Error
          ? error.message
          : "That undo is no longer available.",
      );
    }
  }

  async function updateGovernedPreferences(
    learningEnabled: boolean,
    reportingEnabled: boolean,
    notificationsEnabled: boolean,
    launchAtLoginEnabled: boolean,
  ) {
    if (!engineSnapshot || !snapshotDigest) return;
    try {
      const receipt = await updateEnginePreferences(
        learningEnabled,
        reportingEnabled,
        notificationsEnabled,
        launchAtLoginEnabled,
        snapshotDigest,
        crypto.randomUUID(),
      );
      await refreshAfterNativeAction(receipt.message);
    } catch (error: unknown) {
      const failure = normalizeEngineFailure(
        error,
        "Temper could not safely save that setting.",
      );
      await refreshAfterNativeAction(failure.message);
      throw new Error(failure.message);
    }
  }

  async function renewConsent() {
    if (!engineSnapshot || !snapshotDigest) return;
    const receipt = await renewEngineConsent(
      engineSnapshot.consent.expires_at,
      snapshotDigest,
      crypto.randomUUID(),
    );
    await refreshAfterNativeAction(receipt.message);
  }

  async function refreshConnectionState() {
    const inspected = await inspectConnections();
    setSetupSnapshot(inspected.snapshot);
    setSetupDigest(inspected.snapshotDigest);
    setToast("Connection status refreshed.");
  }

  async function completeModeTask(
    message: string,
    result: EngineTaskResult | null,
  ) {
    if (result) setTaskResult(result);
    await refreshAfterNativeAction(message);
    if (result?.change_review) {
      setAdvancedMode(true);
      transitionTo("advanced");
    }
  }

  async function runAdvancedTask(projectId: string, task: string) {
    if (
      !snapshotDigest ||
      !codexConnectionReady ||
      !governedActionsAvailable ||
      !taskRunnerProjects.some((project) => project.project_id === projectId)
    ) {
      throw new Error(
        "Managed tasks are unavailable for that project in the current state.",
      );
    }
    const result = await runManagedTask(
      projectId,
      task,
      snapshotDigest,
      crypto.randomUUID(),
    );
    setTaskResult(result);
  }

  async function applyAdvancedTask() {
    if (!taskResult?.change_review || !snapshotDigest) return;
    const receipt = await applyManagedTask(
      taskResult.change_review,
      snapshotDigest,
      crypto.randomUUID(),
    );
    setTaskResult(null);
    await refreshAfterNativeAction(receipt.message);
  }

  async function discardAdvancedTask() {
    if (!taskResult?.change_review || !snapshotDigest) return;
    const receipt = await discardManagedTask(
      taskResult.change_review.session_id,
      snapshotDigest,
      crypto.randomUUID(),
    );
    setTaskResult(null);
    await refreshAfterNativeAction(receipt.message);
  }

  async function refreshDiagnostics() {
    if (!nativeRuntime) return;
    setDiagnostics(await loadDiagnostics());
  }

  async function refreshAfterNativeAction(message: string) {
    setToast(message);
    if (!nativeRuntime) return;
    try {
      const [{ snapshot, snapshotDigest: digest }, modes, setup, environments] =
        await Promise.all([
          loadEngineSnapshot(),
          loadModes(),
          loadSetupSnapshot(),
          loadInstructionEnvironments(),
        ]);
      setEngineSnapshot(snapshot);
      setSnapshotDigest(digest);
      setModeCatalog(modes);
      setSetupSnapshot(setup.snapshot);
      setSetupDigest(setup.snapshotDigest);
      setInstructionEnvironments(environments);
      setEngineFailure(null);
      setFeedback(null);
    } catch (error: unknown) {
      setFailureStage("refresh");
      setEngineFailure(
        normalizeEngineFailure(
          error,
          "Temper could not refresh your local state.",
        ),
      );
      setBootstrapState("error");
    }
  }

  if (!nativeRuntime && !browserPreviewRuntime) {
    return <DesktopHostRequired />;
  }

  if (
    nativeRuntime &&
    (bootstrapState === "loading" || bootstrapState === "error")
  ) {
    return (
      <NativeStartup
        failure={bootstrapState === "error" ? engineFailure : null}
        failureStage={failureStage}
        onRetry={() => {
          setFailureStage("startup");
          setBootstrapState("loading");
          setEngineFailure(null);
          setBootstrapAttempt((attempt) => attempt + 1);
        }}
      />
    );
  }

  if (
    (nativeRuntime && bootstrapState === "onboarding") ||
    (browserPreviewRuntime && screen === "onboarding")
  )
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
        previewMode={browserPreviewRuntime}
        screen={screen}
        workspaces={
          nativeRuntime
            ? (workspaces ?? [])
            : browserPreviewRuntime
              ? browserWorkspaceOptions
              : []
        }
      >
        <div
          className="screen-transition"
          data-direction={navigationDirection}
          data-screen={screen}
          key={screen}
        >
          {screen === "today" ||
          screen === "suggestion" ||
          screen === "tray" ? (
            <TodayPage
              automaticLearning={automaticLearning}
              feedback={feedback}
              onFeedback={recordFeedback}
              onOpenCore={() => navigate("core")}
              onReview={reviewSuggestion}
              workspace={activeWorkspace}
              selectedSuggestionId={selectedSuggestion?.id ?? null}
              suggestions={displayedSuggestions}
              liveSummary={
                engineSnapshot
                  ? {
                      activeAdaptationCount: scopedAdaptationCount,
                      health: engineSnapshot.health,
                      pendingFeedbackCount:
                        activeWorkspace === "all"
                          ? engineSnapshot.activation_feedback.length
                          : 0,
                      feedbackAvailable: governedActionsAvailable,
                      pendingReviewCount: scopedSuggestionCount,
                      projectCount:
                        activeWorkspace === "all"
                          ? engineSnapshot.projects.length
                          : selectedProjectId
                            ? 1
                            : 0,
                      secureStoreReady,
                    }
                  : undefined
              }
              instructionEnvironments={instructionEnvironments}
              liveProjects={engineSnapshot?.projects ?? []}
            />
          ) : null}
          {screen === "core" ? (
            <CorePage
              activeWorkspace={activeWorkspace}
              initialItems={
                nativeRuntime
                  ? (liveCoreItems ?? [])
                  : browserPreviewRuntime
                    ? demoCoreItems
                    : []
              }
              instructionEnvironments={instructionEnvironments}
              liveProjects={engineSnapshot?.projects ?? []}
              availableWorkspaces={
                nativeRuntime
                  ? engineSnapshot?.projects.map(
                      (project) => project.display_name,
                    )
                  : browserPreviewRuntime
                    ? demoProjects.map((project) => project.name)
                    : []
              }
              key={`${activeWorkspace}-${snapshotDigest ?? "browser"}`}
              governedMutationUnavailableReason={
                governedMutationUnavailableReason
              }
              governedMutationsAvailable={governedActionsAvailable}
              nativeRuntime={nativeRuntime}
              onRevoke={revokeAdaptation}
              onUndo={undoRecentAdaptation}
              onNotice={(message) => {
                if (nativeRuntime) {
                  void refreshAfterNativeAction(message);
                } else {
                  setToast(message);
                }
              }}
              recentUndo={engineSnapshot?.recent_undos[0]}
              snapshotDigest={snapshotDigest}
            />
          ) : null}
          {screen === "modes" ? (
            <ModesPage
              error={null}
              loading={false}
              modes={modeCatalog}
              nativeRuntime={nativeRuntime}
              onOpenCore={() => navigate("core")}
              onTaskComplete={completeModeTask}
              projects={
                nativeRuntime
                  ? (taskRunnerProjects.map((project) => ({
                      id: project.project_id,
                      label: project.display_name,
                    })) ?? [])
                  : browserPreviewRuntime
                    ? browserProjects
                    : []
              }
              runnerReady={
                nativeRuntime
                  ? codexConnectionReady && governedActionsAvailable
                  : false
              }
              runnerUnavailableReason={managedTaskUnavailableReason}
              snapshotDigest={snapshotDigest}
              instructionEnvironments={instructionEnvironments}
            />
          ) : null}
          {screen === "connections" ? (
            <ConnectionsPage
              liveConnections={
                nativeRuntime ? (setupSnapshot?.connections ?? []) : undefined
              }
              liveProjects={
                nativeRuntime ? (engineSnapshot?.projects ?? []) : undefined
              }
              instructionEnvironments={instructionEnvironments}
              nativeRuntime={nativeRuntime}
              previewConnections={browserPreviewRuntime ? demoConnections : []}
              previewProjects={browserPreviewRuntime ? demoProjects : []}
              onRefresh={refreshConnectionState}
              onProjectRegistered={refreshAfterNativeAction}
              onInstructionChanged={refreshAfterNativeAction}
              registrationAvailable={governedActionsAvailable}
              registrationUnavailableReason={governedMutationUnavailableReason}
              snapshotDigest={snapshotDigest}
            />
          ) : null}
          {screen === "settings" ? (
            <SettingsPage
              advancedMode={advancedMode}
              automaticLearning={automaticLearning}
              backgroundLearning={engineSnapshot?.background_enabled ?? false}
              nativeRuntime={nativeRuntime}
              onAdvancedModeChange={setAdvancedMode}
              onAutomaticLearningChange={setAutomaticLearning}
              onGovernedPreferencesChange={updateGovernedPreferences}
              onRenewConsent={renewConsent}
              onThemeChange={setTheme}
              theme={theme}
              telemetryEnabled={
                engineSnapshot?.aggregate_reporting_enabled ?? false
              }
              decisionNotificationsEnabled={
                engineSnapshot?.decision_notifications_enabled ?? false
              }
              launchAtLoginEnabled={
                engineSnapshot?.launch_at_login_enabled ?? false
              }
              consent={engineSnapshot?.consent ?? null}
              secureStoreReady={setupSnapshot?.secure_store.status === "ready"}
            />
          ) : null}
          {screen === "advanced" ? (
            <AdvancedPage
              diagnostics={diagnostics}
              longitudinalGate={
                engineSnapshot?.terminal.review_mode.gate ?? null
              }
              nativeRuntime={nativeRuntime}
              onApply={applyAdvancedTask}
              onDiagnostics={refreshDiagnostics}
              onDiscard={discardAdvancedTask}
              onRun={runAdvancedTask}
              projects={taskRunnerProjects.map((project) => ({
                id: project.project_id,
                label: project.display_name,
              }))}
              previewProjects={browserPreviewRuntime ? browserProjects : []}
              runnerReady={codexConnectionReady && governedActionsAvailable}
              runnerUnavailableReason={managedTaskUnavailableReason}
              taskResult={taskResult}
            />
          ) : null}
        </div>
      </Shell>
      {selectedSuggestion && (!nativeRuntime || governedActionsAvailable) ? (
        <ReviewDialog
          availableProjects={engineSnapshot?.projects.map(
            (project) => project.display_name,
          )}
          key={selectedSuggestion.id}
          onDecision={decide}
          onOpenChange={setReviewOpen}
          open={reviewOpen}
          previewMode={browserPreviewRuntime}
          suggestion={selectedSuggestion}
        />
      ) : null}
      {!nativeRuntime && screen === "tray" ? (
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

function coreItemFromEngine(
  item: EngineDesktopSnapshot["adaptations"][number],
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
    isGlobal: scopeIsGlobal(item.scope),
    projectNames,
    scope: describeScope(item.scope, snapshot),
    sourceSummary: `Approved from ${item.evidence_count} supporting source${item.evidence_count === 1 ? "" : "s"}`,
    title: item.intent,
  };
}

function suggestionFromEngine(
  item: EngineSuggestion,
  snapshot: EngineDesktopSnapshot,
): Suggestion {
  const projectNames = item.suggested_scope.project_ids.map(
    (projectId) =>
      snapshot.projects.find((project) => project.project_id === projectId)
        ?.display_name ?? projectId,
  );
  const affected = item.affected_artifact_id
    ? snapshot.adaptations.find(
        (adaptation) => adaptation.artifact_id === item.affected_artifact_id,
      )
    : null;
  return {
    automationDisposition: "review-required",
    automationReason: "A decision is required before anything changes.",
    behavior:
      item.proposed_behavior ??
      `Remove ${affected?.intent ?? "the affected adaptation"}`,
    capturedAt: new Date(item.created_at).toLocaleString(),
    confidenceReason: item.reason_summary.join(" "),
    digest: item.proposal_digest,
    explanation:
      item.reason_summary.join(" ") ||
      "This proposal came from approved, prospectively captured feedback.",
    id: item.queue_id,
    isRevocation: item.signal_kind === "revocation",
    isGlobal: scopeIsGlobal(item.suggested_scope),
    availableDecisions: [
      ...(item.available_actions.some((action) =>
        ["keep_suggested", "approve_revocation"].includes(action),
      )
        ? (["suggested"] as const)
        : []),
      ...(item.available_actions.includes("keep_project")
        ? (["project"] as const)
        : []),
      ...(item.available_actions.includes("keep_narrowed")
        ? (["narrowed"] as const)
        : []),
      ...(item.available_actions.some((action) =>
        ["ignore", "reject_revocation"].includes(action),
      )
        ? (["ignore"] as const)
        : []),
    ],
    projectNames,
    sourceProject: projectNames.length === 1 ? projectNames[0] : null,
    suggestedScope: describeScope(item.suggested_scope, snapshot),
  };
}

function projectIdForSuggestion(
  suggestion: EngineSuggestion,
  snapshot: EngineDesktopSnapshot,
  activeWorkspace: WorkspaceScope,
): string | null {
  if (activeWorkspace !== "all") {
    return (
      snapshot.projects.find(
        (project) => project.display_name === activeWorkspace,
      )?.project_id ?? null
    );
  }
  return suggestion.suggested_scope.project_ids.length === 1
    ? suggestion.suggested_scope.project_ids[0]
    : null;
}

function coreKind(value: string): CoreKind {
  if (
    value === "preference" ||
    value === "memory" ||
    value === "example" ||
    value === "procedure" ||
    value === "prompt_rule" ||
    value === "skill" ||
    value === "tool_recommendation"
  ) {
    return value;
  }
  throw new Error("Temper received an unsupported adaptation kind.");
}

function scopeIsGlobal(scope: EngineSuggestion["suggested_scope"]): boolean {
  return (
    scope.workspace_ids.length === 0 &&
    scope.project_ids.length === 0 &&
    scope.repository_ids.length === 0 &&
    scope.task_classes.length === 0 &&
    scope.target_families.length === 0 &&
    scope.environment_ids.length === 0 &&
    scope.activation_conditions.length === 0 &&
    scope.exclusions.length === 0 &&
    scope.valid_from === null &&
    scope.valid_until === null
  );
}

function describeScope(
  scope: EngineSuggestion["suggested_scope"],
  snapshot: EngineDesktopSnapshot,
): string {
  if (scopeIsGlobal(scope)) return "All registered projects";
  const parts: string[] = [];
  const projectNames = scope.project_ids.map(
    (projectId) =>
      snapshot.projects.find((project) => project.project_id === projectId)
        ?.display_name ?? projectId,
  );
  if (projectNames.length) parts.push(projectNames.join(", "));
  if (scope.workspace_ids.length)
    parts.push(`Workspaces: ${scope.workspace_ids.join(", ")}`);
  if (scope.repository_ids.length)
    parts.push(`Repositories: ${scope.repository_ids.join(", ")}`);
  if (scope.task_classes.length)
    parts.push(`Tasks: ${scope.task_classes.join(", ")}`);
  if (scope.target_families.length)
    parts.push(`Agents: ${scope.target_families.join(", ")}`);
  if (scope.environment_ids.length)
    parts.push(`Environments: ${scope.environment_ids.join(", ")}`);
  if (scope.activation_conditions.length)
    parts.push(`When ${scope.activation_conditions.join(", ")}`);
  if (scope.exclusions.length)
    parts.push(`Excluding ${scope.exclusions.join(", ")}`);
  if (scope.valid_from)
    parts.push(`From ${new Date(scope.valid_from).toLocaleDateString()}`);
  if (scope.valid_until)
    parts.push(`Until ${new Date(scope.valid_until).toLocaleDateString()}`);
  return parts.length ? parts.join(" · ") : "Scoped adaptation";
}
