import { api } from "../api";
import type { Link, Project } from "../types";
import { Checkbox } from "./Checkbox";
import { DownloadIcon, ExternalIcon, RefreshIcon } from "./Icons";
import { StatusCell } from "./StatusCell";

const KIND_LABEL: Record<Link["kind"], string> = { share: "Share link", export: "Web export", scorm: "SCORM" };

export function selectable(link: Link) {
  return link.extractable && link.status !== "queued" && link.status !== "running";
}

interface Props {
  project: Project;
  selected: Set<string>;
  onSelect: (ids: string[], checked: boolean) => void;
  onRetry: (link: Link) => void;
  now: number;
}

export function LinksTable({ project, selected, onSelect, onRetry, now }: Props) {
  // Group rows by Canvas module, keeping the course's own order.
  const groups: { module: string; links: Link[] }[] = [];
  for (const link of project.links) {
    const last = groups[groups.length - 1];
    if (last && last.module === link.module) last.links.push(link);
    else groups.push({ module: link.module, links: [link] });
  }

  return (
    <div className="table-wrap">
      <table className="links">
        <colgroup>
          <col style={{ width: 44 }} />
          <col />
          <col style={{ width: 112 }} />
          <col style={{ width: "34%" }} />
          <col style={{ width: 132 }} />
        </colgroup>
        <thead>
          <tr>
            <th aria-label="Select" />
            <th>Course</th>
            <th>Type</th>
            <th>Status</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        {groups.map((group) => {
          const pickable = group.links.filter(selectable);
          const picked = pickable.filter((l) => selected.has(l.id)).length;
          return (
            <tbody key={group.module + group.links[0].id}>
              <tr className="module-row">
                <td>
                  <Checkbox
                    label={`Select all in ${group.module}`}
                    checked={pickable.length > 0 && picked === pickable.length}
                    indeterminate={picked > 0}
                    disabled={pickable.length === 0}
                    onChange={(c) => onSelect(pickable.map((l) => l.id), c)}
                  />
                </td>
                <td colSpan={4}>
                  <span className="module-name">{group.module}</span>
                  <span className="module-count">{group.links.length} {group.links.length === 1 ? "course" : "courses"}</span>
                </td>
              </tr>
              {group.links.map((link) => (
                <tr key={link.id} className={`link-row is-${link.status}${selected.has(link.id) ? " is-selected" : ""}`}>
                  <td>
                    <Checkbox
                      label={`Select ${link.title}`}
                      checked={selected.has(link.id)}
                      disabled={!selectable(link)}
                      onChange={(c) => onSelect([link.id], c)}
                    />
                  </td>
                  <td>
                    <div className="course-title">{link.course_title ?? link.title}</div>
                    <div className="course-sub">
                      {link.course_title && link.course_title !== link.title && <span>{link.title} · </span>}
                      <a href={link.course_url} target="_blank" rel="noreferrer" className="course-url">
                        {link.course_url.replace(/^https?:\/\//, "")}
                        <ExternalIcon size={11} />
                      </a>
                    </div>
                  </td>
                  <td><span className={`kind kind-${link.kind}`}>{KIND_LABEL[link.kind]}</span></td>
                  <td><StatusCell link={link} now={now} /></td>
                  <td className="actions">
                    {link.has_pdf && (
                      <a className="btn btn-small" href={api.pdfUrl(project.id, link.id)} download>
                        <DownloadIcon size={14} /> PDF
                      </a>
                    )}
                    {link.status === "failed" && (
                      <button className="btn btn-small btn-ghost" onClick={() => onRetry(link)}>
                        <RefreshIcon size={14} /> Retry
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          );
        })}
      </table>
    </div>
  );
}
