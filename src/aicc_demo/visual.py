import glob
import os
import subprocess
import sys

import imagehash
from PIL import Image

from aicc_demo.assembly import Chunk, _format_timestamp
from aicc_demo.audio import _download_file_directly
from aicc_demo.images import ocr_image
from aicc_demo.utils import extract_youtube_id

# Deliberate demo-scope trade-off: one frame every 15s keeps frame count
# (and OCR time) manageable while still catching most on-screen text.
DEFAULT_FRAME_INTERVAL_SECONDS = 15


def dedupe_frames(frame_paths: list[str], threshold: int = 5) -> list[str]:
    """Drop near-duplicate frames using average-hash + Hamming distance.

    Note: average_hash compares each pixel to the image's own mean, so
    distinct solid-color/textureless frames (e.g. different title cards)
    can collide to an identical hash regardless of hue and get
    incorrectly deduplicated. Fine for frames with real visual content;
    a known blind spot for flat/solid-color frames.
    """
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


def _download_video(url: str, output_dir: str) -> str | None:
    video_id = extract_youtube_id(url)
    if video_id is None:
        # Not a YouTube URL: Articulate-hosted media is served from a direct
        # HTTPS file URL, so reuse the same direct-download helper audio.py
        # uses for Articulate videos (typically already an mp4).
        return _download_file_directly(url, output_dir)

    result = subprocess.run(
        [
            "yt-dlp", "-f", "best[height<=480]",
            "-o", os.path.join(output_dir, "%(id)s.%(ext)s"),
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    matches = glob.glob(os.path.join(output_dir, f"{video_id}*"))
    matches = [m for m in matches if not m.endswith(".vtt")]
    if not matches:
        if result.returncode != 0:
            stderr_tail = (result.stderr or "").strip()[-200:]
            print(
                f"WARNING: yt-dlp video download failed for {url} (exit {result.returncode}): {stderr_tail}",
                file=sys.stderr,
            )
        return None
    return matches[0]


def extract_frames(
    video_path: str, output_dir: str, interval_seconds: int = DEFAULT_FRAME_INTERVAL_SECONDS
) -> list[str]:
    result = subprocess.run(
        [
            "ffmpeg", "-i", video_path,
            "-vf", f"fps=1/{interval_seconds}",
            os.path.join(output_dir, "frame_%04d.png"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    frames = sorted(glob.glob(os.path.join(output_dir, "frame_*.png")))
    if not frames and result.returncode != 0:
        stderr_tail = (result.stderr or "").strip()[-200:]
        print(
            f"WARNING: ffmpeg frame extraction failed for {video_path} "
            f"(exit {result.returncode}): {stderr_tail}",
            file=sys.stderr,
        )
    return frames


def process_video_visuals(
    video_url: str,
    lesson_title: str,
    block_order: int,
    output_dir: str,
    interval_seconds: int = DEFAULT_FRAME_INTERVAL_SECONDS,
) -> list[Chunk]:
    video_path = _download_video(video_url, output_dir)
    if video_path is None:
        return []

    frames = extract_frames(video_path, output_dir, interval_seconds)
    surviving_frames = dedupe_frames(frames)

    chunks: list[Chunk] = []
    for frame_path in surviving_frames:
        ocr_text = ocr_image(frame_path)
        if not ocr_text:
            continue

        frame_index = frames.index(frame_path) if frame_path in frames else 0
        timestamp = _format_timestamp(frame_index * interval_seconds)
        chunks.append(
            Chunk(
                lesson_title=lesson_title,
                block_order=block_order,
                text=ocr_text,
                citation=f"{lesson_title} @ {timestamp} (frame)",
            )
        )

    return chunks
