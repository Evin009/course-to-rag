import os
import stat
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aicc_demo import utils
from aicc_demo.utils import ytdlp_cookie_args

YT = "https://www.youtube.com/watch?v=abc12345678"
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def cookies(tmp_path, monkeypatch):
    source = tmp_path / "mounted.txt"
    source.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tx\n")
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    monkeypatch.setenv("AICC_YT_COOKIES_FILE", str(source))
    monkeypatch.setattr(utils.tempfile, "gettempdir", lambda: str(scratch))
    return source, scratch


def test_no_cookie_args_without_config(monkeypatch):
    monkeypatch.delenv("AICC_YT_COOKIES_FILE", raising=False)
    assert ytdlp_cookie_args(YT) == []


def test_cookies_only_go_to_youtube_and_use_a_private_writable_copy(cookies):
    source, scratch = cookies
    os.chmod(source, 0o400)  # a mounted secret is read-only

    args = ytdlp_cookie_args(YT)

    copy = scratch / "aicc-yt-cookies.txt"
    assert args == ["--cookies", str(copy)]
    assert copy.read_text() == source.read_text()
    assert stat.S_IMODE(copy.stat().st_mode) == 0o600
    assert ytdlp_cookie_args("kaltura:1933811:1_abc") == []
    assert ytdlp_cookie_args("https://vimeo.com/123") == []


def test_every_youtube_download_passes_cookies(cookies, tmp_path):
    from aicc_demo.audio import _download_audio, fetch_youtube_captions
    from aicc_demo.visual import _download_video

    with patch("aicc_demo.audio.subprocess.run", return_value=MagicMock(returncode=1, stderr="")) as audio_run, \
         patch("aicc_demo.visual.subprocess.run", return_value=MagicMock(returncode=1, stderr="")) as video_run:
        fetch_youtube_captions(YT, str(tmp_path))
        _download_audio(YT, str(tmp_path))
        _download_video(YT, str(tmp_path))

    for call in [*audio_run.call_args_list, *video_run.call_args_list]:
        assert "--cookies" in call.args[0]


def test_upload_script_keeps_only_youtube_and_google_cookies(tmp_path):
    # A fake gcloud records what would be uploaded.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    captured = tmp_path / "uploaded.txt"
    fake = bin_dir / "gcloud"
    fake.write_text(f"""#!/bin/bash
if [ "$1 $2" = "secrets describe" ]; then exit 1; fi
for a in "$@"; do case "$a" in --data-file=*) cp "${{a#--data-file=}}" "{captured}";; esac; done
exit 0
""")
    fake.chmod(0o755)
    exported = tmp_path / "exported.txt"
    exported.write_text(
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tkeep1\n"
        "#HttpOnly_.google.com\tTRUE\t/\tTRUE\t0\tHSID\tkeep2\n"
        ".accounts.google.com\tTRUE\t/\tTRUE\t0\tLSID\tkeep3\n"
        ".mybank.com\tTRUE\t/\tTRUE\t0\tsession\tDROP1\n"
        ".notyoutube.com\tTRUE\t/\tTRUE\t0\tx\tDROP2\n"
    )

    result = subprocess.run(
        [str(ROOT / "deploy" / "set-youtube-cookies.sh"), str(exported)],
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "PROJECT_ID": "p"},
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    uploaded = captured.read_text()
    assert all(k in uploaded for k in ("keep1", "keep2", "keep3"))
    assert "DROP" not in uploaded
    assert not any(k in result.stdout for k in ("keep1", "keep2", "keep3"))  # values are never printed


def test_upload_script_refuses_a_file_without_youtube_cookies(tmp_path):
    exported = tmp_path / "exported.txt"
    exported.write_text(".mybank.com\tTRUE\t/\tTRUE\t0\tsession\tx\n")

    result = subprocess.run(
        [str(ROOT / "deploy" / "set-youtube-cookies.sh"), str(exported)],
        env={**os.environ, "PROJECT_ID": "p"}, capture_output=True, text=True,
    )

    assert result.returncode == 1 and "No youtube.com cookies" in result.stderr
