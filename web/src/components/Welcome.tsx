import { FileIcon, LayersIcon, PlusIcon } from "./Icons";

export function Welcome({ onNew }: { onNew: () => void }) {
  return (
    <section className="welcome">
      <div className="welcome-mark" aria-hidden="true"><FileIcon size={26} /></div>
      <h1>Turn a course into PDFs</h1>
      <p>Paste a Canvas course link. We find every Articulate Rise course in its modules, you pick the ones you want, and each becomes a PDF ready for the AI Course Companion.</p>
      <ol className="steps">
        <li><span>1</span><div><strong>Create a project</strong>Name it after the course and paste the link.</div></li>
        <li><span>2</span><div><strong>Pick the modules</strong>Tick rows in the table, or select all.</div></li>
        <li><span>3</span><div><strong>Extract</strong>Text, images, video transcripts and frames, in reading order.</div></li>
      </ol>
      <button className="btn btn-primary btn-large" onClick={onNew}><PlusIcon size={16} /> New project</button>
      <p className="welcome-note"><LayersIcon size={13} /> Works with Canvas courses, Rise share links and Rise web exports.</p>
    </section>
  );
}
