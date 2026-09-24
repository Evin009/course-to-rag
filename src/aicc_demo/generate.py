import os

from google import genai

from aicc_demo.assembly import Chunk

MODEL_NAME = "gemini-2.5-flash"


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
    response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
    return response.text.strip()
