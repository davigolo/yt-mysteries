import os
from pathlib import Path

import requests

GRAPH_VERSION = "v24.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"


def is_configured() -> bool:
    return bool(os.environ.get("FB_PAGE_ID") and os.environ.get("FB_PAGE_TOKEN"))


def _check(response: requests.Response) -> dict:
    if not response.ok:
        raise RuntimeError(f"Facebook respondió {response.status_code}: {response.text[:500]}")
    return response.json()


def upload_reel(video: Path, description: str) -> str:
    page_id, token = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
    start = _check(requests.post(
        f"{GRAPH_URL}/{page_id}/video_reels",
        data={"upload_phase": "start", "access_token": token},
        timeout=60,
    ))
    video_id = start["video_id"]
    data = video.read_bytes()
    _check(requests.post(
        start.get("upload_url", f"https://rupload.facebook.com/video-upload/{GRAPH_VERSION}/{video_id}"),
        headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(data))},
        data=data,
        timeout=600,
    ))
    _check(requests.post(
        f"{GRAPH_URL}/{page_id}/video_reels",
        data={
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": description,
            "access_token": token,
        },
        timeout=120,
    ))
    return video_id
