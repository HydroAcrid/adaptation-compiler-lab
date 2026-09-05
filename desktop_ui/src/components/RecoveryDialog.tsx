import * as Dialog from "@radix-ui/react-dialog";
import {
  Check,
  Download,
  FolderOpen,
  KeyRound,
  LoaderCircle,
  ShieldCheck,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  exportRecovery,
  loadRecoveryExportPreview,
  loadRecoveryImportPreview,
  restoreRecovery,
  selectRecoveryProject,
  type EngineRecoveryPreview,
  type EngineRecoveryProjectSelection,
} from "../engine";
import { Button } from "./ui";

export function RecoveryExportDialog({
  open,
  onOpenChange,
  snapshotDigest,
  onComplete,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  snapshotDigest: string;
  onComplete: (message: string) => void;
}) {
  const [preview, setPreview] = useState<EngineRecoveryPreview | null>(null);
  const [passphrase, setPassphrase] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let active = true;
    loadRecoveryExportPreview()
      .then((value) => {
        if (active) setPreview(value);
      })
      .catch((reason: unknown) =>
        active
          ? setError(
              reason instanceof Error
                ? reason.message
                : "Temper could not prepare a recovery file.",
            )
          : undefined,
      )
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [open]);

  function changeOpen(value: boolean) {
    if (!value) {
      setPreview(null);
      setPassphrase("");
      setConfirmation("");
      setError(null);
      setBusy(false);
    }
    onOpenChange(value);
  }

  async function save() {
    if (!preview) return;
    if (passphrase.length < 14) {
      setError("Use a passphrase with at least 14 characters.");
      return;
    }
    if (passphrase !== confirmation) {
      setError("The two passphrases do not match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await exportRecovery(
        preview,
        passphrase,
        snapshotDigest,
        crypto.randomUUID(),
      );
      if (!result) return;
      setPassphrase("");
      setConfirmation("");
      changeOpen(false);
      onComplete("Encrypted recovery file created.");
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Temper could not create the recovery file.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog.Root onOpenChange={changeOpen} open={open}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="recovery-dialog">
          <Dialog.Close aria-label="Close" className="dialog-close">
            <X size={18} />
          </Dialog.Close>
          <div className="dialog-heading-icon">
            <Download size={20} />
          </div>
          <Dialog.Title>Create a recovery file</Dialog.Title>
          <Dialog.Description>
            Restore this same Temper identity and its governed history on
            another supported device.
          </Dialog.Description>
          {busy && !preview ? (
            <div className="recovery-dialog__loading" role="status">
              <LoaderCircle className="setup-progress__spinner" size={20} />
              Verifying local state…
            </div>
          ) : null}
          {preview ? (
            <>
              <div className="recovery-dialog__summary">
                <SummaryRow
                  label="Projects"
                  value={String(preview.projects.length)}
                />
                <SummaryRow
                  label="Governed files"
                  value={String(preview.governed_file_count)}
                />
                <SummaryRow
                  label="Encrypted evidence"
                  value={`${preview.encrypted_raw_file_count} files`}
                />
              </div>
              <div className="recovery-dialog__notice">
                <ShieldCheck size={18} />
                <span>
                  Includes your Temper identity and encryption key. It excludes
                  Codex, Claude, and API credentials. Keep the file and
                  passphrase separately.
                </span>
              </div>
              <label className="recovery-dialog__field">
                <span>Recovery passphrase</span>
                <input
                  autoComplete="new-password"
                  onChange={(event) => setPassphrase(event.target.value)}
                  type="password"
                  value={passphrase}
                />
              </label>
              <label className="recovery-dialog__field">
                <span>Confirm passphrase</span>
                <input
                  autoComplete="new-password"
                  onChange={(event) => setConfirmation(event.target.value)}
                  type="password"
                  value={confirmation}
                />
              </label>
            </>
          ) : null}
          {error ? <p role="alert">{error}</p> : null}
          <div className="dialog-footer">
            <Button
              disabled={busy}
              onClick={() => changeOpen(false)}
              tone="quiet"
            >
              Cancel
            </Button>
            <Button
              disabled={busy || !preview || !passphrase || !confirmation}
              onClick={() => void save()}
              tone="primary"
            >
              {busy ? "Creating…" : "Choose where to save"}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function RecoveryImportDialog({
  open,
  onOpenChange,
  setupDigest,
  onRestored,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  setupDigest: string;
  onRestored: () => void | Promise<void>;
}) {
  const [passphrase, setPassphrase] = useState("");
  const [preview, setPreview] = useState<EngineRecoveryPreview | null>(null);
  const [selections, setSelections] = useState<
    Record<string, EngineRecoveryProjectSelection>
  >({});
  const [busy, setBusy] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function changeOpen(value: boolean) {
    if (!value) {
      setPassphrase("");
      setPreview(null);
      setSelections({});
      setBusy(false);
      setRestoring(false);
      setError(null);
    }
    onOpenChange(value);
  }

  async function chooseFile() {
    if (passphrase.length < 14) {
      setError("Enter the recovery passphrase first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await loadRecoveryImportPreview(passphrase);
      setPassphrase("");
      if (result) setPreview(result);
    } catch (reason: unknown) {
      setPassphrase("");
      setError(
        reason instanceof Error
          ? reason.message
          : "Temper could not verify that recovery file.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function chooseProject(projectId: string) {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      const selection = await selectRecoveryProject(
        preview.preview_token,
        projectId,
      );
      if (selection) {
        setSelections((current) => ({ ...current, [projectId]: selection }));
      }
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Temper could not use that project folder.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function restore() {
    if (!preview || Object.keys(selections).length !== preview.projects.length)
      return;
    setBusy(true);
    setRestoring(true);
    setError(null);
    try {
      await restoreRecovery(
        preview,
        selections,
        setupDigest,
        crypto.randomUUID(),
      );
      await onRestored();
    } catch (reason: unknown) {
      setRestoring(false);
      setError(
        reason instanceof Error
          ? reason.message
          : "Temper could not safely restore this installation.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog.Root onOpenChange={changeOpen} open={open}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="recovery-dialog">
          {!restoring ? (
            <Dialog.Close aria-label="Close" className="dialog-close">
              <X size={18} />
            </Dialog.Close>
          ) : null}
          <div className="dialog-heading-icon">
            {restoring ? (
              <LoaderCircle className="setup-progress__spinner" size={20} />
            ) : (
              <KeyRound size={20} />
            )}
          </div>
          <Dialog.Title>
            {restoring
              ? "Restoring your Temper"
              : "Restore from a recovery file"}
          </Dialog.Title>
          <Dialog.Description>
            {restoring
              ? "Verifying the identity, restoring governed history, and binding projects on this device."
              : "Nothing is replaced. Restore is available only before a new Temper identity is created."}
          </Dialog.Description>
          {!preview && !restoring ? (
            <>
              <label className="recovery-dialog__field">
                <span>Recovery passphrase</span>
                <input
                  autoComplete="current-password"
                  onChange={(event) => setPassphrase(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void chooseFile();
                  }}
                  type="password"
                  value={passphrase}
                />
              </label>
              <Button
                disabled={busy || passphrase.length < 14}
                onClick={() => void chooseFile()}
                tone="primary"
              >
                {busy ? "Verifying…" : "Choose recovery file"}
              </Button>
            </>
          ) : null}
          {preview && !restoring ? (
            <div className="recovery-projects">
              <div className="recovery-dialog__notice">
                <ShieldCheck size={18} />
                <span>
                  Identity verified. Choose where each registered project lives
                  on this device; source paths are never displayed.
                </span>
              </div>
              {preview.projects.map((project) => {
                const selected = selections[project.project_id];
                return (
                  <div className="recovery-project" key={project.project_id}>
                    <div>
                      <strong>{project.display_name}</strong>
                      <span>
                        {selected
                          ? `Using ${selected.display_name}`
                          : "Project folder required"}
                      </span>
                    </div>
                    <Button
                      disabled={busy}
                      icon={
                        selected ? (
                          <Check size={15} />
                        ) : (
                          <FolderOpen size={15} />
                        )
                      }
                      onClick={() => void chooseProject(project.project_id)}
                      tone="quiet"
                    >
                      {selected ? "Change" : "Choose folder"}
                    </Button>
                  </div>
                );
              })}
            </div>
          ) : null}
          {restoring ? (
            <div className="recovery-dialog__loading" role="status">
              <LoaderCircle className="setup-progress__spinner" size={20} />
              Keep Temper open while recovery finishes…
            </div>
          ) : null}
          {error ? <p role="alert">{error}</p> : null}
          {preview && !restoring ? (
            <div className="dialog-footer">
              <Button
                disabled={busy}
                onClick={() => changeOpen(false)}
                tone="quiet"
              >
                Cancel
              </Button>
              <Button
                disabled={
                  busy ||
                  Object.keys(selections).length !== preview.projects.length
                }
                onClick={() => void restore()}
                tone="primary"
              >
                Restore Temper
              </Button>
            </div>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
