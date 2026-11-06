"""FastAPI app behind the web UI. Run it with `python webapp.py`."""
import io
import os
import re
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from aicc_demo.canvas import load_token
from aicc_demo.export import DEFAULT_PDF_DIR, slugify
from aicc_demo.web.course_key import course_key
from aicc_demo.web.pdf_store import LocalPdfStore
from aicc_demo.web.store import ProjectStore
from aicc_demo.web.worker import Worker

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STORE = PROJECT_ROOT / "data" / "web" / "projects.json"
STATIC_DIR = Path(__file__).resolve().parent / "static"


class NewProject(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2000)


class ExtractRequest(BaseModel):
    link_ids: list[str] = Field(min_length=1)
    text_only: bool = False


def summary(project: dict) -> dict:
    counts: dict[str, int] = {}
    for link in project["links"]:
        counts[link["status"]] = counts.get(link["status"], 0) + 1
    return {
        "id": project["id"],
        "name": project["name"],
        "slug": project["slug"],
        "url": project["url"],
        "course_key": project.get("course_key") or course_key(project["url"]),
        "created_at": project["created_at"],
        "scan": project["scan"],
        "total": len(project["links"]),
        "counts": counts,
    }


def public(project: dict) -> dict:
    """The project as the UI sees it: file names, not server paths or bucket URIs."""
    links = []
    for link in project["links"]:
        row = {k: v for k, v in link.items() if k != "pdf_path"}
        row["has_pdf"] = bool(link.get("pdf_path"))
        row["pdf_name"] = link["pdf_path"].rsplit("/", 1)[-1] if row["has_pdf"] else None
        links.append(row)
    return {**summary(project), "links": links}


def with_runner(project: dict, store) -> dict:
    """Add the local runner's status when a row is waiting on it, so the UI can say if it's offline."""
    view = public(project)
    if any(link.get("runner") == "local" for link in project["links"]) and hasattr(store, "runner_status"):
        view["runner"] = store.runner_status()
    return view


def create_app(
    store_path: str | os.PathLike = DEFAULT_STORE,
    pdf_root: str = DEFAULT_PDF_DIR,
    executor=None,
    *,
    store=None,
    pdf_store=None,
    worker=None,
) -> FastAPI:
    """Local by default; the cloud factory below passes Firestore, Cloud Storage and Cloud Run instead."""
    store = store or ProjectStore(str(store_path))
    pdf_store = pdf_store or LocalPdfStore(pdf_root)
    worker = worker or Worker(store, pdf_store, executor)
    app = FastAPI(title="Course to PDF", docs_url="/api/docs", openapi_url="/api/openapi.json")

    def get_project(project_id: str) -> dict:
        project = store.get(project_id)
        if project is None:
            raise HTTPException(404, "Project not found")
        return project

    @app.get("/api/config")
    def config() -> dict:
        try:
            load_token()
            canvas_ready = True
        except ValueError:
            canvas_ready = False
        return {
            "canvas_token": canvas_ready,
            "mode": "cloud" if not isinstance(pdf_store, LocalPdfStore) else "local",
            # "{folder}" is replaced by the project's folder name in the UI.
            "pdf_location": pdf_store.location("{folder}"),
        }

    @app.get("/api/projects")
    def list_projects() -> list[dict]:
        return [summary(p) for p in store.all()]

    @app.post("/api/projects", status_code=201)
    def create_project(body: NewProject) -> dict:
        url = body.url.strip()
        if not re.match(r"https?://", url):
            raise HTTPException(422, "Enter a full link starting with https://")
        name = body.name.strip()
        slug = slugify(name)
        key = course_key(url)
        for existing in store.all():
            if (existing.get("course_key") or course_key(existing["url"])) == key:
                raise HTTPException(409, {
                    "message": f"This course already has a project: “{existing['name']}”",
                    "project_id": existing["id"],
                    "project_name": existing["name"],
                })
            if existing["slug"] == slug:
                raise HTTPException(409, {"message": f"A project named “{name}” already exists"})
        project = store.create(name, url, slug, key)
        worker.start_scan(project["id"])
        return public(store.get(project["id"]))

    @app.get("/api/projects/{project_id}")
    def read_project(project_id: str) -> dict:
        return with_runner(get_project(project_id), store)

    @app.delete("/api/projects/{project_id}", status_code=204)
    def delete_project(project_id: str, delete_pdfs: bool = False) -> None:
        project = get_project(project_id)
        # A row only waiting for the local runner can go: the runner may be off for days.
        active = [
            l for l in project["links"]
            if l["status"] == "running" or (l["status"] == "queued" and l.get("runner") != "local")
        ]
        if active:
            raise HTTPException(409, {"message": f"{len(active)} extraction(s) still running; wait for them to finish, then delete."})
        if delete_pdfs:
            for link in project["links"]:
                if link.get("pdf_path"):
                    pdf_store.delete(link["pdf_path"])
        if hasattr(store, "finish_runner_entry"):
            for link in project["links"]:
                if link["status"] == "queued" and link.get("runner") == "local":
                    store.finish_runner_entry(link["id"])
        store.delete(project_id)

    @app.post("/api/projects/{project_id}/scan")
    def rescan(project_id: str) -> dict:
        if get_project(project_id)["scan"]["status"] == "scanning":
            raise HTTPException(409, "A scan is already running")
        worker.start_scan(project_id)
        return public(store.get(project_id))

    @app.post("/api/projects/{project_id}/extract")
    def extract(project_id: str, body: ExtractRequest) -> dict:
        get_project(project_id)
        queued = worker.start_extract(project_id, body.link_ids, body.text_only)
        if not queued:
            raise HTTPException(409, "None of the selected rows can be extracted right now")
        return with_runner(store.get(project_id), store)

    @app.get("/api/projects/{project_id}/links/{link_id}/pdf")
    def download_pdf(project_id: str, link_id: str):
        link = next((l for l in get_project(project_id)["links"] if l["id"] == link_id), None)
        if link is None or not pdf_store.exists(link.get("pdf_path")):
            raise HTTPException(404, "No PDF for this row yet")
        name = link["pdf_path"].rsplit("/", 1)[-1]
        return Response(
            pdf_store.read(link["pdf_path"]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    @app.get("/api/projects/{project_id}/pdfs.zip")
    def download_all(project_id: str):
        project = get_project(project_id)
        refs = [l["pdf_path"] for l in project["links"] if pdf_store.exists(l.get("pdf_path"))]
        if not refs:
            raise HTTPException(404, "No PDFs yet")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:  # PDFs are already compressed
            for ref in refs:
                archive.writestr(f"{project['slug']}/{ref.rsplit('/', 1)[-1]}", pdf_store.read(ref))
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{project["slug"]}-pdfs.zip"'},
        )

    if STATIC_DIR.exists():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404)
            return FileResponse(STATIC_DIR / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def not_built():
            return HTMLResponse(
                "<h1>Frontend not built</h1><p>Run <code>cd web && npm install && npm run build</code>, "
                "then reload. The API is at <a href='/api/docs'>/api/docs</a>.</p>"
            )

    app.state.store = store
    app.state.worker = worker
    return app


def create_app_from_env() -> FastAPI:
    """App factory for `uvicorn --factory`: cloud mode when AICC_MODE=cloud.

    Cloud mode needs AICC_GCP_PROJECT, AICC_REGION, AICC_BUCKET and
    AICC_JOB_NAME; CANVAS_TOKEN comes from Secret Manager as an env var.
    """
    if os.environ.get("AICC_MODE") != "cloud":
        return create_app()
    from aicc_demo.web.cloud_store import FirestoreProjectStore
    from aicc_demo.web.pdf_store import GcsPdfStore
    from aicc_demo.web.worker import CloudRunWorker

    store = FirestoreProjectStore()
    pdf_store = GcsPdfStore(os.environ["AICC_BUCKET"])
    worker = CloudRunWorker(
        store, pdf_store,
        gcp_project=os.environ["AICC_GCP_PROJECT"],
        region=os.environ["AICC_REGION"],
        job_name=os.environ["AICC_JOB_NAME"],
    )
    return create_app(store=store, pdf_store=pdf_store, worker=worker)
