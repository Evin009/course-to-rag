# AICC Demo

A demonstration pipeline that ingests an Articulate Rise course (text, images,
and embedded/hosted video), transcribes its videos via YouTube captions
(falling back to ASR where out of scope), and chunks the result into small,
citable text passages for retrieval — showing that a well-structured text
pipeline costs far fewer LLM tokens than feeding raw video directly to a
model, while still answering course questions with an accurate citation back
to the source lesson and timestamp.

## Setup

### System dependencies

Beyond the Python packages, this project shells out to two binaries that must
be installed on the system:

- **ffmpeg** — used to extract keyframes from downloaded videos (and by
  `yt-dlp` to merge separate video/audio streams).
- **tesseract** — the actual OCR engine. The `pytesseract` pip package is only
  a wrapper; without the binary, OCR calls fail. Image/frame OCR failures are
  caught and logged, so the run degrades to "no text from that image" rather
  than crashing, but you lose all OCR-derived chunks.

On macOS: `brew install ffmpeg tesseract`.

### Environment variables

- **`GEMINI_API_KEY`** — used by the answer-generation step (Gemini). If it is
  missing or misconfigured, generation fails and the demo falls back to
  printing the top retrieved chunk's raw text. That is a legitimate
  degraded-but-working mode, not a hard requirement — the retrieval and
  citation parts of the demo still work without it.

### Python setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running the tests

```bash
pytest
```

(No manual `PYTHONPATH` export needed — `pyproject.toml`'s
`[tool.pytest.ini_options]` sets `pythonpath = ["src"]`.)

## Extracting a course to PDF

```bash
python extract.py https://share.articulate.com/<share-id>
```

Pass any Articulate Rise share link (`share.articulate.com/<id>`,
`rise.articulate.com/share/<id>#/...`, or a bare share id). Outputs go to
`data/<course-title>/` (override with `-o`), except the PDF:

- `course_text.json` / `course_text.md` — course text labeled
  `section` / `title` / `heading` / `paragraph` / `list_item`, plus `image` /
  `video` blocks, in reading order
- `course_package.json` — the same blocks plus transcripts, kept keyframes
  and OCR text
- `pdf/<course-title>.pdf` (in the project root, override with
  `--pdf-dir`) — text, images, video keyframes and the transcript spoken
  after each keyframe, interleaved in reading order, for the AI Course
  Companion

Options: `--interval N` seconds between sampled video frames (default 10),
`--max-frames N` frames per video in the PDF (default 15, `0` = no cap),
`--text-only` to skip video processing. Downloaded videos and captions are
cached in the output folder, so re-runs skip the downloads.

`python -m aicc_demo <link>` also works when `src/` is importable. (Inside
iCloud Drive the editable install can be skipped: iCloud marks the venv's
`.pth` files hidden and Python 3.13 ignores hidden `.pth` files, which is why
`extract.py` and `demo.py` add `src/` to the path themselves.)

### Frame sampling experiment

```bash
python scripts/frame_experiment.py data/<course-folder> --intervals 3 5 10 15
```

Re-extracts frames from already-downloaded videos at each interval and
reports frames kept after the blank and near-duplicate filters, disk size,
and how many kept frames carry OCR-readable text.

## Running the retrieval demo

```bash
python demo.py https://share.articulate.com/<share-id> ["question"] [-o data/<folder>]
```

Pass `-o` pointing at a folder from an earlier `extract.py` run to reuse its
downloaded videos and captions.

This fetches the course, transcribes its videos, builds citable chunks,
prints a token-cost comparison (raw video vs. pipeline output) with a
transcription-coverage caveat, and answers a question with a citation.
