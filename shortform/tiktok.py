import os
import time
from pathlib import Path

import requests

API_URL = "https://open.tiktokapis.com/v2"
TITLE_LIMIT = 2200
SINGLE_CHUNK_LIMIT = 64 * 1024 * 1024
CHUNK_SIZE = 10 * 1024 * 1024


def is_configured() -> bool:
    return all(os.environ.get(name) for name in ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"))


def _check(response: requests.Response) -> dict:
    body = response.json() if response.content else {}
    error = body.get("error", {})
    if not response.ok or (error.get("code") not in (None, "", "ok")):
        raise RuntimeError(f"TikTok respondió {response.status_code}: {response.text[:500]}")
    return body.get("data", body)


def _access_token() -> str:
    response = requests.post(
        f"{API_URL}/oauth/token/",
        data={
            "client_key": os.environ["TIKTOK_CLIENT_KEY"],
            "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
            "grant_type": "refresh_token",
            "refresh_token": os.environ["TIKTOK_REFRESH_TOKEN"],
        },
        timeout=30,
    )
    body = response.json()
    if "access_token" not in body:
        raise RuntimeError(f"TikTok no renovó el token: {response.text[:500]}")
    return body["access_token"]


def _privacy_level(headers: dict) -> str:
    creator = _check(requests.post(f"{API_URL}/post/publish/creator_info/query/", headers=headers, timeout=30))
    options = creator.get("privacy_level_options", [])
    preferred = os.environ.get("TIKTOK_PRIVACY_LEVEL", "PUBLIC_TO_EVERYONE")
    return preferred if preferred in options else "SELF_ONLY"


def _chunks(size: int) -> tuple[int, int]:
    if size <= SINGLE_CHUNK_LIMIT:
        return size, 1
    return CHUNK_SIZE, size // CHUNK_SIZE


def _wait_until_published(publish_id: str, headers: dict, timeout: int = 300) -> str:
    deadline = time.monotonic() + timeout
    status = {}
    while time.monotonic() < deadline:
        status = _check(requests.post(
            f"{API_URL}/post/publish/status/fetch/", headers=headers, json={"publish_id": publish_id}, timeout=30,
        ))
        if status.get("status") == "PUBLISH_COMPLETE":
            return status.get("status")
        if status.get("status") == "FAILED":
            raise RuntimeError(f"TikTok rechazó la publicación: {status.get('fail_reason')}")
        time.sleep(10)
    return status.get("status", "UNKNOWN")


def upload_video(video: Path, caption: str) -> tuple[str, str]:
    headers = {"Authorization": f"Bearer {_access_token()}", "Content-Type": "application/json; charset=UTF-8"}
    privacy = _privacy_level(headers)
    data = video.read_bytes()
    chunk_size, total_chunks = _chunks(len(data))
    init = _check(requests.post(
        f"{API_URL}/post/publish/video/init/",
        headers=headers,
        json={
            "post_info": {
                "title": caption[:TITLE_LIMIT],
                "privacy_level": privacy,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                "video_cover_timestamp_ms": 1000,
                "is_aigc": True,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": len(data),
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            },
        },
        timeout=60,
    ))
    for index in range(total_chunks):
        start = index * chunk_size
        end = len(data) if index == total_chunks - 1 else start + chunk_size
        response = requests.put(
            init["upload_url"],
            headers={"Content-Type": "video/mp4", "Content-Range": f"bytes {start}-{end - 1}/{len(data)}"},
            data=data[start:end],
            timeout=600,
        )
        if response.status_code not in (200, 201, 206):
            raise RuntimeError(f"TikTok falló al subir el fragmento {index}: {response.status_code} {response.text[:300]}")
    status = _wait_until_published(init["publish_id"], headers)
    return init["publish_id"], f"{status} ({privacy})"
