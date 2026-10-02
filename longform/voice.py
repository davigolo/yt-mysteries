import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from longform import cache
from longform.media import duration

API = "https://api.elevenlabs.io/v1"


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class SceneAudio:
    path: Path
    duration: float
    words: list[Word]


def _headers() -> dict[str, str]:
    return {"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}


def remaining_characters() -> int | None:
    try:
        response = requests.get(f"{API}/user/subscription", headers=_headers(), timeout=30)
        response.raise_for_status()
        data = response.json()
        return data["character_limit"] - data["character_count"]
    except Exception as e:
        print(f"No se pudo consultar la cuota de ElevenLabs ({e})")
        return None


def _words(alignment: dict) -> list[Word]:
    words: list[Word] = []
    current, start, end = "", 0.0, 0.0
    for char, char_start, char_end in zip(
        alignment["characters"], alignment["character_start_times_seconds"], alignment["character_end_times_seconds"]
    ):
        if char.isspace():
            if current:
                words.append(Word(start, end, current))
            current = ""
            continue
        if not current:
            start = char_start
        current += char
        end = char_end
    if current:
        words.append(Word(start, end, current))
    return words


def _request(text: str, previous: str, following: str, voice: dict) -> dict:
    for attempt in range(4):
        response = requests.post(
            f"{API}/text-to-speech/{voice['voice_id']}/with-timestamps",
            params={"output_format": "mp3_44100_128"},
            headers=_headers(),
            json={
                "text": text,
                "model_id": voice["model_id"],
                "previous_text": previous or None,
                "next_text": following or None,
                "voice_settings": {
                    "stability": voice["stability"],
                    "similarity_boost": voice["similarity_boost"],
                    "style": voice["style"],
                    "use_speaker_boost": True,
                },
            },
            timeout=180,
        )
        if response.status_code in {429, 500, 502, 503}:
            time.sleep(10 * (attempt + 1))
            continue
        if not response.ok:
            raise RuntimeError(f"ElevenLabs {response.status_code}: {response.text[:500]}")
        return response.json()
    raise RuntimeError("ElevenLabs no responde")


def synthesize(narrations: list[str], config: dict, workdir: Path) -> list[SceneAudio]:
    voice = config["voice"]
    result: list[SceneAudio] = []
    for i, text in enumerate(narrations):
        previous = narrations[i - 1] if i > 0 else ""
        following = narrations[i + 1] if i + 1 < len(narrations) else ""
        name = cache.key("tts", text, voice["voice_id"], voice["model_id"], voice["stability"], voice["style"])
        audio, alignment = cache.get(f"{name}.mp3"), cache.get(f"{name}.json")
        if not (audio and alignment):
            data = _request(text, previous, following, voice)
            tmp_audio, tmp_alignment = workdir / f"{name}.mp3", workdir / f"{name}.json"
            tmp_audio.write_bytes(base64.b64decode(data["audio_base64"]))
            tmp_alignment.write_text(json.dumps(data["alignment"]))
            audio, alignment = cache.put(tmp_audio.name, tmp_audio), cache.put(tmp_alignment.name, tmp_alignment)
        result.append(SceneAudio(audio, duration(audio), _words(json.loads(alignment.read_text()))))
        print(f"\rVoz: {i + 1}/{len(narrations)}", end="", flush=True)
    print()
    return result
