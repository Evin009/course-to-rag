import responses
import json

import pytest

from aicc_demo.extractor import (
    course_to_markdown,
    extract_blocks,
    extract_course,
    fetch_course_json,
    parse_share_id,
    save_course_text,
    strip_html,
    walk_lesson,
)

SHARE_ID_SUTURE = "9enP3jMLBp-wenr5LIa0R"

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
    # Keys are used raw: the CDN serves `%2520` keys only in that form.
    assert entry["url"] == "https://articulateusercontent.com/abc%2520def.mp4"
    assert entry["captions_available"] is True
    assert entry["caption_key"] == "abc%2520def.vtt"


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


def test_walk_lesson_extracts_image_block_with_raw_key():
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
    assert entry["url"] == "https://articulateusercontent.com/diagram%2520one.png"
    assert entry["captions_available"] is False
    assert entry["caption_key"] is None


@pytest.mark.parametrize("url", [
    "https://share.articulate.com/9enP3jMLBp-wenr5LIa0R",
    "https://share.articulate.com/9enP3jMLBp-wenr5LIa0R#/lessons/abc",
    "https://rise.articulate.com/share/9enP3jMLBp-wenr5LIa0R#/",
    "https://share.articulate.com/api/instant-links/9enP3jMLBp-wenr5LIa0R/course",
    "  9enP3jMLBp-wenr5LIa0R  ",
])
def test_parse_share_id_accepts_every_link_form(url):
    assert parse_share_id(url) == SHARE_ID_SUTURE


def test_parse_share_id_rejects_non_articulate_url():
    with pytest.raises(ValueError):
        parse_share_id("https://example.com/course")


def test_strip_html_keeps_list_items_on_separate_lines():
    html = "<ul><li>Granny knot&nbsp;</li><li>Square knot</li></ul>"
    assert strip_html(html) == "• Granny knot\n• Square knot"


def test_extract_blocks_labels_heading_paragraph_and_list_items():
    lesson = {
        "id": "l1",
        "title": "Suture Materials",
        "items": [
            {"type": "text", "items": [{"heading": "<p>Selection</p>", "paragraph": "<p>Based on tissue.</p>"}]},
            {"type": "list", "items": [{"paragraph": "<p>healing</p>"}, {"paragraph": "<p>location</p>"}]},
        ],
    }

    blocks = extract_blocks(lesson)

    assert blocks == [
        {"label": "heading", "text": "Selection"},
        {"label": "paragraph", "text": "Based on tissue."},
        {"label": "list_item", "text": "healing"},
        {"label": "list_item", "text": "location"},
    ]


def test_extract_blocks_reads_flashcard_faces_and_step_titles():
    lesson = {
        "id": "l1",
        "title": "Terms",
        "items": [
            {"type": "interactive", "items": [
                {"front": {"description": "<p>Pliability</p>"}, "back": {"description": "<p>Ease of handling.</p>"}},
                {"type": "step", "title": "Needle Parts", "description": "<p>Eye, body, point.</p>"},
            ]},
        ],
    }

    blocks = extract_blocks(lesson)

    assert [b["label"] for b in blocks] == ["heading", "paragraph", "heading", "paragraph"]
    assert [b["text"] for b in blocks] == ["Pliability", "Ease of handling.", "Needle Parts", "Eye, body, point."]


def test_extract_blocks_drops_rise_placeholders_dividers_and_hidden_items():
    default_image = {"image": {"key": "assets/rise/assets/block-defaults/mountains.jpg"}}
    lesson = {
        "id": "l1",
        "title": "Intro",
        "items": [
            {"type": "divider", "items": [{"title": "CONTINUE"}]},
            {"type": "text", "items": [{"heading": "<strong>Subheading</strong>", "paragraph": "<p>Real text.</p>"}]},
            {"type": "interactive", "items": [
                {"type": "summary", "title": "Summary", "description": "<p>Lorem ipsum dolor sit amet.</p>"},
                {"title": "Hidden", "isHidden": True},
                {"front": {"description": "<p>Term</p>", "media": default_image}},
            ]},
        ],
    }

    blocks = extract_blocks(lesson)

    assert blocks == [
        {"label": "paragraph", "text": "Real text."},
        {"label": "heading", "text": "Term"},
    ]


def test_extract_blocks_titles_video_from_embed_or_preceding_heading():
    lesson = {
        "id": "l1",
        "title": "Knots",
        "items": [
            {"type": "interactive", "items": [
                {"type": "step", "title": "Square Knot", "media": {"embed": {"originalUrl": "https://youtu.be/abcdefghijk"}}},
                {"media": {"embed": {"originalUrl": "https://youtu.be/bcdefghijkl", "title": "YT Title"}}},
            ]},
        ],
    }

    videos = [b for b in extract_blocks(lesson) if b["label"] == "video"]

    assert [v["title"] for v in videos] == ["Square Knot", "YT Title"]
    assert [v["media"]["block_order"] for v in videos] == [0, 1]


def test_extract_course_marks_sections_and_saves_json_and_markdown(tmp_path):
    raw = {"course": {
        "title": "Suturing",
        "shareId": SHARE_ID_SUTURE,
        "description": "<p>Welcome.</p>",
        "lessons": [
            {"id": "s1", "title": "Basics", "type": "section"},
            {"id": "l1", "title": "Needles", "type": "blocks", "items": [
                {"type": "text", "items": [{"paragraph": "<p>Curved needles.</p>"}]},
            ]},
        ],
    }}

    course = extract_course(raw, source_url="https://share.articulate.com/x")
    json_path, md_path = save_course_text(course, str(tmp_path))

    assert [l["label"] for l in course["lessons"]] == ["section", "title"]
    assert json.load(open(json_path))["lessons"][1]["blocks"] == [{"label": "paragraph", "text": "Curved needles."}]
    markdown = open(md_path).read()
    assert markdown.startswith("# Suturing")
    assert "## Basics" in markdown and "### Needles" in markdown and "Curved needles." in markdown
    assert course_to_markdown(course) == markdown


def test_extract_blocks_moves_process_summary_after_steps():
    lesson = {
        "id": "l1",
        "title": "Process",
        "items": [{"type": "interactive", "items": [
            {"type": "intro", "title": "Intro"},
            {"type": "summary", "title": "Wrap-up"},
            {"type": "step", "title": "Step one"},
        ]}],
    }

    assert [b["text"] for b in extract_blocks(lesson)] == ["Intro", "Step one", "Wrap-up"]


def test_image_uses_crushed_key_when_rise_does():
    lesson = {"id": "l", "title": "T", "items": [{"type": "image", "items": [{"media": {"image": {
        "key": "c/orig%2520name.jpeg", "crushedKey": "c/small.jpg", "useCrushedKey": True}}}]}]}

    _, manifest = walk_lesson(lesson)

    assert manifest[0]["url"] == "https://articulateusercontent.com/c/small.jpg"
