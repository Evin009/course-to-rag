from unittest.mock import patch

from aicc_demo.assembly import Chunk
from aicc_demo.images import ocr_image, process_image_entries


def _png(tmp_path):
    from PIL import Image

    path = tmp_path / "slide.png"
    Image.new("RGB", (20, 20), "white").save(path)
    return str(path)


def test_ocr_image_returns_stripped_text(tmp_path):
    with patch("aicc_demo.images.pytesseract.image_to_string", return_value="  Hello World  \n"):
        assert ocr_image(_png(tmp_path)) == "Hello World"


def test_ocr_image_returns_empty_string_when_no_text(tmp_path):
    with patch("aicc_demo.images.pytesseract.image_to_string", return_value="   \n"):
        assert ocr_image(_png(tmp_path)) == ""


def test_ocr_image_reads_last_frame_of_animated_gif(tmp_path):
    from PIL import Image

    path = tmp_path / "anim.gif"
    first, last = Image.new("RGB", (20, 20), "black"), Image.new("RGB", (20, 20), "white")
    first.save(path, save_all=True, append_images=[Image.new("RGB", (20, 20), "red"), last])
    seen = []

    with patch("aicc_demo.images.pytesseract.image_to_string", side_effect=lambda img: seen.append(img.getpixel((0, 0))) or "done"):
        assert ocr_image(str(path)) == "done"

    assert seen == [(255, 255, 255)]


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


def test_flatten_to_rgb_puts_transparent_pixels_on_white():
    from PIL import Image
    from aicc_demo.images import flatten_to_rgb

    rgba = Image.new("RGBA", (4, 4), (0, 0, 0, 0))  # fully transparent
    rgba.putpixel((1, 1), (0, 0, 0, 255))  # one black "line" pixel
    flat = flatten_to_rgb(rgba)
    assert flat.getpixel((0, 0)) == (255, 255, 255)
    assert flat.getpixel((1, 1)) == (0, 0, 0)

    palette = rgba.convert("P")
    palette.info["transparency"] = palette.getpixel((0, 0))
    assert flatten_to_rgb(palette).getpixel((0, 0)) == (255, 255, 255)
