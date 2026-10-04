from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from longform.upload import credentials

MAX_DESCRIPTION = 4900


def build_description(summary: str, episode_id: str, credits: list[str], hashtags: str) -> str:
    text = (
        f"{summary.strip()}\n\n"
        f"▶ Full investigation: https://youtu.be/{episode_id}\n\n"
        "Narration voice and some illustrative images are AI-generated reconstructions. "
        "Archive images are public domain or Creative Commons."
    )
    if credits:
        block = "Image credits (Wikimedia Commons):\n" + "\n".join(f"- {c}" for c in dict.fromkeys(credits))
        room = MAX_DESCRIPTION - len(text) - len(hashtags) - 4
        if len(block) > room:
            block = block[:room].rsplit("\n", 1)[0]
        if room > 200:
            text += "\n\n" + block
    return f"{text}\n\n{hashtags}"


def upload_short(video: Path, title: str, description: str, tags: list[str], episode_id: str, config: dict) -> str:
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
        media_body=MediaFileUpload(str(video), mimetype="video/mp4", chunksize=-1, resumable=True),
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    video_id = response["id"]
    try:
        youtube.commentThreads().insert(part="snippet", body={"snippet": {
            "videoId": video_id,
            "topLevelComment": {"snippet": {"textOriginal": f"The full investigation is here: https://youtu.be/{episode_id}"}},
        }}).execute()
    except HttpError as e:
        print(f"No se pudo publicar el comentario con el enlace: {e}")
    return video_id
