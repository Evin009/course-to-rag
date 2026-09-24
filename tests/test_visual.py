from PIL import Image, ImageDraw
from aicc_demo.visual import dedupe_frames, caption_frame


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
