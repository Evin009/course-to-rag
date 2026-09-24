from unittest.mock import patch, MagicMock

from PIL import Image, ImageDraw
from aicc_demo.assembly import Chunk
from aicc_demo.visual import (
    dedupe_frames,
    caption_frame,
    _download_video,
    extract_frames,
    process_video_visuals,
)


def _make_solid_image(path, color):
    img = Image.new("RGB", (64, 64), color=color)
    # Add fine white stripes so average_hash can distinguish different colors
    # This is necessary because uniform solid colors all hash identically with average_hash
    draw = ImageDraw.Draw(img)
    for x in range(0, 64, 2):
        draw.line([(x, 0), (x, 63)], fill=(255, 255, 255), width=1)
    img.save(path)


def test_dedupe_frames_keeps_one_of_near_identical_images(tmp_path):
    path_a = tmp_path / "frame_a.png"
    path_b = tmp_path / "frame_b.png"
    _make_solid_image(path_a, (255, 0, 0))
    _make_solid_image(path_b, (255, 0, 0))

    result = dedupe_frames([str(path_a), str(path_b)])

    assert len(result) == 1


def test_dedupe_frames_keeps_both_of_different_images(tmp_path):
    path_a = tmp_path / "frame_a.png"
    path_b = tmp_path / "frame_b.png"
    _make_solid_image(path_a, (255, 0, 0))
    _make_solid_image(path_b, (0, 0, 255))

    result = dedupe_frames([str(path_a), str(path_b)])

    assert len(result) == 2


def test_caption_frame_not_implemented_for_demo_scope():
    import pytest
    with pytest.raises(NotImplementedError):
        caption_frame("/tmp/some_frame.png")


def test_download_video_returns_path_to_downloaded_youtube_file(tmp_path):
    video_path = tmp_path / "abc12345678.mp4"

    def fake_run(*args, **kwargs):
        video_path.write_bytes(b"fake video")
        return MagicMock(returncode=0, stderr="")

    with patch("aicc_demo.visual.subprocess.run", side_effect=fake_run) as mock_run:
        with patch("aicc_demo.visual.extract_youtube_id", return_value="abc12345678"):
            result = _download_video("https://www.youtube.com/watch?v=abc12345678", str(tmp_path))

    assert result == str(video_path)
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "-x" not in args
    # Progressive/muxed <=480p streams no longer exist on YouTube.
    assert "bv*[height<=480]+ba/b[height<=480]/b" in args


def test_download_video_skips_ytdlp_when_video_already_downloaded(tmp_path):
    video_path = tmp_path / "abc12345678.mp4"
    video_path.write_bytes(b"fake video")

    with patch("aicc_demo.visual.subprocess.run") as mock_run:
        with patch("aicc_demo.visual.extract_youtube_id", return_value="abc12345678"):
            result = _download_video("https://www.youtube.com/watch?v=abc12345678", str(tmp_path))

    assert result == str(video_path)
    mock_run.assert_not_called()


def test_download_video_ignores_same_id_audio_file_from_asr_path(tmp_path):
    # _download_audio writes {video_id}.mp3 into the SAME output_dir; it
    # must never be handed to ffmpeg as if it were the video.
    (tmp_path / "abc12345678.mp3").write_bytes(b"fake audio")

    with patch("aicc_demo.visual.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        with patch("aicc_demo.visual.extract_youtube_id", return_value="abc12345678"):
            result = _download_video("https://www.youtube.com/watch?v=abc12345678", str(tmp_path))

    assert result is None
    mock_run.assert_called_once()


def test_download_video_returns_none_when_no_matching_file(tmp_path):
    with patch("aicc_demo.visual.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        with patch("aicc_demo.visual.extract_youtube_id", return_value="abc12345678"):
            result = _download_video("https://www.youtube.com/watch?v=abc12345678", str(tmp_path))

    assert result is None


def test_download_video_delegates_to_direct_download_for_non_youtube_url(tmp_path):
    fake_path = str(tmp_path / "foo.mp4")

    with patch("aicc_demo.visual.extract_youtube_id", return_value=None):
        with patch("aicc_demo.visual._download_file_directly", return_value=fake_path) as mock_direct:
            result = _download_video("https://articulateusercontent.com/foo.mp4", str(tmp_path))

    mock_direct.assert_called_once_with("https://articulateusercontent.com/foo.mp4", str(tmp_path))
    assert result == fake_path


def test_extract_frames_returns_sorted_frame_paths(tmp_path):
    # Simulate what ffmpeg would have produced, out of order on disk.
    (tmp_path / "frame_0002.png").write_bytes(b"fake")
    (tmp_path / "frame_0001.png").write_bytes(b"fake")
    (tmp_path / "frame_0003.png").write_bytes(b"fake")

    with patch("aicc_demo.visual.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = extract_frames("/fake/video.mp4", str(tmp_path))

    assert result == [
        str(tmp_path / "frame_0001.png"),
        str(tmp_path / "frame_0002.png"),
        str(tmp_path / "frame_0003.png"),
    ]
    mock_run.assert_called_once()


def test_extract_frames_is_isolated_per_video_directory(tmp_path):
    """Regression: frames from one video must never leak into another's.

    Previously every video wrote `frame_%04d.png` into one shared
    output_dir and globbed ALL of them, so a later video would return the
    earlier video's stale frames and mis-attribute them (wrong lesson,
    fabricated timestamp). Per-video subdirectories prevent this.
    """
    base = tmp_path / "data"
    video_a_dir = base / "frames" / "videoAAAAAAA"
    video_b_dir = base / "frames" / "videoBBBBBBB"
    video_a_dir.mkdir(parents=True)

    # Leftover frames from a previous video's extraction.
    stale_frames = []
    for i in range(1, 6):
        stale = video_a_dir / f"frame_{i:04d}.png"
        stale.write_bytes(b"stale")
        stale_frames.append(str(stale))

    # ffmpeg for the NEW video writes only into its own directory.
    def fake_run(*args, **kwargs):
        video_b_dir.mkdir(parents=True, exist_ok=True)
        (video_b_dir / "frame_0001.png").write_bytes(b"new")
        return MagicMock(returncode=0, stderr="")

    with patch("aicc_demo.visual.subprocess.run", side_effect=fake_run):
        result = extract_frames("/fake/video_b.mp4", str(video_b_dir))

    assert result == [str(video_b_dir / "frame_0001.png")]
    for stale in stale_frames:
        assert stale not in result


def test_process_video_visuals_uses_per_video_frame_directory(tmp_path):
    captured = {}

    def fake_extract(video_path, output_dir, interval_seconds):
        captured["output_dir"] = output_dir
        return []

    with patch("aicc_demo.visual._download_video", return_value="/fake/video.mp4"):
        with patch("aicc_demo.visual.extract_frames", side_effect=fake_extract):
            process_video_visuals(
                "https://www.youtube.com/watch?v=abc12345678", "Knots", 0, str(tmp_path)
            )

    assert captured["output_dir"] == str(tmp_path / "frames" / "abc12345678")


def test_process_video_visuals_timestamp_comes_from_frame_number(tmp_path):
    # frame_0003.png is the 3rd frame -> index 2 -> 2 * 15s = 0:30
    frame_paths = [str(tmp_path / "frame_0003.png")]

    with patch("aicc_demo.visual._download_video", return_value="/fake/video.mp4"):
        with patch("aicc_demo.visual.extract_frames", return_value=frame_paths):
            with patch("aicc_demo.visual.dedupe_frames", return_value=frame_paths):
                with patch("aicc_demo.visual.ocr_image", return_value="Step 3"):
                    chunks = process_video_visuals(
                        "https://www.youtube.com/watch?v=abc123", "Knots", 0, str(tmp_path)
                    )

    assert chunks[0].citation == "Knots @ 0:30 (frame)"


def test_process_video_visuals_skips_frame_when_ocr_raises(tmp_path):
    frame_paths = [str(tmp_path / "frame_0001.png")]

    with patch("aicc_demo.visual._download_video", return_value="/fake/video.mp4"):
        with patch("aicc_demo.visual.extract_frames", return_value=frame_paths):
            with patch("aicc_demo.visual.dedupe_frames", return_value=frame_paths):
                with patch("aicc_demo.visual.ocr_image", side_effect=RuntimeError("tesseract missing")):
                    chunks = process_video_visuals(
                        "https://www.youtube.com/watch?v=abc123", "Knots", 0, str(tmp_path)
                    )

    assert chunks == []


def test_extract_frames_returns_empty_list_when_no_frames_produced(tmp_path):
    with patch("aicc_demo.visual.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="boom")
        result = extract_frames("/fake/video.mp4", str(tmp_path))

    assert result == []


def test_process_video_visuals_returns_empty_list_when_download_fails(tmp_path):
    with patch("aicc_demo.visual._download_video", return_value=None):
        with patch("aicc_demo.visual.extract_frames") as mock_extract:
            chunks = process_video_visuals(
                "https://www.youtube.com/watch?v=abc123", "Knots", 0, str(tmp_path)
            )

    mock_extract.assert_not_called()
    assert chunks == []


def test_process_video_visuals_creates_chunk_for_frame_with_ocr_text(tmp_path):
    frame_paths = [str(tmp_path / "frame_0001.png"), str(tmp_path / "frame_0002.png")]

    with patch("aicc_demo.visual._download_video", return_value="/fake/video.mp4"):
        with patch("aicc_demo.visual.extract_frames", return_value=frame_paths):
            with patch("aicc_demo.visual.dedupe_frames", return_value=[frame_paths[1]]):
                with patch("aicc_demo.visual.ocr_image", return_value="Suture technique steps"):
                    chunks = process_video_visuals(
                        "https://www.youtube.com/watch?v=abc123", "Knots", 0, str(tmp_path)
                    )

    assert len(chunks) == 1
    assert chunks[0].lesson_title == "Knots"
    assert chunks[0].block_order == 0
    assert chunks[0].text == "Suture technique steps"
    assert chunks[0].citation.startswith("Knots @")
    assert chunks[0].citation.endswith("(frame)")


def test_process_video_visuals_returns_empty_list_when_all_ocr_empty(tmp_path):
    frame_paths = [str(tmp_path / "frame_0001.png")]

    with patch("aicc_demo.visual._download_video", return_value="/fake/video.mp4"):
        with patch("aicc_demo.visual.extract_frames", return_value=frame_paths):
            with patch("aicc_demo.visual.dedupe_frames", return_value=frame_paths):
                with patch("aicc_demo.visual.ocr_image", return_value=""):
                    chunks = process_video_visuals(
                        "https://www.youtube.com/watch?v=abc123", "Knots", 0, str(tmp_path)
                    )

    assert chunks == []
