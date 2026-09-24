import requests
from bs4 import BeautifulSoup
from urllib.parse import unquote

SHARE_ID_SUTURE = "wFfts7vyFk1HxZneZqamI"
INSTANT_LINKS_URL = "https://share.articulate.com/api/instant-links/{share_id}/course"


def fetch_course_json(share_id: str) -> dict:
    url = INSTANT_LINKS_URL.format(share_id=share_id)
    response = requests.post(url, json={}, timeout=30)
    response.raise_for_status()
    return response.json()


def strip_html(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text()


def _decode_key(key: str) -> str:
    return unquote(key)


def _extract_text(item: dict) -> str | None:
    for field in ("heading", "paragraph", "description"):
        if field in item and item[field]:
            return strip_html(item[field])
    return None


def _extract_media_entry(item: dict, lesson_id: str, lesson_title: str, order: int) -> dict | None:
    media = item.get("media")
    if not media:
        return None

    if "embed" in media and media["embed"].get("originalUrl"):
        return {
            "lesson_id": lesson_id,
            "lesson_title": lesson_title,
            "block_order": order,
            "type": "youtube",
            "url": media["embed"]["originalUrl"],
            "captions_available": False,
            "caption_key": None,
        }

    if "video" in media:
        video = media["video"]
        captions = video.get("captions") or []
        caption_key = _decode_key(captions[0]["key"]) if captions else None
        return {
            "lesson_id": lesson_id,
            "lesson_title": lesson_title,
            "block_order": order,
            "type": "articulate_video",
            "url": f"https://articulateusercontent.com/{_decode_key(video['key'])}",
            "captions_available": bool(captions),
            "caption_key": caption_key,
        }

    if "image" in media:
        image = media["image"]
        return {
            "lesson_id": lesson_id,
            "lesson_title": lesson_title,
            "block_order": order,
            "type": "image",
            "url": f"https://articulateusercontent.com/{_decode_key(image['key'])}",
            "captions_available": False,
            "caption_key": None,
        }

    return None


def _walk_items(items: list[dict], lesson_id: str, lesson_title: str, order_counter: list[int]) -> tuple[list[str], list[dict]]:
    text_lines: list[str] = []
    manifest: list[dict] = []

    for item in items:
        text = _extract_text(item)
        if text:
            text_lines.append(text)

        media_entry = _extract_media_entry(item, lesson_id, lesson_title, order_counter[0])
        if media_entry:
            manifest.append(media_entry)
            order_counter[0] += 1

        nested = item.get("items")
        if nested:
            nested_text, nested_manifest = _walk_items(nested, lesson_id, lesson_title, order_counter)
            text_lines.extend(nested_text)
            manifest.extend(nested_manifest)

    return text_lines, manifest


def walk_lesson(lesson: dict) -> tuple[str, list[dict]]:
    lesson_id = lesson["id"]
    lesson_title = lesson["title"]
    order_counter = [0]

    text_lines, manifest = _walk_items(lesson.get("items", []), lesson_id, lesson_title, order_counter)

    markdown = f"## {lesson_title}\n\n" + "\n\n".join(text_lines)
    return markdown, manifest
