import json
from unittest.mock import patch

import pytest
import responses

from aicc_demo.canvas import (
    CanvasClient,
    LinkedCourse,
    classify_course_link,
    find_linked_courses,
    links_in_html,
    load_token,
    parse_canvas_course_url,
)
from aicc_demo.canvas_cli import main, parse_selection

BASE = "https://canvas.example.edu"
API = f"{BASE}/api/v1/courses/2151228"

PAGE_W1 = """
<p>Watch the lecture:</p>
<p><a href="https://webapps.usf.edu/courseresources/eng/cot5407/asymptotic/index.html" target="_blank">Open module</a></p>
<a href="https://canvas.example.edu/">Home</a>
"""
PAGE_W2 = """
<a href="https://rise.articulate.com/share/KNQvqrENehitIzyIkT0R7E5npmNxddLz">Part 1</a>
<a href="https://rise.articulate.com/share/KNQvqrENehitIzyIkT0R7E5npmNxddLz">Part 1 again</a>
<iframe src="https://www.youtube.com/embed/abcdefghijk"></iframe>
"""
PAGE_POLICY = '<a href="https://articulate.com/privacy">Articulate privacy</a>'


def guarded(data):
    return "while(1);" + json.dumps(data)


def add_canvas_course(rsps):
    modules_p1 = [{"id": 1, "name": "Week 1", "items": [
        {"type": "Page", "title": "W1 Asymptotic Analysis Lecture", "page_url": "w1",
         "html_url": f"{BASE}/courses/2151228/modules/items/11"},
        {"type": "Quiz", "title": "W1 Quiz"},
        {"type": "Page", "title": "Policies", "page_url": "policy", "html_url": f"{BASE}/courses/2151228/modules/items/12"},
    ]}]
    modules_p2 = [{"id": 2, "name": "Week 2"}]  # no inline items: fetched separately
    rsps.add(responses.GET, f"{API}/modules", body=guarded(modules_p1), status=200,
             headers={"Link": f'<{API}/modules?page=2&per_page=100>; rel="next"'})
    rsps.add(responses.GET, f"{API}/modules?page=2&per_page=100", body=guarded(modules_p2), status=200)
    rsps.add(responses.GET, f"{API}/modules/2/items", json=[
        {"type": "Page", "title": "W2 Recursive Lectures", "page_url": "w2", "html_url": f"{BASE}/courses/2151228/modules/items/21"},
        {"type": "ExternalUrl", "title": "W2 Extra", "external_url": "https://share.articulate.com/7eoQIvElhke17L-WaUoIS"},
    ], status=200)
    rsps.add(responses.GET, f"{API}/pages/w1", json={"body": PAGE_W1}, status=200)
    rsps.add(responses.GET, f"{API}/pages/policy", json={"body": PAGE_POLICY}, status=200)
    rsps.add(responses.GET, f"{API}/pages/w2", json={"body": PAGE_W2}, status=200)


def test_parse_canvas_course_url():
    assert parse_canvas_course_url("https://usflearn.instructure.com/courses/2151228/modules") == (
        "https://usflearn.instructure.com", "2151228")
    with pytest.raises(ValueError):
        parse_canvas_course_url("https://share.articulate.com/abc")


@responses.activate
def test_find_linked_courses_walks_modules_pages_and_external_urls():
    add_canvas_course(responses)
    client = CanvasClient(BASE, "token-123")

    courses = find_linked_courses(f"{BASE}/courses/2151228", client, is_web_export=lambda url: True)

    assert [(c.module, c.item_title, c.kind, c.course_url) for c in courses] == [
        ("Week 1", "W1 Asymptotic Analysis Lecture", "export",
         "https://webapps.usf.edu/courseresources/eng/cot5407/asymptotic/index.html"),
        ("Week 2", "W2 Recursive Lectures", "share", "https://rise.articulate.com/share/KNQvqrENehitIzyIkT0R7E5npmNxddLz"),
        ("Week 2", "W2 Extra", "share", "https://share.articulate.com/7eoQIvElhke17L-WaUoIS"),
    ]
    assert responses.calls[0].request.headers["Authorization"] == "Bearer token-123"
    assert "include%5B%5D=items" in responses.calls[0].request.url


def test_classify_course_link_ignores_ordinary_links_without_fetching():
    probe = []
    is_export = lambda url: probe.append(url) or True

    assert classify_course_link("https://articulate.com/privacy", is_export) is None
    assert classify_course_link("https://www.youtube.com/embed/abcdefghijk", is_export) is None
    assert classify_course_link("mailto:x@usf.edu", is_export) is None
    assert probe == []
    assert classify_course_link("https://site.example/c/index.html", is_export) == "export"
    assert classify_course_link("https://site.example/c/index.html", lambda url: False) is None


def test_links_in_html_resolves_relative_links_and_skips_anchors():
    html = '<a href="/courses/1/pages/x">x</a><a href="#top">top</a><iframe src="//player.example/v"></iframe>'
    assert links_in_html(html, "https://canvas.example.edu/courses/1") == [
        "https://canvas.example.edu/courses/1/pages/x", "https://player.example/v"]


@responses.activate
def test_bad_token_gives_instructions():
    responses.add(responses.GET, f"{API}/modules", status=401)
    with pytest.raises(ValueError, match="New Access Token"):
        find_linked_courses(f"{BASE}/courses/2151228", CanvasClient(BASE, "bad"))


def test_load_token_from_env_then_dotenv(tmp_path, monkeypatch):
    monkeypatch.setenv("CANVAS_TOKEN", "from-env")
    assert load_token(str(tmp_path)) == "from-env"

    monkeypatch.delenv("CANVAS_TOKEN")
    (tmp_path / ".env").write_text('OTHER=1\nCANVAS_TOKEN="from-file"\n')
    assert load_token(str(tmp_path)) == "from-file"

    (tmp_path / ".env").write_text("OTHER=1\n")
    with pytest.raises(ValueError, match="New Access Token"):
        load_token(str(tmp_path))


def test_parse_selection():
    assert parse_selection("all", 3) == [0, 1, 2]
    assert parse_selection("1, 3-4, 3", 5) == [0, 2, 3]
    with pytest.raises(ValueError):
        parse_selection("6", 5)


COURSES = [
    LinkedCourse("Week 1", "W1 Lecture", "https://c/1", "https://webapps.usf.edu/x/index.html", "export"),
    LinkedCourse("Week 2", "W2 Lecture", "https://c/2", "https://share.articulate.com/abcdefghijkl", "share"),
]


def test_cli_lists_courses_by_module(capsys):
    with patch("aicc_demo.canvas_cli.find_linked_courses", return_value=COURSES):
        assert main(["https://canvas.example.edu/courses/1"]) == 0

    out = capsys.readouterr().out
    assert "Found 2 linked Rise courses" in out
    assert out.index("Week 1") < out.index(" 1. W1 Lecture  [export]") < out.index("Week 2") < out.index(" 2. W2 Lecture  [share]")


def test_cli_extracts_selection_and_keeps_going_after_a_failure(capsys, tmp_path):
    def fake_export(link, **kwargs):
        if "webapps" in link:
            raise RuntimeError("boom")
        return {"pdf": str(tmp_path / "w2.pdf")}

    with patch("aicc_demo.canvas_cli.find_linked_courses", return_value=COURSES), \
         patch("aicc_demo.canvas_cli.export_course", side_effect=fake_export) as mock_export:
        assert main(["https://canvas.example.edu/courses/1", "--extract", "all", "--text-only",
                     "--pdf-dir", str(tmp_path)]) == 1

    assert mock_export.call_count == 2
    assert mock_export.call_args.kwargs["include_video"] is False
    out = capsys.readouterr().out
    assert "1. FAILED" in out and str(tmp_path / "w2.pdf") in out


def test_cli_reports_missing_token(capsys, monkeypatch, tmp_path):
    monkeypatch.delenv("CANVAS_TOKEN", raising=False)
    with patch("aicc_demo.canvas.load_token", side_effect=ValueError("Canvas needs an access token.")):
        assert main(["https://canvas.example.edu/courses/1"]) == 2
    assert "Canvas needs an access token" in capsys.readouterr().err


SCORM_IFRAME = ('<iframe src="https://canvas.example.edu/courses/2151228/external_tools/retrieve?borderless=true'
                '&amp;url=https%3A%2F%2Fscone-prod.us-east-1.insops.net%2Fpackages%2F815487%2Flaunch"></iframe>')


@responses.activate
def test_follows_off_module_pages_one_level_and_lists_scorm_packages():
    modules = [{"id": 8, "name": "Week 8", "items": [
        {"type": "Page", "title": "W8 NP-Complete Lecture", "page_url": "w8", "html_url": f"{BASE}/courses/2151228/modules/items/81"},
    ]}]
    responses.add(responses.GET, f"{API}/modules", json=modules, status=200)
    responses.add(responses.GET, f"{API}/pages/w8", json={"body":
        '<a href="https://canvas.example.edu/courses/2151228/pages/np-hard">Open the lecture</a>'}, status=200)
    responses.add(responses.GET, f"{API}/pages/np-hard", json={"body": SCORM_IFRAME +
        '<a href="https://canvas.example.edu/courses/2151228/pages/deeper">not followed</a>'}, status=200)

    courses = find_linked_courses(f"{BASE}/courses/2151228", CanvasClient(BASE, "t"), is_web_export=lambda u: False)

    assert [(c.item_title, c.kind, c.course_url, c.extractable) for c in courses] == [
        ("W8 NP-Complete Lecture", "scorm", "https://scone-prod.us-east-1.insops.net/packages/815487/launch", False)]
    assert not any("pages/deeper" in call.request.url for call in responses.calls)  # one level only


def test_scorm_package_url_strips_query_and_ignores_other_tools():
    from aicc_demo.canvas import scorm_package_url

    assert scorm_package_url("https://c/courses/1/external_tools/retrieve?url=https%3A%2F%2Fx.insops.net%2Fpackages%2F9%2Flaunch%3Ftoken%3Dsecret") \
        == "https://x.insops.net/packages/9/launch"
    assert scorm_package_url("https://c/courses/1/external_tools/retrieve?url=https%3A%2F%2Fkaltura.example%2Fv") is None


def test_cli_lists_and_skips_scorm_packages(capsys):
    courses = COURSES + [LinkedCourse("Week 8", "W8 Lecture", "https://c/8", "https://x.insops.net/packages/9/launch", "scorm")]
    with patch("aicc_demo.canvas_cli.find_linked_courses", return_value=courses), \
         patch("aicc_demo.canvas_cli.export_course", return_value={"pdf": "a.pdf"}) as mock_export:
        assert main(["https://canvas.example.edu/courses/1", "--extract", "3"]) == 0

    mock_export.assert_not_called()
    out = capsys.readouterr().out
    assert "(1 SCORM package that cannot be extracted)" in out
    assert "3. W8 Lecture  [scorm]  (Canvas SCORM package" in out
    assert "3. SKIPPED (SCORM package)" in out
