import * as Dialog from "@radix-ui/react-dialog";
import { Check, PackageOpen, Share2, Upload, X } from "lucide-react";
import { useEffect, useState } from "react";

import {
  engineFailureMessage,
  exportPackage,
  loadPackageExportPreview,
  loadPackageImportPreview,
  stagePackageImport,
  type PackageExportPreview,
  type PackageImportPreview,
} from "../engine";
import type { CapabilityModeSummary, ShareablePackagePreview } from "../types";
import { Button } from "./ui";

type PackageDialogIntent = "export-behaviors" | "export-mode" | "import";

export function ShareablePackageDialog({
  intent,
  mode,
  nativeRuntime,
  onClose,
  onComplete,
  snapshotDigest,
}: {
  intent: PackageDialogIntent;
  mode?: CapabilityModeSummary | null;
  nativeRuntime: boolean;
  onClose: () => void;
  onComplete: (message: string) => void;
  snapshotDigest: string | null;
}) {
  const [preview, setPreview] = useState<
    PackageExportPreview | PackageImportPreview | null
  >(null);
  const [busy, setBusy] = useState(intent !== "import" && nativeRuntime);
  const [error, setError] = useState<string | null>(null);
  const exporting = intent !== "import";

  useEffect(() => {
    if (!exporting || !nativeRuntime) return;
    let active = true;
    const load = async () => {
      try {
        const result = await loadPackageExportPreview(
          intent === "export-mode" ? "capability_mode" : "behavior_pack",
          mode?.mode_id,
        );
        if (active) setPreview(result);
      } catch (reason: unknown) {
        if (active) {
          setError(
            engineFailureMessage(
              reason,
              "Temper could not prepare this package.",
            ),
          );
        }
      } finally {
        if (active) setBusy(false);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [exporting, intent, mode?.mode_id, nativeRuntime]);

  async function chooseImport() {
    if (!nativeRuntime) return;
    setBusy(true);
    setError(null);
    try {
      setPreview(await loadPackageImportPreview());
    } catch (reason: unknown) {
      setError(
        engineFailureMessage(reason, "Temper could not verify that package."),
      );
    } finally {
      setBusy(false);
    }
  }

  async function complete() {
    if (!preview || !snapshotDigest || !nativeRuntime) return;
    setBusy(true);
    setError(null);
    try {
      if (exporting) {
        const exportPreview = preview as PackageExportPreview;
        const safeName = `${exportPreview.package_id}.temper-pack`;
        await exportPackage(
          exportPreview,
          safeName,
          snapshotDigest,
          crypto.randomUUID(),
        );
        onComplete(`${exportPreview.display_name} was exported.`);
      } else {
        const importPreview = preview as PackageImportPreview;
        await stagePackageImport(
          importPreview,
          snapshotDigest,
          crypto.randomUUID(),
        );
        onComplete(
          `${importPreview.display_name} is inactive and ready for governed review.`,
        );
      }
      onClose();
    } catch (reason: unknown) {
      setError(
        engineFailureMessage(
          reason,
          "Temper could not complete this package action.",
        ),
      );
    } finally {
      setBusy(false);
    }
  }

  const title = exporting
    ? intent === "export-mode"
      ? `Share ${mode?.name ?? "this Mode"}`
      : "Share approved behaviors"
    : "Review a Temper package";

  return (
    <Dialog.Root onOpenChange={(open) => (open ? undefined : onClose())} open>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="core-dialog portability-dialog">
          <Dialog.Close aria-label="Close" className="dialog-close">
            <X size={18} />
          </Dialog.Close>
          <span className="portability-symbol" aria-hidden="true">
            {exporting ? <Share2 size={21} /> : <PackageOpen size={21} />}
          </span>
          <span className="folio-kicker">Offline package</span>
          <Dialog.Title>{title}</Dialog.Title>
          <Dialog.Description>
            {exporting
              ? "Create a signed, raw-free package. The recipient must review it before anything can become active."
              : "Verify who signed the package, what it contains, and any conflicts before staging it inactive."}
          </Dialog.Description>

          {busy && !preview ? (
            <div className="portability-loading">Checking the package…</div>
          ) : null}
          {error ? (
            <div className="portability-error" role="alert">
              {error}
            </div>
          ) : null}
          {!exporting && !preview ? (
            <div className="portability-actions">
              <Button
                disabled={busy || !nativeRuntime}
                onClick={chooseImport}
                tone="primary"
              >
                <Upload aria-hidden="true" size={15} /> Choose package
              </Button>
            </div>
          ) : null}
          {preview ? <PackagePreview value={preview} /> : null}
          {!nativeRuntime ? (
            <p className="portability-browser-note">
              Package files are available in the installed desktop app.
            </p>
          ) : null}
          {preview ? (
            <div className="core-dialog__actions portability-actions">
              <Button onClick={onClose} tone="quiet">
                Cancel
              </Button>
              <Button
                disabled={busy || !snapshotDigest || !nativeRuntime}
                onClick={complete}
                tone="primary"
              >
                {busy
                  ? "Working…"
                  : exporting
                    ? "Save package"
                    : "Stage for review"}
              </Button>
            </div>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function PackagePreview({ value }: { value: ShareablePackagePreview }) {
  return (
    <div className="portability-preview">
      <header>
        <div>
          <span>{value.package_type.replaceAll("_", " ")}</span>
          <strong>{value.display_name}</strong>
        </div>
        <span>v{value.release_version}</span>
      </header>
      <dl className="mode-detail-list">
        <div>
          <dt>Publisher</dt>
          <dd>{value.publisher_name}</dd>
        </div>
        <div>
          <dt>License</dt>
          <dd>{value.source_license}</dd>
        </div>
        <div>
          <dt>Signature</dt>
          <dd>Verified</dd>
        </div>
        <div>
          <dt>Effect</dt>
          <dd>Inactive until local review</dd>
        </div>
      </dl>
      <ul aria-label="Package contents">
        {value.items.map((item) => (
          <li key={item.item_id}>
            <Check aria-hidden="true" size={15} />
            <span>
              <strong>{item.summary}</strong>
              <small>{item.disposition.replaceAll("_", " ")}</small>
            </span>
          </li>
        ))}
      </ul>
      {value.conflicting_item_ids.length ? (
        <p role="alert">
          {value.conflicting_item_ids.length} item
          {value.conflicting_item_ids.length === 1 ? "" : "s"} need conflict
          review.
        </p>
      ) : null}
      <div className="portability-assurances">
        {value.warnings.map((warning) => (
          <div className="portability-assurance" key={warning}>
            <Check aria-hidden="true" size={14} /> {warning}
          </div>
        ))}
      </div>
    </div>
  );
}
