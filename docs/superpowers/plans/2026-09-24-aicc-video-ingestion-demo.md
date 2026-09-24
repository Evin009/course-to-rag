# AICC Video Ingestion Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an end-to-end pipeline that converts the Articulate Rise "Suture Materials and Techniques" course into a structured, chunked text corpus with citations (lesson name + timestamp/image), queryable by an LLM — proving video content can reach AICC without sending raw video to an LLM.

**Architecture:** A single Python package with one module per pipeline stage (extract → audio → visual → assemble → retrieve), wired together by one orchestrator script. Each stage writes its output to disk as an intermediate artifact (JSON/Markdown/images) so stages can be tested and re-run independently. No database — retrieval is in-memory cosine similarity over `sentence-transformers` embeddings, matching the demo's explicit "no Postgres/pgvector yet" scope.

**Tech Stack:** Python 3.11+, `requests` (HTTP), `beautifulsoup4` (HTML stripping), `yt-dlp` (YouTube captions), `webvtt-py` (VTT parsing), `sentence-transformers` (embeddings), `numpy` (cosine sim), `pytest` (tests). Visual/ASR pipeline (imagehash/OCR/Whisper) stubbed for Suture scope per Global Constraints below — Suture's only videos are YouTube embeds with captions, so ASR/keyframe code is written but not required for the demo's happy path and is tested in isolation.

**Spec:** `/Users/evinbento/Library/Mobile Documents/com~apple~CloudDocs/DEV-WORK/AICC-dmo/plan.md`

## Global Constraints

- Demo scope is the Suture course ONLY (`https://share.articulate.com/wFfts7vyFk1HxZneZqamI`, shareId `wFfts7vyFk1HxZneZqamI`). PCC and PrEP are explicitly out of scope for this plan.
- Course JSON comes from `POST https://share.articulate.com/api/instant-links/<shareId>/course`, no auth required.
- Suture videos are YouTube embeds (`media.embed.originalUrl`) — no Articulate-hosted video/ASR path needed for this demo, but the fallback code must exist and be tested since the manifest format must support it for PCC later.
- Caption fetch order per video: YouTube auto-captions via `yt-dlp --write-auto-sub --skip-download` first; ASR fallback only if none exist. For Suture, expect captions to exist.
- No vector DB. Retrieval is in-memory: embed with `sentence-transformers`, cosine similarity via `numpy`.
- Every chunk in the final assembled corpus must carry lesson name + timestamp (video) or image path (image block) for citation.
- Preserve original JSON block order through extraction → assembly.

---

## File Structure

```
AICC-dmo/
  pyproject.toml
  src/
    aicc_demo/
      __init__.py
      extractor.py        # fetch course JSON, recursive walk, HTML->Markdown, manifest
      audio.py             # yt-dlp caption fetch + ASR fallback stub
      visual.py            # keyframe extraction + dedupe + OCR/caption stub
      assembly.py          # merge lesson text + transcripts + captions into ordered chunks
      retrieval.py         # embed chunks, cosine similarity search
      pipeline.py          # orchestrator: runs all stages end to end
  tests/
    test_extractor.py
    test_audio.py
    test_visual.py
    test_assembly.py
    test_retrieval.py
  data/                    # gitignored — course JSON, transcripts, chunks land here at runtime
  demo.py                  # entry point: run pipeline on Suture course, print Q&A + cost comparison
```

---

### Task 1: Project scaffold + course JSON extractor

**Files:**
- Create: `pyproject.toml`
- Create: `src/aicc_demo/__init__.py`
- Create: `src/aicc_demo/extractor.py`
- Test: `tests/test_extractor.py`

**Interfaces:**
- Produces: `extractor.fetch_course_json(share_id: str) -> dict` — POSTs to the instant-links endpoint, returns parsed JSON.
- Produces: `extractor.SHARE_ID_SUTURE = "wFfts7vyFk1HxZneZqamI"` module constant.

- [ ] **Step 1: Write pyproject.toml**

```toml
[project]
name = "aicc-demo"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "requests>=2.31",
    "beautifulsoup4>=4.12",
    "yt-dlp>=2024.8.6",
    "webvtt-py>=0.4.6",
    "sentence-transformers>=3.0",
    "numpy>=1.26",
    "imagehash>=4.3",
    "pillow>=10.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "responses>=0.25"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create package init**

`src/aicc_demo/__init__.py`:
```python
```
(empty file — marks the package)

- [ ] **Step 3: Write the failing test for `fetch_course_json`**

`tests/test_extractor.py`:
```python
import responses
from aicc_demo.extractor import fetch_course_json, SHARE_ID_SUTURE

COURSE_ENDPOINT = f"https://share.articulate.com/api/instant-links/{SHARE_ID_SUTURE}/course"

@responses.activate
def test_fetch_course_json_posts_to_instant_links_endpoint():
    fake_course = {"course": {"lessons": [{"id": "l1", "title": "Intro", "items": []}]}}
    responses.add(responses.POST, COURSE_ENDPOINT, json=fake_course, status=200)

    result = fetch_course_json(SHARE_ID_SUTURE)

    assert result == fake_course
    assert responses.calls[0].request.url == COURSE_ENDPOINT
    assert responses.calls[0].request.method == "POST"


@responses.activate
def test_fetch_course_json_raises_on_http_error():
    responses.add(responses.POST, COURSE_ENDPOINT, status=500)

    import pytest
    from requests import HTTPError
    with pytest.raises(HTTPError):
        fetch_course_json(SHARE_ID_SUTURE)
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_extractor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'aicc_demo.extractor'` (or `ImportError`).

- [ ] **Step 5: Write minimal implementation**

`src/aicc_demo/extractor.py`:
```python
import requests

SHARE_ID_SUTURE = "wFfts7vyFk1HxZneZqamI"
INSTANT_LINKS_URL = "https://share.articulate.com/api/instant-links/{share_id}/course"


def fetch_course_json(share_id: str) -> dict:
    url = INSTANT_LINKS_URL.format(share_id=share_id)
    response = requests.post(url, timeout=30)
    response.raise_for_status()
    return response.json()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pip install -e ".[dev]" && pytest tests/test_extractor.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/aicc_demo/__init__.py src/aicc_demo/extractor.py tests/test_extractor.py
git commit -m "feat: fetch Suture course JSON from Articulate instant-links endpoint"
```

---

### Task 2: Recursive content walker → Markdown + media manifest

**Files:**
- Modify: `src/aicc_demo/extractor.py`
- Test: `tests/test_extractor.py`

**Interfaces:**
- Consumes: raw course dict from `fetch_course_json()` (Task 1) — shape `{"course": {"lessons": [...]}}`
- Produces: `extractor.walk_lesson(lesson: dict) -> tuple[str, list[dict]]` — returns `(markdown_text, media_manifest_entries)` for one lesson.
- Produces: `extractor.strip_html(html: str) -> str` — HTML → plain text.
- Produces: manifest entry shape (used by Task 3/4/5):
  ```python
  {
      "lesson_id": str,
      "lesson_title": str,
      "block_order": int,       # position within lesson, for reassembly ordering
      "type": "youtube" | "articulate_video" | "image",
      "url": str,                # YouTube watch URL, articulateusercontent URL, or image URL
      "captions_available": bool,  # only meaningful for video types
      "caption_key": str | None,   # media.video.captions[0].key if present, else None
  }
  ```

- [ ] **Step 1: Write the failing test for HTML stripping**

Append to `tests/test_extractor.py`:
```python
from aicc_demo.extractor import strip_html, walk_lesson

def test_strip_html_removes_tags_keeps_text():
    html = "<p>Hold the needle at a <strong>45-degree</strong> angle.</p>"
    assert strip_html(html) == "Hold the needle at a 45-degree angle."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_extractor.py::test_strip_html_removes_tags_keeps_text -v`
Expected: FAIL — `ImportError: cannot import name 'strip_html'`

- [ ] **Step 3: Write minimal `strip_html`**

Append to `src/aicc_demo/extractor.py`:
```python
from bs4 import BeautifulSoup


def strip_html(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text()
```

- [ ] **Step 4: Run test, verify pass**

Run: `pytest tests/test_extractor.py::test_strip_html_removes_tags_keeps_text -v`
Expected: PASS

- [ ] **Step 5: Write the failing test for `walk_lesson` — text block**

Append to `tests/test_extractor.py`:
```python
def test_walk_lesson_extracts_text_block_as_markdown():
    lesson = {
        "id": "lesson-1",
        "title": "Suturing Basics",
        "items": [
            {
                "type": "text",
                "items": [{"paragraph": "<p>Suturing closes wounds.</p>"}],
            }
        ],
    }

    markdown, manifest = walk_lesson(lesson)

    assert "## Suturing Basics" in markdown
    assert "Suturing closes wounds." in markdown
    assert manifest == []


def test_walk_lesson_extracts_youtube_video_into_manifest():
    lesson = {
        "id": "lesson-2",
        "title": "Knot Tying",
        "items": [
            {
                "type": "multimedia",
                "items": [
                    {
                        "media": {
                            "embed": {"originalUrl": "https://www.youtube.com/watch?v=abc123"}
                        }
                    }
                ],
            }
        ],
    }

    markdown, manifest = walk_lesson(lesson)

    assert len(manifest) == 1
    entry = manifest[0]
    assert entry["lesson_id"] == "lesson-2"
    assert entry["lesson_title"] == "Knot Tying"
    assert entry["type"] == "youtube"
    assert entry["url"] == "https://www.youtube.com/watch?v=abc123"
    assert entry["captions_available"] is False
    assert entry["block_order"] == 0


def test_walk_lesson_extracts_articulate_hosted_video_with_captions():
    lesson = {
        "id": "lesson-3",
        "title": "Wound Assessment",
        "items": [
            {
                "type": "multimedia",
                "items": [
                    {
                        "media": {
                            "video": {
                                "key": "abc%2520def.mp4",
                                "captions": [{"key": "abc%2520def.vtt"}],
                            }
                        }
                    }
                ],
            }
        ],
    }

    markdown, manifest = walk_lesson(lesson)

    entry = manifest[0]
    assert entry["type"] == "articulate_video"
    assert entry["url"] == "https://articulateusercontent.com/abc%20def.mp4"
    assert entry["captions_available"] is True
    assert entry["caption_key"] == "abc%20def.vtt"


def test_walk_lesson_recurses_into_nested_items():
    lesson = {
        "id": "lesson-4",
        "title": "Flashcards",
        "items": [
            {
                "type": "flashcard",
                "items": [
                    {
                        "items": [
                            {"description": "<p>Nested text block.</p>"}
                        ]
                    }
                ],
            }
        ],
    }

    markdown, manifest = walk_lesson(lesson)

    assert "Nested text block." in markdown
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest tests/test_extractor.py -v`
Expected: FAIL on the 4 new `walk_lesson` tests (function returns nothing/doesn't exist yet).

- [ ] **Step 7: Write minimal `walk_lesson` implementation**

Append to `src/aicc_demo/extractor.py`:
```python
def _decode_key(key: str) -> str:
    return key.replace("%2520", "%20")


def _extract_text(item: dict) -> str | None:
    for field in ("heading", "paragraph", "description"):
        if field in item and item[field]:
            return strip_html(item[field])
    return None


def _extract_media_entry(item: dict, lesson_id: str, lesson_title: str, order: int) -> dict | None:
    media = item.get("media")
    if not media:
        return None

    if "embed" in media and media["embed"].get("originalUrl"):
        return {
            "lesson_id": lesson_id,
            "lesson_title": lesson_title,
            "block_order": order,
            "type": "youtube",
            "url": media["embed"]["originalUrl"],
            "captions_available": False,
            "caption_key": None,
        }

    if "video" in media:
        video = media["video"]
        captions = video.get("captions") or []
        caption_key = _decode_key(captions[0]["key"]) if captions else None
        return {
            "lesson_id": lesson_id,
            "lesson_title": lesson_title,
            "block_order": order,
            "type": "articulate_video",
            "url": f"https://articulateusercontent.com/{_decode_key(video['key'])}",
            "captions_available": bool(captions),
            "caption_key": caption_key,
        }

    if "image" in media:
        image = media["image"]
        return {
            "lesson_id": lesson_id,
            "lesson_title": lesson_title,
            "block_order": order,
            "type": "image",
            "url": f"https://articulateusercontent.com/{_decode_key(image['key'])}",
            "captions_available": False,
            "caption_key": None,
        }

    return None


def _walk_items(items: list[dict], lesson_id: str, lesson_title: str, order_counter: list[int]) -> tuple[list[str], list[dict]]:
    text_lines: list[str] = []
    manifest: list[dict] = []

    for item in items:
        text = _extract_text(item)
        if text:
            text_lines.append(text)

        media_entry = _extract_media_entry(item, lesson_id, lesson_title, order_counter[0])
        if media_entry:
            manifest.append(media_entry)
            order_counter[0] += 1

        nested = item.get("items")
        if nested:
            nested_text, nested_manifest = _walk_items(nested, lesson_id, lesson_title, order_counter)
            text_lines.extend(nested_text)
            manifest.extend(nested_manifest)

    return text_lines, manifest


def walk_lesson(lesson: dict) -> tuple[str, list[dict]]:
    lesson_id = lesson["id"]
    lesson_title = lesson["title"]
    order_counter = [0]

    text_lines, manifest = _walk_items(lesson.get("items", []), lesson_id, lesson_title, order_counter)

    markdown = f"## {lesson_title}\n\n" + "\n\n".join(text_lines)
    return markdown, manifest
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_extractor.py -v`
Expected: PASS (all tests)

- [ ] **Step 9: Commit**

```bash
git add src/aicc_demo/extractor.py tests/test_extractor.py
git commit -m "feat: recursively walk lesson items into Markdown + media manifest"
```

---

### Task 3: Audio pipeline — YouTube captions with ASR fallback stub

**Files:**
- Create: `src/aicc_demo/audio.py`
- Test: `tests/test_audio.py`

**Interfaces:**
- Consumes: manifest entries from Task 2 with `type == "youtube"` or `type == "articulate_video"`.
- Produces: `audio.get_transcript(manifest_entry: dict, output_dir: str) -> list[dict]` — returns list of `{"start": float, "end": float, "text": str}` caption segments.
- Produces: `audio.fetch_youtube_captions(url: str, output_dir: str) -> list[dict] | None` — returns segments or `None` if no captions exist.
- Produces: `audio.transcribe_with_asr(audio_path: str) -> list[dict]` — stub for Parakeet/faster-whisper; raises `NotImplementedError` for this demo (Suture has no path that needs it, but the seam must exist for PCC later).

- [ ] **Step 1: Write the failing tests**

`tests/test_audio.py`:
```python
from unittest.mock import patch, MagicMock
import webvtt
from aicc_demo.audio import get_transcript, fetch_youtube_captions, transcribe_with_asr


VTT_CONTENT = """WEBVTT

00:00:00.000 --> 00:00:03.000
Hold the needle driver like this.

00:00:03.000 --> 00:00:06.000
Angle it at forty-five degrees.
"""


def test_fetch_youtube_captions_parses_vtt_when_ytdlp_writes_file(tmp_path):
    vtt_path = tmp_path / "video.en.vtt"
    vtt_path.write_text(VTT_CONTENT)

    with patch("aicc_demo.audio.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with patch("aicc_demo.audio._find_vtt_file", return_value=str(vtt_path)):
            segments = fetch_youtube_captions("https://www.youtube.com/watch?v=abc123", str(tmp_path))

    assert segments == [
        {"start": 0.0, "end": 3.0, "text": "Hold the needle driver like this."},
        {"start": 3.0, "end": 6.0, "text": "Angle it at forty-five degrees."},
    ]


def test_fetch_youtube_captions_returns_none_when_no_vtt_produced(tmp_path):
    with patch("aicc_demo.audio.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with patch("aicc_demo.audio._find_vtt_file", return_value=None):
            result = fetch_youtube_captions("https://www.youtube.com/watch?v=nocaption", str(tmp_path))

    assert result is None


def test_transcribe_with_asr_not_implemented_for_demo_scope():
    import pytest
    with pytest.raises(NotImplementedError):
        transcribe_with_asr("/tmp/some_video.mp4")


def test_get_transcript_uses_youtube_captions_for_youtube_entries(tmp_path):
    entry = {"type": "youtube", "url": "https://www.youtube.com/watch?v=abc123"}
    fake_segments = [{"start": 0.0, "end": 3.0, "text": "hi"}]

    with patch("aicc_demo.audio.fetch_youtube_captions", return_value=fake_segments) as mock_fetch:
        result = get_transcript(entry, str(tmp_path))

    mock_fetch.assert_called_once_with(entry["url"], str(tmp_path))
    assert result == fake_segments


def test_get_transcript_falls_back_to_asr_when_no_youtube_captions(tmp_path):
    entry = {"type": "youtube", "url": "https://www.youtube.com/watch?v=nocaption"}

    with patch("aicc_demo.audio.fetch_youtube_captions", return_value=None):
        with patch("aicc_demo.audio.transcribe_with_asr", side_effect=NotImplementedError):
            import pytest
            with pytest.raises(NotImplementedError):
                get_transcript(entry, str(tmp_path))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_audio.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aicc_demo.audio'`

- [ ] **Step 3: Write minimal implementation**

`src/aicc_demo/audio.py`:
```python
import glob
import os
import subprocess

import webvtt


def _find_vtt_file(output_dir: str) -> str | None:
    matches = glob.glob(os.path.join(output_dir, "*.vtt"))
    return matches[0] if matches else None


def _timestamp_to_seconds(ts: str) -> float:
    hours, minutes, seconds = ts.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def fetch_youtube_captions(url: str, output_dir: str) -> list[dict] | None:
    subprocess.run(
        [
            "yt-dlp",
            "--write-auto-sub",
            "--sub-lang", "en",
            "--skip-download",
            "-o", os.path.join(output_dir, "%(id)s.%(ext)s"),
            url,
        ],
        capture_output=True,
        check=False,
    )

    vtt_path = _find_vtt_file(output_dir)
    if not vtt_path:
        return None

    segments = []
    for caption in webvtt.read(vtt_path):
        segments.append({
            "start": _timestamp_to_seconds(caption.start),
            "end": _timestamp_to_seconds(caption.end),
            "text": caption.text.strip(),
        })
    return segments


def transcribe_with_asr(audio_path: str) -> list[dict]:
    raise NotImplementedError(
        "ASR (Parakeet/faster-whisper) is out of scope for the Suture demo; "
        "required for PCC course's uncaptioned Articulate-hosted videos."
    )


def get_transcript(manifest_entry: dict, output_dir: str) -> list[dict]:
    if manifest_entry["type"] == "youtube":
        segments = fetch_youtube_captions(manifest_entry["url"], output_dir)
        if segments is not None:
            return segments
        return transcribe_with_asr(manifest_entry["url"])

    if manifest_entry["type"] == "articulate_video":
        if manifest_entry["captions_available"]:
            raise NotImplementedError("VTT download from articulateusercontent.com not needed for Suture scope")
        return transcribe_with_asr(manifest_entry["url"])

    raise ValueError(f"Unsupported manifest entry type: {manifest_entry['type']}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pip install webvtt-py yt-dlp && pytest tests/test_audio.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/aicc_demo/audio.py tests/test_audio.py
git commit -m "feat: fetch YouTube captions via yt-dlp, stub ASR fallback for future PCC work"
```

---

### Task 4: Visual pipeline — keyframe extraction + dedupe (stub for demo, tested in isolation)

**Files:**
- Create: `src/aicc_demo/visual.py`
- Test: `tests/test_visual.py`

**Interfaces:**
- Produces: `visual.dedupe_frames(frame_paths: list[str], threshold: int = 5) -> list[str]` — returns subset of paths with near-duplicates removed, using `imagehash.average_hash` + Hamming distance.
- Produces: `visual.caption_frame(frame_path: str) -> str` — stub; raises `NotImplementedError` (vision-model captioning wired up in follow-on PCC work, not required since Suture's demo path uses YouTube captions only).

- [ ] **Step 1: Write the failing tests**

`tests/test_visual.py`:
```python
from PIL import Image
from aicc_demo.visual import dedupe_frames, caption_frame


def _make_solid_image(path, color):
    img = Image.new("RGB", (64, 64), color=color)
    img.save(path)


def test_dedupe_frames_keeps_one_of_near_identical_images(tmp_path):
    path_a = tmp_path / "frame_a.png"
    path_b = tmp_path / "frame_b.png"
    _make_solid_image(path_a, (255, 0, 0))
    _make_solid_image(path_b, (255, 0, 0))

    result = dedupe_frames([str(path_a), str(path_b)])

    assert len(result) == 1


def test_dedupe_frames_keeps_both_of_different_images(tmp_path):
    path_a = tmp_path / "frame_a.png"
    path_b = tmp_path / "frame_b.png"
    _make_solid_image(path_a, (255, 0, 0))
    _make_solid_image(path_b, (0, 0, 255))

    result = dedupe_frames([str(path_a), str(path_b)])

    assert len(result) == 2


def test_caption_frame_not_implemented_for_demo_scope():
    import pytest
    with pytest.raises(NotImplementedError):
        caption_frame("/tmp/some_frame.png")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_visual.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aicc_demo.visual'`

- [ ] **Step 3: Write minimal implementation**

`src/aicc_demo/visual.py`:
```python
import imagehash
from PIL import Image


def dedupe_frames(frame_paths: list[str], threshold: int = 5) -> list[str]:
    kept: list[str] = []
    kept_hashes: list[imagehash.ImageHash] = []

    for path in frame_paths:
        current_hash = imagehash.average_hash(Image.open(path))
        if any(current_hash - kept_hash <= threshold for kept_hash in kept_hashes):
            continue
        kept.append(path)
        kept_hashes.append(current_hash)

    return kept


def caption_frame(frame_path: str) -> str:
    raise NotImplementedError(
        "Vision-model frame captioning (Gemini Flash / Qwen2.5-VL) is out of scope "
        "for the Suture demo; required for PCC's Articulate-hosted uncaptioned videos."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pip install imagehash pillow && pytest tests/test_visual.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/aicc_demo/visual.py tests/test_visual.py
git commit -m "feat: keyframe dedup via perceptual hashing, stub vision captioning for PCC"
```

---

### Task 5: Assembly — merge lesson text + transcripts into ordered, citable chunks

**Files:**
- Create: `src/aicc_demo/assembly.py`
- Test: `tests/test_assembly.py`

**Interfaces:**
- Consumes: `(markdown, manifest)` per lesson from Task 2, transcript segments from Task 3 (`get_transcript` return shape: `list[{"start": float, "end": float, "text": str}]`).
- Produces: `assembly.Chunk` dataclass:
  ```python
  @dataclass
  class Chunk:
      lesson_title: str
      block_order: int
      text: str
      citation: str  # e.g. "Knot Tying @ 0:03" or "Wound Assessment (image)"
  ```
- Produces: `assembly.build_chunks(lesson_title: str, manifest_entries: list[dict], transcripts: dict[int, list[dict]]) -> list[Chunk]` — `transcripts` keyed by `block_order`, one transcript-segment-list per video manifest entry.
- Produces: `assembly.chunk_lesson_text(lesson_title: str, markdown: str, max_chars: int = 800) -> list[Chunk]` — splits lesson prose into citable chunks by paragraph, merging small paragraphs up to `max_chars`.

- [ ] **Step 1: Write the failing tests**

`tests/test_assembly.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_assembly.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aicc_demo.assembly'`

- [ ] **Step 3: Write minimal implementation**

`src/aicc_demo/assembly.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_assembly.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/aicc_demo/assembly.py tests/test_assembly.py
git commit -m "feat: assemble ordered, citable chunks from lesson text and transcripts"
```

---

### Task 6: Retrieval — embed chunks, cosine similarity search

**Files:**
- Create: `src/aicc_demo/retrieval.py`
- Test: `tests/test_retrieval.py`

**Interfaces:**
- Consumes: `list[Chunk]` from Task 5 (`.text` and `.citation` fields).
- Produces: `retrieval.Retriever` class:
  ```python
  class Retriever:
      def __init__(self, chunks: list[Chunk], model_name: str = "all-MiniLM-L6-v2"): ...
      def query(self, question: str, top_k: int = 3) -> list[tuple[Chunk, float]]: ...
  ```

- [ ] **Step 1: Write the failing tests**

`tests/test_retrieval.py`:
```python
import numpy as np
from unittest.mock import patch, MagicMock
from aicc_demo.assembly import Chunk
from aicc_demo.retrieval import Retriever


def _fake_encode(texts, **kwargs):
    vectors = []
    for text in texts:
        vec = np.zeros(3)
        if "needle" in text:
            vec[0] = 1.0
        if "suture" in text:
            vec[1] = 1.0
        if "wound" in text:
            vec[2] = 1.0
        vectors.append(vec)
    return np.array(vectors)


def test_query_returns_most_similar_chunk_first():
    chunks = [
        Chunk("Knot Tying", 0, "Hold the needle driver correctly.", "Knot Tying @ 0:00"),
        Chunk("Wound Care", 1, "Clean the wound thoroughly.", "Wound Care @ 0:10"),
    ]

    with patch("aicc_demo.retrieval.SentenceTransformer") as mock_st_cls:
        mock_model = MagicMock()
        mock_model.encode.side_effect = _fake_encode
        mock_st_cls.return_value = mock_model

        retriever = Retriever(chunks)
        results = retriever.query("how do I hold the needle")

    assert results[0][0].citation == "Knot Tying @ 0:00"
    assert results[0][1] > results[1][1]


def test_query_respects_top_k():
    chunks = [
        Chunk("A", 0, "needle text", "A @ 0:00"),
        Chunk("B", 1, "suture text", "B @ 0:00"),
        Chunk("C", 2, "wound text", "C @ 0:00"),
    ]

    with patch("aicc_demo.retrieval.SentenceTransformer") as mock_st_cls:
        mock_model = MagicMock()
        mock_model.encode.side_effect = _fake_encode
        mock_st_cls.return_value = mock_model

        retriever = Retriever(chunks)
        results = retriever.query("needle", top_k=2)

    assert len(results) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_retrieval.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aicc_demo.retrieval'`

- [ ] **Step 3: Write minimal implementation**

`src/aicc_demo/retrieval.py`:
```python
import numpy as np
from sentence_transformers import SentenceTransformer

from aicc_demo.assembly import Chunk


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


class Retriever:
    def __init__(self, chunks: list[Chunk], model_name: str = "all-MiniLM-L6-v2"):
        self.chunks = chunks
        self.model = SentenceTransformer(model_name)
        self.embeddings = self.model.encode([c.text for c in chunks])

    def query(self, question: str, top_k: int = 3) -> list[tuple[Chunk, float]]:
        query_vec = self.model.encode([question])[0]
        scored = [
            (chunk, _cosine_similarity(query_vec, emb))
            for chunk, emb in zip(self.chunks, self.embeddings)
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pip install sentence-transformers numpy && pytest tests/test_retrieval.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/aicc_demo/retrieval.py tests/test_retrieval.py
git commit -m "feat: in-memory cosine-similarity retrieval over chunk embeddings"
```

---

### Task 7: Orchestrator + demo script — end to end, cost comparison, sample Q&A

**Files:**
- Create: `src/aicc_demo/pipeline.py`
- Create: `demo.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: all prior modules (`extractor`, `audio`, `assembly`, `retrieval`).
- Produces: `pipeline.run_pipeline(share_id: str, output_dir: str) -> list[Chunk]` — runs extract → audio → assembly for every lesson, returns flat chunk list.
- Produces: `pipeline.estimate_raw_video_tokens(duration_seconds: float, tokens_per_second: float = 263.0) -> int`.
- Produces: `pipeline.estimate_chunk_tokens(chunks: list[Chunk], chars_per_token: float = 4.0) -> int`.

- [ ] **Step 1: Write the failing tests**

`tests/test_pipeline.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aicc_demo.pipeline'`

- [ ] **Step 3: Write minimal implementation**

`src/aicc_demo/pipeline.py`:
```python
import os

from aicc_demo.extractor import fetch_course_json, walk_lesson
from aicc_demo.audio import get_transcript
from aicc_demo.assembly import Chunk, build_chunks, chunk_lesson_text


def estimate_raw_video_tokens(duration_seconds: float, tokens_per_second: float = 263.0) -> int:
    return int(duration_seconds * tokens_per_second)


def estimate_chunk_tokens(chunks: list[Chunk], chars_per_token: float = 4.0) -> int:
    total_chars = sum(len(c.text) for c in chunks)
    return int(total_chars / chars_per_token)


def run_pipeline(share_id: str, output_dir: str) -> list[Chunk]:
    os.makedirs(output_dir, exist_ok=True)
    course = fetch_course_json(share_id)
    lessons = course["course"]["lessons"]

    all_chunks: list[Chunk] = []

    for lesson in lessons:
        markdown, manifest = walk_lesson(lesson)
        all_chunks.extend(chunk_lesson_text(lesson["title"], markdown))

        video_entries = [e for e in manifest if e["type"] in ("youtube", "articulate_video")]
        transcripts = {}
        for entry in video_entries:
            try:
                transcripts[entry["block_order"]] = get_transcript(entry, output_dir)
            except NotImplementedError:
                continue
        all_chunks.extend(build_chunks(lesson["title"], manifest, transcripts))

    return all_chunks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Write the demo entry point**

`demo.py`:
```python
from aicc_demo.extractor import SHARE_ID_SUTURE
from aicc_demo.pipeline import run_pipeline, estimate_raw_video_tokens, estimate_chunk_tokens
from aicc_demo.retrieval import Retriever

OUTPUT_DIR = "data/suture"
SAMPLE_QUESTION = "How do I hold the needle driver when suturing?"
ESTIMATED_COURSE_VIDEO_SECONDS = 600  # placeholder until real durations are pulled from manifest


def main():
    print(f"Extracting Suture course (share id: {SHARE_ID_SUTURE})...")
    chunks = run_pipeline(SHARE_ID_SUTURE, OUTPUT_DIR)
    print(f"Produced {len(chunks)} citable chunks.")

    raw_tokens = estimate_raw_video_tokens(ESTIMATED_COURSE_VIDEO_SECONDS)
    chunk_tokens = estimate_chunk_tokens(chunks)
    print(f"Estimated raw-video token cost: {raw_tokens:,}")
    print(f"Actual pipeline token cost:      {chunk_tokens:,}")
    print(f"Reduction: {(1 - chunk_tokens / raw_tokens) * 100:.1f}%")

    retriever = Retriever(chunks)
    results = retriever.query(SAMPLE_QUESTION, top_k=1)
    top_chunk, score = results[0]
    print(f"\nQ: {SAMPLE_QUESTION}")
    print(f"A: {top_chunk.text}")
    print(f"Citation: {top_chunk.citation} (score: {score:.3f})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the demo end to end**

Run: `python demo.py`
Expected: prints extraction count, token cost comparison, and one sample Q&A with citation. (First real run against the live endpoint — confirms Task 1's endpoint assumption still holds.)

- [ ] **Step 7: Commit**

```bash
git add src/aicc_demo/pipeline.py demo.py tests/test_pipeline.py
git commit -m "feat: orchestrate full pipeline, add demo script with cost comparison and sample Q&A"
```

---

## Self-Review Notes

- **Spec coverage:** Step 1 (extractor) → Task 1–2. Step 2 (audio) → Task 3. Step 3 (visual) → Task 4 (stubbed per Global Constraints — Suture has no Articulate-hosted/uncaptioned video, so it's tested in isolation but not wired into `pipeline.py`; wiring it in is PCC follow-on work). Step 4 (image blocks) → covered by `_extract_media_entry`'s `"image"` branch in Task 2; OCR/caption of those images is the same `caption_frame` stub as Task 4, deferred for the same reason. Step 5 (assembly) → Task 5. Step 6 (retrieval) → Task 6. Step 7 (demo package) → Task 7.
- **Known gap carried forward:** `demo.py`'s `ESTIMATED_COURSE_VIDEO_SECONDS` is a placeholder until real per-video durations are available from `yt-dlp`'s metadata — call out during Task 7 review whether to pull real duration via `yt-dlp --dump-json` before the actual demo presentation.
- **Type consistency check:** `Chunk` fields (`lesson_title`, `block_order`, `text`, `citation`) are used identically across Tasks 5, 6, 7. Manifest entry keys (`lesson_id`, `lesson_title`, `block_order`, `type`, `url`, `captions_available`, `caption_key`) defined in Task 2 are consumed unchanged in Tasks 3, 5, 7.
