from dataclasses import dataclass
from statistics import mean
from uuid import uuid4

MICRONICHES = {
    "last-messages": {
        "title": "Last Messages Before Disappearances",
        "format": "disappearance",
        "focus": (
            "Unsolved historical disappearances reconstructed through a surviving final note, radio message, log entry "
            "or inscription left by the missing people. The actual message and its limits must drive the investigation, "
            "not just appear as a passing detail. Exclude unrelated codes, supernatural stories and solved cases."
        ),
        "adjacent": ["empty-vessels", "lost-expeditions"],
    },
    "empty-vessels": {
        "title": "Vessels Found Without Their Crews",
        "format": "disappearance",
        "focus": (
            "Historical ships or aircraft physically recovered without their crews, with an unresolved disappearance. "
            "Reconstruct what the surviving vessel and onboard evidence reveal. Exclude vessels never found, ordinary "
            "shipwrecks, ghost legends and disappearances unrelated to a recovered vessel."
        ),
        "adjacent": ["last-messages", "lost-expeditions"],
    },
    "lost-expeditions": {
        "title": "The Last Traces of Lost Expeditions",
        "format": "lost",
        "focus": (
            "Historical expeditions whose members disappeared, reconstructed through recovered camps, equipment, "
            "journals or a documented final route. The people and their surviving traces are central. Exclude general "
            "lost cities, treasure legends without a missing expedition and fully explained accidents."
        ),
        "adjacent": ["last-messages", "missing-prospectors"],
    },
    "missing-prospectors": {
        "title": "Prospectors Who Never Returned",
        "format": "lost",
        "focus": (
            "Historical prospectors or treasure hunters who disappeared during a documented search, leaving a map, "
            "camp, note or personal belongings. Investigate their final movements and unresolved fate. Exclude generic "
            "treasure lists, curses, invented mines and solved crimes."
        ),
        "adjacent": ["lost-expeditions", "last-messages"],
    },
}


@dataclass(frozen=True)
class Series:
    microniche: str
    series_id: str
    reason: str


def active_series(history: list[dict]) -> list[dict]:
    latest = next((e for e in reversed(history) if e.get("microniche")), None)
    if latest is None:
        return []
    if latest["microniche"] not in MICRONICHES or not latest.get("series_id"):
        raise ValueError("El historial contiene una serie de micronicho desconocida o sin identificador")
    return [
        e for e in history
        if e.get("series_id") == latest["series_id"] and e.get("microniche") == latest["microniche"]
    ]


def _eligible_episodes(history: list[dict], episodes: list[dict], min_views: int) -> list[dict]:
    by_id = {e["video_id"]: e for e in episodes if e["views"] >= min_views}
    return [by_id[e["video_id"]] for e in history if e.get("video_id") in by_id]


def neighbor_microniches(
    microniche: str, history: list[dict], episodes: list[dict], settings: dict,
) -> list[str]:
    def rank(name: str) -> tuple[float, int]:
        own = [e for e in history if e.get("microniche") == name]
        eligible = _eligible_episodes(own, episodes, settings["min_episode_views"])
        window = settings["review_after"]
        retention = (
            mean(e["retention"] for e in eligible[-window:])
            if len(eligible) >= window else settings["retention_floor"]
        )
        last_used = max((i for i, e in enumerate(history) if e.get("microniche") == name), default=-1)
        return -retention, last_used

    return sorted(MICRONICHES[microniche]["adjacent"], key=rank)


def choose_series(history: list[dict], episodes: list[dict], settings: dict) -> Series:
    if (
        settings["initial"] not in MICRONICHES or settings["review_after"] < 3
        or settings["min_episode_views"] < 1 or not 0 < settings["retention_floor"] <= 100
        or not 0 < settings["min_relative_drop"] < 1
    ):
        raise ValueError("Configuración de micronichos inválida")
    current = active_series(history)
    if not current:
        return Series(settings["initial"], uuid4().hex, "Start the configured editorial microniche; no tagged series yet.")
    name, series_id = current[-1]["microniche"], current[-1]["series_id"]
    window = settings["review_after"]
    eligible = _eligible_episodes(current, episodes, settings["min_episode_views"])
    if len(eligible) < window * 2:
        return Series(
            name, series_id,
            f"Continue: {len(eligible)} settled episodes meet the sample threshold; "
            f"need two blocks of {window} to assess a sustained decline. Episode count alone never ends a series.",
        )
    previous, recent = eligible[-window * 2:-window], eligible[-window:]
    baseline = mean(e["retention"] for e in previous)
    latest = mean(e["retention"] for e in recent)
    declining = (
        baseline >= settings["retention_floor"]
        and all(e["retention"] < settings["retention_floor"] for e in recent)
        and latest <= baseline * (1 - settings["min_relative_drop"])
    )
    if declining:
        next_name = neighbor_microniches(name, history, episodes, settings)[0]
        return Series(
            next_name, uuid4().hex,
            f"Adjacent pivot from {name}: the latest {window} eligible episodes are all below "
            f"{settings['retention_floor']}% viewed, with mean retention down from {baseline:.1f}% to {latest:.1f}%. "
            "This is an editorial experiment, not proof the microniche caused the decline.",
        )
    return Series(name, series_id, "Continue: no sustained decline meeting the sample and retention rules.")


def microniche_scope(microniche: str) -> str:
    definition = MICRONICHES[microniche]
    return (
        f'Locked microniche: {microniche} / {definition["title"]}.\n'
        f'Audience promise and boundaries: {definition["focus"]}'
    )


def series_rule(microniche: str, history: list[dict]) -> str:
    own = [e["topic"] for e in history if e.get("microniche") == microniche]
    return (
        f"{microniche_scope(microniche)}\n"
        "Stay inside these boundaries even if global analytics praise an unrelated case. Choose a DIFFERENT real case "
        "for the same viewer, not a retelling of an existing episode or the same plot with different names. Keep the "
        "audience promise consistent but vary the evidence, hook and composition; do not mass-produce near-duplicates.\n"
        f"Previous cases in this microniche: {'; '.join(own) or 'none tagged yet; do not infer tags for older episodes'}"
    )


def microniche_playlist(microniche: str) -> dict:
    definition = MICRONICHES[microniche]
    return {"title": f'Unsolved Archives: {definition["title"]}', "description": definition["focus"]}
