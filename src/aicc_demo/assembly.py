from dataclasses import dataclass


@dataclass
class Chunk:
    lesson_title: str
    block_order: int
    text: str
    citation: str


def _format_timestamp(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def chunk_lesson_text(lesson_title: str, markdown: str, max_chars: int = 800) -> list[Chunk]:
    body = markdown.split("\n\n", 1)[1] if "\n\n" in markdown else ""
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]

    chunks: list[Chunk] = []
    buffer = ""
    order = 0

    for paragraph in paragraphs:
        candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        if len(candidate) > max_chars and buffer:
            chunks.append(Chunk(lesson_title, order, buffer, lesson_title))
            order += 1
            buffer = paragraph
        else:
            buffer = candidate

    if buffer:
        chunks.append(Chunk(lesson_title, order, buffer, lesson_title))

    return chunks


def build_chunks(lesson_title: str, manifest_entries: list[dict], transcripts: dict[int, list[dict]]) -> list[Chunk]:
    chunks: list[Chunk] = []

    for entry in manifest_entries:
        segments = transcripts.get(entry["block_order"])
        if not segments:
            continue
        for segment in segments:
            citation = f"{lesson_title} @ {_format_timestamp(segment['start'])}"
            chunks.append(Chunk(lesson_title, entry["block_order"], segment["text"], citation))

    return chunks
