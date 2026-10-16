import os
import sys

from aicc_demo.extractor import walk_lesson
from aicc_demo.audio import YTDLP_VIDEO_TYPES, get_transcript
from aicc_demo.sources import load_course
from aicc_demo.assembly import Chunk, build_chunks, chunk_lesson_text
from aicc_demo.images import process_image_entries
from aicc_demo.visual import process_video_visuals


def estimate_raw_video_tokens(duration_seconds: float, tokens_per_second: float = 263.0) -> int:
    return int(duration_seconds * tokens_per_second)


def estimate_chunk_tokens(chunks: list[Chunk], chars_per_token: float = 4.0) -> int:
    total_chars = sum(len(c.text) for c in chunks)
    return int(total_chars / chars_per_token)


VIDEO_TYPES = (*YTDLP_VIDEO_TYPES, "articulate_video")


def run_pipeline(course_link: str, output_dir: str, stats: dict | None = None) -> list[Chunk]:
    """Run the extraction/transcription/chunking pipeline.

    If `stats` is provided, it is populated in place with:
      - "attempted": total video entries (embedded + articulate_video) seen
      - "succeeded": how many of those produced a transcript
      - "video_entries": the flat list of all video manifest entries
      - "total_duration_seconds": sum of each successfully-transcribed
        video's duration, taken from the last transcript segment's "end"
        timestamp (already available from the caption fetch, so no
        separate yt-dlp `--dump-json` call is needed). Scoped to videos
        that were actually transcribed, same as "succeeded".
    """
    os.makedirs(output_dir, exist_ok=True)
    source = load_course(course_link)
    lessons = source.course_json["course"]["lessons"]

    all_chunks: list[Chunk] = []
    all_video_entries: list[dict] = []
    total_attempted = 0
    total_succeeded = 0
    total_duration_seconds = 0.0

    for lesson in lessons:
        markdown, manifest = walk_lesson(lesson, source.asset_url)
        all_chunks.extend(chunk_lesson_text(lesson["title"], markdown))

        video_entries = [e for e in manifest if e["type"] in VIDEO_TYPES]
        all_video_entries.extend(video_entries)
        transcripts = {}
        succeeded = 0
        for entry in video_entries:
            try:
                segments = get_transcript(entry, output_dir)
                transcripts[entry["block_order"]] = segments
                succeeded += 1
                if segments:
                    total_duration_seconds += segments[-1]["end"]
            except Exception as exc:
                # Any transcript failure for one video (out-of-scope path,
                # corrupt audio, ASR model download failure, ...) must not
                # kill the whole run — log it and move on.
                print(
                    f"  WARNING: transcript failed for {entry['url']} "
                    f"in lesson '{lesson['title']}': {exc}",
                    file=sys.stderr,
                )

            # Visual analysis (frame extraction/dedup/OCR) runs independently
            # of narration/captions, for every video, regardless of whether
            # a transcript was successfully produced above.
            all_chunks.extend(
                process_video_visuals(
                    entry["url"], lesson["title"], entry["block_order"], output_dir, key=entry.get("media_key")
                )
            )

        if video_entries:
            print(
                f"  [{lesson['title']}] transcribed {succeeded}/{len(video_entries)} videos",
                file=sys.stderr,
            )
        total_attempted += len(video_entries)
        total_succeeded += succeeded

        all_chunks.extend(build_chunks(lesson["title"], manifest, transcripts))
        all_chunks.extend(process_image_entries(manifest, output_dir))

    if stats is not None:
        stats["attempted"] = total_attempted
        stats["succeeded"] = total_succeeded
        stats["video_entries"] = all_video_entries
        stats["total_duration_seconds"] = total_duration_seconds

    return all_chunks
