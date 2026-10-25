"""Background work for the web UI: scanning a course URL and extracting PDFs."""
import os
import threading
from collections import defaultdict
from concurrent.futures import Executor, ThreadPoolExecutor

from aicc_demo import canvas, export
from aicc_demo.sources import load_course
from aicc_demo.web.store import ProjectStore, now

# Two extractions at once: each is mostly downloads and ffmpeg, so a third
# would mostly compete for the same bandwidth and CPU on a laptop.
DEFAULT_WORKERS = 2


def find_course_links(url: str) -> list[dict]:
    """Rows for the table: every Rise course in a Canvas course, or the one course a link points at."""
    try:
        canvas.parse_canvas_course_url(url)
        is_canvas = True
    except ValueError:
        is_canvas = False
    if is_canvas:
        return [
            {
                "module": c.module,
                "title": c.item_title,
                "course_url": c.course_url,
                "kind": c.kind,
                "extractable": c.extractable,
                "canvas_url": c.item_url,
            }
            for c in canvas.find_linked_courses(url)
        ]
    source = load_course(url)  # raises ValueError for anything that is not a Rise course
    title = (source.course_json.get("course") or {}).get("title") or url
    return [{"module": "Course", "title": title, "course_url": url, "kind": source.kind,
             "extractable": True, "canvas_url": None}]


class Worker:
    def __init__(self, store: ProjectStore, pdf_root: str, executor: Executor | None = None):
        self.store = store
        self.pdf_root = pdf_root
        self.executor = executor or ThreadPoolExecutor(max_workers=DEFAULT_WORKERS, thread_name_prefix="extract")
        self.scanner = executor or ThreadPoolExecutor(max_workers=2, thread_name_prefix="scan")
        # Two projects can list the same course. Both runs would write the same
        # download cache (data/<course>/), so the second waits for the first
        # and then reuses its downloads.
        self._course_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)
        self._locks_guard = threading.Lock()

    def _course_lock(self, course_url: str) -> threading.Lock:
        with self._locks_guard:
            return self._course_locks[course_url]

    def start_scan(self, project_id: str) -> None:
        self.store.update_scan(project_id, status="scanning", error=None)
        self.scanner.submit(self._scan, project_id)

    def _scan(self, project_id: str) -> None:
        project = self.store.get(project_id)
        if project is None:
            return
        try:
            rows = find_course_links(project["url"])
        except Exception as exc:  # shown to the user as the scan error
            self.store.update_scan(project_id, status="error", error=str(exc), finished_at=now())
            return
        self.store.replace_links(project_id, rows)
        self.store.update_scan(project_id, status="done", error=None, finished_at=now())

    def start_extract(self, project_id: str, link_ids: list[str], text_only: bool) -> list[str]:
        """Queue the chosen rows; returns the ids actually queued."""
        project = self.store.get(project_id)
        if project is None:
            return []
        queued = []
        for link in project["links"]:
            if link["id"] not in link_ids or not link["extractable"] or link["status"] in ("queued", "running"):
                continue
            self.store.update_link(project_id, link["id"], status="queued", progress="Waiting", error=None)
            self.executor.submit(self._extract, project_id, link["id"], link["course_url"], project["slug"], text_only)
            queued.append(link["id"])
        return queued

    def _extract(self, project_id: str, link_id: str, course_url: str, slug: str, text_only: bool) -> None:
        if self.store.get(project_id) is None:  # project deleted while queued
            return
        lock = self._course_lock(course_url)
        if not lock.acquire(blocking=False):
            self.store.update_link(project_id, link_id, progress="Waiting: same course is extracting in another project")
            lock.acquire()
        try:
            self._run_export(project_id, link_id, course_url, slug, text_only)
        finally:
            lock.release()

    def _run_export(self, project_id: str, link_id: str, course_url: str, slug: str, text_only: bool) -> None:
        self.store.update_link(project_id, link_id, status="running", progress="Starting", started_at=now(), finished_at=None)
        try:
            result = export.export_course(
                course_url,
                include_video=not text_only,
                pdf_dir=os.path.join(self.pdf_root, slug),
                progress=lambda message: self.store.update_link(project_id, link_id, progress=message),
            )
        except Exception as exc:  # one failed course must not stop the others
            self.store.update_link(project_id, link_id, status="failed", progress="", error=str(exc)[:500], finished_at=now())
            return
        self.store.update_link(
            project_id,
            link_id,
            status="done",
            progress="",
            pdf_path=result["pdf"],
            pdf_size=os.path.getsize(result["pdf"]),
            course_title=result["title"],
            lessons=result["lessons"],
            videos=result["videos"],
            images=result["images"],
            finished_at=now(),
        )
