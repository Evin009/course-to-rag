"""Command line: list (and optionally extract) the Rise courses linked in a Canvas course.

    python canvas.py https://usflearn.instructure.com/courses/2151228
    python canvas.py https://usflearn.instructure.com/courses/2151228 --extract all
    python canvas.py https://usflearn.instructure.com/courses/2151228 --extract 1,3
"""
import argparse
import json
import sys

from aicc_demo.canvas import as_dicts, find_linked_courses
from aicc_demo.export import DEFAULT_MAX_FRAMES_PER_VIDEO, DEFAULT_PDF_DIR, export_course
from aicc_demo.visual import DEFAULT_FRAME_INTERVAL_SECONDS


def parse_selection(selection: str, count: int) -> list[int]:
    """1-based numbers from "all" or "1,3,5-7" -> 0-based indexes."""
    if selection.strip().lower() == "all":
        return list(range(count))
    picked: list[int] = []
    for part in selection.split(","):
        part = part.strip()
        if not part:
            continue
        start, _, end = part.partition("-")
        for number in range(int(start), int(end or start) + 1):
            if not 1 <= number <= count:
                raise ValueError(f"No course number {number} (choose 1-{count})")
            if number - 1 not in picked:
                picked.append(number - 1)
    return picked


def print_listing(courses) -> None:
    current_module = None
    for number, course in enumerate(courses, 1):
        if course.module != current_module:
            current_module = course.module
            print(f"\n{current_module}")
        note = "" if course.extractable else "  (Canvas SCORM package: plays only inside Canvas, cannot be extracted)"
        print(f"  {number:>2}. {course.item_title}  [{course.kind}]{note}")
        print(f"      {course.course_url}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="canvas.py",
        description="List the Articulate Rise courses linked in a Canvas course's modules, and optionally extract them to PDFs.",
    )
    parser.add_argument("canvas_url", help="Canvas course URL, e.g. https://usflearn.instructure.com/courses/2151228")
    parser.add_argument("--extract", metavar="WHICH", help='courses to turn into PDFs: "all" or numbers like "1,3,5-7"')
    parser.add_argument("--json", metavar="FILE", help="also save the list as JSON")
    parser.add_argument("--pdf-dir", default=DEFAULT_PDF_DIR, help="where PDFs are saved (default: pdf/)")
    parser.add_argument("--interval", type=int, default=DEFAULT_FRAME_INTERVAL_SECONDS)
    parser.add_argument("--max-frames", type=int, default=DEFAULT_MAX_FRAMES_PER_VIDEO)
    parser.add_argument("--text-only", action="store_true", help="skip video transcripts and frames")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        courses = find_linked_courses(args.canvas_url)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    blocked = sum(not c.extractable for c in courses)
    print(
        f"Found {len(courses)} linked Rise course{'s' if len(courses) != 1 else ''} in {args.canvas_url}"
        + (f" ({blocked} SCORM package{'s' if blocked != 1 else ''} that cannot be extracted)" if blocked else "")
    )
    print_listing(courses)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(as_dicts(courses), f, indent=2)
        print(f"\nSaved list: {args.json}")
    if not args.extract or not courses:
        return 0

    try:
        picked = parse_selection(args.extract, len(courses))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    results = []
    for index in picked:
        course = courses[index]
        print(f"\n=== [{index + 1}] {course.item_title} ===", file=sys.stderr)
        if not course.extractable:
            print("  SKIPPED: Canvas SCORM package; ask the instructor for its Rise share link or web export", file=sys.stderr)
            results.append((index, "SKIPPED (SCORM package)"))
            continue
        try:
            outputs = export_course(
                course.course_url,
                interval_seconds=args.interval,
                max_frames_per_video=args.max_frames or None,
                include_video=not args.text_only,
                pdf_dir=args.pdf_dir,
            )
            results.append((index, outputs["pdf"]))
        except Exception as exc:  # one broken course must not stop the rest
            print(f"  FAILED: {exc}", file=sys.stderr)
            results.append((index, None))

    print("\nPDFs:")
    for index, pdf in results:
        print(f"  {index + 1:>2}. {pdf or 'FAILED (see log above)'}")
    return 0 if all(pdf for _, pdf in results) else 1  # a skipped SCORM package is not a failure


if __name__ == "__main__":
    sys.exit(main())
