import os
import time
from pathlib import Path

import requests

GRAPH_VERSION = "v24.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"
CAPTION_LIMIT = 2200


def is_configured() -> bool:
    return bool(os.environ.get("IG_USER_ID") and _token())


def _token() -> str | None:
    return os.environ.get("IG_ACCESS_TOKEN") or os.environ.get("FB_PAGE_TOKEN")


def _check(response: requests.Response) -> dict:
    if not response.ok:
        raise RuntimeError(f"Instagram respondió {response.status_code}: {response.text[:500]}")
    return response.json()


def _wait_until_ready(container_id: str, token: str, timeout: int = 600) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = _check(requests.get(
            f"{GRAPH_URL}/{container_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=30,
        ))
        if status.get("status_code") == "FINISHED":
            return
        if status.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram no pudo procesar el vídeo: {status}")
        time.sleep(10)
    raise TimeoutError("Instagram no terminó de procesar el vídeo a tiempo")


def upload_reel(video: Path, caption: str) -> str:
    user_id, token = os.environ["IG_USER_ID"], _token()
    container = _check(requests.post(
        f"{GRAPH_URL}/{user_id}/media",
        data={
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption[:CAPTION_LIMIT],
            "share_to_feed": "true",
            "access_token": token,
        },
        timeout=60,
    ))
    container_id = container["id"]
    data = video.read_bytes()
    _check(requests.post(
        container.get("uri", f"https://rupload.facebook.com/ig-api-upload/{GRAPH_VERSION}/{container_id}"),
        headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(data))},
        data=data,
        timeout=600,
    ))
    _wait_until_ready(container_id, token)
    published = _check(requests.post(
        f"{GRAPH_URL}/{user_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=120,
    ))
    return published["id"]
