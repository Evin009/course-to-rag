from unittest.mock import patch
from aicc_demo.assembly import Chunk
from aicc_demo.pipeline import (
    run_pipeline,
    estimate_raw_video_tokens,
    estimate_chunk_tokens,
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


def test_run_pipeline_includes_visual_chunks_from_process_video_visuals(tmp_path):
    fake_course = {
        "course": {
            "lessons": [
                {"id": "l1", "title": "Knots", "items": [
                    {"type": "multimedia", "items": [
                        {"media": {"embed": {"originalUrl": "https://www.youtube.com/watch?v=okvideo111"}}}
                    ]},
                ]},
            ]
        }
    }

    fake_visual_chunk = Chunk(
        lesson_title="Knots",
        block_order=0,
        text="Slide text from frame OCR",
        citation="Knots @ 0:15 (frame)",
    )

    def fake_get_transcript(entry, output_dir):
        return [{"start": 0.0, "end": 2.0, "text": "Tie the knot like this."}]

    with patch("aicc_demo.pipeline.fetch_course_json", return_value=fake_course):
        with patch("aicc_demo.pipeline.get_transcript", side_effect=fake_get_transcript):
            with patch("aicc_demo.pipeline.process_video_visuals", return_value=[fake_visual_chunk]) as mock_visuals:
                chunks = run_pipeline("fake-share-id", str(tmp_path))

    assert fake_visual_chunk in chunks
    mock_visuals.assert_called_once_with(
        "https://www.youtube.com/watch?v=okvideo111", "Knots", 0, str(tmp_path)
    )


def test_run_pipeline_includes_image_chunks_from_process_image_entries(tmp_path):
    fake_course = {
        "course": {
            "lessons": [
                {"id": "l1", "title": "Intro", "items": [
                    {"type": "text", "items": [{"paragraph": "<p>Suturing basics text.</p>"}]}
                ]},
            ]
        }
    }

    fake_image_chunk = Chunk(
        lesson_title="Intro",
        block_order=0,
        text="Slide text from OCR",
        citation="Intro (image)",
    )

    with patch("aicc_demo.pipeline.fetch_course_json", return_value=fake_course):
        with patch("aicc_demo.pipeline.process_image_entries", return_value=[fake_image_chunk]):
            chunks = run_pipeline("fake-share-id", str(tmp_path))

    assert fake_image_chunk in chunks


def test_run_pipeline_populates_stats_with_coverage_and_video_entries(tmp_path):
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

    stats: dict = {}
    with patch("aicc_demo.pipeline.fetch_course_json", return_value=fake_course):
        with patch("aicc_demo.pipeline.get_transcript", side_effect=fake_get_transcript):
            run_pipeline("fake-share-id", str(tmp_path), stats=stats)

    assert stats["attempted"] == 2
    assert stats["succeeded"] == 1
    assert len(stats["video_entries"]) == 2


def test_run_pipeline_sums_duration_from_transcript_segments_excluding_failures(tmp_path):
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
                    {"type": "multimedia", "items": [
                        {"media": {"embed": {"originalUrl": "https://www.youtube.com/watch?v=okvideo222"}}}
                    ]},
                ]},
            ]
        }
    }

    def fake_get_transcript(entry, output_dir):
        if "failvideo1" in entry["url"]:
            raise NotImplementedError("no captions")
        if "okvideo111" in entry["url"]:
            return [
                {"start": 0.0, "end": 2.0, "text": "Tie the knot like this."},
                {"start": 2.0, "end": 45.5, "text": "Now pull it tight."},
            ]
        return [{"start": 0.0, "end": 120.0, "text": "Second video content."}]

    stats: dict = {}
    with patch("aicc_demo.pipeline.fetch_course_json", return_value=fake_course):
        with patch("aicc_demo.pipeline.get_transcript", side_effect=fake_get_transcript):
            run_pipeline("fake-share-id", str(tmp_path), stats=stats)

    # Only the two successfully-transcribed videos contribute their last
    # segment's "end" value; the failed video contributes nothing.
    assert stats["total_duration_seconds"] == 45.5 + 120.0
