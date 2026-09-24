import glob
import os
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


def fetch_youtube_captions(url: str, output_dir: str) -> list[dict] | None:
    video_id = _extract_youtube_id(url)

    # Reuse a VTT cached by an earlier run instead of re-invoking yt-dlp
    # for every video on every run (which gets the demo rate-limited).
    vtt_path = _find_vtt_file(output_dir, video_id)
    if vtt_path:
        return _parse_vtt(vtt_path)

    result = subprocess.run(
        [
            "yt-dlp",
            "--write-auto-sub",
            "--sub-lang", "en",
            "--skip-download",
            "-o", os.path.join(output_dir, "%(id)s.%(ext)s"),
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

    segments = []
    for caption in webvtt.read(vtt_path):
        segments.append({
            "start": _timestamp_to_seconds(caption.start),
            "end": _timestamp_to_seconds(caption.end),
            "text": caption.text.strip(),
        })
    return segments


def _download_audio(url: str, output_dir: str) -> str | None:
    video_id = extract_youtube_id(url)
    if video_id is None:
        return None

    result = subprocess.run(
        [
            "yt-dlp", "-x", "--audio-format", "mp3",
            "-o", os.path.join(output_dir, "%(id)s.%(ext)s"),
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
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"WARNING: direct download failed for {url}: {exc}", file=sys.stderr)
        return None

    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    return dest_path


def transcribe_with_asr(audio_path: str) -> list[dict]:
    model = WhisperModel(ASR_MODEL_SIZE, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_path)
    return [
        {"start": seg.start, "end": seg.end, "text": seg.text.strip()}
        for seg in segments
    ]


def get_transcript(manifest_entry: dict, output_dir: str) -> list[dict]:
    if manifest_entry["type"] == "youtube":
        segments = fetch_youtube_captions(manifest_entry["url"], output_dir)
        if segments is not None:
            return segments
        audio_path = _download_audio(manifest_entry["url"], output_dir)
        if audio_path is None:
            raise NotImplementedError(
                "ASR fallback failed: could not download audio for "
                f"{manifest_entry['url']}"
            )
        return transcribe_with_asr(audio_path)

    if manifest_entry["type"] == "articulate_video":
        if manifest_entry["captions_available"]:
            raise NotImplementedError("VTT download from articulateusercontent.com not needed for Suture scope")
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
