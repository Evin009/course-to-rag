# AICC Multimedia Ingestion — Handoff Plan

## Project Context

Evin Bento (USF CS junior) is building a research prototype for AICC (AI Course
Companion). The original task: AICC can only ingest text/PDF, not video. The
team's ask was to figure out how to convert course video into a text-like
artifact an LLM could consume, without sending raw video to an LLM directly
(too expensive, no chunking/retrieval/citations).

Three course materials were shared by the professor as reference:

1. **PrEP** — `https://decade.it.usf.edu/nursing/PrEP/story.html`
   Articulate **Storyline** package (not Rise). Has a downloadable transcript
   already provided in its resource section.
2. **Suture Materials and Techniques** —
   `https://share.articulate.com/wFfts7vyFk1HxZneZqamI`
   Articulate **Rise** course.
3. **PCC Simulation Resource** —
   `https://share.articulate.com/9enP3jMLBp-wenr5LIa0R`
   Articulate **Rise** course, clinical skills simulations.

## Key Finding: These Are Not Videos

All three are interactive e-learning modules, not raw video files. The
original plan (crawl the page, click through every interactive element,
screenshot/process video) is unnecessary for known formats. Both Rise courses
load their **entire content as one JSON payload** on page open — clicking
through lessons reveals already-loaded data, it does not trigger new network
requests. This was confirmed in Chrome DevTools (Network tab, Fetch/XHR
filter) on both Rise URLs.

**Confirmed working access, no auth required:**
```
POST https://share.articulate.com/api/instant-links/<shareId>/course
```
Returns the full course JSON: all lessons, all text blocks, all media
references (video URLs, image URLs, captions).

The `articulate-parser` open-source tool (github.com/kjanat/articulate-parser)
was initially considered but targets a different, older endpoint
(`rise.articulate.com/api/rise-runtime/boot/share/<id>`). Since we can hit the
`share.articulate.com` endpoint directly and already understand its JSON
shape, we do not need that tool — a small custom script is simpler and more
maintainable than adapting it.

The web-crawler idea (LLM-guided clicking) is not dead, it's the fallback for
any future course material in a format we haven't reverse-engineered a data
endpoint for. It's not the primary approach anymore.

## JSON Structure (both Rise courses, same shape)

```
course.lessons[]                 — array of lessons (or "section" headers, no content)
  .items[]                       — content blocks, in reading order
    .type / .family              — "text", "list", "flashcard", "interactive",
                                    "multimedia", "image", "divider"
    .items[]                     — the actual content for that block
      heading / paragraph / description   — raw HTML text (strip tags to use)
      media.embed.originalUrl             — YouTube URL (if video is a YT embed)
      media.video.key / .url              — Articulate-hosted video (if not YouTube)
      media.video.captions[]              — bundled VTT captions (if present)
      media.image.key / .src              — image reference
```

Blocks nest (e.g. flashcards, `interactive-fullscreen` process steps), so the
walk must be recursive.

## Media Hosting — Two Different Patterns Found

**Suture course:** videos are YouTube embeds
(`media.embed.originalUrl` → `https://www.youtube.com/watch?v=...`).
No Articulate-hosted media files to fetch for video.

**PCC course:** videos are hosted directly by Articulate.
Confirmed working URL pattern (tested live, opens/downloads the video):
```
https://articulateusercontent.com/<key>
```
where `<key>` is the `media.video.key` field from the JSON. Same pattern
works for images and for VTT caption files referenced in `media.video.captions[].key`.

**Important encoding gotcha:** keys contain double-encoded characters, e.g.
`%2520` in the raw JSON. Decode this to `%20` before requesting the URL.

**Caption availability is mixed even within PCC:** some videos have
`media.video.captions` (e.g. AIDET, Medication Validation), most do not
(Standard Procedures, CVAD, Sterile Field, Tracheostomy, both Foley Catheter
videos, Wound Care, all IV/injection videos). Only the ones without captions
need full ASR.

## Per-Video Decision Logic

For every video block encountered during extraction:

1. Has `media.video.captions[]`? → download the VTT directly from
   `articulateusercontent.com/<key>`. Done, no ASR needed.
2. Is a YouTube embed (`media.embed.originalUrl`)? → run `yt-dlp` with
   `--write-auto-sub --skip-download` first to try to get YouTube's own
   captions. Only fall back to ASR if no captions exist on the YouTube side.
3. Is an Articulate-hosted video with no captions? → download the mp4 from
   `articulateusercontent.com/<key>`, run full ASR (NVIDIA Parakeet TDT 0.6B
   v3 preferred, faster-whisper as fallback).

**Keyframes run in parallel with the audio pipeline for every video**,
captioned or not — captions cover speech, not what's visually happening,
and this is nursing skills training where the visual demonstration often
matters more than narration.

- Screenshot every N seconds
- Deduplicate near-identical consecutive frames with perceptual hashing
  (`imagehash`)
- OCR surviving frames (on-screen text) or caption them with a vision model
  (diagrams/visuals with no text) — Gemini Flash or a local Qwen2.5-VL 7B
- Each surviving frame becomes its own chunk: timestamp + caption/OCR text +
  image path

**Clarification for the team:** none of this trains a custom model. Scene
detection, perceptual hashing, and captioning models are all off-the-shelf,
zero training data required. An earlier team member's estimate of "a couple
semesters to train" appears to be based on hearing "ML" and assuming a custom
model was needed — that's not the plan.

## Verified So Far (do not re-test)

- `POST share.articulate.com/api/instant-links/<id>/course` works with no
  auth, returns full course JSON — tested on both Rise share links.
- `articulateusercontent.com/<key>` serves video files directly with no auth
  — tested live on a PCC course video, confirmed it opens/plays.
- The double-encoding (`%2520` → `%20`) needs handling before requests.

## Not Yet Tested / Open Items

- Whether the same `articulateusercontent.com/<key>` pattern works for VTT
  caption files and images (should, same key structure, but not explicitly
  confirmed with a live request yet).
- PrEP (Storyline) has not been put through the DevTools check. Likely lower
  priority since a transcript is already provided for it, but its slide
  images/diagrams may still need OCR if the transcript doesn't cover on-slide
  visual content.
- Whether PrEP's Storyline package can be downloaded wholesale (its `html5`
  folder structure) for slide image extraction, or whether that's needed at
  all given the existing transcript.

## Demo Project Plan (build this)

**Goal:** prove the pipeline end to end on the Suture Materials course.
Output a clean structured document, feed it to an LLM, show it can answer
questions with citations back to source lesson/video/timestamp.

**Scope:** Suture course only for the first working demo (richer structured
text, YouTube-hosted video, simplest media path). PCC and PrEP are follow-on
work once this is proven, since PCC exercises the ASR + Articulate-hosted-
video path that Suture doesn't need.

### Step 1 — Extractor
- POST to the share endpoint for the Suture course, save the JSON
- Recursively walk `lessons[].items[]`
- Strip HTML from text fields into clean Markdown, one file/section per lesson
- Collect every video/image reference into a manifest (url, type, caption
  availability, block position/order)

### Step 2 — Audio pipeline (per video in the manifest)
- Try YouTube auto-captions via `yt-dlp` first
- Fall back to ASR (Parakeet, or faster-whisper) only if none exist
- Output: transcript with timestamps

### Step 3 — Visual pipeline (per video, runs alongside Step 2)
- Screenshot every N seconds (start with N=3, tune later)
- Deduplicate with `imagehash` perceptual hashing
- OCR (PaddleOCR, Tesseract fallback) or caption (vision model) surviving
  frames
- Output: timestamp + caption/OCR + image path per frame

### Step 4 — Image blocks (non-video images referenced directly in JSON)
- Download via `articulateusercontent.com/<key>` (decode `%2520` → `%20`)
- OCR/caption same as Step 3

### Step 5 — Assembly
- Merge lesson text + inline video transcripts + inline keyframe captions +
  inline image captions into one structured document per lesson, preserving
  original block order
- Chunk by topic/section; each chunk keeps its timestamp/image_path metadata

### Step 6 — Retrieval + LLM
- Embed chunks with `sentence-transformers`
- Store in-memory (list + cosine similarity) for the demo — no need for
  Postgres/pgvector infra yet
- Take a test question, retrieve top chunks, pass to an LLM, produce an
  answer with a citation back to lesson name + timestamp or image

### Step 7 — Demo package
- One script that runs the whole pipeline end to end given the Suture course
  share URL
- A before/after comparison: estimated raw-video token cost (~263 tokens/sec
  per Gemini's video billing) vs. actual chunk/token count the pipeline
  produced
- One sample Q&A demonstrating retrieval + citation

### Explicitly out of scope for this demo (but understood/planned)
- PCC course's uncaptioned Articulate-hosted videos (would exercise the ASR
  branch — do this once Suture demo works)
- PrEP Storyline visual extraction (transcript already covers most content)
- Production-grade vector storage (Postgres + pgvector is the intended
  target long-term, per the original design doc)

## Reference: Original Full Pipeline Design

A more detailed, general-purpose version of this pipeline (covering
unknown/future course formats, generic video ingestion, storage schema, and
full cost/architecture rationale) was written up earlier and published here:
https://claude.ai/artifact/46S7yraCcFLgdEJo9RPW82

That doc is the "why" and long-term architecture. This plan.md is the
concrete "what to build right now" for the working demo.
