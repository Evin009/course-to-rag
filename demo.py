import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from aicc_demo.extractor import parse_share_id
from aicc_demo.pipeline import (
    run_pipeline,
    estimate_raw_video_tokens,
    estimate_chunk_tokens,
)
from aicc_demo.retrieval import Retriever
from aicc_demo.generate import generate_answer

DEFAULT_QUESTION = "How do I hold the needle driver when suturing?"


def main():
    parser = argparse.ArgumentParser(description="Retrieval + citation demo for one Articulate course.")
    parser.add_argument("course_url", help="Articulate share link, e.g. https://share.articulate.com/<id>")
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    parser.add_argument("-o", "--output-dir", help="download/cache folder (default: data/<share-id>)")
    args = parser.parse_args()
    try:
        share_id = parse_share_id(args.course_url)
    except ValueError as exc:
        sys.exit(f"error: {exc}")
    question = args.question
    output_dir = args.output_dir or f"data/{share_id}"

    print(f"Extracting course (share id: {share_id})...")
    stats: dict = {}
    chunks = run_pipeline(share_id, output_dir, stats=stats)
    print(f"Produced {len(chunks)} citable chunks.")

    attempted = stats.get("attempted", 0)
    succeeded = stats.get("succeeded", 0)
    actual_video_seconds = stats.get("total_duration_seconds", 0.0)

    raw_tokens = estimate_raw_video_tokens(actual_video_seconds)
    chunk_tokens = estimate_chunk_tokens(chunks)
    print(f"Transcribed {succeeded}/{attempted} videos")
    print(f"Actual total video duration:     {actual_video_seconds:,.0f}s")
    print(f"Estimated raw-video token cost: {raw_tokens:,}")
    print(f"Actual pipeline token cost:      {chunk_tokens:,}")
    if raw_tokens == 0:
        print("Reduction: N/A (no raw video token estimate available)")
    else:
        print(f"Reduction: {(1 - chunk_tokens / raw_tokens) * 100:.1f}%")
    print(f"(Coverage caveat: reduction above is based on {succeeded}/{attempted} videos actually transcribed.)")

    retriever = Retriever(chunks)
    results = retriever.query(question, top_k=3)
    top_chunk, _top_score = results[0]
    retrieved_chunks = [chunk for chunk, score in results]

    print(f"\nQ: {question}")
    try:
        answer = generate_answer(question, retrieved_chunks)
    except Exception as exc:
        print(f"[generation failed ({exc}), falling back to raw retrieved chunk]")
        answer = top_chunk.text
    print(f"A: {answer}")

    for chunk, score in results:
        print(f"Citation: {chunk.citation} (score: {score:.3f})")


if __name__ == "__main__":
    main()
