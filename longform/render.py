import random
import wave
from dataclasses import dataclass
from pathlib import Path

from longform.media import duration, image_size, run
from longform.visuals import Visual
from longform.voice import SceneAudio, Word

FONTS = Path(__file__).parent.parent / "fonts"
SAMPLE_RATE = 48000
TAIL_SECONDS = 2.5
CHAPTER_CARD_SECONDS = 3.2
HIGHLIGHT = r"{\c&H00D6FF&}"
MUSIC_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg"}
MOTIONS = ["zoom_in", "zoom_out", "pan_right", "pan_left"]
OVERSAMPLE = 4

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Chapter,Anton,150,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,2,0,1,3,6,5,120,120,0,1
Style: ChapterLabel,Anton,52,&H0000D6FF,&H0000D6FF,&H00000000,&H64000000,0,0,0,0,100,100,8,0,1,2,4,5,120,120,190,1
Style: Veil,DejaVu Sans,10,&H00000000,&H00000000,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
Style: Title,Anton,135,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,4,0,1,3,8,5,160,160,0,1
Style: Caption,DejaVu Sans,58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,4,2,2,160,160,70,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


@dataclass
class Timeline:
    starts: list[float]
    ends: list[float]
    chapter_starts: list[float]
    words: list[Word]
    total: float
    title_start: float | None = None


def _ts(seconds: float, sep: str = ".", digits: int = 2) -> str:
    units = 10 ** digits
    value = int(round(seconds * units))
    h, value = divmod(value, 3600 * units)
    m, value = divmod(value, 60 * units)
    s, frac = divmod(value, units)
    return f"{h}:{m:02d}:{s:02d}{sep}{frac:0{digits}d}" if sep == "." else f"{h:02d}:{m:02d}:{s:02d}{sep}{frac:0{digits}d}"


def build_voice_track(audios: list[SceneAudio], chapter_of: list[int], config: dict, workdir: Path, out: Path) -> Timeline:
    voice = config["voice"]
    starts, chapter_starts, words = [], [], []
    title_start = None
    cursor = 0
    with wave.open(str(out), "wb") as track:
        track.setnchannels(1)
        track.setsampwidth(2)
        track.setframerate(SAMPLE_RATE)
        for i, audio in enumerate(audios):
            new_chapter = i == 0 or chapter_of[i] != chapter_of[i - 1]
            visual_start = cursor / SAMPLE_RATE
            if new_chapter:
                chapter_starts.append(visual_start)
                if i > 0:
                    after_cold_open = chapter_of[i - 1] == 0
                    if after_cold_open:
                        title_start = visual_start
                    silence = int(voice["title_pause" if after_cold_open else "chapter_pause"] * SAMPLE_RATE)
                    track.writeframes(b"\x00\x00" * silence)
                    cursor += silence
            pcm = workdir / f"scene_{i:03d}.wav"
            run(["ffmpeg", "-y", "-i", str(audio.path), "-ac", "1", "-ar", str(SAMPLE_RATE), "-sample_fmt", "s16", str(pcm)])
            with wave.open(str(pcm), "rb") as scene:
                count = scene.getnframes()
                track.writeframes(scene.readframes(count))
            voice_start = cursor / SAMPLE_RATE
            cursor += count
            words += [Word(voice_start + w.start, voice_start + w.end, w.text) for w in audio.words]
            starts.append(visual_start)
            if i + 1 < len(audios) and chapter_of[i + 1] == chapter_of[i]:
                pause = int(voice["scene_pause"] * SAMPLE_RATE)
                track.writeframes(b"\x00\x00" * pause)
                cursor += pause
        tail = int(TAIL_SECONDS * SAMPLE_RATE)
        track.writeframes(b"\x00\x00" * tail)
        cursor += tail
    total = cursor / SAMPLE_RATE
    return Timeline(starts, starts[1:] + [total], chapter_starts, words, total, title_start)


def _clean(text: str) -> str:
    return text.replace("{", "").replace("}", "").replace("\\", "")


def _caption_lines(words: list[Word], max_chars: int = 42) -> list[tuple[float, float, str]]:
    lines, current = [], []
    for word in words:
        candidate = " ".join(w.text for w in current + [word])
        sentence_end = current and current[-1].text[-1:] in ".?!"
        if current and (len(candidate) > max_chars or sentence_end or word.start - current[-1].end > 0.6):
            lines.append((current[0].start, current[-1].end, " ".join(w.text for w in current)))
            current = []
        current.append(word)
    if current:
        lines.append((current[0].start, current[-1].end, " ".join(w.text for w in current)))
    return lines


def write_srt(timeline: Timeline, out: Path) -> None:
    lines = _caption_lines(timeline.words)
    blocks = []
    for i, (start, end, text) in enumerate(lines):
        until = min(end + 0.15, lines[i + 1][0]) if i + 1 < len(lines) else end + 0.15
        blocks.append(f"{i + 1}\n{_ts(start, ',', 3)} --> {_ts(until, ',', 3)}\n{text}\n")
    out.write_text("\n".join(blocks), encoding="utf-8")


def _karaoke(words: list[Word], max_chars: int = 36) -> list[str]:
    events = []
    groups, current = [], []
    for word in words:
        candidate = " ".join(w.text for w in current + [word])
        sentence_end = current and current[-1].text[-1:] in ".?!"
        if current and (len(candidate) > max_chars or sentence_end or word.start - current[-1].end > 0.6):
            groups.append(current)
            current = []
        current.append(word)
    if current:
        groups.append(current)
    for g, group in enumerate(groups):
        next_start = groups[g + 1][0].start if g + 1 < len(groups) else group[-1].end + 0.3
        group_end = min(group[-1].end + 0.3, next_start)
        for j, word in enumerate(group):
            start = group[0].start if j == 0 else word.start
            end = group[j + 1].start if j + 1 < len(group) else group_end
            text = " ".join(
                f"{HIGHLIGHT}{_clean(w.text)}{{\\r}}" if k == j else _clean(w.text) for k, w in enumerate(group)
            )
            events.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Caption,,0,0,0,,{text}\n")
    return events


def write_ass(timeline: Timeline, chapter_titles: list[str], episode_title: str, config: dict, out: Path) -> None:
    video = config["video"]
    lines = [ASS_HEADER.format(w=video["width"], h=video["height"])]
    veil = f"m 0 0 l {video['width']} 0 {video['width']} {video['height']} 0 {video['height']}"
    if timeline.title_start is not None:
        start, end = timeline.title_start + 0.3, timeline.title_start + config["voice"]["title_pause"]
        lines.append(f"Dialogue: 1,{_ts(start)},{_ts(end)},Veil,,0,0,0,,{{\\an7\\pos(0,0)\\1a&H50&\\fad(500,400)\\p1}}{veil}\n")
        lines.append(f"Dialogue: 2,{_ts(start)},{_ts(end)},Title,,0,0,0,,{{\\fad(700,400)}}{_clean(episode_title.upper())}\n")
    for number, (title, start) in enumerate(zip(chapter_titles, timeline.chapter_starts)):
        if not title:
            continue
        if number == 1 and timeline.title_start is not None:
            start = timeline.title_start + config["voice"]["title_pause"]
        end = start + CHAPTER_CARD_SECONDS
        lines.append(f"Dialogue: 1,{_ts(start)},{_ts(end)},Veil,,0,0,0,,{{\\an7\\pos(0,0)\\1a&H70&\\fad(400,500)\\p1}}{veil}\n")
        lines.append(f"Dialogue: 2,{_ts(start)},{_ts(end)},ChapterLabel,,0,0,0,,{{\\fad(400,500)}}CHAPTER {number}\n")
        lines.append(f"Dialogue: 2,{_ts(start)},{_ts(end)},Chapter,,0,0,0,,{{\\fad(400,500)}}{_clean(title.upper())}\n")
    if video["burn_subtitles"]:
        lines += _karaoke(timeline.words)
    out.write_text("".join(lines), encoding="utf-8")


def _image_filter(motion: str, w: int, h: int, frames: int, zoom: float, fit_blur: bool) -> str:
    sw, sh = w * OVERSAMPLE, h * OVERSAMPLE
    if fit_blur:
        base = (
            f"split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=30:3,"
            f"eq=brightness=-0.15,scale={sw}:{sh}[bg];"
            f"[b]scale={sw}:{sh}:force_original_aspect_ratio=decrease:flags=lanczos[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        )
    else:
        base = f"scale={sw}:{sh}:force_original_aspect_ratio=increase:flags=lanczos,crop={sw}:{sh},"
    p = f"(on/{max(frames - 1, 1)})"
    if motion == "zoom_in":
        z, x, y = f"1+{zoom}*{p}", "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    elif motion == "zoom_out":
        z, x, y = f"1+{zoom}*(1-{p})", "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    elif motion == "pan_right":
        z, x, y = f"{1 + zoom}", f"(iw-iw/zoom)*{p}", "(ih-ih/zoom)/2"
    else:
        z, x, y = f"{1 + zoom}", f"(iw-iw/zoom)*(1-{p})", "(ih-ih/zoom)/2"
    return f"{base}zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={{fps}},setsar=1"


def _render_parts(visuals: list[Visual], timeline: Timeline, chapter_of: list[int], config: dict, workdir: Path) -> list[Path]:
    video = config["video"]
    w, h, fps, zoom = video["width"], video["height"], video["fps"], video["zoom"]
    parts, motion = [], None
    for i, (visual, start, end) in enumerate(zip(visuals, timeline.starts, timeline.ends)):
        frames = round(end * fps) - round(start * fps)
        seconds = frames / fps
        chapter_start = i > 0 and chapter_of[i] != chapter_of[i - 1]
        fade = ",fade=t=in:st=0:d=0.6" if chapter_start or i == 0 else ""
        part = workdir / f"part_{i:03d}.mp4"
        if visual.is_video:
            clip_length = duration(visual.path)
            offset = random.uniform(0, max(clip_length - seconds, 0))
            inputs = ["-ss", f"{offset:.3f}", "-stream_loop", "-1", "-i", str(visual.path)]
            vf = f"setpts=PTS-STARTPTS,fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
        else:
            iw, ih = image_size(visual.path)
            motion = random.choice([m for m in MOTIONS if m != motion])
            inputs = ["-i", str(visual.path)]
            vf = _image_filter(motion, w, h, frames, zoom, not 1.55 <= iw / ih <= 1.95).replace("{fps}", str(fps))
        run([
            "ffmpeg", "-y", *inputs, "-frames:v", str(frames), "-an", "-filter_complex", f"[0:v]{vf}{fade},format=yuv420p[v]",
            "-map", "[v]", "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(part),
        ])
        parts.append(part)
        print(f"\rRender: {i + 1}/{len(visuals)}", end="", flush=True)
    print()
    return parts


def _music_bed(music_dir: Path, total: float, volume: float, workdir: Path) -> Path | None:
    tracks = [p for p in music_dir.glob("*") if p.suffix.lower() in MUSIC_EXTENSIONS] if music_dir.exists() else []
    if not tracks:
        return None
    random.shuffle(tracks)
    chosen, length = [], 0.0
    while length < total + 5:
        track = tracks[len(chosen) % len(tracks)]
        chosen.append(track)
        length += duration(track) - 3
    print(f"Música: {', '.join(t.stem for t in chosen)}")
    inputs = [arg for t in chosen for arg in ("-i", str(t))]
    chain = "".join(f"[{i}:a]aresample={SAMPLE_RATE},aformat=channel_layouts=stereo[m{i}];" for i in range(len(chosen)))
    label = "m0"
    for i in range(1, len(chosen)):
        chain += f"[{label}][m{i}]acrossfade=d=3[x{i}];"
        label = f"x{i}"
    chain += (
        f"[{label}]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,volume={volume},"
        f"afade=t=in:d=2,afade=t=out:st={max(total - 3, 0):.3f}:d=3[out]"
    )
    out = workdir / "music.wav"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", chain, "-map", "[out]", str(out)])
    return out


def render(
    visuals: list[Visual], timeline: Timeline, chapter_of: list[int], voice_track: Path, subtitles: Path,
    config: dict, workdir: Path, music_dir: Path, out: Path,
) -> None:
    parts = _render_parts(visuals, timeline, chapter_of, config, workdir)
    concat_list = workdir / "concat.txt"
    concat_list.write_text("".join(f"file '{p.name}'\n" for p in parts))
    joined = workdir / "joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(joined)])

    voice = workdir / "voice_norm.wav"
    run(["ffmpeg", "-y", "-i", str(voice_track), "-af", "loudnorm=I=-14:TP=-1.5:LRA=9", "-ar", str(SAMPLE_RATE), "-ac", "2", str(voice)])

    mixed = workdir / "mix.wav"
    music = _music_bed(music_dir, timeline.total, config["music"]["volume"], workdir)
    if music:
        run([
            "ffmpeg", "-y", "-i", str(voice), "-i", str(music), "-filter_complex",
            "[0:a]asplit=2[vo][sc];[1:a][sc]sidechaincompress=threshold=0.05:ratio=4:attack=50:release=600[ducked];"
            "[vo][ducked]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.89[a]",
            "-map", "[a]", "-ar", str(SAMPLE_RATE), str(mixed),
        ])
    else:
        mixed = voice

    run([
        "ffmpeg", "-y", "-i", str(joined.resolve()), "-i", str(mixed.resolve()), "-filter_complex",
        f"[0:v]eq=saturation=0.85:contrast=1.04,vignette=PI/5,noise=alls=3:allf=t,"
        f"ass={subtitles.name}:fontsdir={FONTS.resolve()},format=yuv420p[v]",
        "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-t", f"{timeline.total:.3f}", "-movflags", "+faststart", str(out.resolve()),
    ], cwd=workdir)
