import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from longform.playlists import add_to_playlist

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
MAX_DESCRIPTION = 4900
RETRYABLE_UPLOAD_CODES = {410, 500, 502, 503, 504}
UPLOAD_ATTEMPTS = 3


def credentials() -> Credentials:
    return Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )


def hashtags(topic_tags: list[str], base: str, limit: int = 8) -> str:
    tags = []
    for raw in [*topic_tags, *base.split()]:
        tag = "#" + re.sub(r"[^\w]", "", raw.lstrip("#"))
        if len(tag) > 2 and tag.lower() not in [t.lower() for t in tags]:
            tags.append(tag)
    return " ".join(tags[:limit])


def _clock(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def build_description(summary: str, chapters: list[tuple[float, str]], sources: list[dict], credits: list[str], hashtags: str) -> str:
    parts = [summary.strip(), "Chapters:\n" + "\n".join(f"{_clock(t)} {title}" for t, title in chapters)]
    domains = list(dict.fromkeys(s["title"] if "." in s["title"] else urlparse(s["uri"]).netloc for s in sources))
    if domains:
        parts.append("Sources consulted: " + ", ".join(domains[:15]))
    parts.append(
        "Narration voice and some illustrative images are AI-generated reconstructions. "
        "Archive images are public domain or Creative Commons."
    )
    footer = hashtags
    text = "\n\n".join(parts)
    if credits:
        credit_block = "Image credits (Wikimedia Commons):\n" + "\n".join(f"- {c}" for c in dict.fromkeys(credits))
        room = MAX_DESCRIPTION - len(text) - len(footer) - 4
        if len(credit_block) > room:
            credit_block = credit_block[:room].rsplit("\n", 1)[0]
        if room > 200:
            text += "\n\n" + credit_block
    return f"{text}\n\n{footer}"


def privacy_status(default: str, publish_at: datetime | None) -> dict:
    if not publish_at:
        return {"privacyStatus": default}
    return {"privacyStatus": "private", "publishAt": publish_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def insert_video(youtube, body: dict, video: Path, chunksize: int) -> str:
    for attempt in range(1, UPLOAD_ATTEMPTS + 1):
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=MediaFileUpload(str(video), mimetype="video/mp4", chunksize=chunksize, resumable=True),
        )
        try:
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"\rSubida: {status.progress() * 100:.0f}%", end="", flush=True)
            print()
            return response["id"]
        except HttpError as e:
            if e.resp.status not in RETRYABLE_UPLOAD_CODES or attempt == UPLOAD_ATTEMPTS:
                raise
            print(f"\nSubida interrumpida ({e.resp.status}), se reintenta desde cero ({attempt}/{UPLOAD_ATTEMPTS})")
            time.sleep(20 * attempt)
    raise RuntimeError("No se pudo subir el vídeo")


def add_to_playlists(youtube, video_id: str, playlists: list[dict]) -> None:
    for playlist in playlists:
        add_to_playlist(youtube, video_id, playlist["title"], playlist["description"])


def upload(
    video: Path, thumbnail: Path, captions: Path, title: str, description: str, tags: list[str], playlists: list[dict], config: dict,
    publish_at: datetime | None = None,
) -> str:
    youtube = build("youtube", "v3", credentials=credentials(), cache_discovery=False)
    settings = config["upload"]
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": settings["category_id"],
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            **privacy_status(settings["privacy"], publish_at),
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": settings["contains_synthetic_media"],
            "publicStatsViewable": True,
        },
    }
    video_id = insert_video(youtube, body, video, 64 * 1024 * 1024)

    try:
        youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumbnail), mimetype="image/jpeg")).execute()
    except HttpError as e:
        print(f"No se pudo poner la miniatura (¿canal sin verificar por teléfono?): {e}")
    try:
        youtube.captions().insert(
            part="snippet",
            body={"snippet": {"videoId": video_id, "language": "en", "name": "English", "isDraft": False}},
            media_body=MediaFileUpload(str(captions), mimetype="application/octet-stream"),
        ).execute()
    except HttpError as e:
        print(f"No se pudieron subir los subtítulos: {e}")
    add_to_playlists(youtube, video_id, playlists)
    return video_id
