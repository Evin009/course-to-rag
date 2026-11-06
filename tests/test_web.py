import json
import zipfile
from concurrent.futures import Executor, Future
from io import BytesIO
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from aicc_demo.canvas import LinkedCourse
from aicc_demo.web.app import create_app
from aicc_demo.web.store import ProjectStore


class InlineExecutor(Executor):
    """Runs submitted work immediately, so background jobs finish inside the request."""

    def submit(self, fn, *args, **kwargs):
        future = Future()
        future.set_result(fn(*args, **kwargs))
        return future


CANVAS_URL = "https://usflearn.instructure.com/courses/2151228"
FOUND = [
    LinkedCourse("Week 1", "W1 Asymptotic Analysis Lecture", "https://c/1", "https://webapps.usf.edu/x/asymptotic/index.html", "export"),
    LinkedCourse("Week 2", "W2 Recursive Lectures", "https://c/2", "https://rise.articulate.com/share/abcdefghijklmnop", "share"),
    LinkedCourse("Week 8", "W8 NP-Complete Lecture", "https://c/8", "https://x.insops.net/packages/1/launch", "scorm"),
]


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "projects.json", pdf_root=str(tmp_path / "pdf"), executor=InlineExecutor())
    return TestClient(app)


def fake_export(course_url, include_video, pdf_dir, progress):
    progress("Video 1 of 1")
    import os
    os.makedirs(pdf_dir, exist_ok=True)
    path = os.path.join(pdf_dir, "cot5407-asymptotic.pdf")
    with open(path, "wb") as f:
        f.write(b"%PDF-1.4 fake")
    return {"pdf": path, "title": "COT5407 Asymptotic", "lessons": 9, "videos": 1 if include_video else 0, "images": 3}


def test_create_project_scans_canvas_and_marks_scorm_skipped(client):
    with patch("aicc_demo.canvas.find_linked_courses", return_value=FOUND):
        r = client.post("/api/projects", json={"name": "COT5407 Algorithms", "url": CANVAS_URL})

    assert r.status_code == 201
    project = r.json()
    assert project["scan"]["status"] == "done"
    assert [(l["module"], l["kind"], l["status"]) for l in project["links"]] == [
        ("Week 1", "export", "found"), ("Week 2", "share", "found"), ("Week 8", "scorm", "skipped")]
    assert client.get("/api/projects").json()[0]["total"] == 3


def test_single_course_link_becomes_one_row(client):
    source = type("S", (), {"kind": "share", "course_json": {"course": {"title": "Suture Course"}}})()
    with patch("aicc_demo.web.worker.load_course", return_value=source):
        project = client.post("/api/projects", json={"name": "Suture", "url": "https://share.articulate.com/abcdefghijkl"}).json()

    assert [(l["title"], l["kind"]) for l in project["links"]] == [("Suture Course", "share")]


def test_scan_error_is_shown_not_raised(client):
    with patch("aicc_demo.canvas.find_linked_courses", side_effect=ValueError("Canvas needs an access token.")):
        project = client.post("/api/projects", json={"name": "X", "url": CANVAS_URL}).json()

    assert project["scan"] == {**project["scan"], "status": "error", "error": "Canvas needs an access token."}


def test_rejects_bad_url_and_duplicate_names(client):
    assert client.post("/api/projects", json={"name": "A", "url": "not a link"}).status_code == 422
    with patch("aicc_demo.canvas.find_linked_courses", return_value=[]):
        assert client.post("/api/projects", json={"name": "COT", "url": CANVAS_URL}).status_code == 201
        assert client.post("/api/projects", json={"name": "cot", "url": CANVAS_URL}).status_code == 409


def test_extract_selected_rows_then_download_pdf_and_zip(client):
    with patch("aicc_demo.canvas.find_linked_courses", return_value=FOUND):
        project = client.post("/api/projects", json={"name": "COT5407 Algorithms", "url": CANVAS_URL}).json()
    first, _, scorm = project["links"]

    with patch("aicc_demo.export.export_course", side_effect=fake_export) as mock_export:
        r = client.post(f"/api/projects/{project['id']}/extract", json={"link_ids": [first["id"], scorm["id"]], "text_only": True})

    assert r.status_code == 200
    assert mock_export.call_count == 1  # the SCORM row is never queued
    assert mock_export.call_args.kwargs["include_video"] is False
    row = r.json()["links"][0]
    # Filed as <project folder>/<module order>-<course title>.pdf
    assert (row["status"], row["has_pdf"], row["pdf_name"], row["course_title"], row["images"]) == (
        "done", True, "01-cot5407-asymptotic.pdf", "COT5407 Asymptotic", 3)
    assert "pdf_path" not in row  # no server paths leak to the browser

    pdf = client.get(f"/api/projects/{project['id']}/links/{first['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    archive = zipfile.ZipFile(BytesIO(client.get(f"/api/projects/{project['id']}/pdfs.zip").content))
    assert archive.namelist() == ["cot5407-algorithms/01-cot5407-asymptotic.pdf"]


def test_failed_extraction_is_recorded_per_row(client):
    with patch("aicc_demo.canvas.find_linked_courses", return_value=FOUND):
        project = client.post("/api/projects", json={"name": "COT", "url": CANVAS_URL}).json()

    with patch("aicc_demo.export.export_course", side_effect=RuntimeError("Kaltura timed out")):
        rows = client.post(f"/api/projects/{project['id']}/extract",
                           json={"link_ids": [l["id"] for l in project["links"]]}).json()["links"]

    assert [(r["status"], r["error"]) for r in rows] == [
        ("failed", "Kaltura timed out"), ("failed", "Kaltura timed out"), ("skipped", None)]


def test_rescan_keeps_finished_rows(client):
    with patch("aicc_demo.canvas.find_linked_courses", return_value=FOUND[:1]):
        project = client.post("/api/projects", json={"name": "COT", "url": CANVAS_URL}).json()
    with patch("aicc_demo.export.export_course", side_effect=fake_export):
        client.post(f"/api/projects/{project['id']}/extract", json={"link_ids": [project["links"][0]["id"]]})
    with patch("aicc_demo.canvas.find_linked_courses", return_value=FOUND):
        rows = client.post(f"/api/projects/{project['id']}/scan").json()["links"]

    assert [r["status"] for r in rows] == ["done", "found", "skipped"]


def test_restart_marks_interrupted_work(tmp_path):
    path = tmp_path / "projects.json"
    store = ProjectStore(str(path))
    project = store.create("COT", CANVAS_URL, "cot")
    store.update_scan(project["id"], status="scanning")
    store.replace_links(project["id"], [{"module": "W1", "title": "t", "course_url": "u", "kind": "share",
                                         "extractable": True, "canvas_url": None}])
    store.update_link(project["id"], store.get(project["id"])["links"][0]["id"], status="running")

    reloaded = ProjectStore(str(path)).get(project["id"])
    assert reloaded["scan"]["status"] == "error"
    assert reloaded["links"][0]["status"] == "failed" and "restart" in reloaded["links"][0]["error"]


def test_delete_project_and_404s(client):
    with patch("aicc_demo.canvas.find_linked_courses", return_value=[]):
        project = client.post("/api/projects", json={"name": "COT", "url": CANVAS_URL}).json()
    assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    assert client.get(f"/api/projects/{project['id']}").status_code == 404


def test_same_course_never_extracts_twice_at_once(tmp_path):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from aicc_demo.web.pdf_store import LocalPdfStore
    from aicc_demo.web.worker import Worker

    store = ProjectStore(str(tmp_path / "p.json"))
    row = {"module": "W1", "title": "t", "course_url": "https://same/course", "kind": "share", "extractable": True, "canvas_url": None}
    a, b = store.create("A", CANVAS_URL, "a"), store.create("B", CANVAS_URL, "b")
    store.replace_links(a["id"], [row])
    store.replace_links(b["id"], [row])
    running, overlap = [0], [False]
    guard = threading.Lock()

    def slow_export(course_url, include_video, pdf_dir, progress):
        with guard:
            running[0] += 1
            overlap[0] |= running[0] > 1
        time.sleep(0.2)
        with guard:
            running[0] -= 1
        return fake_export(course_url, include_video, pdf_dir, lambda m: None)

    pool = ThreadPoolExecutor(max_workers=2)
    worker = Worker(store, LocalPdfStore(str(tmp_path / "pdf")), pool)
    with patch("aicc_demo.export.export_course", side_effect=slow_export):
        for project in (a, b):
            worker.start_extract(project["id"], [store.get(project["id"])["links"][0]["id"]], text_only=True)
        pool.shutdown(wait=True)

    assert overlap[0] is False
    assert [store.get(p["id"])["links"][0]["status"] for p in (a, b)] == ["done", "done"]


@pytest.mark.parametrize("a, b", [
    ("https://usflearn.instructure.com/courses/2151228", "https://USFLEARN.instructure.com/courses/2151228/modules?foo=1"),
    ("https://share.articulate.com/abcdefghijkl", "https://share.articulate.com/abcdefghijkl#/lessons/x"),
    ("https://webapps.usf.edu/courseresources/eng/cot5407/asymptotic/index.html",
     "https://webapps.usf.edu/courseresources/eng/cot5407/asymptotic/"),
])
def test_course_key_treats_url_variants_as_one_course(a, b):
    from aicc_demo.web.course_key import course_key

    assert course_key(a) == course_key(b)


def test_course_key_keeps_different_courses_apart():
    from aicc_demo.web.course_key import course_key

    keys = {course_key(u) for u in [
        "https://usflearn.instructure.com/courses/2151228",
        "https://usflearn.instructure.com/courses/2151229",
        "https://other.instructure.com/courses/2151228",
        "https://share.articulate.com/abcdefghijkl",
        "https://webapps.usf.edu/courseresources/eng/cot5407/asymptotic/index.html",
        "https://webapps.usf.edu/courseresources/eng/cot5407/big_oh/index.html",
    ]}
    assert len(keys) == 6


def test_second_project_for_same_course_is_refused_with_a_pointer(client):
    with patch("aicc_demo.canvas.find_linked_courses", return_value=[]):
        first = client.post("/api/projects", json={"name": "COT5407 Algorithms", "url": CANVAS_URL}).json()
        r = client.post("/api/projects", json={"name": "Algorithms again", "url": CANVAS_URL + "/modules"})

    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["project_id"] == first["id"] and detail["project_name"] == "COT5407 Algorithms"
    assert "already has a project" in detail["message"]
    assert client.get("/api/projects").json()[0]["course_key"] == "canvas:usflearn.instructure.com:2151228"


def test_delete_keeps_pdfs_unless_asked(client, tmp_path):
    with patch("aicc_demo.canvas.find_linked_courses", return_value=FOUND[:1]):
        keep = client.post("/api/projects", json={"name": "Keep", "url": CANVAS_URL}).json()
        drop = client.post("/api/projects", json={"name": "Drop", "url": "https://usflearn.instructure.com/courses/9"}).json()
    with patch("aicc_demo.export.export_course", side_effect=fake_export):
        for p in (keep, drop):
            client.post(f"/api/projects/{p['id']}/extract", json={"link_ids": [p["links"][0]["id"]]})
    keep_pdf = tmp_path / "pdf" / "keep" / "01-cot5407-asymptotic.pdf"
    drop_pdf = tmp_path / "pdf" / "drop" / "01-cot5407-asymptotic.pdf"
    assert keep_pdf.exists() and drop_pdf.exists()

    assert client.delete(f"/api/projects/{keep['id']}").status_code == 204
    assert client.delete(f"/api/projects/{drop['id']}?delete_pdfs=true").status_code == 204

    assert keep_pdf.exists() and not drop_pdf.exists()
    assert client.get("/api/projects").json() == []


def test_delete_is_blocked_while_extracting(client):
    with patch("aicc_demo.canvas.find_linked_courses", return_value=FOUND[:1]):
        project = client.post("/api/projects", json={"name": "Busy", "url": CANVAS_URL}).json()
    client.app.state.store.update_link(project["id"], project["links"][0]["id"], status="running")

    r = client.delete(f"/api/projects/{project['id']}")

    assert r.status_code == 409 and "still running" in r.json()["detail"]["message"]


def test_problems_reach_the_row_and_clear_on_retry(client):
    with patch("aicc_demo.canvas.find_linked_courses", return_value=FOUND[:1]):
        project = client.post("/api/projects", json={"name": "COT", "url": CANVAS_URL}).json()
    link_id = project["links"][0]["id"]

    def with_problem(*args, **kwargs):
        return {**fake_export(*args, **kwargs), "problems": ["Needles: no transcript, no frames"]}

    with patch("aicc_demo.export.export_course", side_effect=with_problem):
        row = client.post(f"/api/projects/{project['id']}/extract", json={"link_ids": [link_id]}).json()["links"][0]
    assert (row["status"], row["problems"]) == ("done", ["Needles: no transcript, no frames"])

    with patch("aicc_demo.export.export_course", side_effect=fake_export):
        row = client.post(f"/api/projects/{project['id']}/extract", json={"link_ids": [link_id]}).json()["links"][0]
    assert row["status"] == "done" and not row["problems"]
