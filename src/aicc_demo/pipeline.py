import os

from aicc_demo.extractor import fetch_course_json, walk_lesson
from aicc_demo.audio import get_transcript
from aicc_demo.assembly import Chunk, build_chunks, chunk_lesson_text


def estimate_raw_video_tokens(duration_seconds: float, tokens_per_second: float = 263.0) -> int:
    return int(duration_seconds * tokens_per_second)


def estimate_chunk_tokens(chunks: list[Chunk], chars_per_token: float = 4.0) -> int:
    total_chars = sum(len(c.text) for c in chunks)
    return int(total_chars / chars_per_token)


def run_pipeline(share_id: str, output_dir: str) -> list[Chunk]:
    os.makedirs(output_dir, exist_ok=True)
    course = fetch_course_json(share_id)
    lessons = course["course"]["lessons"]

    all_chunks: list[Chunk] = []

    for lesson in lessons:
        markdown, manifest = walk_lesson(lesson)
        all_chunks.extend(chunk_lesson_text(lesson["title"], markdown))

        video_entries = [e for e in manifest if e["type"] in ("youtube", "articulate_video")]
        transcripts = {}
        for entry in video_entries:
            try:
                transcripts[entry["block_order"]] = get_transcript(entry, output_dir)
            except NotImplementedError:
                continue
        all_chunks.extend(build_chunks(lesson["title"], manifest, transcripts))

    return all_chunks
