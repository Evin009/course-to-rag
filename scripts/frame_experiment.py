"""Compare frame sampling intervals and filtering on already-downloaded videos.

For each video and interval: extract frames, then report how many survive
the blank-frame filter and the near-duplicate filter, how much disk they
take, and how many kept frames carry OCR-readable text.

    python scripts/frame_experiment.py data/suture --intervals 3 5 10 15
"""
import argparse
import csv
import glob
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aicc_demo.images import ocr_image
from aicc_demo.visual import (
    VIDEO_EXTENSIONS,
    dedupe_frames,
    extract_frames,
    is_low_information,
)

# A frame "has text" when OCR finds at least this many letters/digits;
# below that tesseract output is mostly noise from textures.
MIN_OCR_CHARS = 20


def _duration_seconds(video_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video_path],
        capture_output=True, text=True, check=False,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _bytes(paths: list[str]) -> int:
    return sum(os.path.getsize(p) for p in paths)


def _has_text(frame_path: str) -> bool:
    try:
        text = ocr_image(frame_path)
    except Exception:
        return False
    return sum(ch.isalnum() for ch in text) >= MIN_OCR_CHARS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("video_dir", help="directory holding downloaded course videos")
    parser.add_argument("--intervals", type=int, nargs="+", default=[3, 5, 10, 15])
    parser.add_argument("--thresholds", type=int, nargs="+", default=[5, 10],
                        help="average-hash Hamming thresholds for near-duplicate removal")
    parser.add_argument("--out", default="data/experiments/frames")
    parser.add_argument("--no-ocr", action="store_true", help="skip OCR yield measurement")
    args = parser.parse_args()

    videos = sorted(
        p for p in glob.glob(os.path.join(args.video_dir, "*"))
        if os.path.splitext(p)[1].lower() in VIDEO_EXTENSIONS
    )
    if not videos:
        sys.exit(f"No videos found in {args.video_dir}")

    rows = []
    for video in videos:
        video_id = Path(video).stem
        duration = _duration_seconds(video)
        for interval in args.intervals:
            frame_dir = os.path.join(args.out, video_id, f"{interval}s")
            started = time.time()
            frames = extract_frames(video, frame_dir, interval)
            extract_s = time.time() - started
            informative = [f for f in frames if not is_low_information(f)]
            for threshold in args.thresholds:
                kept = dedupe_frames(informative, threshold=threshold)
                with_text = None if args.no_ocr else sum(_has_text(f) for f in kept)
                row = {
                    "video": video_id,
                    "duration_s": round(duration),
                    "interval_s": interval,
                    "threshold": threshold,
                    "raw_frames": len(frames),
                    "after_blank_filter": len(informative),
                    "kept_frames": len(kept),
                    "raw_mb": round(_bytes(frames) / 1e6, 2),
                    "kept_mb": round(_bytes(kept) / 1e6, 2),
                    "kept_with_text": with_text,
                    "extract_s": round(extract_s, 1),
                }
                rows.append(row)
                print(row, flush=True)

    os.makedirs(args.out, exist_ok=True)
    csv_path = os.path.join(args.out, "frame_experiment.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nPer-course totals ({len(videos)} videos)  -> {csv_path}")
    print("interval  thr  raw  blank-filtered  kept  kept%  raw MB  kept MB  kept w/ text")
    for interval in args.intervals:
        for threshold in args.thresholds:
            group = [r for r in rows if r["interval_s"] == interval and r["threshold"] == threshold]
            raw = sum(r["raw_frames"] for r in group)
            kept = sum(r["kept_frames"] for r in group)
            text = "-" if args.no_ocr else sum(r["kept_with_text"] for r in group)
            print(
                f"{interval:>6}s  {threshold:>3}  {raw:>4}  {sum(r['after_blank_filter'] for r in group):>14}  "
                f"{kept:>4}  {kept / raw * 100 if raw else 0:>4.0f}%  "
                f"{sum(r['raw_mb'] for r in group):>6.1f}  {sum(r['kept_mb'] for r in group):>7.1f}  {text:>12}"
            )


if __name__ == "__main__":
    main()
