from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from longform.upload import add_to_playlists, credentials


def build_description(summary: str, episode_id: str, hashtags: str) -> str:
    return f"{summary.strip()}\n\n▶ Full investigation: https://youtu.be/{episode_id}\n\n{hashtags}"


def upload_short(
    video: Path, thumbnail: Path | None, title: str, description: str, tags: list[str], episode_id: str,
    playlists: list[dict], config: dict,
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
            "privacyStatus": settings["privacy"],
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": settings["contains_synthetic_media"],
            "publicStatsViewable": True,
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
    if thumbnail:
        try:
            youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumbnail), mimetype="image/jpeg")).execute()
            print("Miniatura personalizada subida")
        except HttpError as e:
            print(f"No se pudo poner la miniatura: {e}")
    try:
        youtube.commentThreads().insert(part="snippet", body={"snippet": {
            "videoId": video_id,
            "topLevelComment": {"snippet": {"textOriginal": f"The full investigation is here: https://youtu.be/{episode_id}"}},
        }}).execute()
    except HttpError as e:
        print(f"No se pudo publicar el comentario con el enlace: {e}")
    add_to_playlists(youtube, video_id, playlists)
    return video_id
