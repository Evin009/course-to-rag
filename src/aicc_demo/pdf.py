"""Render an extracted course as one PDF that interleaves text, images and video content.

Videos become: a header, then each kept keyframe followed by the
transcript spoken from that frame until the next one. All text stays a
real text layer, so the AICC companion can parse it, and every block
keeps its lesson/timestamp for citations.
"""
import io
import re
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    CondPageBreak,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from PIL import Image as PILImage

from aicc_demo.assembly import _format_timestamp

# Caption-track noise such as "[Music]" or "[Applause]".
_SOUND_TAG_RE = re.compile(r"\[[^\]]{1,20}\]")

# Without keyframes, a transcript is split into paragraphs of about this
# many seconds so it stays readable and each paragraph has a timestamp.
_TRANSCRIPT_PARAGRAPH_SECONDS = 90

# Stock course photos arrive at up to ~4000px / 2 MB; 1200px is sharp at
# print size and keeps the PDF small enough for the companion to ingest.
MAX_EMBEDDED_IMAGE_PX = 1200

PAGE_WIDTH, PAGE_HEIGHT = LETTER
MARGIN = 2 * cm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

ACCENT = colors.HexColor("#1F4E79")
MUTED = colors.HexColor("#555555")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=base["BodyText"], fontSize=10.5, leading=14.5, spaceAfter=6)
    return {
        "cover_title": ParagraphStyle("cover_title", parent=base["Title"], fontSize=24, leading=30, textColor=ACCENT),
        "cover_meta": ParagraphStyle("cover_meta", parent=body, alignment=TA_CENTER, textColor=MUTED),
        "section": ParagraphStyle("section", parent=base["Heading1"], fontSize=18, textColor=ACCENT, spaceBefore=6),
        "title": ParagraphStyle("title", parent=base["Heading2"], fontSize=15, textColor=ACCENT, spaceBefore=4),
        "heading": ParagraphStyle("heading", parent=base["Heading3"], fontSize=12, spaceBefore=8, spaceAfter=3),
        "video": ParagraphStyle("video", parent=base["Heading3"], fontSize=12, textColor=ACCENT, spaceBefore=10),
        "body": body,
        "bullet": ParagraphStyle("bullet", parent=body, leftIndent=14, bulletIndent=4, spaceAfter=3),
        "caption": ParagraphStyle("caption", parent=body, fontSize=9, leading=12, textColor=MUTED, alignment=TA_CENTER),
        "meta": ParagraphStyle("meta", parent=body, fontSize=9, leading=12, textColor=MUTED),
        "transcript": ParagraphStyle("transcript", parent=body, leftIndent=8, borderPadding=0),
    }


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


def _scaled_image(path: str, max_width: float, max_height: float) -> Image | None:
    """Fit an image into the box, re-encoding large originals so the PDF stays small."""
    try:
        with PILImage.open(path) as source:
            picture = source.convert("RGB")
    except Exception:
        return None
    picture.thumbnail((MAX_EMBEDDED_IMAGE_PX, MAX_EMBEDDED_IMAGE_PX))
    buffer = io.BytesIO()
    picture.save(buffer, format="JPEG", quality=82)
    buffer.seek(0)
    width, height = picture.size
    scale = min(max_width / width, max_height / height)
    return Image(buffer, width=width * scale, height=height * scale)


def clean_transcript_text(segments: list[dict]) -> str:
    text = " ".join(s["text"] for s in segments)
    return " ".join(_SOUND_TAG_RE.sub(" ", text).split())


def interleave_transcript(transcript: list[dict], keyframes: list[dict]) -> list[dict]:
    """Group transcript segments under the keyframe they were spoken after.

    Returns ordered parts: {"frame": keyframe | None, "start": s, "end": s, "text": str}.
    Speech before the first keyframe gets a part with no frame. Without
    keyframes, the transcript is split into fixed-length paragraphs.
    """
    if not keyframes:
        parts: list[dict] = []
        for segment in transcript:
            if not parts or segment["start"] - parts[-1]["start"] >= _TRANSCRIPT_PARAGRAPH_SECONDS:
                parts.append({"frame": None, "start": segment["start"], "end": segment["end"], "segments": []})
            parts[-1]["segments"].append(segment)
            parts[-1]["end"] = segment["end"]
    else:
        frames = sorted(keyframes, key=lambda k: k["seconds"])
        parts = [{"frame": None, "start": 0, "end": frames[0]["seconds"], "segments": []}]
        for i, frame in enumerate(frames):
            end = frames[i + 1]["seconds"] if i + 1 < len(frames) else None
            parts.append({"frame": frame, "start": frame["seconds"], "end": end, "segments": []})
        for segment in transcript:
            # Attribute each segment to the last part that started at or before it.
            owner = parts[0]
            for part in parts[1:]:
                if part["start"] <= segment["start"]:
                    owner = part
            owner["segments"].append(segment)
        if transcript:
            parts[-1]["end"] = max(parts[-1]["end"] or 0, transcript[-1]["end"])

    result = []
    for part in parts:
        text = clean_transcript_text(part.pop("segments"))
        if text or part["frame"] is not None:
            result.append({**part, "text": text})
    return result


def _video_flowables(block: dict, lesson_title: str, s: dict) -> list:
    out = [CondPageBreak(6 * cm), _p(f"Video: {block['title']}", s["video"])]
    out.append(_p(f"Lesson: {lesson_title} | Source: {block['media']['url']}", s["meta"]))
    if "transcript" not in block and "keyframes" not in block:
        out.append(_p("(Video content not processed in this run.)", s["meta"]))
        return out
    transcript = block.get("transcript") or []
    keyframes = block.get("keyframes") or []
    if not transcript and not keyframes:
        out.append(_p("(No transcript or frames could be extracted for this video.)", s["meta"]))
        return out

    for part in interleave_transcript(transcript, keyframes):
        frame = part["frame"]
        if frame is not None:
            group = []
            image = _scaled_image(frame["path"], CONTENT_WIDTH * 0.62, 8 * cm)
            if image is not None:
                group.append(image)
            group.append(_p(f"Video frame at {_format_timestamp(frame['seconds'])}", s["caption"]))
            if frame.get("ocr"):
                group.append(_p(f"On-screen text: {frame['ocr']}", s["caption"]))
            out.append(Spacer(1, 4))
            out.append(KeepTogether(group))
        if part["text"]:
            span = _format_timestamp(part["start"])
            if part["end"] is not None:
                span += f"–{_format_timestamp(part['end'])}"
            out.append(Paragraph(f"<b>Transcript {span}:</b> {escape(part['text'])}", s["transcript"]))
    return out


def course_flowables(course: dict) -> list:
    s = _styles()
    out: list = [
        Spacer(1, 5 * cm),
        _p(course["title"], s["cover_title"]),
        Spacer(1, 0.6 * cm),
    ]
    if course.get("source_url"):
        out.append(_p(f"Source: {course['source_url']}", s["cover_meta"]))
    out.append(_p(f"Extracted {date.today().isoformat()} for the AI Course Companion", s["cover_meta"]))
    if course.get("description"):
        out += [Spacer(1, 1 * cm), _p(course["description"], s["body"])]
    lesson_titles = [l["title"] for l in course["lessons"] if l["label"] == "title"]
    if lesson_titles:
        out += [Spacer(1, 0.6 * cm), _p("Lessons", s["heading"])]
        out += [Paragraph(escape(t), s["bullet"], bulletText="•") for t in lesson_titles]
    out.append(PageBreak())

    for lesson in course["lessons"]:
        if lesson["label"] == "section":
            out += [CondPageBreak(8 * cm), _p(lesson["title"], s["section"])]
            continue
        out += [CondPageBreak(6 * cm), _p(lesson["title"], s["title"])]
        for block in lesson["blocks"]:
            label = block["label"]
            if label == "heading":
                out.append(_p(block["text"], s["heading"]))
            elif label == "paragraph":
                out.append(_p(block["text"], s["body"]))
            elif label == "list_item":
                out.append(Paragraph(escape(block["text"]), s["bullet"], bulletText="•"))
            elif label == "image" and block.get("path"):
                image = _scaled_image(block["path"], CONTENT_WIDTH, 9 * cm)
                if image is not None:
                    group = [Spacer(1, 4), image]
                    if block.get("ocr"):
                        group.append(_p(f"Text in image: {block['ocr']}", s["caption"]))
                    out.append(KeepTogether(group))
            elif label == "video":
                out += _video_flowables(block, lesson["title"], s)
    return out


def render_course_pdf(course: dict, pdf_path: str) -> str:
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 1.2 * cm, course["title"][:90])
        canvas.drawRightString(PAGE_WIDTH - MARGIN, 1.2 * cm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=LETTER,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=course["title"],
        author="AICC course extractor",
        subject=course.get("source_url") or "",
    )
    doc.build(course_flowables(course), onFirstPage=footer, onLaterPages=footer)
    return pdf_path
