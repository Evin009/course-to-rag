import { formatAgo, formatBytes, formatDuration } from "../format";
import type { Link, RunnerStatus } from "../types";
import { AlertIcon, CheckIcon, ClockIcon, LockIcon, Spinner } from "./Icons";

export function StatusCell({ link, now, runner }: { link: Link; now: number; runner?: RunnerStatus }) {
  switch (link.status) {
    case "running": {
      const elapsed = link.started_at ? formatDuration(now - link.started_at) : "";
      return (
        <div className="status">
          <span className="pill pill-running"><Spinner size={11} /> Running</span>
          {link.runner === "local" && runner && !runner.online ? (
            <span className="status-detail status-offline">Local runner offline. This course restarts when it’s back.</span>
          ) : (
            <span className="status-detail">{link.progress || "Starting"}{elapsed && ` · ${elapsed}`}</span>
          )}
        </div>
      );
    }
    case "queued":
      return (
        <div className="status">
          <span className="pill pill-queued"><ClockIcon size={12} /> Queued</span>
          {link.runner === "local" && runner && !runner.online ? (
            <span className="status-detail status-offline">
              Local runner offline{runner.last_seen ? `, last seen ${formatAgo(runner.last_seen)}` : ""}. Will start when it’s back.
            </span>
          ) : (
            link.progress && <span className="status-detail">{link.progress}</span>
          )}
        </div>
      );
    case "done": {
      const took = link.started_at && link.finished_at ? formatDuration(link.finished_at - link.started_at) : "";
      const parts = [
        link.lessons ? `${link.lessons} lessons` : "",
        link.videos ? `${link.videos} videos` : "",
        formatBytes(link.pdf_size),
        took && `in ${took}`,
      ].filter(Boolean);
      const problems = link.problems ?? [];
      if (problems.length > 0) {
        return (
          <div className="status">
            <span className="pill pill-warn"><AlertIcon size={12} /> Done with problems</span>
            <details className="problems">
              <summary>{problems.length} {problems.length === 1 ? "part" : "parts"} missing from the PDF</summary>
              <ul>{problems.map((p) => <li key={p}>{p}</li>)}</ul>
            </details>
          </div>
        );
      }
      return (
        <div className="status">
          <span className="pill pill-done"><CheckIcon size={12} /> Done</span>
          <span className="status-detail">{parts.join(" · ")}</span>
        </div>
      );
    }
    case "failed":
      return (
        <div className="status">
          <span className="pill pill-failed"><AlertIcon size={12} /> Failed</span>
          <span className="status-detail status-error" title={link.error ?? ""}>{link.error}</span>
        </div>
      );
    case "skipped":
      return (
        <div className="status" title="Canvas SCORM package: it only plays inside Canvas. Ask the instructor for the Rise share link or web export.">
          <span className="pill pill-skipped"><LockIcon size={12} /> Can’t extract</span>
          <span className="status-detail">SCORM package, plays only inside Canvas</span>
        </div>
      );
    default:
      return <span className="status-ready">Ready</span>;
  }
}
