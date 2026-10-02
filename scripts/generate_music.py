import os
import sys
from pathlib import Path

import requests

MUSIC_DIR = Path(__file__).parent.parent / "music"
PROMPTS = [
    "dark ambient documentary underscore, slow evolving drones, distant piano notes, mysterious and tense, no drums",
    "cinematic mystery underscore, soft pulsing low strings, subtle ticking clock, suspenseful but calm, no vocals",
    "eerie atmospheric soundscape, warm analog pads, sparse cello, investigative documentary mood, no percussion",
    "melancholic investigative documentary score, minimal piano motif over airy synth pads, slow tempo",
]

count = int(sys.argv[1]) if len(sys.argv) > 1 else len(PROMPTS)
MUSIC_DIR.mkdir(exist_ok=True)
for i, prompt in enumerate(PROMPTS[:count], 1):
    out = MUSIC_DIR / f"mystery_bed_{i:02d}.mp3"
    if out.exists():
        continue
    response = requests.post(
        "https://api.elevenlabs.io/v1/music",
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
        json={"prompt": prompt, "music_length_ms": 180_000, "force_instrumental": True},
        timeout=600,
    )
    if not response.ok:
        sys.exit(f"ElevenLabs {response.status_code}: {response.text[:300]}")
    out.write_bytes(response.content)
    print(f"Guardada {out.name}")
