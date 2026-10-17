from datetime import date, datetime, timedelta
from statistics import mean, median
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from longform.upload import credentials

MIN_VIDEOS_FOR_INSIGHTS = 2
MIN_VIDEOS_PER_FORMAT = 2
MIN_VIEWS = 100
MIN_EPISODE_VIEWS = 20
MIN_ENGAGED_VIEWS = 50
MIN_SHORTS_FOR_INSIGHTS = 4
SETTLE_DAYS = 3
RETENTION_TARGET = 40
SHORT_RETENTION_TARGET = 75
PERFORMANCE_METRICS = "views,engagedViews,averageViewPercentage,averageViewDuration,likes,subscribersGained"


def fetch_performance(entries: list[dict], days: int = 90, min_views: int = MIN_VIEWS) -> list[dict]:
    by_id = {e["video_id"]: e for e in entries if e.get("video_id")}
    if not by_id:
        return []
    analytics = build("youtubeAnalytics", "v2", credentials=credentials(), cache_discovery=False)
    start = (date.today() - timedelta(days=days)).isoformat()
    available = analytics.reports().query(
        ids="channel==MINE",
        startDate=start,
        endDate=date.today().isoformat(),
        metrics=PERFORMANCE_METRICS,
        dimensions="day",
        sort="-day",
        maxResults=1,
    ).execute()
    if not available.get("rows"):
        print("Analytics todavía no devuelve días con datos")
        return []
    end = available["rows"][0][0]
    limit = date.fromisoformat(end) - timedelta(days=SETTLE_DAYS)
    youtube = build("youtube", "v3", credentials=credentials(), cache_discovery=False)
    eligible = {}
    ids = list(by_id)
    for offset in range(0, len(ids), 50):
        response = youtube.videos().list(
            part="snippet,status", id=",".join(ids[offset:offset + 50]),
        ).execute()
        for video in response.get("items", []):
            if video["status"]["privacyStatus"] != "public":
                continue
            published = video["snippet"]["publishedAt"]
            published_date = datetime.fromisoformat(published.replace("Z", "+00:00")).astimezone(
                ZoneInfo("America/Los_Angeles"),
            ).date()
            if published_date <= limit:
                eligible[video["id"]] = {
                    **by_id[video["id"]], "published_at": published, "analytics_end": end,
                }
    print(f"Analytics hasta {end}: {len(eligible)} vídeos públicos con al menos {SETTLE_DAYS} días de datos")
    performance = []
    ids = list(eligible)
    for offset in range(0, len(ids), 200):
        response = analytics.reports().query(
            ids="channel==MINE",
            startDate=start,
            endDate=end,
            metrics=PERFORMANCE_METRICS,
            dimensions="video",
            filters=f"video=={','.join(ids[offset:offset + 200])}",
            sort="-views",
            maxResults=200,
        ).execute()
        for video_id, views, engaged, retention, seconds, likes, subscribers in response.get("rows", []):
            if int(views) < min_views:
                continue
            performance.append({
                **eligible[video_id],
                "views": int(views),
                "engaged_views": int(engaged),
                "retention": float(retention),
                "average_seconds": float(seconds),
                "likes": int(likes),
                "subscribers": int(subscribers),
            })
    return performance


def _score(video: dict) -> float:
    retention = min(video["retention"] / 100, 1)
    subscriber_rate = video["subscribers"] / max(video["engaged_views"], 1)
    return 0.8 * retention + 0.2 * min(subscriber_rate / 0.02, 1)


def _eligible_shorts(shorts: list[dict]) -> list[dict]:
    return [s for s in shorts if s["views"] >= MIN_VIEWS and s["engaged_views"] >= MIN_ENGAGED_VIEWS]


def _diagnosis(video: dict) -> str:
    if video["retention"] < RETENTION_TARGET:
        return f"; below the {RETENTION_TARGET}% retention target: the hook or the script lost viewers"
    return "; retention meets the episode target; impressions and CTR are unavailable, so do not diagnose packaging"


def _line(video: dict) -> str:
    return (
        f'- "{video["title"]}" (type {video.get("format", "")}, {video["views"]} views, '
        f'{video["retention"]:.0f}% average viewed, {video["subscribers"]} subscribers gained{_diagnosis(video)})'
    )


def build_insights(performance: list[dict]) -> str:
    performance = [e for e in performance if e["views"] >= MIN_EPISODE_VIEWS]
    if not performance:
        return ""
    lines = [
        "LONG-FORM FEEDBACK (not Shorts): early, low-volume evidence, not proof of what caused the results.",
        "Aim for at least 40% average viewed. Even the strongest episode is not a template if it misses that target.",
        "For low retention, test a shorter opening, earlier evidence and less repeated context; do not promise more twists.",
        *[_line(v) for v in sorted(performance, key=lambda e: e["retention"], reverse=True)[:6]],
    ]
    return "\n".join(lines)


def case_performance(history: list[dict], episodes: list[dict], shorts: list[dict]) -> list[dict]:
    episode_views = {e["video_id"]: e["views"] for e in episodes}
    cases = []
    for entry in history:
        video_id = entry.get("video_id")
        own = _eligible_shorts([s for s in shorts if s.get("episode_id") == video_id])
        if len(own) < 2:
            continue
        engaged = sum(s["engaged_views"] for s in own)
        cases.append({
            **entry,
            "shorts": len(own),
            "short_views": median(s["views"] for s in own),
            "short_retention": sum(s["retention"] * s["engaged_views"] for s in own) / engaged,
            "quality": mean(_score(s) for s in own),
            "subscribers": sum(s["subscribers"] for s in own),
            "episode_views": episode_views.get(video_id, 0),
        })
    return cases


def _case_line(case: dict) -> str:
    return (
        f'- "{case["topic"]}" (type {case.get("format", "")}, episode "{case["title"]}"): its {case["shorts"]} eligible Shorts had '
        f'{case["short_views"]:.0f} median views and {case["short_retention"]:.0f}% engaged-view-weighted retention, '
        f'{case["subscribers"]} subscribers gained; '
        f'episode {case["episode_views"]} views'
    )


def build_case_insights(cases: list[dict]) -> str:
    if len(cases) < MIN_VIDEOS_FOR_INSIGHTS:
        return ""
    ranked = sorted(cases, key=lambda c: c["quality"], reverse=True)
    best = ranked[:max(1, min(4, len(ranked) // 2))]
    worst = ranked[len(best):][-2:]
    lines = [
        "Real performance of previous cases on this channel, measured by their promotional Shorts (Shorts bring almost all",
        "the audience). Pick a NEW case with the same kind of hook as the best ones (without repeating them) and avoid what",
        "the worst ones have in common.",
        "These are Shorts signals, not evidence of long-form retention or measured Shorts-to-episode conversion.",
        "BEST:",
        *[_case_line(c) for c in best],
    ]
    if worst:
        lines += ["WORST:", *[_case_line(c) for c in worst]]
    return "\n".join(lines)


def case_format_weights(cases: list[dict]) -> dict[str, float]:
    by_format: dict[str, list[float]] = {}
    for case in cases:
        by_format.setdefault(case.get("format", ""), []).append(case["quality"])
    if not by_format:
        return {}
    overall = mean(v for values in by_format.values() for v in values) or 1
    return {
        name: min(max(mean(values) / overall, 0.5), 2.0)
        for name, values in by_format.items()
        if len(values) >= MIN_VIDEOS_PER_FORMAT
    }


def _short_line(short: dict) -> str:
    evidence = short.get("hook") or short.get("angle", "")
    return (
        f'- "{short["title"]}" ({short["views"]} views, {short["engaged_views"]} engaged views, '
        f'{short["retention"]:.0f}% viewed, {short["average_seconds"]:.0f}s average watched, '
        f'{short["subscribers"]} subscribers gained). Hook/angle: {evidence}'
    )


def build_short_insights(shorts: list[dict]) -> str:
    shorts = _eligible_shorts(shorts)
    if len(shorts) < MIN_SHORTS_FOR_INSIGHTS:
        return ""
    ranked = sorted(shorts, key=_score, reverse=True)
    best = [s for s in ranked if s["retention"] >= SHORT_RETENTION_TARGET][:3]
    subscribers = sorted(
        [s for s in shorts if s["retention"] >= 60 and s["subscribers"] >= 2],
        key=lambda s: s["subscribers"] / s["engaged_views"], reverse=True,
    )[:2]
    worst = [s for s in reversed(ranked) if s["retention"] < 60][:3]
    return "\n".join([
        "SHORTS FEEDBACK: only public, settled Shorts with at least 100 views and 50 engaged views.",
        "Ranked by 80% capped retention and 20% subscriber yield (saturated at 2% of engaged views), not raw reach.",
        "Use these as hypotheses about concrete angles and hooks, never as facts about a different case.",
        "Target at least 75% average viewed for Shorts; the 40% episode threshold is NOT a Shorts success threshold.",
        "CTR and viewed-versus-swiped-away are unavailable here. Engaged views / views is not a swipe rate.",
        "STRONG RETENTION EXAMPLES:",
        *([_short_line(s) for s in best] or ["None has reached the target yet; do not imitate a weak winner."]),
        "SUBSCRIBER YIELD EXAMPLES (with at least 60% viewed; a separate signal, not proof of long-form interest):",
        *([_short_line(s) for s in subscribers] or ["Not enough subscriber evidence yet."]),
        "LOW RETENTION EXAMPLES:",
        *([_short_line(s) for s in worst] or ["No eligible Short below 60% viewed."]),
    ])
