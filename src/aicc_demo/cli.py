"""Command line: turn an Articulate Rise course link into an AICC-ready PDF.

    python -m aicc_demo https://share.articulate.com/<id>
"""
import argparse
import sys

from aicc_demo.export import DEFAULT_MAX_FRAMES_PER_VIDEO, DEFAULT_PDF_DIR, export_course
from aicc_demo.visual import DEFAULT_FRAME_INTERVAL_SECONDS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aicc-extract",
        description="Extract an Articulate Rise course into labeled text and one interleaved PDF.",
    )
    parser.add_argument("course_url", help="Articulate share link, e.g. https://share.articulate.com/<id>")
    parser.add_argument("-o", "--output-dir", help="where to write outputs (default: data/<course-title>)")
    parser.add_argument(
        "--pdf-dir", default=DEFAULT_PDF_DIR,
        help="where the finished PDF is saved (default: pdf/ in the project root)",
    )
    parser.add_argument(
        "--interval", type=int, default=DEFAULT_FRAME_INTERVAL_SECONDS,
        help=f"seconds between sampled video frames (default: {DEFAULT_FRAME_INTERVAL_SECONDS})",
    )
    parser.add_argument(
        "--max-frames", type=int, default=DEFAULT_MAX_FRAMES_PER_VIDEO,
        help=f"most frames per video placed in the PDF, 0 for no limit (default: {DEFAULT_MAX_FRAMES_PER_VIDEO})",
    )
    parser.add_argument(
        "--text-only", action="store_true",
        help="skip video transcripts and frames (fast; course text and images only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = export_course(
            args.course_url,
            output_dir=args.output_dir,
            interval_seconds=args.interval,
            max_frames_per_video=args.max_frames or None,
            include_video=not args.text_only,
            pdf_dir=args.pdf_dir,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Course text: {outputs['course_text_md']}")
    print(f"PDF:         {outputs['pdf']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
