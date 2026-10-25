import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { NewProjectDialog } from "./components/NewProjectDialog";
import { ProjectView } from "./components/ProjectView";
import { Sidebar } from "./components/Sidebar";
import { Welcome } from "./components/Welcome";
import type { AppConfig, Project, ProjectSummary } from "./types";

const POLL_MS = 1500;

function isBusy(p: Project | null) {
  return !!p && (p.scan.status === "scanning" || p.links.some((l) => l.status === "queued" || l.status === "running"));
}

export default function App() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(() => new URLSearchParams(location.search).get("p"));
  const [project, setProject] = useState<Project | null>(null);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now() / 1000);

  const notify = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast((t) => (t === message ? null : t)), 5000);
  }, []);

  const refreshList = useCallback(async () => {
    const list = await api.projects();
    setProjects(list);
    return list;
  }, []);

  useEffect(() => {
    api.config().then(setConfig).catch(() => setConfig(null));
    refreshList()
      .then((list) => setSelectedId((id) => (id && list.some((p) => p.id === id) ? id : list[0]?.id ?? null)))
      .catch((e: Error) => notify(`Can’t reach the server: ${e.message}`));
  }, [refreshList, notify]);

  // Keep the selected project in the URL so a reload stays on it.
  useEffect(() => {
    const url = new URL(location.href);
    if (selectedId) url.searchParams.set("p", selectedId);
    else url.searchParams.delete("p");
    history.replaceState(null, "", url);
    if (!selectedId) return setProject(null);
    api.project(selectedId).then(setProject).catch((e: Error) => notify(e.message));
  }, [selectedId, notify]);

  // Poll while a scan or extraction is running.
  const busy = isBusy(project);
  useEffect(() => {
    if (!busy || !selectedId) return;
    const timer = window.setInterval(() => {
      api.project(selectedId).then(setProject).catch(() => undefined);
      refreshList().catch(() => undefined);
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [busy, selectedId, refreshList]);

  // A ticking clock for elapsed times, only while something runs.
  useEffect(() => {
    if (!busy) return;
    const timer = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(timer);
  }, [busy]);

  const update = (p: Project) => {
    setProject(p);
    void refreshList();
  };

  return (
    <div className="app">
      <Sidebar projects={projects} selectedId={selectedId} config={config} onSelect={setSelectedId} onNew={() => setShowNew(true)} />
      <main className="main">
        {project ? (
          <ProjectView
            key={project.id}
            project={project}
            now={now}
            onRescan={async () => {
              try { update(await api.rescan(project.id)); } catch (e) { notify((e as Error).message); }
            }}
            onExtract={async (ids, textOnly) => {
              try { update(await api.extract(project.id, ids, textOnly)); } catch (e) { notify((e as Error).message); }
            }}
            onDelete={async () => {
              try {
                await api.deleteProject(project.id);
                const list = await refreshList();
                setSelectedId(list[0]?.id ?? null);
              } catch (e) { notify((e as Error).message); }
            }}
          />
        ) : (
          <Welcome onNew={() => setShowNew(true)} />
        )}
      </main>
      {showNew && (
        <NewProjectDialog
          config={config}
          onCancel={() => setShowNew(false)}
          onCreate={async (name, url) => {
            const created = await api.createProject(name, url);
            setShowNew(false);
            setProject(created);
            setSelectedId(created.id);
            void refreshList();
          }}
        />
      )}
      {toast && (
        <div className="toast" role="status" onClick={() => setToast(null)}>{toast}</div>
      )}
    </div>
  );
}
