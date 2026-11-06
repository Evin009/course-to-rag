"""One key per course, so the same course can't get two projects.

Different URLs for the same course reduce to the same key:
  https://usflearn.instructure.com/courses/2151228/modules?x=1 -> canvas:usflearn.instructure.com:2151228
  https://share.articulate.com/AbC123xyz0#/lessons/q           -> share:AbC123xyz0
  https://webapps.usf.edu/.../asymptotic/index.html            -> export:webapps.usf.edu/.../asymptotic
(An old rise.articulate.com/share link and its current share.articulate.com
link have different ids, so they are not recognised as the same course.)
"""
import re
from urllib.parse import urlsplit

from aicc_demo.canvas import parse_canvas_course_url
from aicc_demo.extractor import parse_share_id


def course_key(url: str) -> str:
    url = url.strip()
    try:
        base, course_id = parse_canvas_course_url(url)
        return f"canvas:{urlsplit(base).netloc.lower()}:{course_id}"
    except ValueError:
        pass
    if re.search(r"share\.articulate\.com/|rise\.articulate\.com/share/", url):
        try:
            return f"share:{parse_share_id(url)}"
        except ValueError:
            pass
    parts = urlsplit(url)
    path = re.sub(r"/index\.html?$", "", parts.path, flags=re.IGNORECASE).rstrip("/")
    return f"export:{parts.netloc.lower()}{path}"
