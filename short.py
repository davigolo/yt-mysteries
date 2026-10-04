import argparse
import json
import shutil
from datetime import date
from pathlib import Path

import yaml

from longform.script import Script
from longform.visuals import VisualSource
from longform.voice import remaining_characters, synthesize
from main import _load_env
from shortform.render import build_timeline, render_short, write_ass
from shortform.script import ShortScript, generate_short
from shortform.upload import build_description, upload_short

ROOT = Path(__file__).parent
EPISODES = ROOT / "episodes"
HISTORY = ROOT / "history.json"
SHORTS_HISTORY = ROOT / "shorts_history.json"
WORKDIR = ROOT / "build"


def _pick_episode(history: list[dict], shorts_history: list[dict], window: int) -> str:
    published = [h["video_id"] for h in history if h.get("video_id") and (EPISODES / f"{h['video_id']}.json").exists()]
    if not published:
        raise RuntimeError("No hay episodios publicados con guion en episodes/ para promocionar")
    candidates = published[-window:]
    counts = {v: sum(1 for s in shorts_history if s["episode_id"] == v) for v in candidates}
    return min(reversed(candidates), key=lambda v: counts[v])


def main() -> None:
    _load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-upload", action="store_true", help="Genera el Short sin subirlo")
    parser.add_argument("--episode", help="video_id del episodio a promocionar (por defecto, el que menos Shorts tenga)")
    parser.add_argument("--script", type=Path, help="Reutiliza un guion de Short ya generado")
    args = parser.parse_args()

    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    shorts = config["shorts"]
    history = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []
    shorts_history = json.loads(SHORTS_HISTORY.read_text(encoding="utf-8")) if SHORTS_HISTORY.exists() else []
    reused = ShortScript.from_json(args.script.read_text(encoding="utf-8")) if args.script else None

    shutil.rmtree(WORKDIR, ignore_errors=True)
    WORKDIR.mkdir()

    if reused:
        script = reused
    else:
        episode_id = args.episode or _pick_episode(history, shorts_history, shorts["episode_window"])
        episode = Script.from_json((EPISODES / f"{episode_id}.json").read_text(encoding="utf-8"))
        print(f"Episodio: {episode.title} (https://youtu.be/{episode_id})")
        used = [s["angle"] for s in shorts_history if s["episode_id"] == episode_id]
        script = generate_short(config, episode_id, episode, used)
    (WORKDIR / "short_script.json").write_text(script.to_json(), encoding="utf-8")
    print(f"Título: {script.title}")

    voice_config = {"voice": {**config["voice"], **shorts.get("voice", {})}}
    narration = " ".join(b.narration for b in script.beats)
    needed = int(len(narration) * voice_config["voice"]["credits_per_char"])
    remaining = remaining_characters()
    print(f"ElevenLabs: {needed} créditos necesarios, {remaining} disponibles")
    if remaining is not None and remaining < needed + shorts["reserve_credits"]:
        raise RuntimeError("Créditos de ElevenLabs reservados para los episodios largos; no se genera el Short")
    audio = synthesize([narration], voice_config, WORKDIR)[0]
    timeline = build_timeline(script.beats, audio.words, audio.duration)

    source = VisualSource({"visuals": shorts["visuals"], "video": shorts["video"]}, WORKDIR)
    durations = [end - start for start, end in zip(timeline.beat_starts, timeline.beat_ends)]
    visuals = source.fetch(script.beats, durations)

    subtitles = WORKDIR / "short.ass"
    write_ass(script.beats, timeline, config, subtitles)
    video = WORKDIR / "short.mp4"
    render_short(script.beats, visuals, timeline, audio.path, subtitles, config, WORKDIR, ROOT / "music", video)
    print(f"Short generado: {video} ({timeline.total:.1f} s)")

    title = f"{script.title} #shorts"
    description = build_description(
        script.description, script.episode_id, [v.credit for v in visuals if v.credit], shorts["hashtags"],
    )
    (WORKDIR / "short_description.txt").write_text(f"{title}\n\n{description}", encoding="utf-8")
    if args.no_upload:
        return
    video_id = upload_short(video, title, description, script.tags, script.episode_id, config)
    print(f"Subido: https://youtube.com/shorts/{video_id}")
    shorts_history.append({
        "date": date.today().isoformat(), "episode_id": script.episode_id, "angle": script.angle,
        "title": script.title, "video_id": video_id,
    })
    SHORTS_HISTORY.write_text(json.dumps(shorts_history, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
