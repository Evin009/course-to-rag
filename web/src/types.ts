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
  url: string;
  created_at: number;
  scan: ScanState;
  total: number;
  counts: Partial<Record<LinkStatus, number>>;
}

export interface Project extends ProjectSummary {
  slug: string;
  links: Link[];
}

export interface AppConfig {
  canvas_token: boolean;
  pdf_root: string;
}
