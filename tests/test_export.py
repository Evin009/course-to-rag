import json
from unittest.mock import patch

import pytest

from aicc_demo.cli import main
from aicc_demo.export import DEFAULT_PDF_DIR
from aicc_demo.export import choose_keyframes, clean_ocr_text, export_course, slugify, spread_evenly

RAW_COURSE = {"course": {
    "title": "Suture Course",
    "shareId": "9enP3jMLBp-wenr5LIa0R",
    "description": "",
    "lessons": [{"id": "l1", "title": "Knots", "type": "blocks", "items": [
        {"type": "text", "items": [{"paragraph": "<p>Square knot.</p>"}]},
        {"type": "multimedia", "items": [{"media": {"embed": {"originalUrl": "https://youtu.be/abcdefghijk", "title": "Knot video"}}}]},
    ]}],
}}


def test_slugify_makes_safe_short_folder_names():
    assert slugify("Introduction to Suture Materials & Techniques!") == "introduction-to-suture-materials-techniques"
    assert slugify("???") == "course"


def test_clean_ocr_text_keeps_words_and_drops_noise_lines():
    assert clean_ocr_text("Needle Driver\n~|| ,;\nx\n  3/8 curve  ") == "Needle Driver\n3/8 curve"


def test_spread_evenly_keeps_first_last_and_order():
    assert spread_evenly(list(range(10)), 4) == [0, 3, 6, 9]
    assert spread_evenly([1, 2], 5) == [1, 2]
    assert spread_evenly([1, 2, 3], None) == [1, 2, 3]


def test_choose_keyframes_keeps_text_frames_then_spreads_the_rest():
    frames = [{"seconds": s, "ocr": "Square knot" if s in (40, 70) else ""} for s in range(0, 100, 10)]

    chosen = choose_keyframes(frames, 4)

    assert [k["seconds"] for k in chosen] == [0, 40, 70, 90]
    assert choose_keyframes(frames, None) == frames


def test_export_course_writes_text_package_and_pdf_from_a_link(tmp_path):
    frame = tmp_path / "frame_0002.jpg"

    with patch("aicc_demo.export.fetch_course_json", return_value=RAW_COURSE) as mock_fetch, \
         patch("aicc_demo.export.get_transcript", return_value=[{"start": 11, "end": 14, "text": "tie it"}]), \
         patch("aicc_demo.export._download_video", return_value="/fake/video.mp4"), \
         patch("aicc_demo.export.extract_frames", return_value=[str(frame)]) as mock_extract, \
         patch("aicc_demo.export.select_keyframes", side_effect=lambda frames: frames), \
         patch("aicc_demo.export.ocr_image", return_value="Square Knot"), \
         patch("aicc_demo.export.render_course_pdf", side_effect=lambda course, path: path) as mock_render:
        outputs = export_course(
            "https://share.articulate.com/9enP3jMLBp-wenr5LIa0R#/lessons/x",
            output_dir=str(tmp_path / "out"),
            interval_seconds=10,
            pdf_dir=str(tmp_path / "pdf"),
        )

    mock_fetch.assert_called_once_with("9enP3jMLBp-wenr5LIa0R")
    assert mock_extract.call_args[0][2] == 10
    assert outputs["pdf"] == str(tmp_path / "pdf" / "suture-course.pdf")
    package = json.load(open(outputs["course_package"]))
    video = package["lessons"][0]["blocks"][1]
    assert video["transcript"][0]["text"] == "tie it"
    assert video["keyframes"] == [{"path": str(frame), "seconds": 10, "ocr": "Square Knot"}]
    assert "Square knot." in open(outputs["course_text_md"]).read()
    mock_render.assert_called_once()


def test_export_course_text_only_skips_video_work(tmp_path):
    with patch("aicc_demo.export.fetch_course_json", return_value=RAW_COURSE), \
         patch("aicc_demo.export.get_transcript") as mock_transcript, \
         patch("aicc_demo.export._download_video") as mock_video, \
         patch("aicc_demo.export.render_course_pdf", side_effect=lambda course, path: path):
        export_course("9enP3jMLBp-wenr5LIa0R", output_dir=str(tmp_path), include_video=False, pdf_dir=str(tmp_path / "pdf"))

    mock_transcript.assert_not_called()
    mock_video.assert_not_called()


def test_cli_rejects_non_articulate_link(capsys):
    assert main(["https://example.com/not-a-course"]) == 2
    assert "Not an Articulate Rise share link" in capsys.readouterr().err


def test_cli_passes_options_through(tmp_path):
    with patch("aicc_demo.cli.export_course", return_value={"course_text_md": "a.md", "pdf": "a.pdf"}) as mock_export:
        assert main(["https://share.articulate.com/9enP3jMLBp-wenr5LIa0R", "-o", str(tmp_path),
                     "--interval", "5", "--max-frames", "0", "--text-only"]) == 0

    mock_export.assert_called_once_with(
        "https://share.articulate.com/9enP3jMLBp-wenr5LIa0R",
        output_dir=str(tmp_path),
        interval_seconds=5,
        max_frames_per_video=None,
        include_video=False,
        pdf_dir=DEFAULT_PDF_DIR,
    )


def test_default_pdf_dir_is_pdf_folder_in_project_root():
    from pathlib import Path

    assert Path(DEFAULT_PDF_DIR) == Path(__file__).resolve().parent.parent / "pdf"
