import os
import sys
import time

from google import genai

from aicc_demo.assembly import Chunk

MODEL_NAME = "gemini-2.5-flash"

# The live demo hit a transient 503 UNAVAILABLE that succeeded on an
# immediate manual retry, so retry the API call itself (and only the API
# call — a missing/invalid API key fails identically every attempt).
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (1, 2)


def _build_prompt(question: str, chunks: list[Chunk]) -> str:
    context = "\n\n".join(
        f"Source: {chunk.citation}\n{chunk.text}" for chunk in chunks
    )
    return (
        "You are answering a question using ONLY the context provided below. "
        "Do not use any outside knowledge. Write a clear, plain-English answer, "
        "and mention which source (citation) the answer draws from.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}\n\n"
        "Answer:"
    )


def generate_answer(question: str, chunks: list[Chunk]) -> str:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    prompt = _build_prompt(question, chunks)

    for attempt in range(MAX_ATTEMPTS):
        try:
            response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
            break
        except Exception as exc:
            if attempt == MAX_ATTEMPTS - 1:
                raise
            delay = RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)]
            print(
                f"WARNING: Gemini call failed ({exc}); retrying in {delay}s "
                f"(attempt {attempt + 2}/{MAX_ATTEMPTS})",
                file=sys.stderr,
            )
            time.sleep(delay)

    return response.text.strip()
