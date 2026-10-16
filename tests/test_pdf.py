from PIL import Image

from aicc_demo.pdf import clean_transcript_text, interleave_transcript, render_course_pdf


def _seg(start, end, text):
    return {"start": start, "end": end, "text": text}


def test_clean_transcript_text_drops_sound_tags_and_extra_spaces():
    segments = [_seg(0, 1, "[Music]"), _seg(1, 2, "hold the  needle"), _seg(2, 3, "[Applause] firmly")]
    assert clean_transcript_text(segments) == "hold the needle firmly"


def test_interleave_transcript_puts_speech_after_the_frame_it_follows():
    transcript = [_seg(2, 5, "intro"), _seg(12, 15, "first step"), _seg(31, 34, "second step")]
    keyframes = [{"seconds": 10, "path": "a.jpg"}, {"seconds": 30, "path": "b.jpg"}]

    parts = interleave_transcript(transcript, keyframes)

    assert [(p["frame"] and p["frame"]["path"], p["start"], p["end"], p["text"]) for p in parts] == [
        (None, 0, 10, "intro"),
        ("a.jpg", 10, 30, "first step"),
        ("b.jpg", 30, 34, "second step"),
    ]


def test_interleave_transcript_keeps_frames_with_no_speech():
    parts = interleave_transcript([], [{"seconds": 0, "path": "a.jpg"}])
    assert len(parts) == 1 and parts[0]["frame"]["path"] == "a.jpg" and parts[0]["text"] == ""


def test_interleave_transcript_without_frames_splits_into_timed_paragraphs():
    transcript = [_seg(0, 5, "a"), _seg(60, 65, "b"), _seg(95, 99, "c")]

    parts = interleave_transcript(transcript, [])

    assert [(p["start"], p["text"]) for p in parts] == [(0, "a b"), (95, "c")]


def test_render_course_pdf_writes_pdf_with_text_images_and_video(tmp_path):
    image_path = tmp_path / "img.jpg"
    Image.new("RGB", (2000, 1000), color=(200, 30, 30)).save(image_path)
    frame_path = tmp_path / "frame_0001.jpg"
    Image.new("RGB", (640, 360), color=(30, 30, 200)).save(frame_path)
    course = {
        "title": "Suturing <Basics> & More",
        "source_url": "https://share.articulate.com/abc",
        "description": "Intro.",
        "lessons": [
            {"id": "s", "title": "Section", "label": "section", "blocks": []},
            {"id": "l", "title": "Needles", "label": "title", "blocks": [
                {"label": "heading", "text": "Parts"},
                {"label": "paragraph", "text": "Eye & body\nsecond line"},
                {"label": "list_item", "text": "Point"},
                {"label": "image", "media": {"url": "u"}, "path": str(image_path), "ocr": "Label"},
                {"label": "video", "title": "Demo", "media": {"url": "https://youtu.be/x"},
                 "transcript": [_seg(1, 4, "watch this")],
                 "keyframes": [{"seconds": 0, "path": str(frame_path), "ocr": "Step 1"}]},
                {"label": "video", "title": "Skipped", "media": {"url": "https://youtu.be/y"}},
                {"label": "video", "title": "Kaltura", "media": {"url": "kaltura:1:1_a", "page_url": "https://kaltura.example/p"},
                 "transcript": [_seg(0, 2, "big oh")], "keyframes": []},
                {"label": "attachment", "title": "FindMin.pdf", "media": {"url": "https://s/assets/FindMin.pdf"},
                 "text": "page one\n\npage two"},
                {"label": "attachment", "title": "Empty.pdf", "media": {"url": "https://s/assets/Empty.pdf"}, "text": ""},
                {"label": "link", "title": "Docs", "media": {"url": "https://docs.example/x"}},
            ]},
        ],
    }
    pdf_path = tmp_path / "out.pdf"

    render_course_pdf(course, str(pdf_path))

    data = pdf_path.read_bytes()
    assert data.startswith(b"%PDF")
    from pypdf import PdfReader
    text = " ".join(page.extract_text() for page in PdfReader(str(pdf_path)).pages)
    assert "Attachment: FindMin.pdf" in text and "page two" in text
    assert "https://kaltura.example/p" in text and "kaltura:1:1_a" not in text
    assert "Embedded content: Docs" in text
    # The 2000px source image is re-encoded at most 1200px wide, so the
    # whole PDF stays small.
    assert len(data) < 200_000
