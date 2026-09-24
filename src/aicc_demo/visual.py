import imagehash
from PIL import Image


def dedupe_frames(frame_paths: list[str], threshold: int = 5) -> list[str]:
    """Drop near-duplicate frames using average-hash + Hamming distance.

    Note: average_hash compares each pixel to the image's own mean, so
    distinct solid-color/textureless frames (e.g. different title cards)
    can collide to an identical hash regardless of hue and get
    incorrectly deduplicated. Fine for frames with real visual content;
    a known blind spot for flat/solid-color frames.
    """
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
