"""Cloud pieces, tested against small in-memory fakes of the Google clients."""
from unittest.mock import MagicMock, patch

from aicc_demo.web.cloud_store import FirestoreProjectStore
from aicc_demo.web.pdf_store import GcsPdfStore, LocalPdfStore, pdf_name
from aicc_demo.web.worker import CloudRunWorker


# ---------- a minimal in-memory Firestore ----------
class _Snap:
    def __init__(self, ref, data):
        self.reference, self.id, self._data = ref, ref.id, data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data)


class _Doc:
    def __init__(self, db, path):
        self.db, self.path, self.id = db, path, path.rsplit("/", 1)[-1]

    def get(self):
        return _Snap(self, self.db.data.get(self.path))

    def set(self, data):
        self.db.data[self.path] = dict(data)

    def update(self, fields):
        doc = self.db.data[self.path]  # KeyError like Firestore's NotFound
        for key, value in fields.items():
            target = doc
            *parents, leaf = key.split(".")
            for part in parents:
                target = target.setdefault(part, {})
            target[leaf] = value

    def delete(self):
        self.db.data.pop(self.path, None)

    def collection(self, name):
        return _Col(self.db, f"{self.path}/{name}")


class _Col:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def document(self, doc_id):
        return _Doc(self.db, f"{self.path}/{doc_id}")

    def stream(self):
        prefix = self.path + "/"
        for path in list(self.db.data):
            if path.startswith(prefix) and "/" not in path[len(prefix):]:
                yield _Doc(self.db, path).get()


class _Batch:
    def __init__(self):
        self.ops = []

    def set(self, ref, data):
        self.ops.append(lambda: ref.set(data))

    def update(self, ref, data):
        self.ops.append(lambda: ref.update(data))

    def delete(self, ref):
        self.ops.append(ref.delete)

    def commit(self):
        for op in self.ops:
            op()


class FakeFirestore:
    def __init__(self):
        self.data = {}

    def collection(self, name):
        return _Col(self, name)

    def batch(self):
        return _Batch()


ROW = {"module": "Week 1", "title": "W1 Lecture", "course_url": "https://share.articulate.com/abcdefghijkl",
       "kind": "share", "extractable": True, "canvas_url": None}
SCORM = {**ROW, "title": "W8", "course_url": "https://x.insops.net/packages/1/launch", "kind": "scorm", "extractable": False}


def test_firestore_store_round_trip_and_rescan_keeps_rows():
    store = FirestoreProjectStore(client=FakeFirestore())
    project = store.create("COT5407 Algorithms", "https://usflearn.instructure.com/courses/1", "cot5407-algorithms")
    store.update_scan(project["id"], status="scanning", error=None)
    store.replace_links(project["id"], [ROW])
    link_id = store.get(project["id"])["links"][0]["id"]
    store.update_link(project["id"], link_id, status="done", pdf_path="gs://b/cot5407-algorithms/01-x.pdf")

    store.replace_links(project["id"], [SCORM, ROW])  # rescan: new row first, old row kept
    got = store.get(project["id"])

    assert got["scan"]["status"] == "scanning"
    assert [(l["title"], l["status"], l["position"]) for l in got["links"]] == [("W8", "skipped", 1), ("W1 Lecture", "done", 2)]
    assert got["links"][1]["id"] == link_id and got["links"][1]["pdf_path"].endswith("01-x.pdf")
    assert [p["id"] for p in store.all()] == [project["id"]]
    assert store.delete(project["id"]) and store.get(project["id"]) is None and store.all() == []


def test_cloud_worker_starts_one_job_execution_with_a_task_per_row():
    store = FirestoreProjectStore(client=FakeFirestore())
    project = store.create("COT", "https://usflearn.instructure.com/courses/1", "cot")
    store.replace_links(project["id"], [ROW, {**ROW, "course_url": "https://share.articulate.com/zzzzzzzzzzzz"}, SCORM])
    ids = [l["id"] for l in store.get(project["id"])["links"]]
    jobs = MagicMock()
    worker = CloudRunWorker(store, MagicMock(), "my-proj", "us-east1", "course-to-pdf-extract", jobs_client=jobs)

    queued = worker.start_extract(project["id"], ids, text_only=True)

    assert queued == ids[:2]  # SCORM row never queued
    request = jobs.run_job.call_args.kwargs["request"]
    assert request.name == "projects/my-proj/locations/us-east1/jobs/course-to-pdf-extract"
    assert request.overrides.task_count == 2
    env = {e.name: e.value for e in request.overrides.container_overrides[0].env}
    assert env == {"AICC_PROJECT_ID": project["id"], "AICC_LINK_IDS": ",".join(ids[:2]), "AICC_TEXT_ONLY": "1"}
    assert [l["status"] for l in store.get(project["id"])["links"]] == ["queued", "queued", "skipped"]


def test_cloud_worker_marks_rows_failed_when_the_job_cannot_start():
    store = FirestoreProjectStore(client=FakeFirestore())
    project = store.create("COT", "u", "cot")
    store.replace_links(project["id"], [ROW])
    jobs = MagicMock()
    jobs.run_job.side_effect = PermissionError("run.jobs.runWithOverrides denied")
    worker = CloudRunWorker(store, MagicMock(), "p", "r", "j", jobs_client=jobs)

    worker.start_extract(project["id"], [store.get(project["id"])["links"][0]["id"]], text_only=False)

    link = store.get(project["id"])["links"][0]
    assert link["status"] == "failed" and "runWithOverrides" in link["error"]


def test_job_task_extracts_its_own_row_and_files_the_pdf(tmp_path, monkeypatch):
    from aicc_demo.web import job

    store = FirestoreProjectStore(client=FakeFirestore())
    project = store.create("COT5407 Algorithms", "u", "cot5407-algorithms")
    store.replace_links(project["id"], [ROW, {**ROW, "course_url": "https://share.articulate.com/second-course"}])
    ids = [l["id"] for l in store.get(project["id"])["links"]]
    monkeypatch.setenv("AICC_PROJECT_ID", project["id"])
    monkeypatch.setenv("AICC_LINK_IDS", ",".join(ids))
    monkeypatch.setenv("AICC_TEXT_ONLY", "1")
    monkeypatch.setenv("CLOUD_RUN_TASK_INDEX", "1")
    monkeypatch.setattr(job, "WORK_DIR", str(tmp_path / "work"))
    monkeypatch.chdir(tmp_path)
    pdfs = LocalPdfStore(str(tmp_path / "bucket"))

    def fake_export(course_url, include_video, pdf_dir, progress):
        import os
        os.makedirs(pdf_dir, exist_ok=True)
        path = os.path.join(pdf_dir, "x.pdf")
        open(path, "wb").write(b"%PDF")
        assert course_url.endswith("second-course") and include_video is False
        return {"pdf": path, "title": "COT5407 Recursive Analysis", "lessons": 6, "videos": 0, "images": 22}

    with patch("aicc_demo.export.export_course", side_effect=fake_export):
        assert job.main(store=store, pdf_store=pdfs) == 0

    first, second = store.get(project["id"])["links"]
    assert first["status"] == "found"
    assert second["status"] == "done"
    assert second["pdf_path"] == str(tmp_path / "bucket" / "cot5407-algorithms" / "02-cot5407-recursive-analysis.pdf")


def test_gcs_pdf_store_uploads_under_project_folder():
    client = MagicMock()
    store = GcsPdfStore("aicc-pdfs", client=client)

    ref = store.save("/tmp/x.pdf", "cot5407-algorithms", pdf_name(3, "COT5407 Sorting Algorithms"))

    assert ref == "gs://aicc-pdfs/cot5407-algorithms/03-cot5407-sorting-algorithms.pdf"
    client.bucket.return_value.blob.assert_called_with("cot5407-algorithms/03-cot5407-sorting-algorithms.pdf")
    client.bucket.return_value.blob.return_value.upload_from_filename.assert_called_once_with(
        "/tmp/x.pdf", content_type="application/pdf")
    assert store.location("{folder}") == "gs://aicc-pdfs/{folder}/"


def _store_with_rows(*rows):
    store = FirestoreProjectStore(client=FakeFirestore())
    project = store.create("COT", "https://usflearn.instructure.com/courses/1", "cot")
    store.replace_links(project["id"], list(rows))
    return store, project["id"], [l["id"] for l in store.get(project["id"])["links"]]


YOUTUBE_ROW = {**ROW, "course_url": "https://share.articulate.com/youtube-course"}


def test_youtube_courses_wait_for_runner_and_others_go_to_cloud_job():
    store, pid, ids = _store_with_rows(ROW, YOUTUBE_ROW)
    jobs = MagicMock()
    worker = CloudRunWorker(store, MagicMock(), "p", "r", "j", jobs_client=jobs,
                            needs_runner=lambda url: "youtube" in url)

    worker.start_extract(pid, ids, text_only=False)

    request = jobs.run_job.call_args.kwargs["request"]
    assert request.overrides.task_count == 1
    assert {e.name: e.value for e in request.overrides.container_overrides[0].env}["AICC_LINK_IDS"] == ids[0]
    cloud_row, runner_row = store.get(pid)["links"]
    assert cloud_row["runner"] is None
    assert (runner_row["status"], runner_row["runner"], runner_row["progress"]) == ("queued", "local", "Waiting for local runner")
    assert [e["link_id"] for e in store.runner_entries()] == [ids[1]]


def test_only_youtube_courses_start_no_cloud_job():
    store, pid, ids = _store_with_rows(YOUTUBE_ROW)
    jobs = MagicMock()
    worker = CloudRunWorker(store, MagicMock(), "p", "r", "j", jobs_client=jobs, needs_runner=lambda url: True)

    worker.start_extract(pid, ids, text_only=False)

    jobs.run_job.assert_not_called()


def test_text_only_never_needs_the_runner():
    store, pid, ids = _store_with_rows(YOUTUBE_ROW)
    jobs = MagicMock()
    worker = CloudRunWorker(store, MagicMock(), "p", "r", "j", jobs_client=jobs, needs_runner=lambda url: True)

    worker.start_extract(pid, ids, text_only=True)

    jobs.run_job.assert_called_once()
    assert store.runner_entries() == []


def test_course_has_youtube_reads_the_course():
    from aicc_demo.web.worker import course_has_youtube

    def source(video):
        media = {"embed": {"originalUrl": video}}
        course = {"course": {"title": "C", "lessons": [{"id": "l", "title": "L", "items": [
            {"type": "multimedia", "items": [{"media": media}]}]}]}}
        return type("S", (), {"course_json": course, "asset_url": staticmethod(lambda k: k)})()

    with patch("aicc_demo.web.worker.load_course", return_value=source("https://youtu.be/abcdefghijk")):
        assert course_has_youtube("u") is True
    with patch("aicc_demo.web.worker.load_course",
               return_value=source('<iframe src="https://cdnapisec.kaltura.com/p/1/x?entry_id=1_abc"></iframe>')):
        assert course_has_youtube("u") is False
    with patch("aicc_demo.web.worker.load_course", side_effect=ValueError("bad link")):
        assert course_has_youtube("u") is False


def test_runner_extracts_oldest_entry_and_clears_it():
    from aicc_demo.web import runner

    store, pid, ids = _store_with_rows(YOUTUBE_ROW, {**YOUTUBE_ROW, "course_url": "https://share.articulate.com/second-one"})
    store.enqueue_for_runner(pid, ids[0], False)
    store.enqueue_for_runner(pid, ids[1], True)

    with patch("aicc_demo.web.runner.run_extraction") as mock_run:
        assert runner.process_next(store, MagicMock(), "scratch") is True
        assert mock_run.call_args.args[2:] == (pid, ids[0], False, "scratch")
        assert [e["link_id"] for e in store.runner_entries()] == [ids[1]]
        assert runner.process_next(store, MagicMock(), "scratch") is True
        assert runner.process_next(store, MagicMock(), "scratch") is False


def test_runner_error_fails_the_row_but_ctrl_c_keeps_it_queued():
    import pytest
    from aicc_demo.web import runner

    store, pid, ids = _store_with_rows(YOUTUBE_ROW)
    store.enqueue_for_runner(pid, ids[0], False)

    with patch("aicc_demo.web.runner.run_extraction", side_effect=KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            runner.process_next(store, MagicMock(), "scratch")
    assert len(store.runner_entries()) == 1  # restarts next time

    with patch("aicc_demo.web.runner.run_extraction", side_effect=RuntimeError("network down")):
        runner.process_next(store, MagicMock(), "scratch")
    assert store.runner_entries() == []
    link = store.get(pid)["links"][0]
    assert link["status"] == "failed" and "network down" in link["error"]


def test_runner_status_reports_online_then_offline():
    store = FirestoreProjectStore(client=FakeFirestore())
    assert store.runner_status()["online"] is False

    store.runner_heartbeat("evins-mac", "link1")
    status = store.runner_status()
    assert (status["online"], status["host"], status["busy_with"]) == (True, "evins-mac", "link1")

    with patch("aicc_demo.web.cloud_store.now", return_value=status["last_seen"] + 91):
        assert store.runner_status()["online"] is False


def test_project_waiting_on_runner_can_be_deleted_and_leaves_the_queue():
    from fastapi.testclient import TestClient
    from aicc_demo.web.app import create_app

    store, pid, ids = _store_with_rows(YOUTUBE_ROW)
    store.update_link(pid, ids[0], status="queued", runner="local")
    store.enqueue_for_runner(pid, ids[0], False)
    client = TestClient(create_app(store=store, pdf_store=MagicMock(), worker=MagicMock()))

    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert store.runner_entries() == [] and store.get(pid) is None


def test_course_running_on_the_runner_cannot_be_deleted():
    from fastapi.testclient import TestClient
    from aicc_demo.web.app import create_app

    store, pid, ids = _store_with_rows(YOUTUBE_ROW)
    store.update_link(pid, ids[0], status="running", runner="local")
    client = TestClient(create_app(store=store, pdf_store=MagicMock(), worker=MagicMock()))

    assert client.delete(f"/api/projects/{pid}").status_code == 409


def test_api_reports_runner_status_only_for_rows_on_the_runner():
    from fastapi.testclient import TestClient
    from aicc_demo.web.app import create_app

    store, pid, ids = _store_with_rows(YOUTUBE_ROW)
    client = TestClient(create_app(store=store, pdf_store=MagicMock(), worker=MagicMock()))
    assert "runner" not in client.get(f"/api/projects/{pid}").json()

    store.update_link(pid, ids[0], status="queued", runner="local")
    assert client.get(f"/api/projects/{pid}").json()["runner"]["online"] is False
