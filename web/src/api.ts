import type { AppConfig, Project, ProjectSummary } from "./types";

/** An API error; `data` carries extra fields the server sent (e.g. the existing project's id). */
export class ApiError extends Error {
  constructor(message: string, public status: number, public data: Record<string, unknown> = {}) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    let data: Record<string, unknown> = {};
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
      else if (body.detail && typeof body.detail === "object") {
        data = body.detail;
        if (typeof body.detail.message === "string") message = body.detail.message;
      }
    } catch {
      /* keep the status text */
    }
    throw new ApiError(message, response.status, data);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export const api = {
  config: () => request<AppConfig>("/api/config"),
  projects: () => request<ProjectSummary[]>("/api/projects"),
  project: (id: string) => request<Project>(`/api/projects/${id}`),
  createProject: (name: string, url: string) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify({ name, url }) }),
  deleteProject: (id: string, deletePdfs: boolean) =>
    request<void>(`/api/projects/${id}?delete_pdfs=${deletePdfs}`, { method: "DELETE" }),
  rescan: (id: string) => request<Project>(`/api/projects/${id}/scan`, { method: "POST" }),
  extract: (id: string, linkIds: string[], textOnly: boolean) =>
    request<Project>(`/api/projects/${id}/extract`, {
      method: "POST",
      body: JSON.stringify({ link_ids: linkIds, text_only: textOnly }),
    }),
  pdfUrl: (projectId: string, linkId: string) => `/api/projects/${projectId}/links/${linkId}/pdf`,
  zipUrl: (projectId: string) => `/api/projects/${projectId}/pdfs.zip`,
};
