"""Projects and their course links, kept in one JSON file.

Small and local on purpose: the plan moves this to Firestore later; the
shape of the records stays the same.
"""
import json
import os
import threading
import time
import uuid
from copy import deepcopy

# Statuses a link moves through; "skipped" is for rows that cannot be
# extracted (Canvas SCORM packages).
LINK_STATUSES = ("found", "queued", "running", "done", "failed", "skipped")


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def now() -> float:
    return round(time.time(), 3)


def new_project(name: str, url: str, slug: str, course_key: str | None = None) -> dict:
    return {
        "id": new_id(),
        "name": name,
        "slug": slug,
        "url": url,
        "course_key": course_key,
        "created_at": now(),
        "scan": {"status": "idle", "error": None, "finished_at": None},
        "links": [],
    }


def new_link(row: dict, position: int) -> dict:
    """A table row for a course found by a scan."""
    return {
        "id": new_id(),
        "status": "found" if row["extractable"] else "skipped",
        "progress": "",
        "error": None,
        "problems": None,
        "runner": None,
        "pdf_path": None,
        "pdf_size": None,
        "course_title": None,
        "lessons": None,
        "videos": None,
        "images": None,
        "started_at": None,
        "finished_at": None,
        "position": position,
        **row,
    }


class ProjectStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        self._projects: dict[str, dict] = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self._projects = {p["id"]: p for p in json.load(f)}
            self._recover_interrupted()

    def _recover_interrupted(self) -> None:
        # A restart kills the worker threads; anything they held is lost.
        for project in self._projects.values():
            if project["scan"]["status"] == "scanning":
                project["scan"].update(status="error", error="Interrupted by a server restart; scan again.")
            for link in project["links"]:
                if link["status"] in ("queued", "running"):
                    link.update(status="failed", progress="", error="Interrupted by a server restart; retry.")
        self._save()

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(list(self._projects.values()), f, indent=2)
        os.replace(tmp, self.path)

    def all(self) -> list[dict]:
        with self._lock:
            return sorted((deepcopy(p) for p in self._projects.values()), key=lambda p: -p["created_at"])

    def get(self, project_id: str) -> dict | None:
        with self._lock:
            project = self._projects.get(project_id)
            return deepcopy(project) if project else None

    def create(self, name: str, url: str, slug: str, course_key: str | None = None) -> dict:
        with self._lock:
            project = new_project(name, url, slug, course_key)
            self._projects[project["id"]] = project
            self._save()
            return deepcopy(project)

    def delete(self, project_id: str) -> bool:
        with self._lock:
            removed = self._projects.pop(project_id, None) is not None
            if removed:
                self._save()
            return removed

    def update_scan(self, project_id: str, **fields) -> None:
        with self._lock:
            project = self._projects.get(project_id)
            if project:
                project["scan"].update(fields)
                self._save()

    def replace_links(self, project_id: str, found: list[dict]) -> None:
        """Store a fresh scan, keeping status and PDFs of rows found before."""
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return
            previous = {link["course_url"]: link for link in project["links"]}
            links = []
            for position, row in enumerate(found, 1):
                link = previous.get(row["course_url"])
                if link:
                    link.update(position=position, **row)
                else:
                    link = new_link(row, position)
                links.append(link)
            project["links"] = links
            self._save()

    def update_link(self, project_id: str, link_id: str, **fields) -> None:
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return
            for link in project["links"]:
                if link["id"] == link_id:
                    link.update(fields)
                    break
            self._save()
