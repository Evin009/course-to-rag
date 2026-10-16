"""Articulate course link (share link or web export) -> labeled course text + media -> one interleaved PDF."""
import difflib
import json
import logging
import os
import re
import subprocess
import sys
from typing import Callable

from aicc_demo.audio import _download_file_directly, get_transcript
from aicc_demo.extractor import extract_course, save_course_text
from aicc_demo.images import ocr_image
from aicc_demo.pdf import render_course_pdf
from aicc_demo.sources import load_course
from aicc_demo.visual import (
    DEFAULT_FRAME_INTERVAL_SECONDS,
    _download_video,
    extract_frames,
    frame_timestamp_seconds,
    select_keyframes,
    video_frame_dir,
)

# Cap on frames shown per video in the PDF. Every image costs the
# downstream LLM tokens, and past ~15 the extra frames of the same
# procedure add little; see scripts/frame_experiment.py.
DEFAULT_MAX_FRAMES_PER_VIDEO = 15

# Finished PDFs are collected in one place, <project root>/pdf/, whatever
# folder the run's downloads and working files go to.
DEFAULT_PDF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "pdf")

# Lecture videos often keep one slide on screen while text is typed onto it:
# every frame hashes the same (COT5407: distance 0 across 98 frames), so
# the image filter keeps only the first, empty frame. A second pass reads
# the text of one dropped frame per TEXT_CHECK_SECONDS and keeps it when its
# text differs from the last kept frame's by more than MAX_TEXT_SIMILARITY.
TEXT_CHECK_SECONDS = 30
MAX_TEXT_SIMILARITY = 0.85

# Text pulled from an attached PDF is capped so one long handout cannot
# swamp the course; the PDF still links to the full file.
MAX_ATTACHMENT_CHARS = 20_000

# OCR on video frames picks up noise from textures and motion blur. A line
# is kept only if it is mostly letters/digits and long enough to be words.
_MIN_OCR_LINE_ALNUM = 4
_MIN_OCR_ALNUM_RATIO = 0.6


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60].rstrip("-") or "course"


def clean_ocr_text(text: str) -> str:
    kept = []
    for line in text.splitlines():
        line = " ".join(line.split())
        alnum = sum(ch.isalnum() for ch in line)
        if alnum >= _MIN_OCR_LINE_ALNUM and alnum / len(line) >= _MIN_OCR_ALNUM_RATIO:
            kept.append(line)
    return "\n".join(kept)


def choose_keyframes(keyframes: list[dict], limit: int | None) -> list[dict]:
    """Cap a video's keyframes, keeping frames with on-screen text first.

    Text-bearing frames are rare (12 of 300 kept frames in the Suture
    course) and carry the most for the reader, so an even spread alone
    would usually drop them. The rest of the budget is spread evenly
    over the remaining frames; the result stays in time order.
    """
    if limit is None or len(keyframes) <= limit:
        return keyframes
    with_text = [k for k in keyframes if k["ocr"]]
    without_text = [k for k in keyframes if not k["ocr"]]
    chosen = spread_evenly(with_text, limit)
    chosen += spread_evenly(without_text, limit - len(chosen))
    return sorted(chosen, key=lambda k: k["seconds"])


def spread_evenly(items: list, limit: int | None) -> list:
    """Pick at most `limit` items spread across the list, keeping order."""
    if limit is None or len(items) <= limit:
        return items
    if limit <= 1:
        return items[:max(limit, 0)]
    step = (len(items) - 1) / (limit - 1)
    return [items[round(i * step)] for i in range(limit)]


def video_title(url: str) -> str | None:
    """The video's own title as yt-dlp reports it, or None."""
    result = subprocess.run(
        ["yt-dlp", "--skip-download", "--no-warnings", "--print", "title", url],
        capture_output=True, text=True, check=False, timeout=120,
    )
    title = result.stdout.strip().splitlines()[-1] if result.returncode == 0 and result.stdout.strip() else ""
    return title or None


def pick_frames(
    frames: list[str],
    visually_distinct: list[str],
    read_text: Callable[[str], str],
    interval_seconds: int,
) -> tuple[list[str], dict[str, str]]:
    """Visually distinct frames plus frames whose on-screen text changed.

    Returns the kept frames in time order and the OCR text read for them.
    """
    step = max(1, TEXT_CHECK_SECONDS // interval_seconds)
    distinct = set(visually_distinct)
    checked = set(frames[::step]) | ({frames[-1]} if frames else set())
    texts: dict[str, str] = {}
    kept: list[str] = []
    last_text = ""
    for frame in frames:
        if frame not in distinct and frame not in checked:
            continue
        texts[frame] = read_text(frame)
        if frame in distinct:
            kept.append(frame)
            last_text = texts[frame] or last_text
        elif texts[frame] and difflib.SequenceMatcher(None, texts[frame], last_text).ratio() < MAX_TEXT_SIMILARITY:
            kept.append(frame)
            last_text = texts[frame]
    return kept, {frame: texts[frame] for frame in kept}


def _read_frame_text(frame_path: str) -> str:
    try:
        return clean_ocr_text(ocr_image(frame_path))
    except Exception as exc:
        print(f"  WARNING: OCR failed for frame {frame_path}: {exc}", file=sys.stderr)
        return ""


def _process_video(block: dict, media_dir: str, interval_seconds: int, max_frames: int | None) -> None:
    entry = block["media"]
    if block.get("title_is_guess") and entry["type"] in ("kaltura", "web_video"):
        try:
            block["title"] = video_title(entry["url"]) or block["title"]
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"  WARNING: could not read title for {entry['url']}: {exc}", file=sys.stderr)
    try:
        block["transcript"] = get_transcript(entry, media_dir)
    except Exception as exc:
        print(f"  WARNING: transcript failed for {entry['url']}: {exc}", file=sys.stderr)
        block["transcript"] = []

    block["keyframes"] = []
    key = entry.get("media_key")
    video_path = _download_video(entry["url"], media_dir, key)
    if video_path is None:
        return
    frame_dir = video_frame_dir(media_dir, key or entry["url"], interval_seconds)
    frames = extract_frames(video_path, frame_dir, interval_seconds)
    distinct = select_keyframes(frames)
    kept, texts = pick_frames(frames, distinct, _read_frame_text, interval_seconds)
    candidates = [
        {"path": frame, "seconds": frame_timestamp_seconds(frame, interval_seconds), "ocr": texts[frame]}
        for frame in kept
    ]
    block["keyframes"] = choose_keyframes(candidates, max_frames)
    print(
        f"  frames: {len(frames)} sampled -> {len(distinct)} distinct by image"
        f" + {len(kept) - len(distinct)} by text -> {len(block['keyframes'])} in PDF",
        file=sys.stderr,
    )


def _process_image(block: dict, media_dir: str) -> None:
    block["path"] = _download_file_directly(block["media"]["url"], media_dir)
    block["ocr"] = ""
    if block["path"] is None:
        return
    try:
        block["ocr"] = clean_ocr_text(ocr_image(block["path"]))
    except Exception as exc:
        print(f"  WARNING: OCR failed for {block['path']}: {exc}", file=sys.stderr)


def pdf_text(path: str, max_chars: int = MAX_ATTACHMENT_CHARS) -> str:
    """Plain text of a PDF's pages, blank lines between pages, capped at `max_chars`."""
    from pypdf import PdfReader

    # pypdf logs harmless repair notes ("Ignoring wrong pointing object")
    # for slightly malformed handouts; the text still comes out.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    pages = []
    for page in PdfReader(path).pages:
        text = "\n".join(" ".join(line.split()) for line in (page.extract_text() or "").splitlines())
        if text.strip():
            pages.append(text.strip())
    text = "\n\n".join(pages)
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + " […]"


def _process_attachment(block: dict, media_dir: str) -> None:
    block["path"] = _download_file_directly(block["media"]["url"], media_dir)
    block["text"] = ""
    if block["path"] is None:
        return
    is_pdf = block["media"].get("mime_type") == "application/pdf" or block["path"].lower().endswith(".pdf")
    if not is_pdf:
        return
    try:
        block["text"] = pdf_text(block["path"])
    except Exception as exc:
        print(f"  WARNING: could not read attachment {block['path']}: {exc}", file=sys.stderr)


def export_course(
    course_url: str,
    output_dir: str | None = None,
    interval_seconds: int = DEFAULT_FRAME_INTERVAL_SECONDS,
    max_frames_per_video: int | None = DEFAULT_MAX_FRAMES_PER_VIDEO,
    include_video: bool = True,
    pdf_dir: str = DEFAULT_PDF_DIR,
) -> dict:
    """Run the whole flow for one course link and return the output paths."""
    source = load_course(course_url)
    print(f"Fetched course ({source.kind}: {source.location})", file=sys.stderr)
    course = extract_course(source.course_json, source_url=course_url, assets=source.asset_url)
    output_dir = output_dir or os.path.join("data", slugify(course["title"]))
    os.makedirs(output_dir, exist_ok=True)
    text_json, text_md = save_course_text(course, output_dir)
    print(f"Course: {course['title']} -> {output_dir}", file=sys.stderr)

    for lesson in course["lessons"]:
        for block in lesson["blocks"]:
            if block["label"] == "image":
                _process_image(block, output_dir)
            elif block["label"] == "attachment":
                _process_attachment(block, output_dir)
            elif block["label"] == "video" and include_video:
                print(f"[{lesson['title']}] video: {block['media']['url']}", file=sys.stderr)
                _process_video(block, output_dir, interval_seconds, max_frames_per_video)
                print(f"  title: {block['title']}", file=sys.stderr)

    package_path = os.path.join(output_dir, "course_package.json")
    with open(package_path, "w", encoding="utf-8") as f:
        json.dump(course, f, indent=2, ensure_ascii=False)

    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, f"{slugify(course['title'])}.pdf")
    render_course_pdf(course, pdf_path)
    return {
        "output_dir": output_dir,
        "course_text_json": text_json,
        "course_text_md": text_md,
        "course_package": package_path,
        "pdf": pdf_path,
    }
