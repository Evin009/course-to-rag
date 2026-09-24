import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from aicc_demo.extractor import SHARE_ID_SUTURE
from aicc_demo.pipeline import (
    run_pipeline,
    estimate_raw_video_tokens,
    estimate_chunk_tokens,
)
from aicc_demo.retrieval import Retriever
from aicc_demo.generate import generate_answer

OUTPUT_DIR = "data/suture"
SAMPLE_QUESTION = "How do I hold the needle driver when suturing?"


def main():
    print(f"Extracting Suture course (share id: {SHARE_ID_SUTURE})...")
    stats: dict = {}
    chunks = run_pipeline(SHARE_ID_SUTURE, OUTPUT_DIR, stats=stats)
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
    results = retriever.query(SAMPLE_QUESTION, top_k=3)
    top_chunk, _top_score = results[0]
    retrieved_chunks = [chunk for chunk, score in results]

    print(f"\nQ: {SAMPLE_QUESTION}")
    try:
        answer = generate_answer(SAMPLE_QUESTION, retrieved_chunks)
        print(f"A: {answer}")
    except Exception as exc:
        print(f"A: [generation failed ({exc}), falling back to raw retrieved chunk]")
        print(f"A: {top_chunk.text}")

    for chunk, score in results:
        print(f"Citation: {chunk.citation} (score: {score:.3f})")


if __name__ == "__main__":
    main()
