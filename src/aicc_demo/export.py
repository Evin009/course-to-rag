"""Articulate course link -> labeled course text + media -> one interleaved PDF."""
import json
import os
import re
import sys

from aicc_demo.audio import _download_file_directly, get_transcript
from aicc_demo.extractor import extract_course, fetch_course_json, parse_share_id, save_course_text
from aicc_demo.images import ocr_image
from aicc_demo.pdf import render_course_pdf
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


def _process_video(block: dict, media_dir: str, interval_seconds: int, max_frames: int | None) -> None:
    entry = block["media"]
    try:
        block["transcript"] = get_transcript(entry, media_dir)
    except Exception as exc:
        print(f"  WARNING: transcript failed for {entry['url']}: {exc}", file=sys.stderr)
        block["transcript"] = []

    block["keyframes"] = []
    video_path = _download_video(entry["url"], media_dir)
    if video_path is None:
        return
    frames = extract_frames(video_path, video_frame_dir(media_dir, entry["url"], interval_seconds), interval_seconds)
    distinct = select_keyframes(frames)
    candidates = []
    for frame_path in distinct:
        try:
            ocr = clean_ocr_text(ocr_image(frame_path))
        except Exception as exc:
            print(f"  WARNING: OCR failed for frame {frame_path}: {exc}", file=sys.stderr)
            ocr = ""
        candidates.append({
            "path": frame_path,
            "seconds": frame_timestamp_seconds(frame_path, interval_seconds),
            "ocr": ocr,
        })
    block["keyframes"] = choose_keyframes(candidates, max_frames)
    print(
        f"  frames: {len(frames)} sampled -> {len(distinct)} distinct -> {len(block['keyframes'])} in PDF",
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


def export_course(
    course_url: str,
    output_dir: str | None = None,
    interval_seconds: int = DEFAULT_FRAME_INTERVAL_SECONDS,
    max_frames_per_video: int | None = DEFAULT_MAX_FRAMES_PER_VIDEO,
    include_video: bool = True,
    pdf_dir: str = DEFAULT_PDF_DIR,
) -> dict:
    """Run the whole flow for one course link and return the output paths."""
    share_id = parse_share_id(course_url)
    print(f"Fetching course {share_id}...", file=sys.stderr)
    course = extract_course(fetch_course_json(share_id), source_url=course_url)
    output_dir = output_dir or os.path.join("data", slugify(course["title"]))
    os.makedirs(output_dir, exist_ok=True)
    text_json, text_md = save_course_text(course, output_dir)
    print(f"Course: {course['title']} -> {output_dir}", file=sys.stderr)

    for lesson in course["lessons"]:
        for block in lesson["blocks"]:
            if block["label"] == "image":
                _process_image(block, output_dir)
            elif block["label"] == "video" and include_video:
                print(f"[{lesson['title']}] video: {block['title']}", file=sys.stderr)
                _process_video(block, output_dir, interval_seconds, max_frames_per_video)

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
