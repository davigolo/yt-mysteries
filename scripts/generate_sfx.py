import os
import sys
from pathlib import Path

import requests

SFX_DIR = Path(__file__).parent.parent / "sfx"
EFFECTS = {
    "hit": (2.5, [
        "deep cinematic sub bass boom impact, movie trailer hit, dark, long reverb tail",
        "heavy low-end braam impact, ominous cinematic hit, short decay",
        "dark cinematic impact with metallic resonance and sub drop",
        "massive sub bass drop thud, documentary tension stinger",
    ]),
    "whoosh": (1.0, [
        "fast dark cinematic whoosh transition, airy swoosh",
        "deep swoosh pass-by with low rumble, cinematic transition",
        "quick reversed whoosh swell into a cut, suspense",
        "breathy dark whoosh with subtle metallic shimmer",
    ]),
    "riser": (3.0, [
        "tension riser building to a climax, dark synth and strings rising in pitch, ends abruptly",
        "cinematic suspense riser, swelling noise and reversed reverb, accelerating, cut at the peak",
        "horror-free psychological thriller riser, rising drone and shepard tone, abrupt end",
    ]),
    "stop": (1.2, [
        "tape stop effect, music slowing down and pitching down to silence",
        "vinyl record slowdown tape stop, dark",
    ]),
}

SFX_DIR.mkdir(exist_ok=True)
for name, (seconds, prompts) in EFFECTS.items():
    for i, prompt in enumerate(prompts, 1):
        out = SFX_DIR / f"{name}_{i:02d}.mp3"
        if out.exists():
            continue
        response = requests.post(
            "https://api.elevenlabs.io/v1/sound-generation",
            headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
            json={"text": prompt, "duration_seconds": seconds, "prompt_influence": 0.6},
            timeout=180,
        )
        if not response.ok:
            sys.exit(f"ElevenLabs {response.status_code}: {response.text[:300]}")
        out.write_bytes(response.content)
        print(f"Guardado {out.name}")
