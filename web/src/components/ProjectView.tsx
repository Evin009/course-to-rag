import { useMemo, useState } from "react";
import { api } from "../api";
import { formatAgo } from "../format";
import type { Link, Project } from "../types";
import { Checkbox } from "./Checkbox";
import { AlertIcon, DownloadIcon, ExternalIcon, FileIcon, RefreshIcon, Spinner, TrashIcon } from "./Icons";
import { LinksTable, selectable } from "./LinksTable";

interface Props {
  project: Project;
  now: number;
  onRescan: () => Promise<void>;
  onExtract: (linkIds: string[], textOnly: boolean) => Promise<void>;
  onDelete: () => Promise<void>;
}

export function ProjectView({ project, now, onRescan, onExtract, onDelete }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [withVideos, setWithVideos] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const pickable = project.links.filter(selectable);
  // Drop selections that stopped being selectable (e.g. now running).
  const chosen = useMemo(() => pickable.filter((l) => selected.has(l.id)), [pickable, selected]);
  const scanning = project.scan.status === "scanning";
  const active = project.links.filter((l) => l.status === "queued" || l.status === "running").length;
  const done = project.links.filter((l) => l.has_pdf).length;
  const blocked = project.links.filter((l) => !l.extractable).length;

  const select = (ids: string[], checked: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => (checked ? next.add(id) : next.delete(id)));
      return next;
    });

  const extract = async (ids: string[]) => {
    setBusy(true);
    try {
      await onExtract(ids, !withVideos);
      setSelected(new Set());
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="project">
      <header className="project-header">
        <div className="project-heading">
          <h1>{project.name}</h1>
          <a className="project-url" href={project.url} target="_blank" rel="noreferrer">
            {project.url.replace(/^https?:\/\//, "")} <ExternalIcon size={12} />
          </a>
          <div className="stats">
            <Stat value={project.total} label={project.total === 1 ? "course found" : "courses found"} />
            {blocked > 0 && <Stat value={blocked} label="can’t extract" tone="muted" />}
            {active > 0 && <Stat value={active} label="in progress" tone="accent" />}
            <Stat value={done} label={done === 1 ? "PDF ready" : "PDFs ready"} tone={done ? "ok" : "muted"} />
            {project.scan.finished_at && <span className="stat-note">Scanned {formatAgo(project.scan.finished_at)}</span>}
          </div>
        </div>
        <div className="project-actions">
          <button className="btn btn-ghost" onClick={() => void onRescan()} disabled={scanning}>
            <RefreshIcon size={15} /> Rescan
          </button>
          {confirmDelete ? (
            <span className="confirm">
              Delete project?
              <button className="btn btn-danger btn-small" onClick={() => void onDelete()}>Delete</button>
              <button className="btn btn-ghost btn-small" onClick={() => setConfirmDelete(false)}>Cancel</button>
            </span>
          ) : (
            <button className="btn btn-ghost btn-icon" aria-label="Delete project" title="Delete project"
              onClick={() => setConfirmDelete(true)}>
              <TrashIcon size={15} />
            </button>
          )}
        </div>
      </header>

      {project.scan.status === "error" && (
        <div className="banner banner-error" role="alert">
          <AlertIcon size={18} />
          <div>
            <strong>Scan failed.</strong> {project.scan.error}
          </div>
          <button className="btn btn-small" onClick={() => void onRescan()}>Try again</button>
        </div>
      )}

      {scanning && project.links.length === 0 ? (
        <ScanningState url={project.url} />
      ) : project.links.length === 0 && project.scan.status === "done" ? (
        <div className="empty-table">
          <FileIcon size={28} />
          <h3>No Rise courses found</h3>
          <p>The modules of this course don’t link any Articulate Rise course. Check the URL, or try a different course.</p>
        </div>
      ) : project.links.length > 0 ? (
        <>
          <div className="toolbar" role="toolbar" aria-label="Selection">
            <label className="select-all">
              <Checkbox
                label="Select all courses"
                checked={pickable.length > 0 && chosen.length === pickable.length}
                indeterminate={chosen.length > 0}
                disabled={pickable.length === 0}
                onChange={(c) => setSelected(c ? new Set(pickable.map((l) => l.id)) : new Set())}
              />
              <span>{chosen.length ? `${chosen.length} selected` : "Select all"}</span>
            </label>
            {scanning && <span className="toolbar-note"><Spinner size={12} /> Rescanning…</span>}
            <div className="toolbar-right">
              <label className="switch" title="Off: text, images and attachments only — much faster">
                <input type="checkbox" checked={withVideos} onChange={(e) => setWithVideos(e.target.checked)} />
                <span className="switch-track" aria-hidden="true"><span className="switch-thumb" /></span>
                Include videos
              </label>
              {done > 0 && (
                <a className="btn btn-ghost" href={api.zipUrl(project.id)} download>
                  <DownloadIcon size={15} /> All PDFs ({done})
                </a>
              )}
              <button className="btn btn-primary" disabled={chosen.length === 0 || busy}
                onClick={() => void extract(chosen.map((l) => l.id))}>
                {busy ? <Spinner size={14} /> : <FileIcon size={15} />}
                {chosen.length ? `Extract ${chosen.length} ${chosen.length === 1 ? "course" : "courses"}` : "Extract"}
              </button>
            </div>
          </div>
          <LinksTable
            project={project}
            selected={selected}
            onSelect={select}
            onRetry={(link: Link) => void extract([link.id])}
            now={now}
          />
          <p className="footnote">
            PDFs are saved on this computer in <code>pdf/{project.slug}/</code>.
            {!withVideos && " Videos are skipped: transcripts and frames won’t be in these PDFs."}
          </p>
        </>
      ) : null}
    </section>
  );
}

function Stat({ value, label, tone }: { value: number; label: string; tone?: "ok" | "accent" | "muted" }) {
  return (
    <span className={`stat${tone ? ` stat-${tone}` : ""}`}>
      <strong>{value}</strong> {label}
    </span>
  );
}

function ScanningState({ url }: { url: string }) {
  const canvas = /\/courses\/\d+/.test(url);
  return (
    <div className="scanning">
      <div className="scanning-head">
        <Spinner size={16} />
        <div>
          <strong>{canvas ? "Reading Canvas modules…" : "Checking the course link…"}</strong>
          <p>{canvas ? "Opening every page in the course’s modules and looking for Rise courses. About 20 seconds." : "Fetching the course to make sure it can be extracted."}</p>
        </div>
      </div>
      {[0, 1, 2, 3, 4].map((i) => (
        <div className="skeleton-row" key={i} style={{ animationDelay: `${i * 120}ms` }}>
          <span className="sk sk-box" />
          <span className="sk sk-line" style={{ width: `${46 + ((i * 17) % 30)}%` }} />
          <span className="sk sk-pill" />
        </div>
      ))}
    </div>
  );
}
