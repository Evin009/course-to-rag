import sys

import pytesseract
from PIL import Image

from aicc_demo.assembly import Chunk
from aicc_demo.audio import _download_file_directly


def flatten_to_rgb(image: Image.Image) -> Image.Image:
    """RGB copy with any transparency composited onto white.

    A plain convert("RGB") turns transparent pixels black, so a diagram
    with black lines on a transparent background becomes all black (in the
    PDF and for OCR); 95 of the COT5407 courses' PNGs are like this.
    """
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def ocr_image(image_path: str) -> str:
    with Image.open(image_path) as image:
        # Tesseract cannot read multi-frame (animated) GIFs. Algorithm
        # animations end on their final state, so read the last frame.
        if getattr(image, "n_frames", 1) > 1:
            image.seek(image.n_frames - 1)
        text = pytesseract.image_to_string(flatten_to_rgb(image))
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
