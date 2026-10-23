import argparse
import json
import os
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from longform.insights import build_series_insights, fetch_performance
from longform.schedule import next_slot
from longform.render import build_voice_track, render, write_ass, write_srt
from longform.script import Script, generate_script
from longform.series import microniche_playlist
from longform.thumbnail import create_thumbnail
from longform.upload import build_description, hashtags, upload
from longform.visuals import VisualSource
from longform.voice import remaining_characters, synthesize

ROOT = Path(__file__).parent
HISTORY = ROOT / "history.json"
SHORTS_HISTORY = ROOT / "shorts_history.json"
WORKDIR = ROOT / "build"


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            if sep and value.strip() and not name.strip().startswith("#"):
                os.environ.setdefault(name.strip(), value.strip())


def main() -> None:
    _load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-upload", action="store_true", help="Genera el vídeo sin subirlo")
    parser.add_argument("--script-only", action="store_true", help="Solo genera build/script.json para revisarlo")
    parser.add_argument("--script", type=Path, help="Reutiliza un guion ya generado en vez de pedir uno nuevo")
    parser.add_argument("--preview", type=int, metavar="N", help="Renderiza solo las N primeras escenas, sin subir")
    parser.add_argument(
        "--publish-at", type=datetime.fromisoformat, metavar="ISO",
        help="Fecha de estreno con zona horaria (p. ej. 2026-10-23T19:00:00-04:00); ignora el calendario automático",
    )
    args = parser.parse_args()

    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    history = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []
    reused = Script.from_json(args.script.read_text(encoding="utf-8")) if args.script else None

    shutil.rmtree(WORKDIR, ignore_errors=True)
    WORKDIR.mkdir()

    if reused:
        script = reused
    else:
        insights, episodes = "", []
        try:
            shorts_history = _load(SHORTS_HISTORY)
            performance = fetch_performance(history + shorts_history, min_views=0)
            episode_ids = {e["video_id"] for e in history if e.get("video_id")}
            episodes = [e for e in performance if e["video_id"] in episode_ids]
            shorts = [e for e in performance if e.get("episode_id")]
            insights = build_series_insights(history, episodes, shorts)
            print(f"Estadísticas: {len(episodes)} episodios y {len(shorts)} Shorts con datos")
        except Exception as e:
            print(f"Sin estadísticas ({type(e).__name__}: {e}); se genera sin ellas")
        script = generate_script(config, history, insights, episode_performance=episodes)
    (WORKDIR / "script.json").write_text(script.to_json(), encoding="utf-8")
    print(f"Título: {script.title}\nGuion guardado en build/script.json")
    if script.microniche:
        print(f"Serie: {script.microniche} ({script.series_id})\nMotivo: {script.series_reason}")
    if script.watch_next:
        print(f"Pantalla final: añade en Studio https://youtu.be/{script.watch_next['video_id']} ({script.watch_next['title']})")
    if args.script_only:
        return

    scenes = [scene for chapter in script.chapters for scene in chapter.scenes]
    chapter_of = [i for i, chapter in enumerate(script.chapters) for _ in chapter.scenes]
    if args.preview:
        scenes, chapter_of = scenes[:args.preview], chapter_of[:args.preview]

    needed = int(sum(len(s.narration) for s in scenes) * config["voice"]["credits_per_char"])
    remaining = remaining_characters()
    print(f"ElevenLabs: {needed} créditos necesarios, {remaining} disponibles")
    if remaining is not None and remaining < needed:
        raise RuntimeError("No quedan suficientes créditos en ElevenLabs para este vídeo")

    audios = synthesize([s.narration for s in scenes], config, WORKDIR)
    durations = [a.words[-1].end if a.words else a.duration for a in audios]
    source = VisualSource(config, WORKDIR)
    visuals = source.fetch(scenes, durations, f'"{script.title}" ({script.topic})')

    voice_track = WORKDIR / "voice.wav"
    timeline = build_voice_track(audios, chapter_of, config, WORKDIR, voice_track)
    titles = [c.title for c in script.chapters]
    captions, subtitles = WORKDIR / "captions.srt", WORKDIR / "overlay.ass"
    write_srt(timeline, captions)
    write_ass(timeline, titles, script.topic, config, subtitles)

    video = WORKDIR / "video.mp4"
    render(visuals, timeline, chapter_of, voice_track, subtitles, config, WORKDIR, ROOT / "music", video)
    print(f"Vídeo generado: {video} ({timeline.total / 60:.1f} min)")

    thumbnail = create_thumbnail(
        script.thumbnail_prompt, script.thumbnail_text, config, WORKDIR, WORKDIR / "thumbnail.jpg", script.title,
    )
    chapters = [(t, titles[i] or "Intro") for i, t in enumerate(timeline.chapter_starts)]
    description = build_description(
        script.description, chapters, script.sources, [v.credit for v in visuals if v.credit],
        hashtags(script.hashtags, config["upload"]["hashtags"], config["upload"]["max_hashtags"]),
        script.watch_next,
    )
    (WORKDIR / "description.txt").write_text(f"{script.title}\n\n{description}", encoding="utf-8")
    print(f"Miniatura: {thumbnail}\nDescripción: build/description.txt")

    if args.preview or args.no_upload:
        return
    playlists = config["playlists"]["episodes"]
    targets = [p for p in (playlists.get("all"), playlists.get(script.format)) if p]
    if script.microniche:
        targets.append(microniche_playlist(script.microniche))
    schedule = config["upload"].get("schedule")
    if args.publish_at:
        if args.publish_at.tzinfo is None or args.publish_at <= datetime.now(timezone.utc):
            raise ValueError("--publish-at necesita zona horaria y una fecha futura")
        publish_at = args.publish_at.astimezone(timezone.utc)
    else:
        publish_at = next_slot(
            schedule["episode_slots"], config["publish"]["timezone"], schedule["min_hours"],
            [h.get("publish_at") for h in history], weekdays=config["publish"]["episode_weekdays"],
        ) if schedule else None
    video_id = upload(video, thumbnail, captions, script.title, description, script.tags, targets, config, publish_at)
    privacy = "scheduled" if publish_at else config["upload"]["privacy"]
    print(f"Subido ({privacy}{f', se publica el {publish_at.isoformat()}' if publish_at else ''}): https://youtu.be/{video_id}")
    episodes = ROOT / "episodes"
    episodes.mkdir(exist_ok=True)
    (episodes / f"{video_id}.json").write_text(script.to_json(), encoding="utf-8")
    history.append({
        "date": date.today().isoformat(), "format": script.format, "topic": script.topic,
        "title": script.title, "video_id": video_id, "privacy": privacy, "country": script.country,
        "uploaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **({"pipeline_revision": config["reporting"]["rollout_id"]} if not reused else {}),
        **({
            "microniche": script.microniche, "series_id": script.series_id, "series_reason": script.series_reason,
        } if script.microniche else {}),
        **({"publish_at": publish_at.isoformat(timespec="seconds")} if publish_at else {}),
    })
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
