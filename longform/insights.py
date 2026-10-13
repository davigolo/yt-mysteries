from datetime import date, timedelta
from statistics import mean

from googleapiclient.discovery import build

from longform.upload import credentials

MIN_VIDEOS_FOR_INSIGHTS = 3
MIN_VIDEOS_PER_FORMAT = 2
MIN_VIEWS = 100
MIN_SHORTS_FOR_INSIGHTS = 6
SETTLE_DAYS = 3


def fetch_performance(entries: list[dict], days: int = 90, min_views: int = MIN_VIEWS) -> list[dict]:
    analytics = build("youtubeAnalytics", "v2", credentials=credentials(), cache_discovery=False)
    response = analytics.reports().query(
        ids="channel==MINE",
        startDate=(date.today() - timedelta(days=days)).isoformat(),
        endDate=date.today().isoformat(),
        metrics="views,averageViewPercentage,likes,subscribersGained",
        dimensions="video",
        sort="-views",
        maxResults=200,
    ).execute()
    by_id = {e["video_id"]: e for e in entries if e.get("video_id")}
    performance = []
    for video_id, views, retention, likes, subscribers in response.get("rows", []):
        entry = by_id.get(video_id)
        if entry and int(views) >= min_views:
            performance.append({
                **entry,
                "views": int(views),
                "retention": float(retention),
                "likes": int(likes),
                "subscribers": int(subscribers),
            })
    return performance


def settled(entries: list[dict], days: int = SETTLE_DAYS) -> list[dict]:
    limit = (date.today() - timedelta(days=days)).isoformat()
    return [e for e in entries if e.get("date", "") <= limit]


def _score(video: dict) -> float:
    return video["views"] * (video["retention"] / 100)


def _line(video: dict) -> str:
    return (
        f'- "{video["title"]}" (type {video.get("format", "")}, {video["views"]} views, '
        f'{video["retention"]:.0f}% average viewed, {video["subscribers"]} subscribers gained)'
    )


def build_insights(performance: list[dict]) -> str:
    if len(performance) < MIN_VIDEOS_FOR_INSIGHTS:
        return ""
    ranked = sorted(performance, key=_score, reverse=True)
    best = ranked[:min(5, len(ranked) // 2)]
    worst = ranked[len(best):][-3:] if len(ranked) >= 6 else []
    lines = ["Real performance of previous episodes. Imitate the kind of case, angle and title of the best ones"]
    lines.append("(without repeating the case) and avoid what the worst ones have in common.")
    lines.append("BEST:")
    lines += [_line(v) for v in best]
    if worst:
        lines.append("WORST:")
        lines += [_line(v) for v in worst]
    return "\n".join(lines)


def case_performance(history: list[dict], episodes: list[dict], shorts: list[dict]) -> list[dict]:
    episode_views = {e["video_id"]: e["views"] for e in episodes}
    cases = []
    for entry in history:
        video_id = entry.get("video_id")
        own = [s for s in shorts if s.get("episode_id") == video_id]
        if not own:
            continue
        cases.append({
            **entry,
            "shorts": len(own),
            "short_views": mean(s["views"] for s in own),
            "short_retention": mean(s["retention"] for s in own),
            "subscribers": sum(s["subscribers"] for s in own),
            "episode_views": episode_views.get(video_id, 0),
        })
    return cases


def _case_line(case: dict) -> str:
    return (
        f'- "{case["topic"]}" (type {case.get("format", "")}, episode "{case["title"]}"): its {case["shorts"]} Shorts averaged '
        f'{case["short_views"]:.0f} views and {case["short_retention"]:.0f}% viewed, {case["subscribers"]} subscribers gained; '
        f'episode {case["episode_views"]} views'
    )


def build_case_insights(cases: list[dict]) -> str:
    if len(cases) < MIN_VIDEOS_FOR_INSIGHTS:
        return ""
    ranked = sorted(cases, key=lambda c: c["short_views"] * c["short_retention"], reverse=True)
    best = ranked[:max(1, min(4, len(ranked) // 2))]
    worst = ranked[len(best):][-2:]
    lines = [
        "Real performance of previous cases on this channel, measured by their promotional Shorts (Shorts bring almost all",
        "the audience). Pick a NEW case with the same kind of hook as the best ones (without repeating them) and avoid what",
        "the worst ones have in common.",
        "BEST:",
        *[_case_line(c) for c in best],
    ]
    if worst:
        lines += ["WORST:", *[_case_line(c) for c in worst]]
    return "\n".join(lines)


def case_format_weights(cases: list[dict]) -> dict[str, float]:
    by_format: dict[str, list[float]] = {}
    for case in cases:
        by_format.setdefault(case.get("format", ""), []).append(case["short_views"])
    if not by_format:
        return {}
    overall = mean(v for values in by_format.values() for v in values) or 1
    return {
        name: min(max(mean(values) / overall, 0.5), 2.0)
        for name, values in by_format.items()
        if len(values) >= MIN_VIDEOS_PER_FORMAT
    }


def _short_line(short: dict) -> str:
    return f'- "{short["title"]}" ({short["views"]} views, {short["retention"]:.0f}% viewed, {short["likes"]} likes)'


def build_short_insights(shorts: list[dict]) -> str:
    if len(shorts) < MIN_SHORTS_FOR_INSIGHTS:
        return ""
    ranked = sorted(shorts, key=_score, reverse=True)
    best, worst = ranked[:5], ranked[-3:]
    return "\n".join([
        "Real performance of previous Shorts on this channel. Copy the hook style, title pattern and kind of detail of the",
        "best ones, and avoid what the worst ones have in common.",
        "BEST:",
        *[_short_line(s) for s in best],
        "WORST:",
        *[_short_line(s) for s in worst],
    ])
