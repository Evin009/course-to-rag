import type { AppConfig, Project, ProjectSummary } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* keep the status text */
    }
    throw new Error(message);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export const api = {
  config: () => request<AppConfig>("/api/config"),
  projects: () => request<ProjectSummary[]>("/api/projects"),
  project: (id: string) => request<Project>(`/api/projects/${id}`),
  createProject: (name: string, url: string) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify({ name, url }) }),
  deleteProject: (id: string) => request<void>(`/api/projects/${id}`, { method: "DELETE" }),
  rescan: (id: string) => request<Project>(`/api/projects/${id}/scan`, { method: "POST" }),
  extract: (id: string, linkIds: string[], textOnly: boolean) =>
    request<Project>(`/api/projects/${id}/extract`, {
      method: "POST",
      body: JSON.stringify({ link_ids: linkIds, text_only: textOnly }),
    }),
  pdfUrl: (projectId: string, linkId: string) => `/api/projects/${projectId}/links/${linkId}/pdf`,
  zipUrl: (projectId: string) => `/api/projects/${projectId}/pdfs.zip`,
};
