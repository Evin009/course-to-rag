import glob
import os
import re
import subprocess
import sys

import requests
import webvtt
from faster_whisper import WhisperModel

from aicc_demo.utils import extract_youtube_id

# "base" is a deliberate accuracy/speed trade-off for CPU inference in a demo:
# "tiny" is noticeably less accurate, "large" is too slow without a GPU.
ASR_MODEL_SIZE = "base"


def _extract_youtube_id(url: str) -> str | None:
    return extract_youtube_id(url)


def _find_vtt_file(output_dir: str, video_id: str | None = None) -> str | None:
    if video_id is None:
        # Without a video id we can't safely scope the glob to the right
        # video, and an unqualified "*.vtt" fallback risks matching a
        # stale transcript left over from a different video. Treat a
        # missing id the same as "no transcript found" so the caller's
        # existing ASR-fallback/skip path handles it instead of guessing.
        return None
    matches = glob.glob(os.path.join(output_dir, f"{video_id}*.vtt"))
    return matches[0] if matches else None


def _timestamp_to_seconds(ts: str) -> float:
    hours, minutes, seconds = ts.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def fetch_youtube_captions(url: str, output_dir: str, key: str | None = None) -> list[dict] | None:
    """Fetch English captions with yt-dlp: YouTube, Kaltura or any site it supports.

    `key` names the cached files (`<key>.en.vtt`); it defaults to the
    YouTube id, and is required for non-YouTube URLs.
    """
    video_id = key or _extract_youtube_id(url)

    # Reuse a VTT cached by an earlier run instead of re-invoking yt-dlp
    # for every video on every run (which gets the demo rate-limited).
    vtt_path = _find_vtt_file(output_dir, video_id)
    if vtt_path:
        return _parse_vtt(vtt_path)

    result = subprocess.run(
        [
            "yt-dlp",
            # Uploaded captions first (Kaltura's are human-made), else
            # YouTube's auto-generated ones; always saved as VTT.
            "--write-subs",
            "--write-auto-sub",
            "--sub-lang", "en",
            "--sub-format", "vtt/best",
            "--convert-subs", "vtt",
            "--skip-download",
            "-o", os.path.join(output_dir, f"{video_id}.%(ext)s"),
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    vtt_path = _find_vtt_file(output_dir, video_id)
    if not vtt_path:
        if result.returncode != 0:
            stderr_tail = (result.stderr or "").strip()[-200:]
            print(
                f"WARNING: yt-dlp failed for {url} (exit {result.returncode}): {stderr_tail}",
                file=sys.stderr,
            )
        return None
    return _parse_vtt(vtt_path)


def _parse_vtt(vtt_path: str) -> list[dict]:
    """Parse a VTT file, dropping YouTube auto-caption "rolling" repeats.

    Auto-generated captions show two lines at a time and scroll: each cue
    repeats the previous cue's bottom line, plus a 10ms cue holding only
    that line. Taken literally every sentence appears 2-3 times, which
    inflates chunks, token counts and the PDF. Keep only lines the
    previous cue did not already show.
    """
    segments = []
    previous_lines: list[str] = []
    for caption in webvtt.read(vtt_path):
        lines = [line.strip() for line in caption.text.strip().split("\n") if line.strip()]
        new_lines = [line for line in lines if line not in previous_lines]
        previous_lines = lines
        if not new_lines:
            continue
        segments.append({
            "start": _timestamp_to_seconds(caption.start),
            "end": _timestamp_to_seconds(caption.end),
            "text": " ".join(new_lines),
        })
    return segments


def _download_audio(url: str, output_dir: str, key: str | None = None) -> str | None:
    video_id = key or extract_youtube_id(url)
    if video_id is None:
        return None
    cached = glob.glob(os.path.join(output_dir, f"{video_id}*.mp3"))
    if cached:
        return cached[0]

    result = subprocess.run(
        [
            "yt-dlp", "-x", "--audio-format", "mp3",
            "-o", os.path.join(output_dir, f"{video_id}.%(ext)s"),
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    matches = glob.glob(os.path.join(output_dir, f"{video_id}*.mp3"))
    if not matches:
        if result.returncode != 0:
            stderr_tail = (result.stderr or "").strip()[-200:]
            print(
                f"WARNING: yt-dlp audio extraction failed for {url} (exit {result.returncode}): {stderr_tail}",
                file=sys.stderr,
            )
        return None
    return matches[0]


def _download_file_directly(url: str, output_dir: str) -> str | None:
    filename = os.path.basename(url.split("?")[0])
    if not filename:
        return None
    dest_path = os.path.join(output_dir, filename)
    # Reuse an earlier download: Articulate-hosted videos are fetched by
    # both the transcript and the frame steps, and again on every re-run.
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        return dest_path
    os.makedirs(output_dir, exist_ok=True)
    partial_path = dest_path + ".part"
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        # Write to a temporary name so an interrupted download is never
        # mistaken for a complete cached file.
        with open(partial_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    except (requests.RequestException, OSError) as exc:
        print(f"WARNING: direct download failed for {url}: {exc}", file=sys.stderr)
        if os.path.exists(partial_path):
            os.remove(partial_path)
        return None
    os.replace(partial_path, dest_path)
    return dest_path


def fetch_articulate_captions(caption_url: str, output_dir: str) -> list[dict] | None:
    """Download and parse a VTT caption file bundled with an Articulate-hosted video."""
    vtt_path = os.path.join(output_dir, os.path.basename(caption_url.split("?")[0]))
    if not os.path.exists(vtt_path):
        vtt_path = _download_file_directly(caption_url, output_dir)
        if vtt_path is None:
            return None
    try:
        return _parse_vtt(vtt_path)
    except Exception as exc:
        print(f"WARNING: could not parse captions {vtt_path}: {exc}", file=sys.stderr)
        return None


# Whisper invents text for audio with no speech: on PCC's music-only
# procedure videos it returned "Music" 24 times, or a made-up "subscribe
# to our channel" line. Skip non-speech audio (VAD) and drop segments the
# model itself rates as probably not speech.
MAX_NO_SPEECH_PROB = 0.6
_NON_SPEECH_TEXT_RE = re.compile(r"^[\W_]*(?:music|applause|silence|laughter)?[\W_]*$", re.IGNORECASE)


def transcribe_with_asr(audio_path: str) -> list[dict]:
    model = WhisperModel(ASR_MODEL_SIZE, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_path, language="en", vad_filter=True)
    return [
        {"start": seg.start, "end": seg.end, "text": seg.text.strip()}
        for seg in segments
        if seg.no_speech_prob <= MAX_NO_SPEECH_PROB and not _NON_SPEECH_TEXT_RE.match(seg.text.strip())
    ]


# Embedded videos fetched through yt-dlp: captions first, then Whisper.
YTDLP_VIDEO_TYPES = ("youtube", "kaltura", "web_video")


def get_transcript(manifest_entry: dict, output_dir: str) -> list[dict]:
    if manifest_entry["type"] in YTDLP_VIDEO_TYPES:
        key = manifest_entry.get("media_key")
        segments = fetch_youtube_captions(manifest_entry["url"], output_dir, key)
        if segments is not None:
            return segments
        audio_path = _download_audio(manifest_entry["url"], output_dir, key)
        if audio_path is None:
            raise NotImplementedError(
                "ASR fallback failed: could not download audio for "
                f"{manifest_entry['url']}"
            )
        return transcribe_with_asr(audio_path)

    if manifest_entry["type"] == "articulate_video":
        if manifest_entry["captions_available"]:
            from aicc_demo.extractor import asset_url

            caption_url = manifest_entry.get("caption_url") or asset_url(manifest_entry["caption_key"])
            segments = fetch_articulate_captions(caption_url, output_dir)
            if segments:
                return segments
            # Caption file missing or empty: fall through to ASR.
        # Articulate-hosted media is served from a direct HTTPS file URL, not
        # a YouTube page, so yt-dlp's site-specific extraction doesn't apply;
        # fetch the raw file instead of going through _download_audio.
        audio_path = _download_file_directly(manifest_entry["url"], output_dir)
        if audio_path is None:
            raise NotImplementedError(
                "ASR fallback failed: could not download audio for "
                f"{manifest_entry['url']}"
            )
        return transcribe_with_asr(audio_path)

    raise ValueError(f"Unsupported manifest entry type: {manifest_entry['type']}")
