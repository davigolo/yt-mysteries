from googleapiclient.errors import HttpError

_cache: dict[str, str] = {}


def _find_playlist(youtube, title: str) -> str | None:
    if not _cache:
        request = youtube.playlists().list(part="snippet", mine=True, maxResults=50)
        while request is not None:
            response = request.execute()
            for item in response.get("items", []):
                _cache.setdefault(item["snippet"]["title"], item["id"])
            request = youtube.playlists().list_next(request, response)
    return _cache.get(title)


def _ensure_playlist(youtube, title: str, description: str) -> str:
    playlist_id = _find_playlist(youtube, title)
    if playlist_id:
        return playlist_id
    response = youtube.playlists().insert(part="snippet,status", body={
        "snippet": {"title": title, "description": description},
        "status": {"privacyStatus": "public"},
    }).execute()
    print(f"Lista de reproducción creada: {title}")
    _cache[title] = response["id"]
    return response["id"]


def add_to_playlist(youtube, video_id: str, title: str, description: str) -> None:
    try:
        playlist_id = _ensure_playlist(youtube, title, description)
        youtube.playlistItems().insert(part="snippet", body={
            "snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}},
        }).execute()
        print(f"Añadido a la lista: {title}")
    except HttpError as e:
        print(f"No se pudo añadir a la lista {title}: {e}")
