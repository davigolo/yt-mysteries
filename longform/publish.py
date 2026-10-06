from datetime import datetime, timedelta, timezone

from googleapiclient.errors import HttpError

WRITABLE_STATUS = ("embeddable", "license", "publicStatsViewable", "selfDeclaredMadeForKids", "containsSyntheticMedia")


def fetch_statuses(youtube, video_ids: list[str]) -> dict[str, dict]:
    statuses = {}
    unique = list(dict.fromkeys(video_ids))
    for i in range(0, len(unique), 50):
        response = youtube.videos().list(part="status", id=",".join(unique[i:i + 50]), maxResults=50).execute()
        statuses.update({item["id"]: item["status"] for item in response.get("items", [])})
    return statuses


def _uploaded_at(entry: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(entry["uploaded_at"])
    except (KeyError, ValueError):
        return None


def pending(entries: list[dict], days: int = 14) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return [e for e in entries if e.get("video_id") and (_uploaded_at(e) or since) > since]


def make_public(youtube, video_id: str, status: dict, overrides: dict, dry_run: bool) -> bool:
    current = {k: status[k] for k in WRITABLE_STATUS if k in status}
    body = {"id": video_id, "status": {**current, **overrides, "privacyStatus": "public"}}
    if dry_run:
        print(f"[dry-run] Se publicaría {video_id}")
        return True
    try:
        youtube.videos().update(part="status", body=body).execute()
        return True
    except HttpError as e:
        print(f"No se pudo publicar {video_id}: {e}")
        return False


def publish_due(
    youtube, entries: list[dict], statuses: dict[str, dict], after_hours: float, overrides: dict,
    limit: int, requires: str | None = None, dry_run: bool = False,
) -> int:
    now = datetime.now(timezone.utc)
    published = 0
    for entry in sorted(entries, key=_uploaded_at):
        video_id = entry["video_id"]
        status = statuses.get(video_id)
        if not status or status.get("privacyStatus") != "unlisted":
            continue
        age = (now - _uploaded_at(entry)).total_seconds() / 3600
        label = f"{video_id} ({entry.get('title', '')})"
        if age < after_hours:
            print(f"Esperando: {label}, oculto hace {age:.1f} h")
            continue
        if status.get("uploadStatus") != "processed":
            print(f"Sin procesar ({status.get('uploadStatus')}): {label}")
            continue
        dependency = entry.get(requires) if requires else None
        if dependency and statuses.get(dependency, {}).get("privacyStatus") != "public":
            print(f"Esperando a que el vídeo {dependency} sea público: {label}")
            continue
        if published >= limit and age < 2 * after_hours:
            print(f"Ya se ha publicado el máximo de esta franja; queda para la siguiente: {label}")
            continue
        if make_public(youtube, video_id, status, overrides, dry_run):
            status["privacyStatus"] = "public"
            published += 1
            print(f"Publicado: {label}")
    return published
