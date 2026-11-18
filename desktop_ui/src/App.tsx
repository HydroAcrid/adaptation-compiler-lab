import * as Tooltip from "@radix-ui/react-tooltip";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

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
import { Shell, WorkspacePicker } from "./components/Shell";
import { Button, LoadingStatus } from "./components/ui";
import { usePageNavigation } from "./usePageNavigation";
import { useWorkspaceResource } from "./useWorkspaceResource";
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
  loadPackageReviews,
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
  decidePackageReview,
  updateEnginePreferences,
  type EngineSuggestion,
  type EngineDesktopSnapshot,
  type EngineTaskResult,
  type EngineDiagnostics,
  type EngineClientFailure,
  type EngineInstructionEnvironmentSummary,
} from "./engine";
import type {
  CoreItem,
  CoreKind,
  FeedbackValue,
  Screen,
  Suggestion,
  SuggestionDecision,
  Theme,
  PackageReviewItem,
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

function initialWorkspaceProject(): string | null {
  const value = new URLSearchParams(window.location.search).get("project");
  if (value === "green-meadow") return "Green Meadow";
  if (value === "kairn") return "Kairn";
  return null;
}

function initialTheme(): Theme {
  const value = new URLSearchParams(window.location.search).get("theme");
  if (value === "light" || value === "dark" || value === "system") {
    return value;
  }
  const saved = window.localStorage.getItem("temper.theme");
  return saved === "dark" || saved === "system" ? saved : "light";
}

const noModes: Awaited<ReturnType<typeof loadModes>> = [];
const noPackageReviews: PackageReviewItem[] = [];
const noInstructionEnvironments: EngineInstructionEnvironmentSummary[] = [];

function ResourceStatus({
  label,
  resource,
}: {
  label: string;
  resource: {
    data: unknown;
    error: EngineClientFailure | null;
    loading: boolean;
    read: () => Promise<void>;
  };
}) {
  if (!resource.error) {
    return resource.loading && !resource.data ? (
      <LoadingStatus>Loading {label.toLowerCase()}…</LoadingStatus>
    ) : null;
  }
  return (
    <div className="modes-empty">
      <p role="alert">
        {resource.data
          ? `${label} may be out of date.`
          : `${label} could not load.`}{" "}
        {resource.error.message}
      </p>
      <Button
        disabled={resource.loading}
        onClick={() => {
          void resource.read().catch(() => undefined);
        }}
        tone="quiet"
        type="button"
      >
        {resource.loading
          ? `Retrying ${label.toLowerCase()}…`
          : `Retry ${label.toLowerCase()}`}
      </Button>
    </div>
  );
}

export default function App() {
  const [nativeRuntime] = useState(isTauriRuntime);
  const browserPreviewRuntime = !nativeRuntime && import.meta.env.DEV;
  const [firstScreen] = useState<Screen>(() =>
    nativeRuntime ? "today" : initialScreen(),
  );
  const { screen, setScreen, scrollHost } = usePageNavigation(firstScreen);
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [advancedMode, setAdvancedMode] = useState(
    firstScreen === "advanced" ||
      window.localStorage.getItem("temper.advanced") === "true",
  );
  const [reviewOpen, setReviewOpen] = useState(firstScreen === "suggestion");
  const reviewOpener = useRef<HTMLElement | null>(null);
  const returnedReviewFocus = useRef<HTMLElement | null>(null);
  const [workspaceProjectId, setWorkspaceProjectId] = useState<string | null>(
    () => (browserPreviewRuntime ? initialWorkspaceProject() : null),
  );
  const [suggestionQueue, setSuggestionQueue] = useState<Suggestion[]>(
    browserPreviewRuntime ? demoSuggestions : [],
  );
  const [reviewSuggestionId, setReviewSuggestionId] = useState<string | null>(
    null,
  );
  const [automaticLearning, setAutomaticLearning] = useState(false);
  const [feedback, setFeedback] = useState<FeedbackValue | null>(null);
  const [savingFeedback, setSavingFeedback] = useState(false);
  const [ratedActivationIds, setRatedActivationIds] = useState<string[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const workspace = useWorkspaceResource(loadEngineSnapshot);
  const setup = useWorkspaceResource(loadSetupSnapshot);
  const catalog = useWorkspaceResource(loadModes);
  const environments = useWorkspaceResource(loadInstructionEnvironments);
  const importedReviews = useWorkspaceResource(loadPackageReviews);
  const { read: readWorkspace } = workspace;
  const { read: readSetup } = setup;
  const { read: readCatalog } = catalog;
  const { read: readEnvironments } = environments;
  const { read: readImportedReviews } = importedReviews;
  const readAuxiliaryResources = useCallback(
    () =>
      Promise.allSettled([
        readCatalog(),
        readSetup(),
        readEnvironments(),
        readImportedReviews(),
      ]),
    [readCatalog, readEnvironments, readImportedReviews, readSetup],
  );
  const engineSnapshot = workspace.data?.snapshot ?? null;
  const snapshotDigest =
    workspace.error || workspace.loading
      ? null
      : (workspace.data?.snapshotDigest ?? null);
  const setupSnapshot = setup.data?.snapshot ?? null;
  const setupDigest =
    setup.error || setup.loading ? null : (setup.data?.snapshotDigest ?? null);
  const modeCatalog =
    catalog.data ?? (browserPreviewRuntime ? browserModes : noModes);
  const packageReviews = importedReviews.data ?? noPackageReviews;
  const instructionEnvironments =
    environments.data ?? noInstructionEnvironments;
  const [bootstrapState, setBootstrapState] = useState<
    "loading" | "onboarding" | "ready" | "error"
  >(nativeRuntime ? "loading" : "ready");
  const [bootstrapAttempt, setBootstrapAttempt] = useState(0);
  const [engineFailure, setEngineFailure] =
    useState<EngineClientFailure | null>(null);
  const [taskResult, setTaskResult] = useState<EngineTaskResult | null>(null);
  const [diagnostics, setDiagnostics] = useState<EngineDiagnostics | null>(
    null,
  );
  const displayedSuggestions = useMemo(
    () =>
      engineSnapshot
        ? engineSnapshot.suggestions.map((item) =>
            suggestionFromEngine(item, engineSnapshot),
          )
        : suggestionQueue,
    [engineSnapshot, suggestionQueue],
  );
  const selectedSuggestion = displayedSuggestions[0];
  const reviewedSuggestion = reviewSuggestionId
    ? displayedSuggestions.find((item) => item.id === reviewSuggestionId)
    : selectedSuggestion;
  const workspaceProjects = useMemo(() => {
    if (!engineSnapshot) {
      return browserPreviewRuntime
        ? browserWorkspaceOptions.map(({ id, label }) => ({ id, label }))
        : [];
    }
    return engineSnapshot.projects.map((project) => {
      const duplicate = engineSnapshot.projects.some(
        (other) =>
          other !== project && other.display_name === project.display_name,
      );
      return {
        id: project.project_id,
        label: duplicate
          ? `${project.display_name} · ${project.project_id}`
          : project.display_name,
      };
    });
  }, [browserPreviewRuntime, engineSnapshot]);
  const selectedScopeIds = engineSnapshot
    ? engineSnapshot.suggestions.find(
        (item) => item.queue_id === reviewedSuggestion?.id,
      )?.suggested_scope.project_ids
    : reviewedSuggestion?.projectNames;
  const activeWorkspaceProjectId = workspaceProjects.some(
    ({ id }) => id === workspaceProjectId,
  )
    ? workspaceProjectId
    : null;
  const eligibleReviewProjects = selectedScopeIds?.length
    ? workspaceProjects.filter(({ id }) => selectedScopeIds.includes(id))
    : workspaceProjects;
  const preferredReviewProjectId = browserPreviewRuntime
    ? reviewedSuggestion?.sourceProject
    : activeWorkspaceProjectId;
  const feedbackTargets = engineSnapshot?.activation_feedback
    .filter(
      (activation) => !ratedActivationIds.includes(activation.activation_id),
    )
    .map((activation) => {
      const task = engineSnapshot.terminal.review_mode.activation_feedback.find(
        (item) => item.activation_id === activation.activation_id,
      );
      return {
        id: activation.activation_id,
        taskLabel: `Task ${shortTaskReference(task?.task_ref_id ?? activation.activation_id)}`,
        completedAt: activation.completed_at,
        guidance: activation.active_artifact_ids.map((artifactId) => {
          const guidance = engineSnapshot.adaptations.find(
            (item) => item.artifact_id === artifactId,
          );
          return guidance?.intent ?? "Previously delivered guidance";
        }),
        outcomes: activation.available_outcomes,
        busy: savingFeedback,
      };
    });

  useLayoutEffect(() => {
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

  useLayoutEffect(() => {
    const opener = returnedReviewFocus.current;
    if (opener && !reviewOpenerIsVisible(opener)) {
      returnedReviewFocus.current = null;
      if (document.activeElement === document.body) {
        scrollHost.current?.focus({ preventScroll: true });
      }
    }
  }, [displayedSuggestions, scrollHost, screen]);

  useEffect(() => {
    if (!nativeRuntime) return;
    let active = true;
    loadEngineHandshake()
      .then(async (handshake) => {
        if (!active) return;
        if (!handshake.configured) {
          await readSetup();
          if (active) {
            setScreen("onboarding");
            setBootstrapState("onboarding");
          }
          return;
        }
        void readAuxiliaryResources();
        await readWorkspace();
        if (!active) return;
        setBootstrapState("ready");
      })
      .catch((error: unknown) => {
        if (active) {
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
  }, [
    bootstrapAttempt,
    nativeRuntime,
    readAuxiliaryResources,
    readSetup,
    readWorkspace,
    setScreen,
  ]);

  async function finishOnboarding() {
    if (browserPreviewRuntime) {
      setScreen("today");
      return;
    }
    void readAuxiliaryResources();
    try {
      await readWorkspace();
      setEngineFailure(null);
      setBootstrapState("ready");
      setScreen("today");
    } catch (error) {
      setEngineFailure(
        normalizeEngineFailure(
          error,
          "Temper could not load your local state.",
        ),
      );
      setBootstrapState("error");
    }
  }

  const liveCoreItems = useMemo(
    () =>
      engineSnapshot?.adaptations.map((item) =>
        coreItemFromEngine(item, engineSnapshot),
      ),
    [engineSnapshot],
  );
  const secureStoreReady = setupSnapshot?.secure_store.status === "ready";
  const governedActionsAvailable = Boolean(
    snapshotDigest &&
    engineSnapshot?.health !== "consent_expired" &&
    secureStoreReady &&
    !setup.error,
  );
  const governedMutationUnavailableReason =
    workspace.error || setup.error
      ? "Refresh your local state before saving changes."
      : !secureStoreReady
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
  const managedTaskUnavailableReason =
    workspace.error || setup.error
      ? "Refresh your local state before running a saved workflow."
      : !secureStoreReady
        ? "Secure storage must be available before Temper can deliver a managed task."
        : engineSnapshot?.health === "consent_expired"
          ? "Renew local consent before Temper can deliver a managed task."
          : !codexConnectionReady
            ? "A compatible Codex installation signed in with ChatGPT is required."
            : taskRunnerProjects.length === 0
              ? "Register a project that allows managed tasks before running this Mode."
              : null;

  function navigate(destination: Screen) {
    setScreen(destination);
    if (destination === "suggestion") setReviewSuggestionId(null);
    setReviewOpen(destination === "suggestion");
  }

  function reviewSuggestion(suggestionId: string, opener?: HTMLElement) {
    if (nativeRuntime && !governedActionsAvailable) return;
    reviewOpener.current =
      opener ??
      (document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null);
    returnedReviewFocus.current = null;
    setReviewSuggestionId(suggestionId);
    setReviewOpen(true);
  }

  function returnReviewFocus() {
    const opener = reviewOpener.current;
    reviewOpener.current = null;
    if (opener && reviewOpenerIsVisible(opener)) {
      opener.focus({ preventScroll: true });
      returnedReviewFocus.current = opener;
    } else {
      scrollHost.current?.focus({ preventScroll: true });
    }
  }

  async function decide(
    decision: SuggestionDecision,
    projectIds: string[] = [],
  ) {
    if (!reviewedSuggestion) return;
    if (nativeRuntime) {
      if (!engineSnapshot || !snapshotDigest || !governedActionsAvailable) {
        throw new Error(
          governedMutationUnavailableReason ??
            "Refresh your local state before saving changes.",
        );
      }
      const suggestion = engineSnapshot.suggestions.find(
        (item) => item.queue_id === reviewedSuggestion.id,
      );
      if (!suggestion) return;
      const selectedProjectIds = [...new Set(projectIds)].sort();
      if (
        selectedProjectIds.some(
          (id) => !eligibleReviewProjects.some((project) => project.id === id),
        )
      ) {
        throw new Error("Choose a registered project from this suggestion.");
      }
      const projectId = selectedProjectIds[0];
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
      if (decision === "project" && selectedProjectIds.length !== 1) {
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
        if (decision !== "ignore") setScreen("core");
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
      (item) => item.id !== reviewedSuggestion.id,
    );
    setSuggestionQueue(remaining);
    setReviewOpen(false);
    if (decision !== "ignore") setScreen("core");
    const suggestedScope = reviewedSuggestion.suggestedScope;
    setToast(
      decision === "suggested"
        ? suggestedScope === "All projects"
          ? "Adaptation kept for all projects."
          : `Adaptation kept for ${suggestedScope}.`
        : decision === "project"
          ? `Adaptation kept for ${eligibleReviewProjects.find((project) => project.id === projectIds[0])?.label ?? reviewedSuggestion.sourceProject} only.`
          : "Suggestion ignored. Nothing changed.",
    );
  }

  async function recordFeedback(value: FeedbackValue, activationId?: string) {
    if (!nativeRuntime) {
      setFeedback(value);
      return;
    }
    if (
      !engineSnapshot ||
      !snapshotDigest ||
      !governedActionsAvailable ||
      savingFeedback
    )
      return;
    const activation = engineSnapshot.activation_feedback.find(
      (item) => item.activation_id === activationId,
    );
    if (
      !activation ||
      ratedActivationIds.includes(activation.activation_id) ||
      !activation.available_outcomes.includes(value)
    )
      return;
    setSavingFeedback(true);
    try {
      const receipt = await recordEngineFeedback(
        activation,
        value,
        snapshotDigest,
        crypto.randomUUID(),
      );
      setRatedActivationIds((current) => [
        ...current,
        activation.activation_id,
      ]);
      await refreshAfterNativeAction(receipt.message);
    } catch (error: unknown) {
      await refreshAfterNativeAction(
        error instanceof Error
          ? error.message
          : "Temper could not safely record that feedback.",
      );
    } finally {
      setSavingFeedback(false);
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
    await readSetup(inspectConnections);
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
      setScreen("advanced");
    }
  }

  async function reviewImportedPackage(
    item: PackageReviewItem,
    decision: "approved" | "rejected",
    projectIds: string[],
  ) {
    if (!snapshotDigest) return;
    const receipt = await decidePackageReview(
      item,
      decision,
      projectIds,
      snapshotDigest,
      crypto.randomUUID(),
    );
    await refreshAfterNativeAction(
      receipt.status === "approved_for_core"
        ? "The approved behavior was added to Personalization."
        : receipt.status === "approved_inactive_mode"
          ? "The imported Mode is available for an explicit task."
          : receipt.status === "approved_inactive_overlay"
            ? "The personal overlay is approved and remains inactive."
            : "The imported item was dismissed.",
    );
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
    void readAuxiliaryResources();
    await readWorkspace().catch(() => undefined);
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
        advancedMode={advancedMode}
        failure={bootstrapState === "error" ? engineFailure : null}
        onRetry={() => {
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

  const workspaceStatus = (
    <ResourceStatus label="Workspace data" resource={workspace} />
  );
  const setupStatus = <ResourceStatus label="Connections" resource={setup} />;
  const instructionStatus = (
    <ResourceStatus label="Project instructions" resource={environments} />
  );
  const workspaceAndSetupStatus = (
    <>
      {workspaceStatus}
      {setupStatus}
    </>
  );
  const fullWorkspaceStatus = (
    <>
      {workspaceAndSetupStatus}
      {instructionStatus}
    </>
  );

  return (
    <Tooltip.Provider delayDuration={500}>
      <Shell
        advancedMode={advancedMode}
        onNavigate={navigate}
        previewMode={browserPreviewRuntime}
        screen={screen}
        scrollHost={scrollHost}
        pages={{
          today: (
            <TodayPage
              nativeAutonomy={nativeRuntime}
              automaticLearning={automaticLearning}
              feedback={feedback}
              feedbackTargets={feedbackTargets}
              onFeedback={recordFeedback}
              onOpenCore={() => navigate("core")}
              onOpenSettings={() => navigate("settings")}
              onOpenTools={() => navigate("modes")}
              onReview={reviewSuggestion}
              reviewAvailable={!nativeRuntime || governedActionsAvailable}
              workspaceProjectId={activeWorkspaceProjectId}
              workspaceControl={
                workspaceProjects.length ? (
                  <WorkspacePicker
                    projectId={activeWorkspaceProjectId}
                    onProjectChange={setWorkspaceProjectId}
                    projects={workspaceProjects}
                  />
                ) : null
              }
              selectedSuggestionId={selectedSuggestion?.id ?? null}
              suggestions={displayedSuggestions}
              liveSummary={
                engineSnapshot
                  ? {
                      activeAdaptationCount: liveCoreItems?.length ?? 0,
                      health: engineSnapshot.health,
                      pendingFeedbackCount: feedbackTargets?.length ?? 0,
                      feedbackAvailable: governedActionsAvailable,
                      pendingReviewCount: displayedSuggestions.length,
                      projectCount: engineSnapshot.projects.length,
                      secureStoreReady: setupSnapshot
                        ? secureStoreReady
                        : undefined,
                    }
                  : undefined
              }
              instructionEnvironments={instructionEnvironments}
              liveProjects={engineSnapshot?.projects ?? []}
              resourceStatus={workspaceStatus}
            />
          ),
          core: (
            <CorePage
              nativeAutonomy={nativeRuntime}
              initialItems={
                nativeRuntime
                  ? (liveCoreItems ?? [])
                  : browserPreviewRuntime
                    ? demoCoreItems
                    : []
              }
              instructionEnvironments={instructionEnvironments}
              liveProjects={engineSnapshot?.projects ?? []}
              workspaceProjects={workspaceProjects}
              governedMutationUnavailableReason={
                governedMutationUnavailableReason
              }
              governedMutationsAvailable={governedActionsAvailable}
              guidanceLoaded={Boolean(engineSnapshot)}
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
              resourceStatus={fullWorkspaceStatus}
              snapshotDigest={snapshotDigest}
            />
          ),
          modes: (
            <ModesPage
              error={null}
              loading={catalog.loading && !catalog.data && !catalog.error}
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
              reviewProjects={
                engineSnapshot?.projects.map((project) => ({
                  id: project.project_id,
                  label: project.display_name,
                })) ?? []
              }
              runnerReady={
                nativeRuntime
                  ? codexConnectionReady && governedActionsAvailable
                  : false
              }
              runnerUnavailableReason={managedTaskUnavailableReason}
              snapshotDigest={snapshotDigest}
              instructionEnvironments={instructionEnvironments}
              packageReviews={packageReviews}
              packageReviewsStatus={
                importedReviews.error ? (
                  <ResourceStatus
                    label="Package reviews"
                    resource={importedReviews}
                  />
                ) : null
              }
              savedWorkflowsStatus={
                catalog.error ? (
                  <ResourceStatus label="Saved workflows" resource={catalog} />
                ) : null
              }
              resourceStatus={fullWorkspaceStatus}
              onPackageDecision={reviewImportedPackage}
            />
          ),
          connections: (
            <ConnectionsPage
              liveConnections={setupSnapshot?.connections}
              liveProjects={engineSnapshot?.projects}
              connectionsLoading={setup.loading}
              projectsLoading={workspace.loading}
              instructionEnvironments={instructionEnvironments}
              nativeRuntime={nativeRuntime}
              previewConnections={browserPreviewRuntime ? demoConnections : []}
              previewProjects={browserPreviewRuntime ? demoProjects : []}
              onRefresh={refreshConnectionState}
              onOpenPersonalization={() => navigate("core")}
              onProjectRegistered={refreshAfterNativeAction}
              onInstructionChanged={refreshAfterNativeAction}
              registrationAvailable={governedActionsAvailable}
              registrationUnavailableReason={governedMutationUnavailableReason}
              resourceStatus={
                <>
                  {workspace.error && workspaceStatus}
                  {setup.error && setupStatus}
                  {instructionStatus}
                </>
              }
              snapshotDigest={snapshotDigest}
            />
          ),
          settings: (
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
              secureStoreReady={secureStoreReady && !setup.error}
              snapshotDigest={snapshotDigest}
              onRecoveryCreated={setToast}
              resourceStatus={workspaceAndSetupStatus}
            />
          ),
          advanced: (
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
              resourceStatus={workspaceAndSetupStatus}
              runnerReady={codexConnectionReady && governedActionsAvailable}
              runnerUnavailableReason={managedTaskUnavailableReason}
              taskResult={taskResult}
            />
          ),
        }}
      />
      {reviewedSuggestion ? (
        <ReviewDialog
          projectChoices={eligibleReviewProjects}
          preferredProjectId={preferredReviewProjectId}
          key={reviewedSuggestion.id}
          onDecision={decide}
          onOpenChange={setReviewOpen}
          onReturnFocus={returnReviewFocus}
          open={reviewOpen}
          previewMode={browserPreviewRuntime}
          suggestion={reviewedSuggestion}
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

function reviewOpenerIsVisible(opener: HTMLElement) {
  return (
    opener.isConnected &&
    !opener.closest("[hidden], [inert], details:not([open])")
  );
}

function shortTaskReference(reference: string) {
  if (reference.length <= 24) return reference;
  return `${reference.slice(0, 8)}…${reference.slice(-6)}`;
}

function coreItemFromEngine(
  item: EngineDesktopSnapshot["adaptations"][number],
  snapshot: EngineDesktopSnapshot,
): CoreItem {
  return {
    description: item.required_behaviors.join(" "),
    id: item.artifact_id,
    kind: coreKind(item.artifact_type),
    isGlobal: scopeIsGlobal(item.scope),
    projectIds: item.scope.project_ids,
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
    projectIds: item.suggested_scope.project_ids,
    projectNames,
    sourceProject: projectNames.length === 1 ? projectNames[0] : null,
    suggestedScope: describeScope(item.suggested_scope, snapshot),
  };
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
