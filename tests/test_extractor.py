import responses
from aicc_demo.extractor import fetch_course_json, SHARE_ID_SUTURE

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
