"""Background work for the web UI: scanning a course URL and extracting PDFs."""
import os
import sys
import threading
from collections import defaultdict
from concurrent.futures import Executor, ThreadPoolExecutor

from aicc_demo import canvas, export
from aicc_demo.extractor import extract_course
from aicc_demo.sources import load_course
from aicc_demo.web.pdf_store import pdf_name
from aicc_demo.web.store import now

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


def course_has_youtube(course_url: str) -> bool:
    """True if a course embeds YouTube videos. If unsure, False: the cloud job reports any error."""
    try:
        source = load_course(course_url)
        course = extract_course(source.course_json, assets=source.asset_url)
    except Exception as exc:
        print(f"Could not check {course_url} for YouTube videos: {exc}", file=sys.stderr)
        return False
    return any(
        block["label"] == "video" and block["media"]["type"] == "youtube"
        for lesson in course["lessons"] for block in lesson["blocks"]
    )


def run_extraction(store, pdf_store, project_id: str, link_id: str, text_only: bool, scratch_dir: str) -> None:
    """Extract one table row and record the outcome on the row.

    Shared by the local worker threads and the Cloud Run job tasks: the
    pipeline writes the PDF into `scratch_dir`, then `pdf_store` files it
    as <project-folder>/<NN>-<course-title>.pdf (locally or in the bucket).
    """
    project = store.get(project_id)
    link = next((l for l in (project or {}).get("links", []) if l["id"] == link_id), None)
    if project is None or link is None:  # deleted while queued
        return
    store.update_link(project_id, link_id, status="running", progress="Starting", error=None,
                      problems=None, started_at=now(), finished_at=None)
    try:
        result = export.export_course(
            link["course_url"],
            include_video=not text_only,
            pdf_dir=scratch_dir,
            progress=lambda message: store.update_link(project_id, link_id, progress=message),
        )
        store.update_link(project_id, link_id, progress="Saving PDF")
        ref = pdf_store.save(result["pdf"], project["slug"], pdf_name(link["position"], result["title"]))
    except Exception as exc:  # one failed course must not stop the others
        store.update_link(project_id, link_id, status="failed", progress="", error=str(exc)[:500], finished_at=now())
        return
    store.update_link(
        project_id,
        link_id,
        status="done",
        progress="",
        pdf_path=ref,
        pdf_size=pdf_store.size(ref),
        course_title=result["title"],
        lessons=result["lessons"],
        videos=result["videos"],
        images=result["images"],
        problems=[p[:300] for p in result.get("problems", [])][:50],
        finished_at=now(),
    )


class Worker:
    """Scans and extractions in background threads on this machine."""

    def __init__(self, store, pdf_store, executor: Executor | None = None, scan_executor: Executor | None = None):
        self.store = store
        self.pdf_store = pdf_store
        self.executor = executor or ThreadPoolExecutor(max_workers=DEFAULT_WORKERS, thread_name_prefix="extract")
        self.scanner = scan_executor or executor or ThreadPoolExecutor(max_workers=2, thread_name_prefix="scan")
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
        links = [
            link for link in project["links"]
            if link["id"] in link_ids and link["extractable"] and link["status"] not in ("queued", "running")
        ]
        for link in links:
            self.store.update_link(project_id, link["id"], status="queued", progress="Waiting", error=None)
        if links:
            self._launch(project, links, text_only)
        return [link["id"] for link in links]

    def _launch(self, project: dict, links: list[dict], text_only: bool) -> None:
        for link in links:
            self.executor.submit(self._extract, project["id"], link["id"], link["course_url"], text_only)

    def _extract(self, project_id: str, link_id: str, course_url: str, text_only: bool) -> None:
        lock = self._course_lock(course_url)
        if not lock.acquire(blocking=False):
            self.store.update_link(project_id, link_id, progress="Waiting: same course is extracting in another project")
            lock.acquire()
        try:
            run_extraction(self.store, self.pdf_store, project_id, link_id, text_only,
                           scratch_dir=os.path.join("data", "web", "scratch", link_id))
        finally:
            lock.release()


class CloudRunWorker(Worker):
    """Scans inline (a Cloud Run service gets no CPU between requests) and
    runs extractions as one Cloud Run job execution, one task per row.

    YouTube refuses downloads from cloud servers, so a course with YouTube
    videos waits for the local runner (web/runner.py) instead. Text-only runs
    download no videos and always stay in the cloud.
    """

    def __init__(self, store, pdf_store, gcp_project: str, region: str, job_name: str, jobs_client=None,
                 needs_runner=None):
        super().__init__(store, pdf_store, executor=_Inline(), scan_executor=_Inline())
        self.job_path = f"projects/{gcp_project}/locations/{region}/jobs/{job_name}"
        self._jobs_client = jobs_client
        self._needs_runner = needs_runner or (lambda url: course_has_youtube(url))

    def _launch(self, project: dict, links: list[dict], text_only: bool) -> None:
        if text_only:
            on_runner = [False] * len(links)
        else:
            with ThreadPoolExecutor(max_workers=8) as pool:
                on_runner = list(pool.map(self._needs_runner, [link["course_url"] for link in links]))
        cloud_links = []
        for link, use_runner in zip(links, on_runner):
            if use_runner:
                self.store.update_link(project["id"], link["id"], runner="local", progress="Waiting for local runner")
                self.store.enqueue_for_runner(project["id"], link["id"], text_only)
            else:
                self.store.update_link(project["id"], link["id"], runner=None)
                cloud_links.append(link)
        if cloud_links:
            self._launch_cloud(project, cloud_links, text_only)

    def _launch_cloud(self, project: dict, links: list[dict], text_only: bool) -> None:
        from google.cloud import run_v2

        client = self._jobs_client or run_v2.JobsClient()
        env = [
            run_v2.EnvVar(name="AICC_PROJECT_ID", value=project["id"]),
            run_v2.EnvVar(name="AICC_LINK_IDS", value=",".join(link["id"] for link in links)),
            run_v2.EnvVar(name="AICC_TEXT_ONLY", value="1" if text_only else "0"),
        ]
        request = run_v2.RunJobRequest(
            name=self.job_path,
            overrides=run_v2.RunJobRequest.Overrides(
                container_overrides=[run_v2.RunJobRequest.Overrides.ContainerOverride(env=env)],
                task_count=len(links),
            ),
        )
        try:
            client.run_job(request=request)  # returns at once; tasks report progress themselves
        except Exception as exc:
            for link in links:
                self.store.update_link(project["id"], link["id"], status="failed", progress="",
                                       error=f"Could not start the cloud job: {exc}"[:500])
            return
        for link in links:
            self.store.update_link(project["id"], link["id"], progress="Starting cloud job")


class _Inline(Executor):
    def submit(self, fn, *args, **kwargs):
        from concurrent.futures import Future

        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception as exc:  # surfaced through the stored row/scan state
            future.set_exception(exc)
        return future
