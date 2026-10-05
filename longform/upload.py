import os
import re
from pathlib import Path
from urllib.parse import urlparse

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
MAX_DESCRIPTION = 4900


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


def upload(video: Path, thumbnail: Path, captions: Path, title: str, description: str, tags: list[str], config: dict) -> str:
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
            "privacyStatus": settings["privacy"],
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": settings["contains_synthetic_media"],
        },
    }
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(video), mimetype="video/mp4", chunksize=64 * 1024 * 1024, resumable=True),
    )
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"\rSubida: {status.progress() * 100:.0f}%", end="", flush=True)
    print()
    video_id = response["id"]

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
    return video_id
