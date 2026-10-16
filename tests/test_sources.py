import base64
import json

import pytest
import responses

from aicc_demo.sources import (
    decode_runtime_data,
    export_asset_url,
    export_folder_url,
    load_course,
)

COURSE = {"course": {"title": "COT5407", "lessons": []}}
RUNTIME_DATA_JS = '__jsonp("runtime-data.js","' + base64.b64encode(json.dumps(COURSE).encode()).decode() + '");'


@pytest.mark.parametrize("url", [
    "https://site.example/eng/cot5407/asymptotic/index.html",
    "https://site.example/eng/cot5407/asymptotic/index.html#/lessons/abc",
    "https://site.example/eng/cot5407/asymptotic/",
    "https://site.example/eng/cot5407/asymptotic",
])
def test_export_folder_url_handles_page_folder_and_fragment(url):
    assert export_folder_url(url) == "https://site.example/eng/cot5407/asymptotic/"


def test_decode_runtime_data_unwraps_jsonp_and_base64():
    assert decode_runtime_data(RUNTIME_DATA_JS) == COURSE


def test_decode_runtime_data_rejects_other_scripts():
    with pytest.raises(ValueError):
        decode_runtime_data("console.log('hi')")


def test_export_asset_url_url_encodes_file_names():
    assets = export_asset_url("https://site.example/c/")
    assert assets("Asymptotic Analysis - FindMin.pdf") == "https://site.example/c/assets/Asymptotic%20Analysis%20-%20FindMin.pdf"
    assert assets("GettyImages-1.png") == "https://site.example/c/assets/GettyImages-1.png"


@responses.activate
def test_load_course_reads_a_web_export():
    responses.add(responses.GET, "https://site.example/c/runtime-data.js", body=RUNTIME_DATA_JS, status=200)

    source = load_course("https://site.example/c/index.html#/")

    assert source.kind == "export"
    assert source.course_json == COURSE
    assert source.location == "https://site.example/c/"
    assert source.asset_url("a b.png") == "https://site.example/c/assets/a%20b.png"


@responses.activate
def test_load_course_uses_the_api_for_share_links():
    responses.add(
        responses.POST,
        "https://share.articulate.com/api/instant-links/9enP3jMLBp-wenr5LIa0R/course",
        json=COURSE,
        status=200,
    )

    source = load_course("https://share.articulate.com/9enP3jMLBp-wenr5LIa0R#/lessons/x")

    assert source.kind == "share"
    assert source.location == "9enP3jMLBp-wenr5LIa0R"
    assert source.asset_url("k/a%2520b.mp4") == "https://articulateusercontent.com/k/a%2520b.mp4"


@responses.activate
def test_load_course_explains_a_site_without_a_course():
    responses.add(responses.GET, "https://example.com/x/runtime-data.js", status=404)

    with pytest.raises(ValueError, match="No Rise course found"):
        load_course("https://example.com/x/index.html")
