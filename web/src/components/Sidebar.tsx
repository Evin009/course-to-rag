import type { AppConfig, ProjectSummary } from "../types";
import { LayersIcon, PlusIcon, Spinner, TrashIcon } from "./Icons";

interface Props {
  projects: ProjectSummary[];
  selectedId: string | null;
  config: AppConfig | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (project: ProjectSummary) => void;
}

function subtitle(p: ProjectSummary) {
  if (p.scan.status === "scanning") return <><Spinner size={10} /> Scanning…</>;
  if (p.scan.status === "error") return <span className="text-danger">Scan failed</span>;
  const active = (p.counts.queued ?? 0) + (p.counts.running ?? 0);
  if (active) return <><Spinner size={10} /> Extracting {active}…</>;
  const done = p.counts.done ?? 0;
  return `${p.total} ${p.total === 1 ? "course" : "courses"}${done ? ` · ${done} PDF${done === 1 ? "" : "s"}` : ""}`;
}

export function Sidebar({ projects, selectedId, config, onSelect, onNew, onDelete }: Props) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true"><LayersIcon size={16} /></span>
        <div>
          <div className="brand-name">Course to PDF</div>
          <div className="brand-sub">AI Course Companion</div>
        </div>
      </div>
      <button className="btn btn-primary btn-block" onClick={onNew}>
        <PlusIcon size={16} /> New project
      </button>
      <nav className="project-list" aria-label="Projects">
        <div className="list-label">Projects</div>
        {projects.length === 0 && <p className="list-empty">No projects yet.</p>}
        {projects.map((p) => (
          <div key={p.id} className={`project-item${p.id === selectedId ? " is-active" : ""}`}>
            <button className="project-item-main" onClick={() => onSelect(p.id)}
              aria-current={p.id === selectedId ? "page" : undefined}>
              <span className="project-item-name">{p.name}</span>
              <span className="project-item-sub">{subtitle(p)}</span>
            </button>
            <button className="project-item-delete" aria-label={`Delete ${p.name}`} title="Delete project"
              onClick={() => onDelete(p)}>
              <TrashIcon size={14} />
            </button>
          </div>
        ))}
      </nav>
      <div className="sidebar-foot">
        <span className={`dot ${config?.canvas_token ? "dot-ok" : "dot-warn"}`} aria-hidden="true" />
        {config ? (config.canvas_token ? "Canvas token connected" : "No Canvas token (.env)") : "Checking…"}
      </div>
    </aside>
  );
}
