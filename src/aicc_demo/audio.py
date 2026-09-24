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
