from unittest.mock import patch, MagicMock
import webvtt
from aicc_demo.audio import (
    get_transcript,
    fetch_youtube_captions,
    transcribe_with_asr,
    _find_vtt_file,
    _extract_youtube_id,
)


VTT_CONTENT = """WEBVTT

00:00:00.000 --> 00:00:03.000
Hold the needle driver like this.

00:00:03.000 --> 00:00:06.000
Angle it at forty-five degrees.
"""


def test_fetch_youtube_captions_parses_vtt_when_ytdlp_writes_file(tmp_path):
    vtt_path = tmp_path / "video.en.vtt"
    vtt_path.write_text(VTT_CONTENT)

    with patch("aicc_demo.audio.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with patch("aicc_demo.audio._find_vtt_file", return_value=str(vtt_path)):
            segments = fetch_youtube_captions("https://www.youtube.com/watch?v=abc123", str(tmp_path))

    assert segments == [
        {"start": 0.0, "end": 3.0, "text": "Hold the needle driver like this."},
        {"start": 3.0, "end": 6.0, "text": "Angle it at forty-five degrees."},
    ]


def test_fetch_youtube_captions_returns_none_when_no_vtt_produced(tmp_path):
    with patch("aicc_demo.audio.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with patch("aicc_demo.audio._find_vtt_file", return_value=None):
            result = fetch_youtube_captions("https://www.youtube.com/watch?v=nocaption", str(tmp_path))

    assert result is None


def test_extract_youtube_id_from_watch_url():
    assert _extract_youtube_id("https://www.youtube.com/watch?v=abc12345678") == "abc12345678"


def test_extract_youtube_id_returns_none_for_non_youtube_url():
    assert _extract_youtube_id("https://articulateusercontent.com/foo.mp4") is None


def test_find_vtt_file_matches_only_the_requested_video_id(tmp_path):
    (tmp_path / "firstvideo11.en.vtt").write_text(VTT_CONTENT)
    (tmp_path / "secondvide22.en.vtt").write_text(VTT_CONTENT)

    result = _find_vtt_file(str(tmp_path), video_id="secondvide22")

    assert result == str(tmp_path / "secondvide22.en.vtt")


def test_find_vtt_file_returns_none_when_requested_video_id_not_present(tmp_path):
    (tmp_path / "firstvideo11.en.vtt").write_text(VTT_CONTENT)

    result = _find_vtt_file(str(tmp_path), video_id="secondvide22")

    assert result is None


def test_transcribe_with_asr_not_implemented_for_demo_scope():
    import pytest
    with pytest.raises(NotImplementedError):
        transcribe_with_asr("/tmp/some_video.mp4")


def test_get_transcript_uses_youtube_captions_for_youtube_entries(tmp_path):
    entry = {"type": "youtube", "url": "https://www.youtube.com/watch?v=abc123"}
    fake_segments = [{"start": 0.0, "end": 3.0, "text": "hi"}]

    with patch("aicc_demo.audio.fetch_youtube_captions", return_value=fake_segments) as mock_fetch:
        result = get_transcript(entry, str(tmp_path))

    mock_fetch.assert_called_once_with(entry["url"], str(tmp_path))
    assert result == fake_segments


def test_get_transcript_falls_back_to_asr_when_no_youtube_captions(tmp_path):
    entry = {"type": "youtube", "url": "https://www.youtube.com/watch?v=nocaption"}

    with patch("aicc_demo.audio.fetch_youtube_captions", return_value=None):
        with patch("aicc_demo.audio.transcribe_with_asr", side_effect=NotImplementedError):
            import pytest
            with pytest.raises(NotImplementedError):
                get_transcript(entry, str(tmp_path))
