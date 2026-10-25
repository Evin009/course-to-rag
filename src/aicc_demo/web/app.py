"""FastAPI app behind the web UI. Run it with `python webapp.py`."""
import io
import os
import re
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from aicc_demo.canvas import load_token
from aicc_demo.export import DEFAULT_PDF_DIR, slugify
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
        "url": project["url"],
        "created_at": project["created_at"],
        "scan": project["scan"],
        "total": len(project["links"]),
        "counts": counts,
    }


def public(project: dict) -> dict:
    """The project as the UI sees it: no server file paths."""
    links = []
    for link in project["links"]:
        row = {k: v for k, v in link.items() if k != "pdf_path"}
        row["has_pdf"] = bool(link.get("pdf_path")) and os.path.exists(link["pdf_path"])
        row["pdf_name"] = os.path.basename(link["pdf_path"]) if row["has_pdf"] else None
        links.append(row)
    return {**summary(project), "slug": project["slug"], "links": links}


def create_app(store_path: str | os.PathLike = DEFAULT_STORE, pdf_root: str = DEFAULT_PDF_DIR, executor=None) -> FastAPI:
    store = ProjectStore(str(store_path))
    worker = Worker(store, pdf_root, executor)
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
        return {"canvas_token": canvas_ready, "pdf_root": pdf_root}

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
        if any(p["slug"] == slug for p in store.all()):
            raise HTTPException(409, f"A project named “{name}” already exists")
        project = store.create(name, url, slug)
        worker.start_scan(project["id"])
        return public(store.get(project["id"]))

    @app.get("/api/projects/{project_id}")
    def read_project(project_id: str) -> dict:
        return public(get_project(project_id))

    @app.delete("/api/projects/{project_id}", status_code=204)
    def delete_project(project_id: str) -> None:
        get_project(project_id)
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
        return public(store.get(project_id))

    @app.get("/api/projects/{project_id}/links/{link_id}/pdf")
    def download_pdf(project_id: str, link_id: str):
        link = next((l for l in get_project(project_id)["links"] if l["id"] == link_id), None)
        if link is None or not link.get("pdf_path") or not os.path.exists(link["pdf_path"]):
            raise HTTPException(404, "No PDF for this row yet")
        return FileResponse(link["pdf_path"], media_type="application/pdf", filename=os.path.basename(link["pdf_path"]))

    @app.get("/api/projects/{project_id}/pdfs.zip")
    def download_all(project_id: str):
        project = get_project(project_id)
        paths = [l["pdf_path"] for l in project["links"] if l.get("pdf_path") and os.path.exists(l["pdf_path"])]
        if not paths:
            raise HTTPException(404, "No PDFs yet")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:  # PDFs are already compressed
            for path in paths:
                archive.write(path, arcname=f"{project['slug']}/{os.path.basename(path)}")
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
