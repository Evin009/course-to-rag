export type LinkStatus = "found" | "queued" | "running" | "done" | "failed" | "skipped";
export type LinkKind = "share" | "export" | "scorm";

export interface Link {
  id: string;
  position: number;
  module: string;
  title: string;
  course_url: string;
  canvas_url: string | null;
  kind: LinkKind;
  extractable: boolean;
  status: LinkStatus;
  progress: string;
  error: string | null;
  /** "local" when the course waits for or runs on the local runner (YouTube courses). */
  runner?: "local" | null;
  /** Parts of the course missing from a finished PDF. */
  problems?: string[] | null;
  has_pdf: boolean;
  pdf_name: string | null;
  pdf_size: number | null;
  course_title: string | null;
  lessons: number | null;
  videos: number | null;
  images: number | null;
  started_at: number | null;
  finished_at: number | null;
}

export interface ScanState {
  status: "idle" | "scanning" | "done" | "error";
  error: string | null;
  finished_at: number | null;
}

export interface ProjectSummary {
  id: string;
  name: string;
  /** Folder name for the project's PDFs. */
  slug: string;
  url: string;
  /** Same value for every URL of the same course; one project per course. */
  course_key: string;
  created_at: number;
  scan: ScanState;
  total: number;
  counts: Partial<Record<LinkStatus, number>>;
}

export interface RunnerStatus {
  online: boolean;
  host: string | null;
  busy_with: string | null;
  last_seen: number | null;
}

export interface Project extends ProjectSummary {
  links: Link[];
  /** Present when a row is on the local runner. */
  runner?: RunnerStatus;
}

export interface AppConfig {
  canvas_token: boolean;
  mode: "local" | "cloud";
  /** Where PDFs go; "{folder}" stands for the project's folder name. */
  pdf_location: string;
}
