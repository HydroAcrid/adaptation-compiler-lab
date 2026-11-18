import * as Dialog from "@radix-ui/react-dialog";
import { FileUp, Plus, X } from "lucide-react";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type Dispatch,
  type SetStateAction,
  type RefObject,
} from "react";
import { normalizeEngineFailure } from "../engine";
import { usePageVisibility } from "../pageVisibility";
import {
  approveSetup,
  approveSetupUpdate,
  connectSetupUpdateSource,
  disconnectSetupUpdateSource,
  loadSetupStatus,
  loadSetupUpdateStatus,
  openSetupFile,
  previewSetupExport,
  previewSetupUpdate,
  removeSetup,
  resetSetup,
  saveSetupFile,
  setupKinds,
  type SetupImportPreview,
  type SetupItem,
  type SetupKind,
  type SetupPreview,
  type SetupUpdatePreview,
  type SetupUpdateStatus,
} from "../portableSetup";
import { hubRequest, type HubProject, type HubState } from "../toolsHub";
import { setupImportBlock } from "./RepositoryReadiness";
import { useDialogFocusReturn } from "./dialogFocus";
import { Button, LoadingStatus, TemperSelect } from "./ui";
import "./PortableSetupPanel.css";

type RepositorySetup = {
  projectId: string;
  active: SetupPreview | null;
  issue?: string;
  stale?: boolean;
  recoveryDigest?: string | null;
};

type SetupAction =
  | { type: "compose" }
  | { type: "open" }
  | { type: "remove"; repository: HubProject; setup: SetupPreview }
  | { type: "reset"; repository: HubProject; digest: string };

type DraftItem = {
  id: string;
  kind: SetupKind;
  title: string;
  text: string;
  path: string;
  operation: "file_exists" | "file_contains";
};

function newDraftItem(kind: SetupKind): DraftItem {
  return {
    id: `item-${crypto.randomUUID().replaceAll("-", "")}`,
    kind,
    title: "",
    text: "",
    path: "",
    operation: "file_exists",
  };
}

function fromSetupItem(item: SetupItem): DraftItem {
  return {
    id: item.id,
    kind: item.kind,
    title: item.title,
    text: item.text ?? "",
    path: item.kind === "check" ? item.path : "",
    operation: item.kind === "check" ? item.operation : "file_exists",
  };
}

function toSetupItem(item: DraftItem): SetupItem {
  const { id, kind, title, text, path, operation } = item;
  if (kind !== "check") return { id, kind, title: title.trim(), text };
  return {
    id,
    kind,
    title: title.trim(),
    path: path.trim(),
    operation,
    ...(operation === "file_contains" ? { text } : {}),
  };
}

type RepositoryStatus = {
  state: HubState | null;
  pending: boolean;
  failed: boolean;
  revision: number;
  refresh: () => void;
};

export function PortableSetupPanel({
  nativeRuntime,
  status,
  onOpenSavedWork,
}: {
  nativeRuntime: boolean;
  status?: RepositoryStatus;
  onOpenSavedWork?: () => void;
}) {
  const visible = usePageVisibility();
  const heading = useId();
  const panelHeading = useRef<HTMLHeadingElement>(null);
  const [rows, setRows] = useState<RepositorySetup[] | null>(null);
  const [standaloneState, setStandaloneState] = useState<HubState | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const state = status ? status.state : standaloneState;
  const suppliedProjects = status?.state
    ? JSON.stringify(status.state.projects.map((project) => project.id))
    : null;
  const sharedStatus = status !== undefined;
  const awaitingHubStatus = Boolean(status?.pending);
  const requestKey = JSON.stringify([
    suppliedProjects,
    status?.revision ?? 0,
    refresh,
  ]);
  const [loadedRequest, setLoadedRequest] = useState<string | null>(null);
  const loading =
    nativeRuntime &&
    !status?.failed &&
    (status?.pending || loadedRequest !== requestKey);
  const [notice, setNotice] = useState<string | null>(null);
  const [action, setAction] = useState<SetupAction | null>(null);
  const [title, setTitle] = useState("");
  const [items, setItems] = useState<DraftItem[]>([]);

  useEffect(() => {
    if (
      !nativeRuntime ||
      !visible ||
      awaitingHubStatus ||
      (sharedStatus && suppliedProjects === null)
    )
      return;
    let live = true;
    async function load() {
      try {
        let projectIds: string[];
        if (suppliedProjects !== null) {
          projectIds = JSON.parse(suppliedProjects) as string[];
        } else {
          const next = await hubRequest<HubState>("status");
          if (!live) return;
          setStandaloneState(next);
          projectIds = next.projects.map((project) => project.id);
        }
        const results = await Promise.allSettled(
          projectIds.map((projectId) => loadSetupStatus(projectId)),
        );
        if (!live) return;
        setRows((previous) =>
          projectIds.map((projectId, index) => {
            const result = results[index];
            return result.status === "fulfilled"
              ? {
                  projectId,
                  active: result.value.active,
                  issue: result.value.issue
                    ? "Temper could not verify the saved setup."
                    : undefined,
                  recoveryDigest: result.value.recovery_digest,
                }
              : {
                  projectId,
                  active:
                    previous?.find((row) => row.projectId === projectId)
                      ?.active ?? null,
                  stale: true,
                  issue: normalizeEngineFailure(
                    result.reason,
                    "Temper could not read this setup.",
                  ).message,
                };
          }),
        );
        setStatusError(null);
      } catch (reason: unknown) {
        if (live)
          setStatusError(
            normalizeEngineFailure(
              reason,
              "Temper could not load repository setups.",
            ).message,
          );
      } finally {
        if (live) setLoadedRequest(requestKey);
      }
    }
    void load();
    return () => {
      live = false;
    };
  }, [
    awaitingHubStatus,
    nativeRuntime,
    requestKey,
    sharedStatus,
    suppliedProjects,
    visible,
  ]);

  function clearDraft() {
    setTitle("");
    setItems([]);
  }

  function completed(message: string) {
    if (action?.type === "compose") clearDraft();
    setNotice(message);
    setAction(null);
    setRefresh((value) => value + 1);
  }

  const repositories = state?.projects ?? [];
  const statusUnavailable = Boolean(status?.failed || statusError);
  function importBlock(repository?: HubProject) {
    if (statusUnavailable)
      return "Refresh repository status to import a setup.";
    if (loading) return "Wait for repository status before importing a setup.";
    if (!state) return "Repository setup is unavailable.";
    const block = setupImportBlock(state, repository);
    if (block) return block;
    const row =
      repository && rows?.find((row) => row.projectId === repository.id);
    if (row?.stale) return "Refresh this repository’s setup before importing.";
    if (row?.issue)
      return "Resolve the saved setup issue for this repository before importing.";
    return null;
  }

  const importable = repositories.filter(
    (repository) => !importBlock(repository),
  );
  const importReason =
    importBlock() ??
    (!repositories.length
      ? "Add a repository to automatic workflows to import a setup."
      : !importable.length
        ? repositories.length === 1
          ? importBlock(repositories[0])
          : "Resolve the setup issues shown beside the repositories below."
        : null);
  const shareUnavailable = state?.secure_store_ready === false;
  const hasDraft = Boolean(title || items.length);
  let repositoryActionBlocked = false;
  if (action?.type === "remove" || action?.type === "reset") {
    const project = repositories.find((row) => row.id === action.repository.id);
    const row = rows?.find((row) => row.projectId === project?.id);
    const expectedDigest =
      action.type === "remove" ? action.setup.digest : action.digest;
    const currentDigest =
      action.type === "remove" ? row?.active?.digest : row?.recoveryDigest;
    repositoryActionBlocked =
      loading ||
      statusUnavailable ||
      shareUnavailable ||
      Boolean(row?.stale) ||
      currentDigest !== expectedDigest;
  }
  return (
    <section className="portable-setup-section" aria-labelledby={heading}>
      <div className="portable-setup-heading">
        <h2
          className="modes-section-title"
          id={heading}
          ref={panelHeading}
          tabIndex={-1}
        >
          Repository setup
        </h2>
        {nativeRuntime && (
          <div className="portable-setup-actions repository-setup-actions">
            <Button
              type="button"
              tone={importReason ? "secondary" : "primary"}
              disabled={Boolean(importReason)}
              onClick={() => setAction({ type: "open" })}
            >
              <FileUp aria-hidden="true" size={15} /> Import setup
            </Button>
            <Button
              type="button"
              disabled={shareUnavailable}
              onClick={() => setAction({ type: "compose" })}
            >
              <Plus aria-hidden="true" size={15} />{" "}
              {hasDraft ? "Resume setup draft" : "Create setup"}
            </Button>
            {onOpenSavedWork && (
              <Button type="button" tone="quiet" onClick={onOpenSavedWork}>
                View saved work
              </Button>
            )}
          </div>
        )}
      </div>
      {!nativeRuntime ? (
        <p>Portable setup files are available in the installed desktop app.</p>
      ) : (
        <>
          {notice && <p role="status">{notice}</p>}
          {loading && (
            <LoadingStatus>
              {rows
                ? "Refreshing repository setups…"
                : "Loading repository setups…"}
            </LoadingStatus>
          )}
          {statusError && <p role="alert">{statusError}</p>}
          {shareUnavailable && <p>Unlock secure storage to share a setup.</p>}
          {hasDraft && rows?.some((row) => row.active) && (
            <p>
              Finish or discard your draft before sharing a different setup.
            </p>
          )}
          {importReason && !loading && <p>{importReason}</p>}
          {repositories.map((repository) => {
            const row = rows?.find((item) => item.projectId === repository.id);
            const { active, issue, recoveryDigest, stale } = row ?? {};
            const setupOutOfDate = statusUnavailable || stale;
            const setupActionsUnavailable =
              loading || setupOutOfDate || shareUnavailable;
            const block =
              !loading && !statusUnavailable && !importBlock()
                ? importBlock(repository)
                : null;
            return (
              <div className="repository-setup-row" key={repository.id}>
                <div className="portable-setup-heading">
                  <div>
                    <strong>{repository.label}</strong>
                    <small>{repository.root}</small>
                    {repository.paused && <p>Repository updates paused</p>}
                    {repository.pending_recovery && (
                      <p>Repository recovery needed</p>
                    )}
                    {repository.attention && (
                      <p>
                        {repository.attention.status === "task_cleanup_blocked"
                          ? "Task cleanup needs attention"
                          : "Edited files need attention"}
                      </p>
                    )}
                    {repository.active.length > 0 && (
                      <p>
                        {statusUnavailable
                          ? "Last known installed guidance"
                          : "Installed guidance"}
                        {" · "}
                        {repository.active.join(", ")}
                      </p>
                    )}
                    {active ? (
                      <p>
                        {setupOutOfDate ? "Last known setup" : "Imported setup"}
                        {" · "}
                        {active.title}
                      </p>
                    ) : row && !issue && !statusUnavailable ? (
                      <p>No setup imported</p>
                    ) : null}
                  </div>
                  {recoveryDigest && (
                    <Button
                      type="button"
                      tone="quiet"
                      disabled={setupActionsUnavailable}
                      onClick={() =>
                        setAction({
                          type: "reset",
                          repository,
                          digest: recoveryDigest,
                        })
                      }
                    >
                      Clear unreadable setup
                    </Button>
                  )}
                  {active && (
                    <div className="repository-setup-actions">
                      <Button
                        type="button"
                        aria-label={"Share setup for " + repository.label}
                        disabled={setupActionsUnavailable || hasDraft}
                        onClick={() => {
                          setTitle(active.title);
                          setItems(active.items.map(fromSetupItem));
                          setAction({ type: "compose" });
                        }}
                      >
                        Share setup
                      </Button>
                    </div>
                  )}
                </div>
                {active && (
                  <details>
                    <summary>View setup contents</summary>
                    <SetupContents value={active} showTitle={false} />
                    <Button
                      type="button"
                      tone="quiet"
                      disabled={setupActionsUnavailable}
                      onClick={() =>
                        setAction({
                          type: "remove",
                          repository,
                          setup: active,
                        })
                      }
                    >
                      Remove setup
                    </Button>
                  </details>
                )}
                {active && (
                  <WorkflowUpdates
                    repository={repository}
                    active={active}
                    blocked={setupActionsUnavailable || Boolean(issue)}
                    revision={requestKey}
                    onComplete={(message) => {
                      setNotice(message);
                      setRefresh((value) => value + 1);
                    }}
                  />
                )}
                {issue && <p role="alert">{issue}</p>}
                {block && repositories.length > 1 && <p>{block}</p>}
              </div>
            );
          })}
          {!loading &&
            (statusUnavailable ||
              rows?.some((row) => row.issue) ||
              !sharedStatus) && (
              <Button
                type="button"
                tone="quiet"
                onClick={() => {
                  status?.refresh();
                  setRefresh((value) => value + 1);
                }}
              >
                Refresh repositories
              </Button>
            )}
        </>
      )}
      {action && (
        <PortableSetupDialog
          action={action}
          repositories={repositories}
          blockedReason={importReason}
          repositoryActionBlocked={repositoryActionBlocked}
          targetBlock={importBlock}
          draft={{ title, items, setTitle, setItems, clear: clearDraft }}
          returnFocusFallback={panelHeading}
          onClose={() => setAction(null)}
          onComplete={completed}
        />
      )}
    </section>
  );
}

function SetupContents({
  value,
  showTitle = true,
}: {
  value: SetupPreview;
  showTitle?: boolean;
}) {
  return (
    <div className="portability-preview portable-setup-contents">
      {showTitle && (
        <header>
          <strong>{value.title}</strong>
        </header>
      )}
      <ul aria-label="Setup contents">
        {value.items.map((item) => (
          <li key={item.id}>
            <span>
              <small>{setupKinds[item.kind]}</small>
              <strong>{item.title}</strong>
              {item.kind === "check" ? (
                <>
                  <span>
                    {item.operation === "file_exists"
                      ? "File exists"
                      : "File contains text"}
                  </span>
                  <code>{item.path}</code>
                  {item.operation === "file_contains" && (
                    <span className="portable-setup-text">{item.text}</span>
                  )}
                </>
              ) : (
                <span className="portable-setup-text">{item.text}</span>
              )}
            </span>
          </li>
        ))}
      </ul>
      <details className="workflow-provenance">
        <summary>Signature and file details</summary>
        <dl className="mode-detail-list">
          <div>
            <dt>Signer fingerprint</dt>
            <dd>
              <code>{value.signer_fingerprint}</code>
            </dd>
          </div>
          <div>
            <dt>Setup digest</dt>
            <dd>
              <code>{value.digest}</code>
            </dd>
          </div>
        </dl>
      </details>
    </div>
  );
}

function WorkflowUpdates({
  repository,
  active,
  blocked,
  revision,
  onComplete,
}: {
  repository: HubProject;
  active: SetupPreview;
  blocked: boolean;
  revision: string;
  onComplete: (message: string) => void;
}) {
  const visible = usePageVisibility();
  const headingId = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const { id: projectId } = repository;
  const [refresh, setRefresh] = useState(0);
  const [status, setStatus] = useState<SetupUpdateStatus | null>(null);
  const [statusError, setStatusError] = useState(false);
  const [lastCheck, setLastCheck] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [review, setReview] = useState<{
    baseline: SetupPreview;
    preview: SetupUpdatePreview;
    idempotencyKey: string;
  } | null>(null);
  const inFlight = useRef(false);
  const reviewOpener = useRef<HTMLButtonElement | null>(null);
  const checkKey = JSON.stringify([active.digest, refresh, revision]);

  useEffect(() => {
    if (!visible) return;
    let live = true;
    void loadSetupUpdateStatus(projectId).then(
      (result) => {
        if (live) {
          setStatus(result);
          setStatusError(false);
          setLastCheck(checkKey);
        }
      },
      () => {
        if (live) {
          setStatusError(true);
          setLastCheck(checkKey);
        }
      },
    );
    return () => {
      live = false;
    };
  }, [checkKey, projectId, visible]);

  useEffect(() => {
    if (!visible) return;
    function checkOnFocus() {
      if (!inFlight.current) setRefresh((value) => value + 1);
    }
    window.addEventListener("focus", checkOnFocus);
    return () => window.removeEventListener("focus", checkOnFocus);
  }, [visible]);

  async function run(message: string, work: () => Promise<void>) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(message);
    setNotice(null);
    setError(null);
    try {
      await work();
    } catch (reason: unknown) {
      const failure = normalizeEngineFailure(
        reason,
        "Temper could not complete this workflow update action.",
      );
      if (failure.code !== "cancelled") setError(failure.message);
    } finally {
      inFlight.current = false;
      setBusy(null);
      setRefresh((value) => value + 1);
    }
  }

  function openReview(
    direction: SetupUpdatePreview["direction"],
    opener: HTMLButtonElement,
  ) {
    reviewOpener.current = opener;
    void run(
      direction === "rollback"
        ? "Preparing the previous setup for review…"
        : "Checking the update…",
      async () => {
        const preview = await previewSetupUpdate(projectId, direction);
        if (
          preview.project_id !== projectId ||
          preview.direction !== direction ||
          preview.active_digest !== active.digest
        )
          throw new Error(
            "The repository setup changed. Check again before reviewing.",
          );
        setReview({
          baseline: active,
          preview,
          idempotencyKey: crypto.randomUUID(),
        });
      },
    );
  }

  function changeSource() {
    void run("Waiting for the update folder and check file…", async () => {
      await connectSetupUpdateSource(projectId);
      setNotice("Update source connected.");
    });
  }

  const unavailable =
    blocked || repository.paused || repository.pending_recovery;
  const rollback = review?.preview.direction === "rollback";
  const reviewChanged = Boolean(
    review && review.preview.active_digest !== active.digest,
  );
  const statusText =
    lastCheck !== checkKey
      ? "Checking for workflow updates…"
      : statusError
        ? "Temper could not check for workflow updates."
        : !status
          ? null
          : status.issue
            ? normalizeEngineFailure(
                { message: status.issue },
                "Temper could not use the update source. Check the folder and test cases, then try again.",
              ).message
            : status.available
              ? "A workflow update is available."
              : status.connected
                ? "Update source connected. No update is ready to review."
                : "No update source connected.";

  return (
    <section className="workflow-updates" aria-labelledby={headingId}>
      <h3 id={headingId} ref={heading} tabIndex={-1}>
        Workflow updates
      </h3>
      <p role="status">{statusText}</p>
      {status && (
        <details
          className="workflow-provenance"
          open={!status.connected || undefined}
        >
          <summary>How to choose an update source</summary>
          <p>
            First choose the folder where your publisher leaves the signed
            <code> workflow.temper-setup</code> file. Then choose a trusted JSON
            file with test cases from outside that folder. Each update needs
            your approval before it changes the setup.
          </p>
        </details>
      )}
      {status && (
        <div className="portable-setup-actions repository-setup-actions">
          {status.available && !statusError && !status.issue && (
            <Button
              type="button"
              tone="primary"
              disabled={unavailable || Boolean(busy)}
              onClick={(event) => openReview("update", event.currentTarget)}
            >
              Review update
            </Button>
          )}
          {status.can_rollback && (
            <Button
              type="button"
              disabled={unavailable || Boolean(busy)}
              onClick={(event) => openReview("rollback", event.currentTarget)}
            >
              Review previous setup
            </Button>
          )}
          <Button
            type="button"
            disabled={unavailable || Boolean(busy)}
            onClick={changeSource}
          >
            {status.connected
              ? "Change update source"
              : "Connect update source"}
          </Button>
          {status.connected && (
            <Button
              type="button"
              tone="quiet"
              disabled={blocked || Boolean(busy)}
              onClick={() => {
                void run("Disconnecting the update source…", async () => {
                  await disconnectSetupUpdateSource(projectId);
                  setNotice("Update source disconnected.");
                });
              }}
            >
              Disconnect source
            </Button>
          )}
          <Button
            type="button"
            tone="quiet"
            disabled={Boolean(busy)}
            onClick={() => setRefresh((value) => value + 1)}
          >
            Check for updates
          </Button>
        </div>
      )}
      {!status && statusError && (
        <Button
          type="button"
          tone="quiet"
          onClick={() => setRefresh((value) => value + 1)}
        >
          Retry update check
        </Button>
      )}
      {!review && busy && <LoadingStatus>{busy}</LoadingStatus>}
      {!review && error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {review && (
        <WorkflowUpdateReview
          repository={repository}
          active={review.baseline}
          preview={review.preview}
          busy={busy}
          error={error}
          canClose={() => !inFlight.current}
          blocked={unavailable || reviewChanged}
          fallbackFocus={heading}
          opener={reviewOpener}
          onClose={() => {
            setReview(null);
            setError(null);
          }}
          onApprove={() => {
            if (unavailable || reviewChanged) return;
            void run(
              rollback
                ? "Restoring the previous setup…"
                : "Applying the workflow update…",
              async () => {
                const applied = await approveSetupUpdate(
                  review.preview,
                  review.idempotencyKey,
                );
                if (applied.digest !== review.preview.digest) {
                  throw new Error(
                    "The active setup differs from the reviewed setup. Check the repository before trying again.",
                  );
                }
                setReview(null);
                onComplete(
                  rollback
                    ? `Restored “${applied.title}” in ${repository.label}.`
                    : `Updated “${applied.title}” in ${repository.label}.`,
                );
              },
            );
          }}
        />
      )}
    </section>
  );
}

function WorkflowUpdateReview({
  repository,
  active,
  preview,
  busy,
  error,
  blocked,
  fallbackFocus,
  opener,
  canClose,
  onClose,
  onApprove,
}: {
  repository: HubProject;
  active: SetupPreview;
  preview: SetupUpdatePreview;
  busy: string | null;
  error: string | null;
  blocked: boolean;
  fallbackFocus: RefObject<HTMLHeadingElement | null>;
  opener: RefObject<HTMLButtonElement | null>;
  canClose: () => boolean;
  onClose: () => void;
  onApprove: () => void;
}) {
  const visible = usePageVisibility();
  const rollback = preview.direction === "rollback";
  const activeChecks = new Map(
    active.items
      .filter((item) => item.kind === "check")
      .map((item) => [item.id, item]),
  );
  const changedChecks = preview.items
    .filter((item) => item.kind === "check")
    .flatMap((item) => {
      const current = activeChecks.get(item.id);
      return current && current.text !== item.text ? [{ item, current }] : [];
    });

  return (
    <Dialog.Root
      open={visible}
      onOpenChange={(open) => {
        if (!open && canClose()) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content
          className="core-dialog portability-dialog portable-setup-dialog"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            const heading = fallbackFocus.current;
            if (!visible || heading?.closest("[hidden], [inert]")) return;
            const target = opener.current;
            if (target?.isConnected && !target.disabled) target.focus();
            else heading?.focus();
          }}
        >
          <Dialog.Close
            aria-label="Close"
            className="dialog-close"
            disabled={Boolean(busy)}
          >
            <X size={18} />
          </Dialog.Close>
          <Dialog.Title>
            {rollback ? "Review previous setup" : "Review workflow update"}
          </Dialog.Title>
          <Dialog.Description>
            {rollback
              ? "Review the setup that will replace the current setup for this repository."
              : "Review the signed setup and the check results before applying the update."}
          </Dialog.Description>
          <dl className="mode-detail-list portable-setup-path">
            <div>
              <dt>Repository</dt>
              <dd>
                {repository.label} <code>{repository.root}</code>
              </dd>
            </div>
          </dl>
          {preview.assertion_count !== undefined &&
            preview.baseline_passed !== undefined &&
            preview.candidate_passed !== undefined && (
              <>
                <h3>Check results</h3>
                <dl className="mode-detail-list">
                  <div>
                    <dt>Current setup</dt>
                    <dd>
                      {preview.baseline_passed} of {preview.assertion_count}{" "}
                      correct
                    </dd>
                  </div>
                  <div>
                    <dt>Updated setup</dt>
                    <dd>
                      {preview.candidate_passed} of {preview.assertion_count}{" "}
                      correct
                    </dd>
                  </div>
                </dl>
              </>
            )}
          {changedChecks.length > 0 && (
            <>
              <h3>Changed checks</h3>
              {changedChecks.map(({ item, current }) => (
                <dl
                  className="mode-detail-list portable-setup-path"
                  key={item.id}
                >
                  <div>
                    <dt>{item.title}</dt>
                    <dd>
                      <code>{item.path}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>Current text</dt>
                    <dd className="portable-setup-text">{current.text}</dd>
                  </div>
                  <div>
                    <dt>{rollback ? "Text to restore" : "Updated text"}</dt>
                    <dd className="portable-setup-text">{item.text}</dd>
                  </div>
                </dl>
              ))}
            </>
          )}
          <details className="workflow-provenance">
            <summary>
              {rollback ? "View setup to restore" : "View updated setup"}
            </summary>
            <p className="portable-setup-path">
              File <code>{preview.source_name}</code>
            </p>
            <SetupContents value={preview} />
          </details>
          <details className="workflow-provenance">
            <summary>View current setup</summary>
            <SetupContents value={active} />
          </details>
          {blocked && (
            <p role="status">
              Close this review and check the latest repository setup before
              making changes.
            </p>
          )}
          <div className="core-dialog__actions">
            <Button
              type="button"
              tone="quiet"
              disabled={Boolean(busy)}
              onClick={onClose}
            >
              Cancel
            </Button>
            <Button
              type="button"
              tone="primary"
              disabled={Boolean(busy) || blocked}
              onClick={onApprove}
            >
              {rollback ? "Restore previous setup" : "Apply workflow update"}
            </Button>
          </div>
          {busy && <LoadingStatus>{busy}</LoadingStatus>}
          {error && (
            <p className="portability-error" role="alert">
              {error}
            </p>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function PortableSetupDialog({
  action,
  repositories,
  blockedReason,
  repositoryActionBlocked,
  targetBlock,
  draft,
  returnFocusFallback,
  onClose,
  onComplete,
}: {
  action: SetupAction;
  repositories: HubProject[];
  blockedReason: string | null;
  repositoryActionBlocked: boolean;
  targetBlock: (repository?: HubProject) => string | null;
  draft: {
    title: string;
    items: DraftItem[];
    setTitle: Dispatch<SetStateAction<string>>;
    setItems: Dispatch<SetStateAction<DraftItem[]>>;
    clear: () => void;
  };
  returnFocusFallback: RefObject<HTMLHeadingElement | null>;
  onClose: () => void;
  onComplete: (message: string) => void;
}) {
  const visible = usePageVisibility();
  const focusReturn = useDialogFocusReturn(visible);
  const { title, setTitle, items, setItems, clear } = draft;
  const [newKind, setNewKind] = useState<SetupKind>("skill");
  const [exportPreview, setExportPreview] = useState<SetupPreview | null>(null);
  const [importPreview, setImportPreview] = useState<SetupImportPreview | null>(
    null,
  );
  const [projectId, setProjectId] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const reviewHeading = useRef<HTMLHeadingElement>(null);
  const draftName = useRef<HTMLInputElement>(null);
  const targetSelectId = useId();
  const openAgain = useRef(false);
  const preview = exportPreview ?? importPreview;
  const editing = action.type === "compose" && !exportPreview;
  const target = repositories.find((row) => row.id === projectId);
  const selectedBlock = target ? targetBlock(target) : blockedReason;
  const targetChanged = Boolean(projectId && !target);

  useEffect(() => {
    if (preview) {
      reviewHeading.current?.focus();
      openAgain.current = true;
    } else if (openAgain.current) {
      (draftName.current ?? document.getElementById(targetSelectId))?.focus();
    }
  }, [preview, targetSelectId]);

  async function run(message: string, work: () => Promise<void>) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(message);
    setError(null);
    try {
      await work();
    } catch (reason: unknown) {
      const failure = normalizeEngineFailure(
        reason,
        "Temper could not complete this setup action.",
      );
      if (failure.code !== "cancelled") setError(failure.message);
    } finally {
      inFlight.current = false;
      setBusy(null);
    }
  }

  function reviewDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!items.length) return;
    const draft = items.map(toSetupItem);
    if (
      !title.trim() ||
      draft.some(
        (item) =>
          !item.title ||
          (item.kind === "check"
            ? !item.path ||
              (item.operation === "file_contains" && !item.text?.trim())
            : !item.text.trim()),
      )
    ) {
      setError(
        "Enter a name and content for every item before reviewing the setup.",
      );
      return;
    }
    void run("Preparing setup review…", async () => {
      setExportPreview(await previewSetupExport(title.trim(), draft));
    });
  }

  function updateItem(id: string, update: Partial<DraftItem>) {
    setItems((current) =>
      current.map((item) => (item.id === id ? { ...item, ...update } : item)),
    );
  }

  function chooseFile() {
    if (!target || selectedBlock) return;
    void run("Opening and verifying the setup…", async () => {
      const result = await openSetupFile(projectId);
      if (result.project_id !== projectId)
        throw new Error(
          "The setup review targets a different repository. Choose the file again.",
        );
      setImportPreview(result);
      setConsent(false);
    });
  }

  function complete() {
    if (repositoryActionBlocked) return;
    if (exportPreview) {
      void run("Saving the setup file…", async () => {
        const saved = await saveSetupFile(exportPreview.digest);
        if (saved.digest !== exportPreview.digest)
          throw new Error(
            "The saved setup digest differs from the reviewed setup. Review the draft again.",
          );
        onComplete(`Saved “${saved.title}”.`);
      });
    } else if (importPreview && consent && target && !selectedBlock) {
      void run("Applying the setup…", async () => {
        const active = await approveSetup(importPreview);
        if (active.digest !== importPreview.digest)
          throw new Error(
            "The active setup differs from the reviewed setup. Reopen the file to review it again.",
          );
        onComplete(
          `“${active.title}” is active in ${target?.label ?? "the selected repository"}.`,
        );
      });
    } else if (action.type === "reset") {
      void run("Clearing the unreadable setup…", async () => {
        await resetSetup(action.repository.id, action.digest);
        onComplete(
          "Unreadable setup cleared. You can open a setup file again.",
        );
      });
    } else if (action.type === "remove") {
      void run("Removing the setup…", async () => {
        await removeSetup(action.repository.id, action.setup.digest);
        onComplete(
          `Removed “${action.setup.title}” from ${action.repository.label}.`,
        );
      });
    }
  }

  const dialogTitle =
    action.type === "remove"
      ? `Remove “${action.setup.title}”?`
      : action.type === "reset"
        ? "Clear the unreadable setup?"
        : action.type === "open"
          ? "Import setup"
          : "Share setup";

  return (
    <Dialog.Root
      open={visible}
      onOpenChange={(open) => {
        if (!open && !inFlight.current) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content
          onOpenAutoFocus={focusReturn.onOpenAutoFocus}
          onCloseAutoFocus={(event) => {
            focusReturn.onCloseAutoFocus(event);
            const heading = returnFocusFallback.current;
            if (
              visible &&
              heading &&
              !heading.closest("[hidden], [inert]") &&
              document.activeElement === document.body
            )
              heading.focus();
          }}
          className="core-dialog portability-dialog portable-setup-dialog"
        >
          <Dialog.Close
            aria-label="Close"
            className="dialog-close"
            disabled={!!busy}
          >
            <X size={18} />
          </Dialog.Close>
          <Dialog.Title>{dialogTitle}</Dialog.Title>
          <Dialog.Description>
            {action.type === "compose"
              ? "Choose what to share in a signed setup file. The recipient reviews its contents before applying it."
              : action.type === "open"
                ? "Choose the repository that will receive the setup, then open a signed .temper-setup file."
                : action.type === "reset"
                  ? "Clear the damaged setup from " +
                    action.repository.label +
                    ". You can then open and review a setup file again."
                  : `Future tasks in ${action.repository.label} will stop receiving this setup through Temper.`}
          </Dialog.Description>

          {editing && (
            <form onSubmit={reviewDraft}>
              <fieldset className="portable-setup-fields" disabled={!!busy}>
                <label className="core-field">
                  <span>Setup name</span>
                  <input
                    ref={draftName}
                    maxLength={120}
                    value={title}
                    onChange={(event) => setTitle(event.currentTarget.value)}
                    required
                  />
                </label>
                {items.map((item) => (
                  <fieldset className="portable-setup-item" key={item.id}>
                    <legend>
                      {setupKinds[item.kind]}
                      {item.title.trim() ? ` · ${item.title.trim()}` : ""}
                    </legend>
                    <label className="core-field">
                      <span>Item name</span>
                      <input
                        maxLength={120}
                        value={item.title}
                        onChange={(event) =>
                          updateItem(item.id, {
                            title: event.currentTarget.value,
                          })
                        }
                        required
                      />
                    </label>
                    {item.kind === "check" ? (
                      <>
                        <div className="core-field">
                          <span>Check type</span>
                          <TemperSelect
                            ariaLabel="Check type"
                            disabled={!!busy}
                            portalled={false}
                            value={item.operation}
                            onValueChange={(operation) =>
                              updateItem(item.id, { operation })
                            }
                            options={[
                              { value: "file_exists", label: "File exists" },
                              {
                                value: "file_contains",
                                label: "File contains text",
                              },
                            ]}
                          />
                        </div>
                        <label className="core-field">
                          <span>Repository-relative file path</span>
                          <input
                            maxLength={240}
                            placeholder="docs/guide.md"
                            value={item.path}
                            onChange={(event) =>
                              updateItem(item.id, {
                                path: event.currentTarget.value,
                              })
                            }
                            required
                          />
                        </label>
                        {item.operation === "file_contains" && (
                          <label className="core-field">
                            <span>Text to find</span>
                            <input
                              maxLength={200}
                              value={item.text}
                              onChange={(event) =>
                                updateItem(item.id, {
                                  text: event.currentTarget.value,
                                })
                              }
                              required
                            />
                          </label>
                        )}
                      </>
                    ) : (
                      <label className="core-field">
                        <span>
                          {item.kind === "skill"
                            ? "Skill guidance"
                            : item.kind === "knowledge"
                              ? "Knowledge text"
                              : "Preference text"}
                        </span>
                        <textarea
                          maxLength={4000}
                          rows={3}
                          value={item.text}
                          onChange={(event) =>
                            updateItem(item.id, {
                              text: event.currentTarget.value,
                            })
                          }
                          required
                        />
                      </label>
                    )}
                    <Button
                      type="button"
                      tone="quiet"
                      onClick={() =>
                        setItems((current) =>
                          current.filter((row) => row.id !== item.id),
                        )
                      }
                    >
                      Remove {setupKinds[item.kind].toLowerCase()}
                    </Button>
                  </fieldset>
                ))}
                <div className="portable-setup-add">
                  <div className="core-field">
                    <span>Item type</span>
                    <TemperSelect
                      ariaLabel="Item type"
                      disabled={!!busy}
                      portalled={false}
                      value={newKind}
                      onValueChange={setNewKind}
                      options={(Object.keys(setupKinds) as SetupKind[]).map(
                        (value) => ({ value, label: setupKinds[value] }),
                      )}
                    />
                  </div>
                  <Button
                    type="button"
                    disabled={items.length >= 20}
                    onClick={() =>
                      setItems((current) => [...current, newDraftItem(newKind)])
                    }
                  >
                    Add item
                  </Button>
                </div>
                {!items.length && <p>Add an item to review your setup.</p>}
                {items.length >= 20 && (
                  <p>A setup can include up to 20 items.</p>
                )}
                <div className="core-dialog__actions">
                  <Button type="button" tone="quiet" onClick={onClose}>
                    {title || items.length ? "Keep draft" : "Cancel"}
                  </Button>
                  {(title || items.length > 0) && (
                    <Button
                      type="button"
                      tone="quiet"
                      onClick={() => {
                        clear();
                        onClose();
                      }}
                    >
                      Discard draft
                    </Button>
                  )}
                  <Button type="submit" tone="primary" disabled={!items.length}>
                    Review setup
                  </Button>
                </div>
              </fieldset>
            </form>
          )}

          {action.type === "open" && !importPreview && (
            <>
              <div className="core-field">
                <span>Target repository</span>
                <TemperSelect
                  id={targetSelectId}
                  ariaLabel="Target repository"
                  disabled={!!busy}
                  portalled={false}
                  value={target?.id ?? "#"}
                  onValueChange={(value) => {
                    setProjectId(value === "#" ? "" : value);
                    setError(null);
                  }}
                  options={[
                    {
                      value: "#",
                      label: "Choose a repository",
                    },
                    ...repositories.map((repository) => ({
                      value: repository.id,
                      label: repository.label,
                      description: targetBlock(repository) ?? repository.root,
                    })),
                  ]}
                />
              </div>
              {target && (
                <p className="portable-setup-path">
                  <code>{target.root}</code>
                </p>
              )}
              <div className="core-dialog__actions">
                <Button
                  type="button"
                  tone="quiet"
                  disabled={!!busy}
                  onClick={onClose}
                >
                  Cancel
                </Button>
                <Button
                  type="button"
                  tone="primary"
                  disabled={!!busy || !target || Boolean(selectedBlock)}
                  onClick={chooseFile}
                >
                  Choose setup file
                </Button>
              </div>
            </>
          )}

          {preview && (
            <>
              <h3 tabIndex={-1} ref={reviewHeading}>
                {importPreview
                  ? "Review before applying"
                  : "Review before saving"}
              </h3>
              {importPreview && (
                <dl className="mode-detail-list portable-setup-path">
                  <div>
                    <dt>File</dt>
                    <dd>{importPreview.source_name}</dd>
                  </div>
                  <div>
                    <dt>Repository</dt>
                    <dd>
                      {target?.label} <code>{target?.root}</code>
                    </dd>
                  </div>
                </dl>
              )}
              <SetupContents value={preview} />
              {importPreview && (
                <>
                  <p>
                    Confirm the signer with the sender under Signature and file
                    details. Future tasks in this repository can load this
                    guidance and the results of these read-only file checks
                    through Temper.
                  </p>
                  <label className="portable-setup-consent">
                    <input
                      type="checkbox"
                      checked={consent}
                      disabled={!!busy}
                      onChange={(event) =>
                        setConsent(event.currentTarget.checked)
                      }
                    />
                    <span>
                      {importPreview.active_digest
                        ? "I approve replacing the active setup for this repository."
                        : "I approve applying these items to this repository."}
                    </span>
                  </label>
                </>
              )}
              <div className="core-dialog__actions">
                <Button
                  type="button"
                  tone="quiet"
                  disabled={!!busy}
                  onClick={() => {
                    setExportPreview(null);
                    setImportPreview(null);
                    setConsent(false);
                    setError(null);
                  }}
                >
                  {importPreview ? "Choose another file" : "Back to edit"}
                </Button>
                <Button
                  type="button"
                  tone="primary"
                  disabled={
                    !!busy ||
                    (!!importPreview &&
                      (!consent || targetChanged || Boolean(selectedBlock)))
                  }
                  onClick={complete}
                >
                  {importPreview
                    ? importPreview.active_digest
                      ? "Replace setup"
                      : "Apply setup"
                    : "Save setup file"}
                </Button>
              </div>
            </>
          )}

          {repositoryActionBlocked && (
            <p role="status">
              Close this review and check the latest repository setup before
              making changes.
            </p>
          )}
          {(action.type === "remove" || action.type === "reset") && (
            <div className="core-dialog__actions">
              <Button
                type="button"
                tone="quiet"
                disabled={!!busy}
                onClick={onClose}
              >
                {action.type === "reset" ? "Cancel" : "Keep setup"}
              </Button>
              <Button
                type="button"
                tone="primary"
                disabled={!!busy || repositoryActionBlocked}
                onClick={complete}
              >
                {action.type === "reset"
                  ? "Clear unreadable setup"
                  : "Remove setup"}
              </Button>
            </div>
          )}

          {action.type === "open" && (selectedBlock || targetChanged) && (
            <p role="status">
              {selectedBlock ??
                "This repository is no longer available. Choose another repository."}
            </p>
          )}
          {busy && <LoadingStatus>{busy}</LoadingStatus>}
          {error && (
            <p className="portability-error" role="alert">
              {error}
            </p>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
