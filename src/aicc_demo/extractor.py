import requests

SHARE_ID_SUTURE = "wFfts7vyFk1HxZneZqamI"
INSTANT_LINKS_URL = "https://share.articulate.com/api/instant-links/{share_id}/course"


def fetch_course_json(share_id: str) -> dict:
    url = INSTANT_LINKS_URL.format(share_id=share_id)
    response = requests.post(url, timeout=30)
    response.raise_for_status()
    return response.json()
