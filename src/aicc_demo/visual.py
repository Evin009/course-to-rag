import glob
import os
import re
import subprocess
import sys

import imagehash
from PIL import Image, ImageStat

from aicc_demo.assembly import Chunk, _format_timestamp
from aicc_demo.audio import _download_file_directly
from aicc_demo.images import ocr_image
from aicc_demo.utils import extract_youtube_id

# Measured on the Suture course's 9 videos (scripts/frame_experiment.py):
# sampling every 5s and dropping near-duplicates at Hamming distance 10
# keeps 300 distinct frames (12 with readable text) from 1,381 sampled;
# 10s keeps only 193 (5 with text), and 3s adds little over 5s.
DEFAULT_FRAME_INTERVAL_SECONDS = 5
DEFAULT_DUPLICATE_THRESHOLD = 10

# Frames are written as 640px-wide JPEGs: full-size PNGs cost ~400 KB
# each (≈1 GB per course at 3s), and neither OCR nor the PDF needs more.
FRAME_WIDTH = 640

# A frame whose grayscale pixels barely vary (black screen, fade, flat
# title card) carries nothing for OCR or the reader.
MIN_FRAME_STDDEV = 12.0

# Explicit allowlist of real video container extensions. yt-dlp's
# `bv*+ba/b` selector merges to .mp4 or .mkv (and .webm when a single
# progressive webm is served), so an allowlist keeps the lookup from
# picking up a same-prefix non-video file — notably the `{video_id}.mp3`
# that the ASR path writes into this SAME output_dir.
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}

_FRAME_NUMBER_RE = re.compile(r"frame_(\d+)\.(?:png|jpg)$")


def _find_video_file(output_dir: str, video_id: str) -> str | None:
    matches = [
        path
        for path in sorted(glob.glob(os.path.join(output_dir, f"{video_id}.*")))
        if os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS
    ]
    return matches[0] if matches else None


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


def is_low_information(frame_path: str, min_stddev: float = MIN_FRAME_STDDEV) -> bool:
    """True for near-uniform frames (black screens, fades, flat cards)."""
    with Image.open(frame_path) as image:
        return ImageStat.Stat(image.convert("L")).stddev[0] < min_stddev


def select_keyframes(frame_paths: list[str], threshold: int = DEFAULT_DUPLICATE_THRESHOLD) -> list[str]:
    """Keep frames worth showing: drop low-information frames, then near-duplicates."""
    informative = [path for path in frame_paths if not is_low_information(path)]
    return dedupe_frames(informative, threshold=threshold)


def frame_timestamp_seconds(frame_path: str, interval_seconds: int) -> int | None:
    """Seconds into the video for an ffmpeg `frame_%04d` file, or None if unnamed."""
    # ffmpeg numbers frames from 1, so the number in the filename IS the
    # chronological index. Parsing it back out avoids an O(n^2)
    # `frames.index()` lookup that would silently mint a false `@ 0:00`
    # citation on a miss.
    match = _FRAME_NUMBER_RE.search(os.path.basename(frame_path))
    if match is None:
        return None
    return (int(match.group(1)) - 1) * interval_seconds


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

    # Reuse an already-downloaded video: repeated demo runs otherwise
    # re-invoke yt-dlp for every video and get rate-limited by YouTube.
    cached = _find_video_file(output_dir, video_id)
    if cached is not None:
        return cached

    # YouTube no longer serves progressive/muxed streams at <=480p, so a
    # plain `best[height<=480]` matches nothing. Ask for the best video +
    # best audio and let yt-dlp merge, with progressive fallbacks.
    result = subprocess.run(
        [
            "yt-dlp", "-f", "bv*[height<=480]+ba/b[height<=480]/b",
            "-o", os.path.join(output_dir, "%(id)s.%(ext)s"),
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    match = _find_video_file(output_dir, video_id)
    if match is None:
        if result.returncode != 0:
            stderr_tail = (result.stderr or "").strip()[-200:]
            print(
                f"WARNING: yt-dlp video download failed for {url} (exit {result.returncode}): {stderr_tail}",
                file=sys.stderr,
            )
        return None
    return match


def video_frame_dir(output_dir: str, video_url: str, interval_seconds: int) -> str:
    """Per-video, per-interval frame directory.

    Keyed by interval too, so frames left over from a run at a different
    interval are never re-read and stamped with the wrong timestamps.
    """
    video_key = extract_youtube_id(video_url) or os.path.splitext(os.path.basename(video_url))[0]
    # Articulate file names carry `%2520`; ffmpeg reads `%` in an output
    # path as a frame-number pattern and writes one garbage file instead.
    video_key = re.sub(r"[^A-Za-z0-9_-]+", "_", video_key).strip("_") or "unknown"
    return os.path.join(output_dir, "frames", video_key, f"{interval_seconds}s")


def extract_frames(
    video_path: str, output_dir: str, interval_seconds: int = DEFAULT_FRAME_INTERVAL_SECONDS
) -> list[str]:
    """Extract one frame every `interval_seconds` into `output_dir`.

    `output_dir` MUST be per-video (see `process_video_visuals`): this
    globs every `frame_*.jpg` in the directory, so a shared directory
    would return a previous video's stale frames alongside this one's
    and mis-attribute them (wrong lesson, fabricated timestamp).
    """
    os.makedirs(output_dir, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"fps=1/{interval_seconds},scale={FRAME_WIDTH}:-2",
            "-q:v", "3",
            os.path.join(output_dir, "frame_%04d.jpg"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    frames = sorted(glob.glob(os.path.join(output_dir, "frame_*.jpg")))
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

    # Each video gets its own frame directory, so one video's frames can
    # never be picked up by another video's extraction glob (which would
    # attribute frame content to the wrong lesson at a fabricated time).
    frame_dir = video_frame_dir(output_dir, video_url, interval_seconds)
    frames = extract_frames(video_path, frame_dir, interval_seconds)
    surviving_frames = select_keyframes(frames)

    chunks: list[Chunk] = []
    for frame_path in surviving_frames:
        try:
            ocr_text = ocr_image(frame_path)
        except Exception as exc:
            print(
                f"WARNING: OCR failed for frame {frame_path}: {exc}",
                file=sys.stderr,
            )
            continue
        if not ocr_text:
            continue

        seconds = frame_timestamp_seconds(frame_path, interval_seconds)
        if seconds is None:
            print(
                f"WARNING: unexpected frame filename {frame_path}; skipping",
                file=sys.stderr,
            )
            continue
        timestamp = _format_timestamp(seconds)
        chunks.append(
            Chunk(
                lesson_title=lesson_title,
                block_order=block_order,
                text=ocr_text,
                citation=f"{lesson_title} @ {timestamp} (frame)",
            )
        )

    return chunks
