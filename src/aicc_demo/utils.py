import os
import re
import shutil
import tempfile

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


def ytdlp_cookie_args(url: str) -> list[str]:
    """`--cookies <file>` for YouTube URLs when AICC_YT_COOKIES_FILE is set, else nothing.

    YouTube refuses downloads from cloud servers without a signed-in session,
    so the cloud job mounts cookies from Secret Manager. They are only ever
    passed for YouTube URLs. yt-dlp rewrites its cookie file on exit and a
    mounted secret is read-only, so it gets a private copy.
    """
    source = os.environ.get("AICC_YT_COOKIES_FILE")
    if not source or not extract_youtube_id(url) or not os.path.exists(source):
        return []
    copy = os.path.join(tempfile.gettempdir(), "aicc-yt-cookies.txt")
    if not os.path.exists(copy):
        shutil.copyfile(source, copy)
        os.chmod(copy, 0o600)
    return ["--cookies", copy]
