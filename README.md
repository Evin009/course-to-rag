# AICC Demo

A demonstration pipeline that ingests an Articulate Rise course (text, images,
and embedded/hosted video), transcribes its videos via YouTube captions
(falling back to ASR where out of scope), and chunks the result into small,
citable text passages for retrieval — showing that a well-structured text
pipeline costs far fewer LLM tokens than feeding raw video directly to a
model, while still answering course questions with an accurate citation back
to the source lesson and timestamp.

## Setup

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
