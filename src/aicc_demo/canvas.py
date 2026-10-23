"""Find the Articulate Rise courses an instructor linked inside a Canvas course.

Given https://<canvas-host>/courses/<id>, walk the course's modules through
the Canvas REST API, read every Page item (and External URL item), and keep
the links that point at a Rise course: a share link, an old
rise.articulate.com/share link, or a web export (a folder with
runtime-data.js). Canvas needs a login; the Rise courses themselves are
public, so only this discovery step uses the Canvas API token.
"""
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

_CANVAS_COURSE_RE = re.compile(r"^(https?://[^/]+)/courses/(\d+)")
_COURSE_PAGE_RE = re.compile(r"/courses/(\d+)/pages/([^/?#]+)")
# Canvas's SCORM tool plays packages from Instructure's servers through an
# LTI launch (`.../external_tools/retrieve?url=https://scone-prod...insops.net/
# packages/<id>/launch`). The package is only reachable inside a Canvas
# session, so it is listed but cannot be extracted (COT5407 Week 8).
_SCORM_PACKAGE_RE = re.compile(r"insops\.net/packages/\d+")
_SHARE_LINK_RE = re.compile(r"share\.articulate\.com/[A-Za-z0-9_-]{10,}|rise\.articulate\.com/share/[A-Za-z0-9_-]{10,}")
# Canvas prefixes JSON responses with this guard against JSON hijacking.
_JSON_GUARD = "while(1);"

TOKEN_HELP = (
    "Canvas needs an access token. In Canvas: Account -> Settings -> "
    "'+ New Access Token'. Then put CANVAS_TOKEN=<token> in a .env file in the "
    "project root (it is git-ignored), or export CANVAS_TOKEN in your shell."
)


@dataclass
class LinkedCourse:
    module: str
    item_title: str
    item_url: str  # the Canvas page the link was found on
    course_url: str  # the Rise course link, as the instructor wrote it
    kind: str  # "share", "export", or "scorm" (listed, not extractable)

    @property
    def extractable(self) -> bool:
        return self.kind in ("share", "export")


def parse_canvas_course_url(url: str) -> tuple[str, str]:
    """(base URL, course id) from https://<host>/courses/<id>[/anything]."""
    match = _CANVAS_COURSE_RE.match(url.strip())
    if match is None:
        raise ValueError(f"Not a Canvas course URL: {url!r} (expected https://<canvas-host>/courses/<id>)")
    return match.group(1), match.group(2)


def load_token(project_root: str | None = None) -> str:
    """CANVAS_TOKEN from the environment, else from <project root>/.env."""
    token = os.environ.get("CANVAS_TOKEN", "").strip()
    if token:
        return token
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
    env_file = root / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "CANVAS_TOKEN" and value.strip():
                return value.strip().strip("\"'")
    raise ValueError(TOKEN_HELP)


class CanvasClient:
    def __init__(self, base_url: str, token: str, session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})

    def _get(self, url: str, params: dict | None = None) -> requests.Response:
        response = self.session.get(url, params=params, timeout=30)
        if response.status_code == 401:
            raise ValueError("Canvas rejected the access token (401). " + TOKEN_HELP)
        if response.status_code == 403:
            raise ValueError(f"Canvas denied access (403) to {url}; is this account enrolled in the course?")
        response.raise_for_status()
        return response

    @staticmethod
    def _json(response: requests.Response):
        text = response.text
        return json.loads(text[len(_JSON_GUARD):] if text.startswith(_JSON_GUARD) else text)

    def get(self, path: str, params: dict | None = None):
        return self._json(self._get(self.base_url + path, params))

    def get_all(self, path: str, params: dict | None = None) -> list:
        """Every page of a paginated list endpoint (Canvas sends rel="next" Link headers)."""
        items: list = []
        response = self._get(self.base_url + path, {"per_page": 100, **(params or {})})
        while True:
            items.extend(self._json(response))
            next_url = response.links.get("next", {}).get("url")
            if not next_url:
                return items
            response = self._get(next_url)


def scorm_package_url(url: str) -> str | None:
    """The SCORM package a Canvas external-tool iframe launches, without query string."""
    parts = urlsplit(url)
    target = url
    if parts.path.endswith("/external_tools/retrieve"):
        target = parse_qs(parts.query).get("url", [""])[0]
    if not _SCORM_PACKAGE_RE.search(target):
        return None
    t = urlsplit(target)
    return f"{t.scheme}://{t.netloc}{t.path}"


def classify_course_link(url: str, is_web_export=None) -> str | None:
    """"share", "export", "scorm" or None for a link found on a Canvas page.

    Exports are only probed when the link names an index.html page or a
    USF course-resources folder, so ordinary links are never fetched.
    """
    if scorm_package_url(url):
        return "scorm"
    if _SHARE_LINK_RE.search(url):
        return "share"
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return None
    looks_exported = parts.path.endswith("/index.html") or "courseresources" in url.lower()
    if looks_exported and (is_web_export or _has_runtime_data)(url):
        return "export"
    return None


def _has_runtime_data(url: str) -> bool:
    from aicc_demo.sources import export_folder_url

    try:
        response = requests.get(export_folder_url(url) + "runtime-data.js", timeout=30, stream=True)
        response.close()
    except requests.RequestException:
        return False
    return response.status_code == 200


def links_in_html(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    urls = [tag.get("href") for tag in soup.find_all("a")] + [tag.get("src") for tag in soup.find_all("iframe")]
    return [urljoin(page_url, u.strip()) for u in urls if u and not u.startswith(("#", "mailto:", "javascript:"))]


def find_linked_courses(canvas_course_url: str, client: CanvasClient | None = None, is_web_export=None) -> list[LinkedCourse]:
    """Every Rise course linked from the Canvas course's modules, in module order.

    A module Page may point at another page of the course that is in no
    module (COT5407's "W8 NP-Complete Lecture" does); such pages are read
    too, one level deep, and what they link counts for the module item.
    """
    base_url, course_id = parse_canvas_course_url(canvas_course_url)
    client = client or CanvasClient(base_url, load_token())
    modules = client.get_all(f"/api/v1/courses/{course_id}/modules", {"include[]": "items"})
    for module in modules:
        if module.get("items") is None:  # large modules come without inline items
            module["items"] = client.get_all(f"/api/v1/courses/{course_id}/modules/{module['id']}/items")
    module_pages = {item.get("page_url") for m in modules for item in m["items"] if item.get("type") == "Page"}

    def page_links(slug: str, page_url: str) -> list[str]:
        page = client.get(f"/api/v1/courses/{course_id}/pages/{slug}")
        return links_in_html(page.get("body") or "", page_url)

    found: list[LinkedCourse] = []
    seen: set[str] = set()
    followed: set[str] = set()
    for module in modules:
        for item in module["items"]:
            if item.get("type") == "Page" and item.get("page_url"):
                links = page_links(item["page_url"], item.get("html_url") or base_url)
            elif item.get("type") == "ExternalUrl" and item.get("external_url"):
                links = [item["external_url"]]
            else:
                continue
            for link in list(links):
                target = _COURSE_PAGE_RE.search(link)
                if target and target.group(1) == course_id and target.group(2) not in module_pages | followed:
                    followed.add(target.group(2))
                    try:
                        links += page_links(target.group(2), link)
                    except (ValueError, requests.HTTPError) as exc:  # unpublished or locked page
                        print(f"  note: could not read linked page {target.group(2)}: {exc}", file=sys.stderr)
            for link in links:
                kind = classify_course_link(link, is_web_export)
                course_url = scorm_package_url(link) if kind == "scorm" else link
                if kind is None or course_url in seen:
                    continue
                seen.add(course_url)
                found.append(LinkedCourse(
                    module=module.get("name", ""),
                    item_title=(item.get("title") or "").strip(),
                    item_url=item.get("html_url") or "",
                    course_url=course_url,
                    kind=kind,
                ))
    return found


def as_dicts(courses: list[LinkedCourse]) -> list[dict]:
    return [asdict(c) for c in courses]
