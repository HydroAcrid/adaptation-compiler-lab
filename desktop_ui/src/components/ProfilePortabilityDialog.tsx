import * as Dialog from "@radix-ui/react-dialog";
import { Check, Download, FileKey2, Upload, X } from "lucide-react";
import { useEffect, useState } from "react";

import {
  exportProfile,
  loadProfileExportPreview,
  loadProfileImportPreview,
  stageProfileImport,
  type ProfileExportPreview,
  type ProfileImportPreview,
} from "../engine";
import {
  profileExportPreview as browserExportPreview,
  profileImportPreview as browserImportPreview,
} from "../data/demo";
import type { PortableProfilePreview } from "../types";
import { Button } from "./ui";

export function ProfilePortabilityDialog({
  mode,
  nativeRuntime,
  snapshotDigest,
  onClose,
  onComplete,
}: {
  mode: "export" | "import";
  nativeRuntime: boolean;
  snapshotDigest: string | null;
  onClose: () => void;
  onComplete: (message: string) => void;
}) {
  const initialExportPreview =
    mode === "export" && !nativeRuntime && import.meta.env.DEV
      ? browserExportPreview
      : null;
  const [preview, setPreview] = useState<PortableProfilePreview | null>(
    initialExportPreview,
  );
  const [exportPreview, setExportPreview] =
    useState<ProfileExportPreview | null>(initialExportPreview);
  const [importPreview, setImportPreview] =
    useState<ProfileImportPreview | null>(null);
  const [passphrase, setPassphrase] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(mode === "export" && nativeRuntime);
  const [error, setError] = useState<string | null>(null);
  const isExport = mode === "export";
  const passphraseReady =
    passphrase.length >= 12 && (isExport ? passphrase === confirmation : true);

  useEffect(() => {
    if (!isExport) return;
    if (!nativeRuntime) return;
    let active = true;
    loadProfileExportPreview()
      .then((value) => {
        if (!active) return;
        setExportPreview(value);
        setPreview(value);
      })
      .catch((reason: unknown) => {
        if (active) setError(readError(reason));
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [isExport, nativeRuntime]);

  async function chooseImport() {
    if (!passphraseReady) return;
    setBusy(true);
    setError(null);
    try {
      const value = nativeRuntime
        ? await loadProfileImportPreview(passphrase)
        : browserImportPreview;
      if (!value) throw new Error("Open the Temper desktop app.");
      setImportPreview(value);
      setPreview(value);
    } catch (reason: unknown) {
      setError(readError(reason));
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    if (!nativeRuntime || !snapshotDigest || !passphraseReady) return;
    setBusy(true);
    setError(null);
    try {
      if (isExport && exportPreview) {
        const result = await exportProfile(
          exportPreview,
          passphrase,
          snapshotDigest,
          crypto.randomUUID(),
        );
        onComplete(
          `${result.item_count} Core item${result.item_count === 1 ? "" : "s"} saved in an encrypted profile.`,
        );
      } else if (importPreview) {
        const result = await stageProfileImport(
          importPreview,
          passphrase,
          snapshotDigest,
          crypto.randomUUID(),
        );
        onComplete(
          `${result.item_count} imported item${result.item_count === 1 ? "" : "s"} staged for review. Nothing was activated.`,
        );
      }
    } catch (reason: unknown) {
      setError(readError(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog.Root onOpenChange={(open) => (open ? undefined : onClose())} open>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content
          className="core-dialog portability-dialog"
          onPointerDownOutside={(event) => event.preventDefault()}
        >
          <Dialog.Close aria-label="Close" className="dialog-close">
            <X size={18} />
          </Dialog.Close>
          <span className="portability-symbol" aria-hidden="true">
            {isExport ? <Download size={21} /> : <Upload size={21} />}
          </span>
          <span className="folio-kicker">Offline portability</span>
          <Dialog.Title>
            {isExport ? "Take your Core with you" : "Review a Temper profile"}
          </Dialog.Title>
          <Dialog.Description>
            {isExport
              ? "Create an encrypted, signed copy of your approved guidance—without conversations, private paths, or keys."
              : "Choose an encrypted profile and inspect exactly what it offers before anything enters your review queue."}
          </Dialog.Description>

          {busy && !preview ? (
            <div className="portability-loading">Preparing a safe preview…</div>
          ) : null}
          {error ? (
            <div className="portability-error" role="alert">
              {error}
            </div>
          ) : null}

          {!isExport && !preview ? (
            <form
              className="portability-passphrase portability-passphrase--first"
              onSubmit={(event) => {
                event.preventDefault();
                void chooseImport();
              }}
            >
              <PassphraseField value={passphrase} onChange={setPassphrase} />
              <Button
                disabled={!passphraseReady || busy}
                icon={<FileKey2 size={15} />}
                tone="primary"
                type="submit"
              >
                {nativeRuntime ? "Choose profile" : "Open example preview"}
              </Button>
            </form>
          ) : null}

          {preview ? <ProfilePreview value={preview} /> : null}

          {preview && isExport ? (
            <div className="portability-passphrase">
              <PassphraseField value={passphrase} onChange={setPassphrase} />
              <label className="core-field">
                <span>Confirm passphrase</span>
                <input
                  autoComplete="new-password"
                  onChange={(event) => setConfirmation(event.target.value)}
                  type="password"
                  value={confirmation}
                />
              </label>
            </div>
          ) : null}

          {preview ? (
            <div className="core-dialog__actions portability-actions">
              <Button onClick={onClose} tone="quiet">
                Cancel
              </Button>
              <Button
                disabled={!nativeRuntime || !passphraseReady || busy}
                onClick={finish}
                tone="primary"
              >
                {isExport ? "Save encrypted profile" : "Stage for review"}
              </Button>
            </div>
          ) : null}
          {!nativeRuntime && preview ? (
            <p className="portability-browser-note">
              This is the visual browser preview. The installed desktop app
              opens the native file chooser and performs the signed local
              action.
            </p>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function PassphraseField({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="core-field">
      <span>Profile passphrase</span>
      <input
        autoComplete="new-password"
        minLength={12}
        onChange={(event) => onChange(event.target.value)}
        placeholder="At least 12 characters"
        type="password"
        value={value}
      />
    </label>
  );
}

function ProfilePreview({ value }: { value: PortableProfilePreview }) {
  return (
    <div className="portability-preview">
      <header>
        <div>
          <span>Profile</span>
          <strong>{value.display_name}</strong>
        </div>
        <div>
          <span>Includes</span>
          <strong>{value.item_count} items to review</strong>
        </div>
      </header>
      <ul>
        {value.items.slice(0, 4).map((item) => (
          <li key={item.item_id}>
            <Check aria-hidden="true" size={14} />
            <span>
              <strong>{item.summary}</strong>
              <small>
                {item.kind.replaceAll("_", " ")}
                {item.scope_mapping_required ? " · choose a local scope" : ""}
              </small>
            </span>
          </li>
        ))}
      </ul>
      {value.item_count > 4 ? (
        <p>And {value.item_count - 4} more in the encrypted package.</p>
      ) : null}
      <div className="portability-assurances">
        {value.warnings.map((warning) => (
          <div className="portability-assurance" key={warning}>
            <FileKey2 aria-hidden="true" size={15} />
            <span>{warning}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function readError(reason: unknown): string {
  if (reason instanceof Error) return reason.message;
  if (
    typeof reason === "object" &&
    reason !== null &&
    "message" in reason &&
    typeof reason.message === "string"
  ) {
    return reason.message;
  }
  return "Temper could not complete that local action.";
}
