import json
from dataclasses import dataclass, field

from longform.gemini import Gemini
from longform.script import Script

CTA_LINE = "Watch the full investigation, linked right here."

PROMPT = """You are a scriptwriter and creative director for high-retention YouTube Shorts on a {language} channel about {niche}.
Audience: {audience}. Tone: deep, cinematic true-crime documentary narrator; {tone}.

The Short is a teaser for this long-form episode already published on the channel:
Episode title: "{title}"
Case: "{topic}"
Episode narration (the ONLY source of facts you may use):
<episode>
{narration}
</episode>

Angles already used in previous Shorts of this episode (pick a DIFFERENT cliffhanger, detail or character): {used_angles}

Write ONE Short of {min_words}-{max_words} spoken words in total (about 50 seconds; NEVER exceed {max_words} words), split into {min_beats}-{max_beats} beats.
Each beat is 3-10 words of narration (about 1-3 seconds on screen) with ONE visual. Structure:
1. Hook (beat 1, max 8 words): a scroll-stopping, concrete statement or quote that opens a question. No greetings, no
   context, no dates, never "In", "On", "Imagine" or "This is". Its visual is the most striking image of the Short.
2. Fast development (until ~35s): shocking facts one after another, short punchy sentences, names, places, numbers.
3. Turning point (~35-45s): the most disturbing piece of evidence or contradiction of the case.
4. CTA: the beat right before it is a COMPLETE cliffhanger sentence at peak tension, WITHOUT solving the mystery. This beat's narration is exactly "{cta}"
5. Loop (final beat): a short unfinished line that flows grammatically straight into the hook, so the replay feels
   seamless (e.g. the last beat "Because the last line still reads..." before the hook "God is over all.").
Use "..." or an em dash surrounded by spaces for dramatic half-second pauses on key words (at most 5 in total).
Present theories and disputed claims as such ("some say", "records suggest"). Never graphic violence or gore.
No calls to subscribe or like. No emojis, no stage directions, no markdown.

Visual for each beat:
- "stock": vertical atmospheric stock footage. "query" = 2-4 literal English words (e.g. "candle dark room", "stormy sea").
- "ai": cinematic vertical reconstruction of the specific person, place or object (e.g. an 18th-century stone monument
  in an English garden). "query" = detailed English prompt with setting, era, objects, lighting. Never identifiable faces
  of real people (silhouettes, hands, backs, distance), never gore, NEVER anything with writing.
Use "ai" for every beat about a concrete person, place, object or event (at most {max_ai} ai beats) and "stock" for
atmosphere, never the same type more than 3 times in a row.

Per beat also return:
- "highlight": 0-2 key words copied exactly from that beat's narration to show in colour (e.g. Vanished, Never, Blood, Unknown).
- "sfx": "hit" (bass drop on a shocking word), "whoosh" (rhythm change), "riser" (tension build that ENDS when this beat
  starts; use it once, on the turning point), "stop" (tape stop that ENDS when this beat starts, when the rhythm brakes
  hard right before a key line; at most once) or "none". Use "hit" at most 5 times.

Return ONLY JSON:
{{
  "angle": "one sentence describing the cliffhanger of this Short",
  "title": "Short title, max 60 characters, curiosity-driven but honest, no hashtags",
  "description": "2-3 sentences that tease the case without spoiling it, naturally including the case name, people, places and search terms",
  "tags": ["10-15 tags: case name, people, places, era and related searches"],
  "hashtags": ["3-5 case-specific hashtags without the # symbol and without spaces"],
  "thumbnail_text": "2-4 punchy words for a vertical thumbnail that open a question and NEVER reveal the answer, the key evidence or the ending (e.g. 'NOBODY CAME BACK', 'WHO WROTE THIS?')",
  "beats": [{{"narration": "...", "kind": "stock|ai", "query": "...", "highlight": ["..."], "sfx": "hit|whoosh|riser|stop|none"}}]
}}"""


@dataclass
class Beat:
    narration: str
    kind: str
    query: str
    highlight: list[str] = field(default_factory=list)
    sfx: str = "none"
    cta: bool = False


@dataclass
class ShortScript:
    episode_id: str
    angle: str
    title: str
    description: str
    tags: list[str]
    beats: list[Beat]
    hashtags: list[str] = field(default_factory=list)
    thumbnail_text: str = ""

    @property
    def words(self) -> int:
        return sum(len(b.narration.split()) for b in self.beats)

    def to_json(self) -> str:
        return json.dumps(self, default=lambda o: o.__dict__, ensure_ascii=False, indent=2)

    @staticmethod
    def from_json(text: str) -> "ShortScript":
        data = json.loads(text)
        data["beats"] = [Beat(**b) for b in data["beats"]]
        return ShortScript(**data)


def _parse(text: str) -> dict:
    data, _ = json.JSONDecoder().raw_decode(text.strip())
    return data[0] if isinstance(data, list) else data


def _beat(raw: dict) -> Beat:
    narration = raw["narration"].strip()
    kind = raw.get("kind") if raw.get("kind") in {"archive", "stock", "ai"} else "stock"
    sfx = raw.get("sfx") if raw.get("sfx") in {"hit", "whoosh", "riser", "stop"} else "none"
    return Beat(narration, kind, raw.get("query", "").strip(), [h for h in raw.get("highlight", []) if h][:2], sfx)


def _with_cta(beats: list[Beat]) -> list[Beat]:
    for beat in beats:
        if beat.narration.rstrip(".").lower() == CTA_LINE.rstrip(".").lower():
            beat.cta = True
            return beats
    beats.insert(max(len(beats) - 1, 0), Beat(CTA_LINE, "stock", "old archive files", [], "whoosh", True))
    return beats


def generate_short(config: dict, episode_id: str, episode: Script, used_angles: list[str]) -> ShortScript:
    shorts = config["shorts"]
    gemini = Gemini(config["script"]["models"])
    narration = "\n".join(s.narration for c in episode.chapters for s in c.scenes)
    min_words, max_words = shorts["min_words"], shorts["max_words"]
    for _ in range(3):
        data = _parse(gemini.json(PROMPT.format(
            **config["channel"],
            title=episode.title,
            topic=episode.topic,
            narration=narration,
            used_angles="; ".join(used_angles[-20:]) or "none",
            min_words=min_words,
            max_words=max_words,
            min_beats=shorts["min_beats"],
            max_beats=shorts["max_beats"],
            max_ai=shorts["visuals"]["max_ai_images"],
            cta=CTA_LINE,
        ), temperature=0.9))
        beats = _with_cta([_beat(b) for b in data["beats"] if b.get("narration", "").strip()])
        script = ShortScript(
            episode_id=episode_id,
            angle=data["angle"],
            title=data["title"][:80],
            description=data["description"],
            tags=data["tags"][:15],
            beats=beats,
            hashtags=[str(h) for h in data.get("hashtags", [])][:5],
            thumbnail_text=data.get("thumbnail_text") or data["title"],
        )
        print(f"Short: {script.words} palabras, {len(beats)} beats\nÁngulo: {script.angle}")
        if min_words - 15 <= script.words <= max_words + 20:
            return script
        print("Longitud fuera de rango, se regenera")
    raise RuntimeError("Gemini no generó un Short de la longitud pedida")
