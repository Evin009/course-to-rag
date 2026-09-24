import sys

import pytesseract

from aicc_demo.assembly import Chunk
from aicc_demo.audio import _download_file_directly


def ocr_image(image_path: str) -> str:
    text = pytesseract.image_to_string(image_path)
    return text.strip()


def process_image_entries(manifest_entries: list[dict], output_dir: str) -> list[Chunk]:
    chunks: list[Chunk] = []

    image_entries = [e for e in manifest_entries if e["type"] == "image"]
    for entry in image_entries:
        image_path = _download_file_directly(entry["url"], output_dir)
        if image_path is None:
            continue

        try:
            ocr_text = ocr_image(image_path)
        except Exception as exc:
            # e.g. TesseractNotFoundError when the tesseract binary isn't
            # installed: treat as "no text found" rather than crashing.
            print(f"WARNING: OCR failed for {image_path}: {exc}", file=sys.stderr)
            continue
        if not ocr_text:
            continue

        chunks.append(
            Chunk(
                lesson_title=entry["lesson_title"],
                block_order=entry["block_order"],
                text=ocr_text,
                citation=f"{entry['lesson_title']} (image)",
            )
        )

    return chunks
