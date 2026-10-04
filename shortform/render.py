import math
import random
import re
from dataclasses import dataclass
from pathlib import Path

from longform.media import duration, run
from longform.render import _image_filter, _ts
from longform.visuals import Visual
from longform.voice import Word
from shortform.script import Beat

FONTS = Path(__file__).parent.parent / "fonts"
SFX_DIR = Path(__file__).parent.parent / "sfx"
SAMPLE_RATE = 48000
TAIL_SECONDS = 0.25
RISER_SECONDS = 2.6
MUSIC_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg"}
MOTIONS = ["zoom_in", "zoom_in", "pan_right", "zoom_out", "pan_left"]
YELLOW = r"{\c&H00D6FF&}"
RED = r"{\c&H2B2BFF&}"
RED_WORDS = {
    "blood", "bloody", "dead", "death", "died", "die", "killed", "kill", "murder", "murdered", "vanished", "vanish",
    "disappeared", "missing", "gone", "body", "bodies", "grave", "corpse", "never", "nobody",
}
POP = r"{\fscx82\fscy82\t(0,90,\fscx100\fscy100)}"
ARROW = "m 38 0 l 82 0 l 82 100 l 120 100 l 60 170 l 0 100 l 38 100"
SFX_VOLUME = {"hit": 0.35, "whoosh": 0.5, "riser": 0.5, "stop": 0.6}
SYNTH_VOLUME = {"hit": 0.9, "whoosh": 0.45, "riser": 0.5}

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Anton,150,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,2,0,1,7,4,2,110,110,600,1
Style: CaptionHigh,Anton,138,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,2,0,1,7,4,2,110,110,980,1
Style: Cta,Anton,112,&H0000D6FF,&H0000D6FF,&H00000000,&H96000000,0,0,0,0,100,100,3,0,1,6,4,7,0,0,0,1
Style: Arrow,DejaVu Sans,10,&H0000D6FF,&H0000D6FF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,5,3,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


@dataclass
class ShortTimeline:
    beat_starts: list[float]
    beat_ends: list[float]
    words: list[Word]
    beat_of_word: list[int]
    total: float


@dataclass
class Segment:
    visual: Visual
    start: float
    end: float


def build_timeline(beats: list[Beat], words: list[Word], audio_seconds: float) -> ShortTimeline:
    beat_of_word = [i for i, beat in enumerate(beats) for _ in beat.narration.split()]
    if len(beat_of_word) != len(words):
        raise RuntimeError(f"La alineación no cuadra: {len(words)} palabras de voz y {len(beat_of_word)} en el guion")
    first_word = {b: w for w, b in reversed(list(enumerate(beat_of_word)))}
    total = (words[-1].end if words else audio_seconds) + TAIL_SECONDS
    starts = [0.0 if i == 0 else words[first_word[i]].start for i in range(len(beats))]
    return ShortTimeline(starts, starts[1:] + [total], words, beat_of_word, total)


def _plain(token: str) -> str:
    return re.sub(r"[^\w']", "", token).lower()


def _caption_chunks(words: list[Word], beat_of_word: list[int]) -> list[list[int]]:
    chunks, current = [], []
    for i, word in enumerate(words):
        if not _plain(word.text):
            if current:
                chunks.append(current)
                current = []
            continue
        if current and (
            len(current) == 2
            or beat_of_word[i] != beat_of_word[current[-1]]
            or words[current[-1]].text[-1:] in ".?!,;:…"
            or word.start - words[current[-1]].end > 0.35
        ):
            chunks.append(current)
            current = []
        current.append(i)
    if current:
        chunks.append(current)
    return chunks


def _clean(text: str) -> str:
    return text.replace("{", "").replace("}", "").replace("\\", "").strip("—-").upper()


def write_ass(beats: list[Beat], timeline: ShortTimeline, config: dict, out: Path) -> None:
    video = config["shorts"]["video"]
    lines = [ASS_HEADER.format(w=video["width"], h=video["height"])]
    words = timeline.words
    cta_beat = next((i for i, b in enumerate(beats) if b.cta), None)
    cta_start = timeline.beat_starts[cta_beat] if cta_beat is not None else timeline.total
    highlights = [{_plain(h) for h in b.highlight} for b in beats]

    chunks = _caption_chunks(words, timeline.beat_of_word)
    for c, chunk in enumerate(chunks):
        start = words[chunk[0]].start
        next_start = words[chunks[c + 1][0]].start if c + 1 < len(chunks) else timeline.total
        end = min(words[chunk[-1]].end + 0.45, next_start)
        parts = []
        for i in chunk:
            text = _clean(words[i].text)
            key = _plain(words[i].text)
            if key in highlights[timeline.beat_of_word[i]] or key in RED_WORDS:
                colour = RED if key in RED_WORDS else YELLOW
                text = f"{colour}{text}{{\\c&HFFFFFF&}}"
            parts.append(text)
        style = "CaptionHigh" if start >= cta_start - 0.05 else "Caption"
        lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},{style},,0,0,0,,{POP}{' '.join(parts)}\n")

    if cta_beat is not None:
        x, y = 120, 1270
        lines.append(f"Dialogue: 1,{_ts(cta_start)},{_ts(timeline.total)},Cta,,0,0,0,,{{\\pos(70,1130)\\fad(150,0)}}FULL CASE\n")
        t, step = cta_start, 0.28
        while t < timeline.total:
            for a, b in ((0, 34), (34, 0)):
                end = min(t + step, timeline.total)
                lines.append(
                    f"Dialogue: 1,{_ts(t)},{_ts(end)},Arrow,,0,0,0,,"
                    f"{{\\an7\\fscx150\\fscy150\\move({x},{y + a},{x},{y + b})\\p1}}{ARROW}\n"
                )
                t = end
                if t >= timeline.total:
                    break
    out.write_text("".join(lines), encoding="utf-8")


def plan_segments(visuals: list[Visual], timeline: ShortTimeline, max_seconds: float) -> list[Segment]:
    segments = []
    for visual, start, end in zip(visuals, timeline.beat_starts, timeline.beat_ends):
        count = max(1, math.ceil((end - start) / max_seconds - 1e-6))
        step = (end - start) / count
        segments += [Segment(visual, start + k * step, start + (k + 1) * step) for k in range(count)]
    return segments


def _render_parts(segments: list[Segment], config: dict, workdir: Path) -> list[Path]:
    video = config["shorts"]["video"]
    w, h, fps, zoom = video["width"], video["height"], video["fps"], video["zoom"]
    parts, motion = [], None
    for i, segment in enumerate(segments):
        frames = max(round(segment.end * fps) - round(segment.start * fps), 1)
        part = workdir / f"short_part_{i:03d}.mp4"
        if segment.visual.is_video:
            offset = random.uniform(0, max(duration(segment.visual.path) - frames / fps, 0))
            inputs = ["-ss", f"{offset:.3f}", "-stream_loop", "-1", "-i", str(segment.visual.path)]
            vf = f"setpts=PTS-STARTPTS,fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
        else:
            motion = random.choice([m for m in MOTIONS if m != motion])
            inputs = ["-i", str(segment.visual.path)]
            vf = _image_filter(motion, w, h, frames, zoom, False).replace("{fps}", str(fps))
        run([
            "ffmpeg", "-y", *inputs, "-frames:v", str(frames), "-an", "-filter_complex", f"[0:v]{vf},format=yuv420p[v]",
            "-map", "[v]", "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(part),
        ])
        parts.append(part)
        print(f"\rRender: {i + 1}/{len(segments)}", end="", flush=True)
    print()
    return parts


def _synth_sfx(workdir: Path, total: float) -> dict[str, Path]:
    sources = {
        "hit": f"aevalsrc='sin(2*PI*(36+80*exp(-9*t))*t)*exp(-2.4*t)':s={SAMPLE_RATE}:d=1.8,lowpass=f=180",
        "whoosh": (
            f"anoisesrc=d=0.7:c=pink:r={SAMPLE_RATE}:a=0.8,highpass=f=300,lowpass=f=4000,"
            "afade=t=in:d=0.4:curve=exp,afade=t=out:st=0.4:d=0.3"
        ),
        "riser": (
            f"aevalsrc='0.5*sin(2*PI*90*pow(7,t/{RISER_SECONDS})*t)+0.2*sin(2*PI*181*pow(7,t/{RISER_SECONDS})*t)"
            f"':s={SAMPLE_RATE}:d={RISER_SECONDS},afade=t=in:d={RISER_SECONDS - 0.1}:curve=exp"
        ),
        "drone": (
            f"aevalsrc='0.6*sin(2*PI*55*t)*(0.8+0.2*sin(2*PI*0.25*t))+0.3*sin(2*PI*82.4*t)+0.15*sin(2*PI*110.3*t)'"
            f":s={SAMPLE_RATE}:d={total:.3f},lowpass=f=240"
        ),
    }
    paths = {}
    for name, source in sources.items():
        path = workdir / f"sfx_{name}.wav"
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", source, "-ac", "2", str(path)])
        paths[name] = path
    return paths


def _sfx_library(synth: dict[str, Path]) -> dict[str, list[tuple[Path, float]]]:
    library = {}
    for name in ("hit", "whoosh", "riser", "stop"):
        real = sorted(p for p in SFX_DIR.glob(f"{name}_*") if p.suffix.lower() in MUSIC_EXTENSIONS) if SFX_DIR.exists() else []
        if real:
            library[name] = [(p, SFX_VOLUME[name]) for p in real]
        elif name in synth:
            library[name] = [(synth[name], SYNTH_VOLUME[name])]
    return library


def _sfx_events(beats: list[Beat], timeline: ShortTimeline, library: dict[str, list[tuple[Path, float]]]) -> list[tuple[Path, float, float]]:
    events = []

    def add(name: str, at: float, ending: bool = False) -> None:
        if name not in library:
            return
        path, volume = random.choice(library[name])
        events.append((path, volume, max(at - duration(path), 0) if ending else max(at, 0)))

    add("hit", 0.0)
    for i, beat in enumerate(beats):
        start = timeline.beat_starts[i]
        if beat.sfx == "whoosh" or beat.cta:
            add("whoosh", start - 0.3)
        elif beat.sfx == "riser":
            add("riser", start, ending=True)
            add("hit", start)
        elif beat.sfx == "stop":
            add("stop", start, ending=True)
        elif beat.sfx == "hit" and i > 0:
            keys = {_plain(h) for h in beat.highlight}
            hit_word = next(
                (w for w, b in zip(timeline.words, timeline.beat_of_word) if b == i and _plain(w.text) in keys), None,
            )
            add("hit", hit_word.start if hit_word else start)
    return events


def _pick_music(music_dir: Path) -> Path | None:
    for folder in (music_dir / "shorts", music_dir):
        tracks = [p for p in folder.glob("*") if p.suffix.lower() in MUSIC_EXTENSIONS] if folder.exists() else []
        if tracks:
            return random.choice(tracks)
    return None


def _mix_audio(beats: list[Beat], timeline: ShortTimeline, voice_mp3: Path, config: dict, workdir: Path, music_dir: Path) -> Path:
    total = timeline.total
    voice = workdir / "short_voice.wav"
    run([
        "ffmpeg", "-y", "-i", str(voice_mp3), "-af", f"loudnorm=I=-14:TP=-1.5:LRA=9,apad=whole_dur={total:.3f}",
        "-ar", str(SAMPLE_RATE), "-ac", "2", str(voice),
    ])
    synth = _synth_sfx(workdir, total)
    events = _sfx_events(beats, timeline, _sfx_library(synth))
    music = _pick_music(music_dir)
    inputs = ["-i", str(voice), "-i", str(synth["drone"])]
    chain = f"[1:a]volume={config['shorts']['drone_volume']}[drone];"
    mixes = ["[vo]", "[drone]"]
    for k, (path, volume, at) in enumerate(events):
        inputs += ["-i", str(path)]
        ms = int(at * 1000)
        chain += f"[{k + 2}:a]aresample={SAMPLE_RATE},aformat=channel_layouts=stereo,adelay={ms}|{ms},volume={volume}[s{k}];"
        mixes.append(f"[s{k}]")
    if music:
        print(f"Música: {music.name}")
        offset = random.uniform(0, max(duration(music) - total - 1, 0))
        inputs += ["-ss", f"{offset:.2f}", "-i", str(music)]
        m = len(events) + 2
        chain += (
            f"[{m}:a]aresample={SAMPLE_RATE},aformat=channel_layouts=stereo,atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
            f"volume={config['shorts']['music_volume']}[mus];[vc][mus]sidechaincompress=threshold=0.05:ratio=3:attack=40:release=400[ducked];"
        )
        mixes.append("[ducked]")
        chain = "[0:a]asplit=2[vo][vc];" + chain
    else:
        chain = "[0:a]anull[vo];" + chain
    chain += f"{''.join(mixes)}amix=inputs={len(mixes)}:duration=first:normalize=0,alimiter=limit=0.89,loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    out = workdir / "short_mix.wav"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", chain, "-map", "[a]", "-t", f"{total:.3f}", "-ar", str(SAMPLE_RATE), str(out)])
    return out


def render_short(
    beats: list[Beat], visuals: list[Visual], timeline: ShortTimeline, voice_mp3: Path, subtitles: Path,
    config: dict, workdir: Path, music_dir: Path, out: Path,
) -> None:
    segments = plan_segments(visuals, timeline, config["shorts"]["video"]["max_segment_seconds"])
    parts = _render_parts(segments, config, workdir)
    concat_list = workdir / "short_concat.txt"
    concat_list.write_text("".join(f"file '{p.name}'\n" for p in parts))
    joined = workdir / "short_joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(joined)])
    mixed = _mix_audio(beats, timeline, voice_mp3, config, workdir, music_dir)
    run([
        "ffmpeg", "-y", "-i", str(joined.resolve()), "-i", str(mixed.resolve()), "-filter_complex",
        "[0:v]eq=saturation=0.42:contrast=1.22:brightness=-0.07:gamma=0.92,"
        "colorbalance=rs=-0.07:gs=-0.02:bs=0.10:rm=-0.05:bm=0.07:rh=-0.03:bh=0.05,vignette=PI/3.6,noise=alls=5:allf=t,"
        f"ass={subtitles.name}:fontsdir={FONTS.resolve()},format=yuv420p[v]",
        "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-c:a", "aac", "-b:a", "192k", "-t", f"{timeline.total:.3f}", "-movflags", "+faststart", str(out.resolve()),
    ], cwd=workdir)
