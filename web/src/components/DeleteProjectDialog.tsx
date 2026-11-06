import { useEffect, useState } from "react";
import type { ProjectSummary } from "../types";
import { AlertIcon, Spinner, TrashIcon, XIcon } from "./Icons";

interface Props {
  project: ProjectSummary;
  pdfLocation: string | null;
  onCancel: () => void;
  onConfirm: (deletePdfs: boolean) => Promise<void>;
}

export function DeleteProjectDialog({ project, pdfLocation, onCancel, onConfirm }: Props) {
  const [deletePdfs, setDeletePdfs] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pdfs = project.counts.done ?? 0;
  const active = (project.counts.queued ?? 0) + (project.counts.running ?? 0);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !busy && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel, busy]);

  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await onConfirm(deletePdfs);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && !busy && onCancel()}>
      <div className="dialog dialog-narrow" role="alertdialog" aria-modal="true" aria-labelledby="delete-title">
        <div className="dialog-head">
          <h2 id="delete-title">Delete “{project.name}”?</h2>
          <button type="button" className="btn btn-ghost btn-icon" aria-label="Close" onClick={onCancel} disabled={busy}>
            <XIcon size={16} />
          </button>
        </div>
        <p className="dialog-lead">
          The project and its list of {project.total} {project.total === 1 ? "course" : "courses"} are removed.
          You can create it again from the same URL later.
        </p>

        {active > 0 ? (
          <div className="banner banner-warn">
            <AlertIcon size={16} />
            <div>{active} extraction{active === 1 ? " is" : "s are"} still running. Wait until {active === 1 ? "it finishes" : "they finish"}, then delete.</div>
          </div>
        ) : pdfs > 0 ? (
          <label className="check-row">
            <input type="checkbox" className="checkbox" checked={deletePdfs} onChange={(e) => setDeletePdfs(e.target.checked)} />
            <span>
              Also delete its {pdfs} PDF{pdfs === 1 ? "" : "s"}
              {pdfLocation && <span className="check-hint">from <code>{pdfLocation}</code></span>}
              {!deletePdfs && <span className="check-hint">Left unticked, the PDFs stay where they are.</span>}
            </span>
          </label>
        ) : null}

        {error && <div className="banner banner-error"><AlertIcon size={16} /><div>{error}</div></div>}

        <div className="dialog-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={busy}>Cancel</button>
          <button type="button" className="btn btn-danger" onClick={() => void confirm()} disabled={busy || active > 0}>
            {busy ? <Spinner size={14} /> : <TrashIcon size={15} />}
            {deletePdfs ? `Delete project and ${pdfs} PDF${pdfs === 1 ? "" : "s"}` : "Delete project"}
          </button>
        </div>
      </div>
    </div>
  );
}
