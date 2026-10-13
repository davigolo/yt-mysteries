from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def _parse(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def next_slot(
    slots: list[str], tz: str, min_hours: float, taken: list[str], not_before: str | None = None, gap_minutes: int = 30,
) -> datetime:
    zone = ZoneInfo(tz)
    earliest = datetime.now(timezone.utc) + timedelta(hours=min_hours)
    if (after := _parse(not_before)) and after + timedelta(minutes=gap_minutes) > earliest:
        earliest = after + timedelta(minutes=gap_minutes)
    busy = {t.astimezone(timezone.utc).replace(second=0, microsecond=0) for t in filter(None, map(_parse, taken))}
    day = earliest.astimezone(zone).date()
    for offset in range(60):
        for slot in sorted(slots):
            hour, minute = map(int, slot.split(":"))
            local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone) + timedelta(days=offset)
            candidate = local.astimezone(timezone.utc)
            if candidate >= earliest and candidate not in busy:
                return candidate
    raise RuntimeError("No hay franjas de publicación libres en los próximos 60 días")
