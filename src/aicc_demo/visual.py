import imagehash
from PIL import Image


def dedupe_frames(frame_paths: list[str], threshold: int = 5) -> list[str]:
    kept: list[str] = []
    kept_hashes: list[imagehash.ImageHash] = []

    for path in frame_paths:
        current_hash = imagehash.average_hash(Image.open(path))
        if any(current_hash - kept_hash <= threshold for kept_hash in kept_hashes):
            continue
        kept.append(path)
        kept_hashes.append(current_hash)

    return kept


def caption_frame(frame_path: str) -> str:
    raise NotImplementedError(
        "Vision-model frame captioning (Gemini Flash / Qwen2.5-VL) is out of scope "
        "for the Suture demo; required for PCC's Articulate-hosted uncaptioned videos."
    )
