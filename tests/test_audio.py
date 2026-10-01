from unittest.mock import patch, MagicMock
import webvtt
import pytest
from aicc_demo.audio import (
    get_transcript,
    fetch_youtube_captions,
    transcribe_with_asr,
    _download_audio,
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


def test_find_vtt_file_returns_none_when_no_video_id_given_even_if_a_vtt_exists(tmp_path):
    # A missing video id must never fall back to an unqualified "*.vtt"
    # glob: that could silently return a stale/unrelated video's transcript.
    (tmp_path / "somevideo11.en.vtt").write_text(VTT_CONTENT)

    result = _find_vtt_file(str(tmp_path), video_id=None)

    assert result is None


def test_download_audio_returns_path_to_downloaded_mp3(tmp_path):
    mp3_path = tmp_path / "abc12345678.mp3"
    mp3_path.write_bytes(b"fake audio")

    with patch("aicc_demo.audio.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        with patch("aicc_demo.audio.extract_youtube_id", return_value="abc12345678"):
            result = _download_audio("https://www.youtube.com/watch?v=abc12345678", str(tmp_path))

    assert result == str(mp3_path)
    mock_run.assert_called_once()


def test_download_audio_returns_none_when_no_matching_file(tmp_path):
    with patch("aicc_demo.audio.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        with patch("aicc_demo.audio.extract_youtube_id", return_value="abc12345678"):
            result = _download_audio("https://www.youtube.com/watch?v=abc12345678", str(tmp_path))

    assert result is None


def test_download_audio_returns_none_when_no_video_id_extractable(tmp_path):
    with patch("aicc_demo.audio.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        with patch("aicc_demo.audio.extract_youtube_id", return_value=None):
            result = _download_audio("https://articulateusercontent.com/foo.mp4", str(tmp_path))

    assert result is None
    mock_run.assert_not_called()


def test_download_audio_warns_on_nonzero_returncode(tmp_path, capsys):
    with patch("aicc_demo.audio.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="boom")
        with patch("aicc_demo.audio.extract_youtube_id", return_value="abc12345678"):
            result = _download_audio("https://www.youtube.com/watch?v=abc12345678", str(tmp_path))

    assert result is None
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "boom" in captured.err


def test_download_file_directly_writes_response_content_to_output_dir(tmp_path):
    from aicc_demo.audio import _download_file_directly

    fake_response = MagicMock()
    fake_response.iter_content.return_value = [b"chunk1", b"chunk2"]
    fake_response.raise_for_status.return_value = None

    with patch("aicc_demo.audio.requests.get", return_value=fake_response) as mock_get:
        result = _download_file_directly("https://articulateusercontent.com/foo.mp4", str(tmp_path))

    mock_get.assert_called_once()
    assert result == str(tmp_path / "foo.mp4")
    assert (tmp_path / "foo.mp4").read_bytes() == b"chunk1chunk2"


def test_download_file_directly_returns_none_on_request_failure(tmp_path):
    import requests
    from aicc_demo.audio import _download_file_directly

    with patch("aicc_demo.audio.requests.get", side_effect=requests.RequestException("boom")):
        result = _download_file_directly("https://articulateusercontent.com/foo.mp4", str(tmp_path))

    assert result is None


def test_transcribe_with_asr_converts_whisper_segments_to_dicts():
    fake_segment_1 = MagicMock(start=0.0, end=3.0, text=" Hold the needle driver like this. ", no_speech_prob=0.05)
    fake_segment_2 = MagicMock(start=3.0, end=6.0, text=" Angle it at forty-five degrees. ", no_speech_prob=0.1)
    fake_model_instance = MagicMock()
    fake_model_instance.transcribe.return_value = ([fake_segment_1, fake_segment_2], MagicMock())

    with patch("aicc_demo.audio.WhisperModel", return_value=fake_model_instance) as mock_model_cls:
        result = transcribe_with_asr("/tmp/some_audio.mp3")

    mock_model_cls.assert_called_once_with("base", device="cpu", compute_type="int8")
    fake_model_instance.transcribe.assert_called_once_with("/tmp/some_audio.mp3", language="en", vad_filter=True)
    assert result == [
        {"start": 0.0, "end": 3.0, "text": "Hold the needle driver like this."},
        {"start": 3.0, "end": 6.0, "text": "Angle it at forty-five degrees."},
    ]


def test_transcribe_with_asr_drops_music_and_unlikely_speech():
    segments = [
        MagicMock(start=0.0, end=2.0, text=" Music ", no_speech_prob=0.2),
        MagicMock(start=2.0, end=4.0, text=" [Music] ", no_speech_prob=0.2),
        MagicMock(start=4.0, end=6.0, text=" Don't forget to subscribe. ", no_speech_prob=0.9),
        MagicMock(start=6.0, end=8.0, text=" Clean the stoma. ", no_speech_prob=0.1),
    ]
    model = MagicMock()
    model.transcribe.return_value = (segments, MagicMock())

    with patch("aicc_demo.audio.WhisperModel", return_value=model):
        result = transcribe_with_asr("/tmp/a.mp4")

    assert result == [{"start": 6.0, "end": 8.0, "text": "Clean the stoma."}]


def test_get_transcript_uses_youtube_captions_for_youtube_entries(tmp_path):
    entry = {"type": "youtube", "url": "https://www.youtube.com/watch?v=abc123"}
    fake_segments = [{"start": 0.0, "end": 3.0, "text": "hi"}]

    with patch("aicc_demo.audio.fetch_youtube_captions", return_value=fake_segments) as mock_fetch:
        result = get_transcript(entry, str(tmp_path))

    mock_fetch.assert_called_once_with(entry["url"], str(tmp_path))
    assert result == fake_segments


def test_get_transcript_downloads_and_transcribes_when_no_youtube_captions(tmp_path):
    entry = {"type": "youtube", "url": "https://www.youtube.com/watch?v=nocaption"}
    fake_segments = [{"start": 0.0, "end": 3.0, "text": "transcribed"}]
    fake_audio_path = str(tmp_path / "nocaption.mp3")

    with patch("aicc_demo.audio.fetch_youtube_captions", return_value=None):
        with patch("aicc_demo.audio._download_audio", return_value=fake_audio_path) as mock_download:
            with patch("aicc_demo.audio.transcribe_with_asr", return_value=fake_segments) as mock_transcribe:
                result = get_transcript(entry, str(tmp_path))

    mock_download.assert_called_once_with(entry["url"], str(tmp_path))
    mock_transcribe.assert_called_once_with(fake_audio_path)
    assert result == fake_segments


def test_get_transcript_raises_not_implemented_when_youtube_audio_download_fails(tmp_path):
    entry = {"type": "youtube", "url": "https://www.youtube.com/watch?v=nocaption"}

    with patch("aicc_demo.audio.fetch_youtube_captions", return_value=None):
        with patch("aicc_demo.audio._download_audio", return_value=None):
            with pytest.raises(NotImplementedError):
                get_transcript(entry, str(tmp_path))


def test_get_transcript_downloads_and_transcribes_articulate_video_without_captions(tmp_path):
    entry = {
        "type": "articulate_video",
        "url": "https://articulateusercontent.com/foo.mp4",
        "captions_available": False,
    }
    fake_segments = [{"start": 0.0, "end": 3.0, "text": "transcribed"}]
    fake_audio_path = str(tmp_path / "foo.mp4")

    with patch("aicc_demo.audio._download_file_directly", return_value=fake_audio_path) as mock_download:
        with patch("aicc_demo.audio.transcribe_with_asr", return_value=fake_segments) as mock_transcribe:
            result = get_transcript(entry, str(tmp_path))

    mock_download.assert_called_once_with(entry["url"], str(tmp_path))
    mock_transcribe.assert_called_once_with(fake_audio_path)
    assert result == fake_segments


def test_get_transcript_raises_not_implemented_when_articulate_audio_download_fails(tmp_path):
    entry = {
        "type": "articulate_video",
        "url": "https://articulateusercontent.com/foo.mp4",
        "captions_available": False,
    }

    with patch("aicc_demo.audio._download_file_directly", return_value=None):
        with pytest.raises(NotImplementedError):
            get_transcript(entry, str(tmp_path))


def test_get_transcript_downloads_bundled_articulate_captions_by_raw_key(tmp_path):
    entry = {
        "type": "articulate_video",
        "url": "https://articulateusercontent.com/c/foo.mp4",
        "captions_available": True,
        "caption_key": "c/AIDET%2520CAPTIONS.vtt",
    }

    def fake_download(url, output_dir):
        path = tmp_path / "AIDET%2520CAPTIONS.vtt"
        path.write_text(VTT_CONTENT)
        return str(path)

    with patch("aicc_demo.audio._download_file_directly", side_effect=fake_download) as mock_dl, \
         patch("aicc_demo.audio.transcribe_with_asr") as mock_asr:
        segments = get_transcript(entry, str(tmp_path))

    mock_dl.assert_called_once_with("https://articulateusercontent.com/c/AIDET%2520CAPTIONS.vtt", str(tmp_path))
    mock_asr.assert_not_called()
    assert segments[0]["text"] == "Hold the needle driver like this."


def test_get_transcript_falls_back_to_asr_when_articulate_captions_fail(tmp_path):
    entry = {
        "type": "articulate_video",
        "url": "https://articulateusercontent.com/c/foo.mp4",
        "captions_available": True,
        "caption_key": "c/missing.vtt",
    }

    with patch("aicc_demo.audio._download_file_directly", side_effect=[None, "/fake/foo.mp4"]), \
         patch("aicc_demo.audio.transcribe_with_asr", return_value=[{"start": 0, "end": 1, "text": "asr"}]) as mock_asr:
        segments = get_transcript(entry, str(tmp_path))

    mock_asr.assert_called_once_with("/fake/foo.mp4")
    assert segments[0]["text"] == "asr"


ROLLING_VTT = """WEBVTT

00:00:01.000 --> 00:00:03.000
hey guys welcome back

00:00:03.000 --> 00:00:03.010
hey guys welcome back

00:00:03.010 --> 00:00:05.000
hey guys welcome back
to another video

00:00:05.000 --> 00:00:07.000
to another video
on suturing
"""


def test_parse_vtt_drops_youtube_rolling_caption_repeats(tmp_path):
    from aicc_demo.audio import _parse_vtt

    vtt_path = tmp_path / "abc.en.vtt"
    vtt_path.write_text(ROLLING_VTT)

    segments = _parse_vtt(str(vtt_path))

    assert [s["text"] for s in segments] == ["hey guys welcome back", "to another video", "on suturing"]
    assert segments[1]["start"] == 3.01


def test_download_file_directly_reuses_cached_file(tmp_path):
    from aicc_demo.audio import _download_file_directly

    cached = tmp_path / "clip.mp4"
    cached.write_bytes(b"video")

    with patch("aicc_demo.audio.requests.get") as mock_get:
        assert _download_file_directly("https://articulateusercontent.com/c/clip.mp4", str(tmp_path)) == str(cached)

    mock_get.assert_not_called()


def test_download_file_directly_leaves_no_partial_file_on_failure(tmp_path):
    import requests
    from aicc_demo.audio import _download_file_directly

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.iter_content.side_effect = requests.ConnectionError("dropped")

    with patch("aicc_demo.audio.requests.get", return_value=response):
        assert _download_file_directly("https://articulateusercontent.com/c/clip.mp4", str(tmp_path)) is None

    assert list(tmp_path.iterdir()) == []
