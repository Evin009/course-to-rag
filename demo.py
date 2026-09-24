from aicc_demo.extractor import SHARE_ID_SUTURE
from aicc_demo.pipeline import (
    run_pipeline,
    estimate_raw_video_tokens,
    estimate_chunk_tokens,
    estimate_actual_video_duration_seconds,
)
from aicc_demo.retrieval import Retriever

OUTPUT_DIR = "data/suture"
SAMPLE_QUESTION = "How do I hold the needle driver when suturing?"


def main():
    print(f"Extracting Suture course (share id: {SHARE_ID_SUTURE})...")
    chunks = run_pipeline(SHARE_ID_SUTURE, OUTPUT_DIR)
    print(f"Produced {len(chunks)} citable chunks.")

    print("Querying actual video durations via yt-dlp...")
    actual_video_seconds = estimate_actual_video_duration_seconds(SHARE_ID_SUTURE)
    raw_tokens = estimate_raw_video_tokens(actual_video_seconds)
    chunk_tokens = estimate_chunk_tokens(chunks)
    print(f"Actual total video duration:     {actual_video_seconds:,.0f}s")
    print(f"Estimated raw-video token cost: {raw_tokens:,}")
    print(f"Actual pipeline token cost:      {chunk_tokens:,}")
    if raw_tokens == 0:
        print("Reduction: N/A (no raw video token estimate available)")
    else:
        print(f"Reduction: {(1 - chunk_tokens / raw_tokens) * 100:.1f}%")

    retriever = Retriever(chunks)
    results = retriever.query(SAMPLE_QUESTION, top_k=1)
    top_chunk, score = results[0]
    print(f"\nQ: {SAMPLE_QUESTION}")
    print(f"A: {top_chunk.text}")
    print(f"Citation: {top_chunk.citation} (score: {score:.3f})")


if __name__ == "__main__":
    main()
