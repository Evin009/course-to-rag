"""Where a Rise course's data and files come from.

Rise publishes a course two ways, with the same course JSON inside:

- Share link (share.articulate.com/<id>): Articulate hosts it. The JSON
  comes from the instant-links API, keyed by the share id, and files are
  served from articulateusercontent.com/<key>.
- Web export ("Publish -> Web", hosted anywhere, e.g. USF's Azure site):
  a static folder. The JSON is baked into <folder>/runtime-data.js as
  `__jsonp("runtime-data.js", "<base64 JSON>")`, and files are copied
  into <folder>/assets/<key>.
"""
import base64
import json
import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote, urlsplit, urlunsplit

import requests

from aicc_demo.extractor import asset_url, fetch_course_json, parse_share_id

_RUNTIME_DATA_RE = re.compile(r'__jsonp\(\s*"runtime-data\.js"\s*,\s*"([A-Za-z0-9+/=]+)"\s*\)')


@dataclass
class CourseSource:
    kind: str  # "share" or "export"
    course_json: dict
    asset_url: Callable[[str], str]  # file key in the JSON -> downloadable URL
    location: str  # share id, or the export folder URL


def export_folder_url(url: str) -> str:
    """Folder URL of a web export, from its index.html (or the folder) URL."""
    parts = urlsplit(url.strip())
    path = parts.path or "/"
    if not path.endswith("/"):
        head, _, last = path.rpartition("/")
        # ".../asymptotic/index.html" -> ".../asymptotic/"; ".../asymptotic" -> ".../asymptotic/"
        path = f"{head}/" if "." in last else f"{path}/"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def decode_runtime_data(text: str) -> dict:
    """Unwrap `__jsonp("runtime-data.js", "<base64>")` into the course JSON."""
    match = _RUNTIME_DATA_RE.search(text)
    if match is None:
        raise ValueError("runtime-data.js does not hold a Rise course payload")
    return json.loads(base64.b64decode(match.group(1)).decode("utf-8"))


def fetch_export_json(folder_url: str) -> dict:
    response = requests.get(folder_url + "runtime-data.js", timeout=60)
    if response.status_code == 404:
        raise ValueError(
            f"No Rise course found at {folder_url} "
            "(not a share.articulate.com link, and no runtime-data.js in that folder)"
        )
    response.raise_for_status()
    return decode_runtime_data(response.text)


def export_asset_url(folder_url: str) -> Callable[[str], str]:
    # Unlike articulateusercontent.com, an export's static host stores files
    # under their plain names, so a key with spaces must be URL-encoded
    # ("Asymptotic Analysis - FindMin Pseudocode.pdf" -> "...%20...").
    # Checked on all 50 files of the COT5407 export, 2026-10-08.
    assets = folder_url + "assets/"
    return lambda key: assets + quote(key, safe="/")


def load_course(link: str) -> CourseSource:
    """Fetch a Rise course from a share link, a bare share id, or a web-export URL."""
    link = link.strip()
    try:
        share_id = parse_share_id(link)
    except ValueError:
        share_id = None
    if share_id is not None:
        return CourseSource("share", fetch_course_json(share_id), asset_url, share_id)

    if not re.match(r"https?://", link):
        raise ValueError(
            f"Not an Articulate Rise course link: {link!r} (expected a share.articulate.com "
            "link or the URL of a web-exported Rise course)"
        )
    folder = export_folder_url(link)
    return CourseSource("export", fetch_export_json(folder), export_asset_url(folder), folder)
