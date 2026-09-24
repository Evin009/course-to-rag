import responses
from aicc_demo.extractor import fetch_course_json, SHARE_ID_SUTURE, strip_html, walk_lesson

COURSE_ENDPOINT = f"https://share.articulate.com/api/instant-links/{SHARE_ID_SUTURE}/course"

@responses.activate
def test_fetch_course_json_posts_to_instant_links_endpoint():
    fake_course = {"course": {"lessons": [{"id": "l1", "title": "Intro", "items": []}]}}
    responses.add(responses.POST, COURSE_ENDPOINT, json=fake_course, status=200)

    result = fetch_course_json(SHARE_ID_SUTURE)

    assert result == fake_course
    assert responses.calls[0].request.url == COURSE_ENDPOINT
    assert responses.calls[0].request.method == "POST"


@responses.activate
def test_fetch_course_json_raises_on_http_error():
    responses.add(responses.POST, COURSE_ENDPOINT, status=500)

    import pytest
    from requests import HTTPError
    with pytest.raises(HTTPError):
        fetch_course_json(SHARE_ID_SUTURE)


def test_strip_html_removes_tags_keeps_text():
    html = "<p>Hold the needle at a <strong>45-degree</strong> angle.</p>"
    assert strip_html(html) == "Hold the needle at a 45-degree angle."


def test_walk_lesson_extracts_text_block_as_markdown():
    lesson = {
        "id": "lesson-1",
        "title": "Suturing Basics",
        "items": [
            {
                "type": "text",
                "items": [{"paragraph": "<p>Suturing closes wounds.</p>"}],
            }
        ],
    }

    markdown, manifest = walk_lesson(lesson)

    assert "## Suturing Basics" in markdown
    assert "Suturing closes wounds." in markdown
    assert manifest == []


def test_walk_lesson_extracts_youtube_video_into_manifest():
    lesson = {
        "id": "lesson-2",
        "title": "Knot Tying",
        "items": [
            {
                "type": "multimedia",
                "items": [
                    {
                        "media": {
                            "embed": {"originalUrl": "https://www.youtube.com/watch?v=abc123"}
                        }
                    }
                ],
            }
        ],
    }

    markdown, manifest = walk_lesson(lesson)

    assert len(manifest) == 1
    entry = manifest[0]
    assert entry["lesson_id"] == "lesson-2"
    assert entry["lesson_title"] == "Knot Tying"
    assert entry["type"] == "youtube"
    assert entry["url"] == "https://www.youtube.com/watch?v=abc123"
    assert entry["captions_available"] is False
    assert entry["block_order"] == 0


def test_walk_lesson_extracts_articulate_hosted_video_with_captions():
    lesson = {
        "id": "lesson-3",
        "title": "Wound Assessment",
        "items": [
            {
                "type": "multimedia",
                "items": [
                    {
                        "media": {
                            "video": {
                                "key": "abc%2520def.mp4",
                                "captions": [{"key": "abc%2520def.vtt"}],
                            }
                        }
                    }
                ],
            }
        ],
    }

    markdown, manifest = walk_lesson(lesson)

    entry = manifest[0]
    assert entry["type"] == "articulate_video"
    assert entry["url"] == "https://articulateusercontent.com/abc%20def.mp4"
    assert entry["captions_available"] is True
    assert entry["caption_key"] == "abc%20def.vtt"


def test_walk_lesson_normalizes_iframe_embed_html_to_clean_youtube_url():
    lesson = {
        "id": "lesson-6",
        "title": "Embedded Video",
        "items": [
            {
                "type": "multimedia",
                "items": [
                    {
                        "media": {
                            "embed": {
                                "originalUrl": '<iframe width="560" height="315" src="https://www.youtube.com/embed/dQw4w9WgXcQ?rel=0" frameborder="0"></iframe>'
                            }
                        }
                    }
                ],
            }
        ],
    }

    markdown, manifest = walk_lesson(lesson)

    assert manifest[0]["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_walk_lesson_recurses_into_nested_items():
    lesson = {
        "id": "lesson-4",
        "title": "Flashcards",
        "items": [
            {
                "type": "flashcard",
                "items": [
                    {
                        "items": [
                            {"description": "<p>Nested text block.</p>"}
                        ]
                    }
                ],
            }
        ],
    }

    markdown, manifest = walk_lesson(lesson)

    assert "Nested text block." in markdown


def test_extract_text_keeps_both_heading_and_paragraph_when_both_present():
    lesson = {
        "id": "lesson-7",
        "title": "Multi-field",
        "items": [
            {"type": "text", "items": [{"heading": "<h2>Key term</h2>", "paragraph": "<p>Definition text.</p>"}]}
        ],
    }
    markdown, _ = walk_lesson(lesson)
    assert "Key term" in markdown
    assert "Definition text." in markdown


def test_walk_lesson_extracts_image_block_with_key_decoding():
    lesson = {
        "id": "lesson-5",
        "title": "Wound Diagram",
        "items": [
            {
                "type": "image",
                "items": [
                    {
                        "media": {
                            "image": {"key": "diagram%2520one.png"}
                        }
                    }
                ],
            }
        ],
    }

    markdown, manifest = walk_lesson(lesson)

    entry = manifest[0]
    assert entry["type"] == "image"
    assert entry["url"] == "https://articulateusercontent.com/diagram%20one.png"
    assert entry["captions_available"] is False
    assert entry["caption_key"] is None
