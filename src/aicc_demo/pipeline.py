import json
import os
import subprocess
import sys

from aicc_demo.extractor import fetch_course_json, walk_lesson
from aicc_demo.audio import get_transcript
from aicc_demo.assembly import Chunk, build_chunks, chunk_lesson_text


def estimate_raw_video_tokens(duration_seconds: float, tokens_per_second: float = 263.0) -> int:
    return int(duration_seconds * tokens_per_second)


def estimate_chunk_tokens(chunks: list[Chunk], chars_per_token: float = 4.0) -> int:
    total_chars = sum(len(c.text) for c in chunks)
    return int(total_chars / chars_per_token)


def estimate_actual_video_duration_seconds(video_entries: list[dict]) -> float:
    """Sum real yt-dlp durations for the given youtube manifest entries.

    Takes already-extracted manifest entries (e.g. from run_pipeline's
    `stats["video_entries"]`) rather than a share_id, so the course JSON
    is fetched and each lesson walked exactly once per demo run instead
    of being independently re-fetched/re-walked here.
    """
    total_seconds = 0.0

    for entry in video_entries:
        if entry["type"] != "youtube":
            continue
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--skip-download", entry["url"]],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout:
            try:
                total_seconds += json.loads(result.stdout).get("duration") or 0
            except json.JSONDecodeError:
                pass

    return total_seconds


def run_pipeline(share_id: str, output_dir: str, stats: dict | None = None) -> list[Chunk]:
    """Run the extraction/transcription/chunking pipeline.

    If `stats` is provided, it is populated in place with:
      - "attempted": total video entries (youtube + articulate_video) seen
      - "succeeded": how many of those produced a transcript
      - "video_entries": the flat list of all video manifest entries,
        for reuse by estimate_actual_video_duration_seconds without a
        second fetch_course_json/walk_lesson pass.
    """
    os.makedirs(output_dir, exist_ok=True)
    course = fetch_course_json(share_id)
    lessons = course["course"]["lessons"]

    all_chunks: list[Chunk] = []
    all_video_entries: list[dict] = []
    total_attempted = 0
    total_succeeded = 0

    for lesson in lessons:
        markdown, manifest = walk_lesson(lesson)
        all_chunks.extend(chunk_lesson_text(lesson["title"], markdown))

        video_entries = [e for e in manifest if e["type"] in ("youtube", "articulate_video")]
        all_video_entries.extend(video_entries)
        transcripts = {}
        succeeded = 0
        for entry in video_entries:
            try:
                transcripts[entry["block_order"]] = get_transcript(entry, output_dir)
                succeeded += 1
            except NotImplementedError:
                continue

        if video_entries:
            print(
                f"  [{lesson['title']}] transcribed {succeeded}/{len(video_entries)} videos",
                file=sys.stderr,
            )
        total_attempted += len(video_entries)
        total_succeeded += succeeded

        all_chunks.extend(build_chunks(lesson["title"], manifest, transcripts))

    if stats is not None:
        stats["attempted"] = total_attempted
        stats["succeeded"] = total_succeeded
        stats["video_entries"] = all_video_entries

    return all_chunks
