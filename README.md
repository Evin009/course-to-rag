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

## Running the demo

```bash
python demo.py
```

This fetches the live Suture course, transcribes its videos, builds citable
chunks, prints a token-cost comparison (raw video vs. pipeline output) with a
transcription-coverage caveat, and answers a sample question with a citation.
