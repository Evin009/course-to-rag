from aicc_demo.assembly import Chunk, build_chunks, chunk_lesson_text


def test_chunk_lesson_text_splits_by_paragraph_with_citation():
    markdown = "## Knot Tying\n\nFirst paragraph.\n\nSecond paragraph."

    chunks = chunk_lesson_text("Knot Tying", markdown)

    assert all(isinstance(c, Chunk) for c in chunks)
    assert chunks[0].text == "First paragraph."
    assert chunks[0].citation == "Knot Tying"
    assert chunks[1].text == "Second paragraph."


def test_chunk_lesson_text_merges_small_paragraphs_up_to_max_chars():
    markdown = "## Lesson\n\nShort one.\n\nShort two."

    chunks = chunk_lesson_text("Lesson", markdown, max_chars=100)

    assert len(chunks) == 1
    assert chunks[0].text == "Short one.\n\nShort two."


def test_build_chunks_creates_timestamped_chunk_per_transcript_segment():
    manifest_entries = [
        {"lesson_title": "Knot Tying", "block_order": 0, "type": "youtube", "url": "https://youtube.com/watch?v=x"},
    ]
    transcripts = {
        0: [
            {"start": 0.0, "end": 3.0, "text": "Hold the needle driver like this."},
            {"start": 3.0, "end": 6.0, "text": "Angle it at forty-five degrees."},
        ]
    }

    chunks = build_chunks("Knot Tying", manifest_entries, transcripts)

    assert len(chunks) == 2
    assert chunks[0].text == "Hold the needle driver like this."
    assert chunks[0].citation == "Knot Tying @ 0:00"
    assert chunks[1].citation == "Knot Tying @ 0:03"


def test_build_chunks_skips_entries_with_no_transcript():
    manifest_entries = [
        {"lesson_title": "Knot Tying", "block_order": 5, "type": "image", "url": "https://articulateusercontent.com/img.png"},
    ]

    chunks = build_chunks("Knot Tying", manifest_entries, transcripts={})

    assert chunks == []
