import json
from unittest.mock import patch, MagicMock
from aicc_demo.assembly import Chunk
from aicc_demo.pipeline import (
    run_pipeline,
    estimate_raw_video_tokens,
    estimate_chunk_tokens,
    estimate_actual_video_duration_seconds,
)


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


def test_estimate_actual_video_duration_seconds_sums_across_videos():
    fake_course = {
        "course": {
            "lessons": [
                {"id": "l1", "title": "Intro", "items": [
                    {"type": "multimedia", "items": [
                        {"media": {"embed": {"originalUrl": "https://www.youtube.com/watch?v=aaaaaaaaaaa"}}}
                    ]},
                    {"type": "multimedia", "items": [
                        {"media": {"embed": {"originalUrl": "https://www.youtube.com/watch?v=bbbbbbbbbbb"}}}
                    ]},
                ]},
            ]
        }
    }

    def fake_run(cmd, capture_output, text, check):
        url = cmd[-1]
        duration = 120 if "aaaaaaaaaaa" in url else 300
        return MagicMock(returncode=0, stdout=json.dumps({"duration": duration}))

    with patch("aicc_demo.pipeline.fetch_course_json", return_value=fake_course):
        with patch("aicc_demo.pipeline.subprocess.run", side_effect=fake_run):
            total = estimate_actual_video_duration_seconds("fake-share-id")

    assert total == 420


def test_run_pipeline_skips_failed_transcript_and_keeps_successful_one(tmp_path):
    fake_course = {
        "course": {
            "lessons": [
                {"id": "l1", "title": "Knots", "items": [
                    {"type": "multimedia", "items": [
                        {"media": {"embed": {"originalUrl": "https://www.youtube.com/watch?v=failvideo1"}}}
                    ]},
                    {"type": "multimedia", "items": [
                        {"media": {"embed": {"originalUrl": "https://www.youtube.com/watch?v=okvideo111"}}}
                    ]},
                ]},
            ]
        }
    }

    def fake_get_transcript(entry, output_dir):
        if "failvideo1" in entry["url"]:
            raise NotImplementedError("no captions")
        return [{"start": 0.0, "end": 2.0, "text": "Tie the knot like this."}]

    with patch("aicc_demo.pipeline.fetch_course_json", return_value=fake_course):
        with patch("aicc_demo.pipeline.get_transcript", side_effect=fake_get_transcript):
            chunks = run_pipeline("fake-share-id", str(tmp_path))

    video_chunks = [c for c in chunks if c.text == "Tie the knot like this."]
    assert len(video_chunks) == 1
    assert video_chunks[0].lesson_title == "Knots"
    assert video_chunks[0].citation == "Knots @ 0:00"
    assert not any("fail" in c.text.lower() for c in chunks)
