import re

# Shared pattern for pulling an 11-character YouTube video id out of a
# watch/embed/short URL, or an iframe embed HTML snippet containing one.
# Used by both extractor.py (to normalize embed URLs) and audio.py (to
# key VTT filenames to the right video), so it lives in exactly one place.
YOUTUBE_ID_PATTERN = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|embed/)|youtu\.be/)([a-zA-Z0-9_-]{11})"
)


def extract_youtube_id(url: str) -> str | None:
    match = YOUTUBE_ID_PATTERN.search(url)
    return match.group(1) if match else None
