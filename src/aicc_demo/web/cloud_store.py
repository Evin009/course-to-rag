"""ProjectStore on Firestore, for the cloud deployment.

Layout: projects/{project_id} holds the project; projects/{id}/links/{link_id}
holds one table row each. Rows are separate documents because several
Cloud Run job tasks update their own rows at the same time.
"""
from aicc_demo.web.store import new_link, new_project, now

# A runner that hasn't checked in for this long is shown as offline.
RUNNER_ONLINE_SECONDS = 90


class FirestoreProjectStore:
    def __init__(self, client=None, collection: str = "projects"):
        if client is None:
            from google.cloud import firestore

            client = firestore.Client()
        self.db = client
        self.projects = client.collection(collection)

    def _links(self, project_id: str):
        return self.projects.document(project_id).collection("links")

    def _assemble(self, snapshot) -> dict:
        project = {**snapshot.to_dict(), "id": snapshot.id}
        links = [{**link.to_dict(), "id": link.id} for link in self._links(snapshot.id).stream()]
        project["links"] = sorted(links, key=lambda link: link.get("position", 0))
        return project

    def all(self) -> list[dict]:
        return sorted((self._assemble(s) for s in self.projects.stream()), key=lambda p: -p["created_at"])

    def get(self, project_id: str) -> dict | None:
        snapshot = self.projects.document(project_id).get()
        return self._assemble(snapshot) if snapshot.exists else None

    def create(self, name: str, url: str, slug: str, course_key: str | None = None) -> dict:
        project = new_project(name, url, slug, course_key)
        fields = {k: v for k, v in project.items() if k not in ("id", "links")}
        self.projects.document(project["id"]).set(fields)
        return project

    def delete(self, project_id: str) -> bool:
        ref = self.projects.document(project_id)
        if not ref.get().exists:
            return False
        for link in self._links(project_id).stream():
            link.reference.delete()
        ref.delete()
        return True

    def update_scan(self, project_id: str, **fields) -> None:
        ref = self.projects.document(project_id)
        if ref.get().exists:
            ref.update({f"scan.{key}": value for key, value in fields.items()})

    def replace_links(self, project_id: str, found: list[dict]) -> None:
        """Store a fresh scan, keeping status and PDFs of rows found before."""
        existing = {link["course_url"]: link for link in (self.get(project_id) or {"links": []})["links"]}
        batch = self.db.batch()
        kept = set()
        for position, row in enumerate(found, 1):
            old = existing.get(row["course_url"])
            if old:
                kept.add(old["id"])
                batch.update(self._links(project_id).document(old["id"]), {"position": position, **row})
            else:
                link = new_link(row, position)
                batch.set(self._links(project_id).document(link.pop("id")), link)
        for link in existing.values():
            if link["id"] not in kept:
                batch.delete(self._links(project_id).document(link["id"]))
        batch.commit()

    def update_link(self, project_id: str, link_id: str, **fields) -> None:
        self._links(project_id).document(link_id).update(fields)

    # ---------- work for the local runner (see web/runner.py) ----------

    def enqueue_for_runner(self, project_id: str, link_id: str, text_only: bool) -> None:
        self.db.collection("runner_queue").document(link_id).set(
            {"project_id": project_id, "link_id": link_id, "text_only": text_only, "created_at": now()}
        )

    def runner_entries(self) -> list[dict]:
        entries = [snapshot.to_dict() for snapshot in self.db.collection("runner_queue").stream()]
        return sorted(entries, key=lambda entry: entry["created_at"])

    def finish_runner_entry(self, link_id: str) -> None:
        self.db.collection("runner_queue").document(link_id).delete()

    def runner_heartbeat(self, host: str, busy_with: str | None) -> None:
        self.db.collection("runner_status").document("local").set(
            {"host": host, "busy_with": busy_with, "last_seen": now()}
        )

    def runner_status(self) -> dict:
        snapshot = self.db.collection("runner_status").document("local").get()
        status = snapshot.to_dict() if snapshot.exists else {"host": None, "busy_with": None, "last_seen": None}
        status["online"] = bool(status["last_seen"]) and now() - status["last_seen"] < RUNNER_ONLINE_SECONDS
        return status
