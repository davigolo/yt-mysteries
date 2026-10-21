from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def _parse(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def publication_days(weekdays: list[int] | None) -> set[int]:
    if weekdays is None:
        return set(range(7))
    if not weekdays or any(type(day) is not int or day not in range(7) for day in weekdays):
        raise ValueError("Los días de publicación deben ser enteros entre 0 (lunes) y 6 (domingo)")
    return set(weekdays)


def next_slot(
    slots: list[str], tz: str, min_hours: float, taken: list[str], not_before: str | None = None, gap_minutes: int = 30,
    weekdays: list[int] | None = None,
) -> datetime:
    zone = ZoneInfo(tz)
    days = publication_days(weekdays)
    earliest = datetime.now(timezone.utc) + timedelta(hours=min_hours)
    if (after := _parse(not_before)) and after + timedelta(minutes=gap_minutes) > earliest:
        earliest = after + timedelta(minutes=gap_minutes)
    busy = {t.astimezone(timezone.utc).replace(second=0, microsecond=0) for t in filter(None, map(_parse, taken))}
    day = earliest.astimezone(zone).date()
    for offset in range(60):
        local_day = day + timedelta(days=offset)
        if local_day.weekday() not in days:
            continue
        for slot in sorted(slots):
            hour, minute = map(int, slot.split(":"))
            local = datetime(local_day.year, local_day.month, local_day.day, hour, minute, tzinfo=zone)
            candidate = local.astimezone(timezone.utc)
            if candidate >= earliest and candidate not in busy:
                return candidate
    raise RuntimeError("No hay franjas de publicación libres en los próximos 60 días")
