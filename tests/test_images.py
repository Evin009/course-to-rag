from unittest.mock import patch

from aicc_demo.assembly import Chunk
from aicc_demo.images import ocr_image, process_image_entries


def test_ocr_image_returns_stripped_text():
    with patch("aicc_demo.images.pytesseract.image_to_string", return_value="  Hello World  \n"):
        assert ocr_image("/fake/path.png") == "Hello World"


def test_ocr_image_returns_empty_string_when_no_text():
    with patch("aicc_demo.images.pytesseract.image_to_string", return_value="   \n"):
        assert ocr_image("/fake/path.png") == ""


def test_process_image_entries_creates_chunk_for_text_found(tmp_path):
    entries = [
        {
            "lesson_id": "l1",
            "lesson_title": "Intro",
            "block_order": 0,
            "type": "image",
            "url": "https://articulateusercontent.com/slide1.png",
            "captions_available": False,
            "caption_key": None,
        }
    ]

    with patch("aicc_demo.images._download_file_directly", return_value=str(tmp_path / "slide1.png")):
        with patch("aicc_demo.images.ocr_image", return_value="Suture technique steps"):
            chunks = process_image_entries(entries, str(tmp_path))

    assert len(chunks) == 1
    assert chunks[0] == Chunk(
        lesson_title="Intro",
        block_order=0,
        text="Suture technique steps",
        citation="Intro (image)",
    )


def test_process_image_entries_skips_when_ocr_finds_nothing(tmp_path):
    entries = [
        {
            "lesson_id": "l1",
            "lesson_title": "Intro",
            "block_order": 0,
            "type": "image",
            "url": "https://articulateusercontent.com/slide1.png",
            "captions_available": False,
            "caption_key": None,
        }
    ]

    with patch("aicc_demo.images._download_file_directly", return_value=str(tmp_path / "slide1.png")):
        with patch("aicc_demo.images.ocr_image", return_value=""):
            chunks = process_image_entries(entries, str(tmp_path))

    assert chunks == []


def test_process_image_entries_skips_when_download_fails(tmp_path):
    entries = [
        {
            "lesson_id": "l1",
            "lesson_title": "Intro",
            "block_order": 0,
            "type": "image",
            "url": "https://articulateusercontent.com/slide1.png",
            "captions_available": False,
            "caption_key": None,
        }
    ]

    with patch("aicc_demo.images._download_file_directly", return_value=None):
        with patch("aicc_demo.images.ocr_image") as mock_ocr:
            chunks = process_image_entries(entries, str(tmp_path))

    mock_ocr.assert_not_called()
    assert chunks == []


def test_process_image_entries_ignores_non_image_entries(tmp_path):
    entries = [
        {
            "lesson_id": "l1",
            "lesson_title": "Intro",
            "block_order": 0,
            "type": "youtube",
            "url": "https://www.youtube.com/watch?v=abc123",
        }
    ]

    with patch("aicc_demo.images._download_file_directly") as mock_download:
        chunks = process_image_entries(entries, str(tmp_path))

    mock_download.assert_not_called()
    assert chunks == []
