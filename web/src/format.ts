export function formatBytes(bytes: number | null): string {
  if (!bytes) return "";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m}m ${String(s % 60).padStart(2, "0")}s` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function formatAgo(epochSeconds: number): string {
  const diff = Date.now() / 1000 - epochSeconds;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return new Date(epochSeconds * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export type UrlKind =
  | { kind: "canvas"; label: string }
  | { kind: "share"; label: string }
  | { kind: "export"; label: string }
  | { kind: "link"; label: string }
  | { kind: "invalid"; label: string }
  | { kind: "empty"; label: string };

export function detectUrl(raw: string): UrlKind {
  const url = raw.trim();
  if (!url) return { kind: "empty", label: "" };
  if (!/^https?:\/\//i.test(url)) return { kind: "invalid", label: "Paste the full link, starting with https://" };
  const canvas = url.match(/^https?:\/\/[^/]+\/courses\/(\d+)/i);
  if (canvas) return { kind: "canvas", label: `Canvas course ${canvas[1]} — every Rise course linked in its modules will be listed` };
  if (/share\.articulate\.com\/|rise\.articulate\.com\/share\//i.test(url)) return { kind: "share", label: "Rise share link — one course" };
  if (/\/index\.html($|[?#])|courseresources/i.test(url)) return { kind: "export", label: "Rise web export — one course" };
  return { kind: "link", label: "Will check whether this is a Rise course" };
}

export function suggestName(raw: string): string {
  // "…/eng/cot5407/asymptotic/index.html" -> "COT5407 Asymptotic"
  try {
    const parts = new URL(raw.trim()).pathname.split("/").filter((p) => p && !/\.html?$/.test(p));
    const course = parts.find((p) => /^[a-z]{3}\d{4}$/i.test(p));
    const last = parts[parts.length - 1];
    if (course && last && last !== course)
      return `${course.toUpperCase()} ${last.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}`;
  } catch {
    /* not a URL yet */
  }
  return "";
}
