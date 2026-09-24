from unittest.mock import patch
from aicc_demo.assembly import Chunk
from aicc_demo.pipeline import run_pipeline, estimate_raw_video_tokens, estimate_chunk_tokens


def test_estimate_raw_video_tokens_uses_gemini_rate():
    assert estimate_raw_video_tokens(60) == 15780  # 60 * 263


def test_estimate_chunk_tokens_divides_chars_by_four():
    chunks = [Chunk("A", 0, "a" * 40, "A"), Chunk("B", 1, "b" * 40, "B")]
    assert estimate_chunk_tokens(chunks) == 20  # 80 chars / 4


def test_run_pipeline_walks_all_lessons_and_returns_chunks(tmp_path):
    fake_course = {
        "course": {
            "lessons": [
                {"id": "l1", "title": "Intro", "items": [
                    {"type": "text", "items": [{"paragraph": "<p>Suturing basics text.</p>"}]}
                ]},
            ]
        }
    }

    with patch("aicc_demo.pipeline.fetch_course_json", return_value=fake_course):
        chunks = run_pipeline("fake-share-id", str(tmp_path))

    assert len(chunks) == 1
    assert chunks[0].text == "Suturing basics text."
    assert chunks[0].lesson_title == "Intro"
