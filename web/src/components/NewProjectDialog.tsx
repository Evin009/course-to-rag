import { useEffect, useRef, useState } from "react";
import { detectUrl, suggestName } from "../format";
import type { AppConfig } from "../types";
import { AlertIcon, Spinner, XIcon } from "./Icons";

interface Props {
  config: AppConfig | null;
  onCancel: () => void;
  onCreate: (name: string, url: string) => Promise<void>;
}

export function NewProjectDialog({ config, onCancel, onCreate }: Props) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const urlRef = useRef<HTMLInputElement>(null);
  const detected = detectUrl(url);

  useEffect(() => {
    urlRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  useEffect(() => {
    if (!nameTouched) setName(suggestName(url));
  }, [url, nameTouched]);

  const canSubmit = name.trim() && detected.kind !== "invalid" && detected.kind !== "empty" && !saving;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    setError(null);
    try {
      await onCreate(name.trim(), url.trim());
    } catch (err) {
      setError((err as Error).message);
      setSaving(false);
    }
  };

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onCancel()}>
      <form className="dialog" role="dialog" aria-modal="true" aria-labelledby="new-project-title" onSubmit={submit}>
        <div className="dialog-head">
          <h2 id="new-project-title">New project</h2>
          <button type="button" className="btn btn-ghost btn-icon" aria-label="Close" onClick={onCancel}>
            <XIcon size={16} />
          </button>
        </div>
        <p className="dialog-lead">Paste a Canvas course or a single Rise course. We’ll list every course we find so you can choose what to extract.</p>

        <label className="field">
          <span className="field-label">Course URL</span>
          <input ref={urlRef} className="input" value={url} onChange={(e) => setUrl(e.target.value)}
            placeholder="https://usflearn.instructure.com/courses/2151228" spellCheck={false} autoComplete="off" />
          {detected.label && (
            <span className={`field-hint hint-${detected.kind}`}>{detected.label}</span>
          )}
        </label>

        {detected.kind === "canvas" && config && !config.canvas_token && (
          <div className="banner banner-warn">
            <AlertIcon size={16} />
            <div>No Canvas token found. Add <code>CANVAS_TOKEN=…</code> to <code>.env</code> in the project folder, then restart the app.</div>
          </div>
        )}

        <label className="field">
          <span className="field-label">Project name</span>
          <input className="input" value={name} onChange={(e) => { setName(e.target.value); setNameTouched(true); }}
            placeholder="COT5407 Algorithms" maxLength={120} />
          <span className="field-hint">Names the PDF folder: <code>pdf/{name.trim() ? name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") : "…"}/</code></span>
        </label>

        {error && <div className="banner banner-error"><AlertIcon size={16} /><div>{error}</div></div>}

        <div className="dialog-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={!canSubmit}>
            {saving && <Spinner size={14} />} Create and scan
          </button>
        </div>
      </form>
    </div>
  );
}
