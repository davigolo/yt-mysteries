import os
import sys
from pathlib import Path

import requests

MUSIC_DIR = Path(__file__).parent.parent / "music"
LONGFORM = [
    "dark ambient documentary underscore, slow evolving drones, distant piano notes, mysterious and tense, no drums",
    "cinematic mystery underscore, soft pulsing low strings, subtle ticking clock, suspenseful but calm, no vocals",
    "eerie atmospheric soundscape, warm analog pads, sparse cello, investigative documentary mood, no percussion",
    "melancholic investigative documentary score, minimal piano motif over airy synth pads, slow tempo",
    "slow cinematic documentary underscore, deep cello drones, sparse music box notes, cold and mysterious, no drums",
    "nocturnal investigative ambient, soft granular textures, low brass swells, unresolved harmony, no percussion",
    "historical mystery underscore, distant wordless choir pads, airy strings, slow building tension",
    "foggy coastal atmosphere score, low synth drones, faint bell tones, lonely and eerie, no drums",
    "minimal suspense underscore, muted piano ostinato, subtle heartbeat pulse, analog synth pads, slow tempo",
    "dark archival documentary theme, warm tape-saturated pads, bowed metal textures, contemplative tension",
]
SHORTS = [
    "psychological thriller tension, deep sub-bass drone from the very first second, pulsing dark synth, constant suspense, no jump scares, no screams",
    "dark ambient synth, heavy sub bass drone, slowly rising tension, cold metallic textures, true crime documentary",
    "true crime thriller underscore, heartbeat-like low pulse, eerie synth arpeggio, relentless tension",
    "cinematic suspense, dark analog synth bass ostinato, distant reversed piano, investigative mood, tense",
    "tense mystery underscore, low cello pulse over sub bass, clock-like rhythm, unresolved and ominous",
    "cold dark synth suspense, slow driving bass pulse, ominous evolving pads, psychological thriller",
    "eerie investigation underscore, granular drones, sparse deep percussion hits, steadily rising tension",
    "noir thriller tension, muted string staccatos, deep drone, minimal and menacing",
]
SETS = {
    "longform": (MUSIC_DIR, "mystery_bed", LONGFORM, 180_000),
    "shorts": (MUSIC_DIR / "shorts", "short_tension", SHORTS, 90_000),
}

names = sys.argv[1:] or list(SETS)
for name in names:
    folder, prefix, prompts, length = SETS[name]
    folder.mkdir(parents=True, exist_ok=True)
    for i, prompt in enumerate(prompts, 1):
        out = folder / f"{prefix}_{i:02d}.mp3"
        if out.exists():
            continue
        response = requests.post(
            "https://api.elevenlabs.io/v1/music",
            headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
            json={"prompt": prompt, "music_length_ms": length, "force_instrumental": True},
            timeout=600,
        )
        if not response.ok:
            sys.exit(f"ElevenLabs {response.status_code}: {response.text[:300]}")
        out.write_bytes(response.content)
        print(f"Guardada {out.relative_to(MUSIC_DIR.parent)}")
