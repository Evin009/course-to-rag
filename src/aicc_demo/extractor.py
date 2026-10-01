import json
import os
import re
import requests
from bs4 import BeautifulSoup

from aicc_demo.utils import extract_youtube_id

INSTANT_LINKS_URL = "https://share.articulate.com/api/instant-links/{share_id}/course"

# Accepts every form an Articulate Rise share link shows up in:
#   https://share.articulate.com/<id>
#   https://share.articulate.com/<id>#/lessons/...
#   https://rise.articulate.com/share/<id>#/...
#   https://share.articulate.com/api/instant-links/<id>/course
_SHARE_URL_RE = re.compile(
    r"(?:share\.articulate\.com/(?:api/instant-links/)?|rise\.articulate\.com/share/)"
    r"([A-Za-z0-9_-]{10,})"
)
_BARE_SHARE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")

# Rise ships stock content for blocks the author never filled in. Leaving
# it in would put "Lorem ipsum" and a stock mountain photo into the PDF the
# LLM reads as course material.
_DEFAULT_ASSET_PREFIX = "assets/rise/assets/block-defaults/"
_PLACEHOLDER_TEXT = {"subheading", "heading", "continue", "start", "summary"}

# Labels a text block can carry. "title" is the lesson title, "section" a
# Rise section header (a lesson with no content of its own).
TEXT_LABELS = ("section", "title", "heading", "paragraph", "list_item")
MEDIA_LABELS = ("image", "video")


def parse_share_id(url_or_id: str) -> str:
    """Pull the Rise share id out of an Articulate course link (or accept a bare id)."""
    candidate = url_or_id.strip()
    match = _SHARE_URL_RE.search(candidate)
    if match:
        return match.group(1)
    if _BARE_SHARE_ID_RE.match(candidate):
        return candidate
    raise ValueError(
        f"Not an Articulate Rise share link: {url_or_id!r} "
        "(expected e.g. https://share.articulate.com/<id>)"
    )


def _normalize_youtube_url(raw: str) -> str:
    video_id = extract_youtube_id(raw)
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return raw


def fetch_course_json(share_id: str) -> dict:
    url = INSTANT_LINKS_URL.format(share_id=share_id)
    response = requests.post(url, json={}, timeout=30)
    response.raise_for_status()
    return response.json()


def strip_html(html: str) -> str:
    """Convert Rise rich-text HTML to plain text, keeping list items and paragraph breaks."""
    soup = BeautifulSoup(html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for li in soup.find_all("li"):
        li.insert_before("\n• ")
    for block in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol"]):
        block.insert_after("\n")

    lines = []
    for line in soup.get_text().replace("\xa0", " ").split("\n"):
        line = " ".join(line.split())
        if line and line != "•":
            lines.append(line)
    return "\n".join(lines)


def asset_url(key: str) -> str:
    """URL of an Articulate-hosted file (video, image, caption) from its JSON key.

    The key is used exactly as stored. Keys with spaces arrive as `%2520`,
    which looks double-encoded, but articulateusercontent.com serves the
    file only under that raw form: decoding it to `%20` returns 403
    (checked live on PCC videos, captions and images, 2026-10-01).
    """
    return f"https://articulateusercontent.com/{key}"


def _is_placeholder(text: str) -> bool:
    return text.lower().startswith("lorem ipsum") or text.lower() in _PLACEHOLDER_TEXT


def _media_entry(media: dict, lesson_id: str, lesson_title: str, order: int) -> dict | None:
    base = {
        "lesson_id": lesson_id,
        "lesson_title": lesson_title,
        "block_order": order,
        "captions_available": False,
        "caption_key": None,
    }

    if "embed" in media and media["embed"].get("originalUrl"):
        return {**base, "type": "youtube", "url": _normalize_youtube_url(media["embed"]["originalUrl"])}

    if "video" in media and media["video"].get("key"):
        video = media["video"]
        captions = video.get("captions") or []
        return {
            **base,
            "type": "articulate_video",
            "url": asset_url(video["key"]),
            "captions_available": bool(captions),
            "caption_key": captions[0]["key"] if captions else None,
        }

    if "image" in media and media["image"].get("key"):
        image = media["image"]
        if image["key"].startswith(_DEFAULT_ASSET_PREFIX):
            return None
        # Rise displays the "crushed" (re-compressed) copy when this flag is
        # set; for some uploads it is the only copy the CDN will serve.
        key = image["crushedKey"] if image.get("useCrushedKey") and image.get("crushedKey") else image["key"]
        return {**base, "type": "image", "url": asset_url(key)}

    return None


class _Walker:
    """Walks one lesson's nested Rise items into an ordered list of labeled blocks."""

    def __init__(self, lesson_id: str, lesson_title: str):
        self.lesson_id = lesson_id
        self.lesson_title = lesson_title
        self.blocks: list[dict] = []
        self.media_order = 0
        self.last_heading: str | None = None

    def _text(self, label: str, html: str | None) -> None:
        if not html:
            return
        text = strip_html(html)
        if not text or _is_placeholder(text):
            return
        if label == "heading":
            self.last_heading = text
        self.blocks.append({"label": label, "text": text})

    def _media(self, media: dict | None) -> None:
        if not media:
            return
        entry = _media_entry(media, self.lesson_id, self.lesson_title, self.media_order)
        if entry is None:
            return
        self.media_order += 1
        label = "image" if entry["type"] == "image" else "video"
        block = {"label": label, "media": entry}
        if label == "video":
            embed_title = (media.get("embed") or {}).get("title")
            block["title"] = embed_title or self.last_heading or self.lesson_title
        self.blocks.append(block)

    def walk(self, items: list[dict], in_list: bool = False) -> None:
        # Process blocks store their "summary" step second in the JSON but
        # Rise shows it last, after every step.
        items = sorted(items, key=lambda i: i.get("type") == "summary")
        for item in items:
            if item.get("isHidden") or item.get("type") == "divider":
                continue

            body_label = "list_item" if in_list or item.get("type") == "list" else "paragraph"
            self._text("heading", item.get("title"))
            self._text("heading", item.get("heading"))
            # Flashcards keep their text on the card faces, not the item.
            for side, label in (("front", "heading"), ("back", "paragraph")):
                face = item.get(side)
                if isinstance(face, dict):
                    self._text(label, face.get("description"))
                    self._media(face.get("media"))
            self._text(body_label, item.get("paragraph"))
            self._text(body_label, item.get("description"))
            self._text("paragraph", item.get("caption"))
            self._media(item.get("media"))

            nested = item.get("items")
            if nested:
                self.walk(nested, in_list=item.get("type") == "list")


def extract_blocks(lesson: dict) -> list[dict]:
    """Return a lesson's content as ordered blocks labeled by type.

    Text blocks: {"label": heading|paragraph|list_item, "text": str}
    Media blocks: {"label": image|video, "media": <manifest entry>, "title"?: str}
    """
    walker = _Walker(lesson["id"], lesson["title"])
    walker.walk(lesson.get("items") or [])
    return walker.blocks


def walk_lesson(lesson: dict) -> tuple[str, list[dict]]:
    blocks = extract_blocks(lesson)
    text_lines = [b["text"] for b in blocks if "text" in b]
    manifest = [b["media"] for b in blocks if "media" in b]
    markdown = f"## {lesson['title']}\n\n" + "\n\n".join(text_lines)
    return markdown, manifest


def extract_course(course_json: dict, source_url: str | None = None) -> dict:
    """Turn the raw instant-links response into a clean, labeled course document."""
    course = course_json["course"]
    lessons = []
    for lesson in course.get("lessons") or []:
        is_section = lesson.get("type") == "section"
        lessons.append({
            "id": lesson["id"],
            "title": strip_html(lesson.get("title") or "").strip(),
            "label": "section" if is_section else "title",
            "blocks": [] if is_section else extract_blocks(lesson),
        })
    return {
        "title": course.get("title") or "Untitled course",
        "share_id": course.get("shareId"),
        "source_url": source_url,
        "description": strip_html(course.get("description") or ""),
        "lessons": lessons,
    }


def course_to_markdown(course: dict) -> str:
    lines = [f"# {course['title']}", ""]
    if course.get("description"):
        lines += [course["description"], ""]
    for lesson in course["lessons"]:
        if lesson["label"] == "section":
            lines += [f"## {lesson['title']}", ""]
            continue
        lines += [f"### {lesson['title']}", ""]
        for block in lesson["blocks"]:
            label = block["label"]
            if label != "list_item" and lines[-1].startswith("- "):
                lines.append("")
            if label == "heading":
                lines += [f"**{block['text']}**", ""]
            elif label == "list_item":
                lines += [f"- {block['text']}"]
            elif label == "paragraph":
                lines += [block["text"], ""]
            elif label == "image":
                lines += [f"![image]({block['media']['url']})", ""]
            elif label == "video":
                lines += [f"[Video: {block['title']}]({block['media']['url']})", ""]
        if lines[-1].startswith("- "):
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def save_course_text(course: dict, output_dir: str) -> tuple[str, str]:
    """Store the labeled course text as JSON (for code) and Markdown (for people)."""
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, "course_text.json")
    md_path = os.path.join(output_dir, "course_text.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(course, f, indent=2, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(course_to_markdown(course))
    return json_path, md_path
