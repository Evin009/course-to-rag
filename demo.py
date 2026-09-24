from aicc_demo.extractor import SHARE_ID_SUTURE
from aicc_demo.pipeline import run_pipeline, estimate_raw_video_tokens, estimate_chunk_tokens
from aicc_demo.retrieval import Retriever

OUTPUT_DIR = "data/suture"
SAMPLE_QUESTION = "How do I hold the needle driver when suturing?"
ESTIMATED_COURSE_VIDEO_SECONDS = 600  # placeholder until real durations are pulled from manifest


def main():
    print(f"Extracting Suture course (share id: {SHARE_ID_SUTURE})...")
    chunks = run_pipeline(SHARE_ID_SUTURE, OUTPUT_DIR)
    print(f"Produced {len(chunks)} citable chunks.")

    raw_tokens = estimate_raw_video_tokens(ESTIMATED_COURSE_VIDEO_SECONDS)
    chunk_tokens = estimate_chunk_tokens(chunks)
    print(f"Estimated raw-video token cost: {raw_tokens:,}")
    print(f"Actual pipeline token cost:      {chunk_tokens:,}")
    print(f"Reduction: {(1 - chunk_tokens / raw_tokens) * 100:.1f}%")

    retriever = Retriever(chunks)
    results = retriever.query(SAMPLE_QUESTION, top_k=1)
    top_chunk, score = results[0]
    print(f"\nQ: {SAMPLE_QUESTION}")
    print(f"A: {top_chunk.text}")
    print(f"Citation: {top_chunk.citation} (score: {score:.3f})")


if __name__ == "__main__":
    main()
