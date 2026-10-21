import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from longform.gemini import Gemini
from longform.script import Script, review_packaging
from longform.series import microniche_scope

CTA_LINE = "Watch the full investigation, linked right here."

PROMPT = """You are a scriptwriter and creative director for high-retention YouTube Shorts on a {language} channel about {niche}.
Audience: {audience}. Tone: deep, cinematic true-crime documentary narrator; {tone}.

The Short is a teaser for this long-form episode already published on the channel:
Episode title: "{title}"
Case: "{topic}"
{series_rule}
Episode narration (the ONLY source of facts you may use):
<episode>
{narration}
</episode>

Angles already used in previous Shorts of this episode (pick a DIFFERENT cliffhanger, detail or character): {used_angles}
Titles already used on the channel (your title must NOT reuse their wording or main noun phrase): {used_titles}

{insights}
Treat individual best or worst episodes as limited observations, not universal formulas or retention guarantees.
Use relevant feedback to improve this angle's clarity within the episode's microniche, not to change its subject.
{revision}

Write ONE Short of {min_words}-{max_words} spoken words INCLUDING the CTA and loop (target {target_seconds} seconds;
NEVER exceed {max_words} words), split into {min_beats}-{max_beats} beats.
Each beat is 3-10 words of narration (about 1-3 seconds on screen) with ONE visual. Structure:
1. Hook (beat 1, max 8 words): a scroll-stopping, concrete statement or quote that opens a question. No greetings, no
   context, no dates, never "In", "On", "Imagine" or "This is". Its visual is the most striking image of the Short.
   State a source-verifiable anomaly about a tangible object, message or recorded observation, not generic dread.
   A contradiction must be documented, not invented to sound impossible. The next beat gives evidence that confirms
   the title's promise; raise a further question only if supported by the episode. Defer names and biography unless
   needed to understand the clue.
2. Development (middle half): follow ONE person, object or message. Use at most two unfamiliar proper names.
   Every beat adds information needed for this angle; no inventory of unrelated eerie details or long setup.
3. Payoff (before the last two beats): deliver the specific verified detail promised by the title. Explain what makes
   it contradictory or revealing. The Short must be satisfying by itself while leaving the wider case unresolved.
4. CTA (penultimate beat): after that payoff, invite the viewer to the remaining investigation. Its narration is
   exactly "{cta}". Never withhold the promised detail just to force a click.
5. Loop (final beat): a short unfinished line that flows grammatically straight into the hook, so the replay feels
   seamless (e.g. the last beat "Because the last line still reads..." before the hook "God is over all.").
Use at most ONE dramatic pause in total. Prefer clear, complete sentences over fragmented suspense.
Use American English: US spelling, US customary units (miles, feet, pounds, degrees Fahrenheit) and US date format.
Present theories and disputed claims as such ("some say", "records suggest"). Never graphic violence or gore.
No calls to subscribe or like. No emojis, no stage directions, no markdown.

Visual for each beat:
- "stock": vertical atmospheric stock footage. "query" = 2-4 literal English words (e.g. "candle dark room", "stormy sea").
- "ai": cinematic vertical reconstruction of the specific person, place or object (e.g. an 18th-century stone monument
  in an English garden). "query" = detailed English prompt with setting, era, objects, lighting. Never identifiable faces
  of real people (silhouettes, hands, backs, distance), never gore, NEVER anything with writing.
Use "ai" for every beat about a concrete person, place, object or event (at most {max_ai} ai beats). Use "stock" only
for timeless atmosphere, never as a substitute for evidence; do not alternate sources just to satisfy a pattern.

Per beat also return:
- "highlight": 0-2 key words copied exactly from that beat's narration to show in colour (e.g. Vanished, Never, Blood, Unknown).
- "sfx": "hit" (bass drop on a shocking word), "whoosh" (rhythm change), "riser" (tension build that ENDS when this beat
  starts; use it once, on the turning point), "stop" (tape stop that ENDS when this beat starts, when the rhythm brakes
  hard right before a key line; at most once) or "none". Use "hit" at most 5 times.

Return ONLY JSON:
{{
  "angle": "one sentence describing the cliffhanger of this Short",
  "title": "Short title, max 60 characters, curiosity-driven but honest and fully delivered by the narration, about a concrete detail of the case (never about tools or AI), no hashtags",
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
    microniche: str = ""
    series_id: str = ""

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
    if any(b.cta for b in beats):
        return beats
    beats.insert(max(len(beats) - 1, 0), Beat(CTA_LINE, "stock", "old archive files", [], "whoosh", True))
    return beats


def _normalize_title(title: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", "", title.lower().replace("#shorts", "")).split())


def _similar_title(title: str, used_titles: list[str], threshold: float) -> str | None:
    candidate = _normalize_title(title)
    for used in used_titles:
        if SequenceMatcher(None, candidate, _normalize_title(used)).ratio() >= threshold:
            return used
    return None


def generate_short(
    config: dict, episode_id: str, episode: Script, used_angles: list[str], used_titles: list[str] | None = None,
    insights: str = "",
) -> ShortScript:
    shorts = config["shorts"]
    gemini = Gemini(config["script"]["models"])
    narration = "\n".join(s.narration for c in episode.chapters for s in c.scenes)
    min_words, max_words = shorts["min_words"], shorts["max_words"]
    used_titles = used_titles or []
    revision = ""
    for _ in range(3):
        data = _parse(gemini.json(PROMPT.format(
            **config["channel"],
            title=episode.title,
            topic=episode.topic,
            series_rule=microniche_scope(episode.microniche) if episode.microniche else "",
            narration=narration,
            used_angles="; ".join(used_angles[-20:]) or "none",
            used_titles="; ".join(used_titles[-40:]) or "none",
            insights=insights,
            revision=revision,
            target_seconds=shorts.get("target_seconds", 40),
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
            title=data["title"].strip(),
            description=data["description"],
            tags=data["tags"][:15],
            beats=beats,
            hashtags=[str(h) for h in data.get("hashtags", [])][:5],
            thumbnail_text=data.get("thumbnail_text") or data["title"],
            microniche=episode.microniche,
            series_id=episode.series_id,
        )
        print(f"Short: {script.words} palabras, {len(beats)} beats\nÁngulo: {script.angle}")
        if not (
            min_words <= script.words <= max_words
            and shorts["min_beats"] <= len(beats) <= shorts["max_beats"]
            and len(beats[0].narration.split()) <= 8
            and sum(b.cta for b in beats) == 1
            and len(beats) >= 2 and beats[-2].cta
        ):
            revision = (
                f"The previous draft had {script.words} words and {len(beats)} beats. Use exactly "
                f"{min_words}-{max_words} words including the CTA, {shorts['min_beats']}-{shorts['max_beats']} beats, "
                "a hook of at most 8 words and exactly one CTA in the penultimate beat."
            )
            print(f"Short fuera de las reglas, se regenera: {revision}")
            continue
        review = review_packaging(
            gemini, script.title, script.thumbnail_text, "\n".join(b.narration for b in beats), narration,
            short=True,
        )
        if not review["narration_supported"] or not review["promise_delivered"] or not review["opening_valid"]:
            revision = (
                "Fix the source, promised-payoff or opening issue from the previous draft: "
                f"{review.get('issue') or 'deliver a verified anomaly in the hook and substantiate the title in beat two'}"
            )
            print(f"Short rechazado por fuentes, promesa o apertura, se regenera: {revision}")
            continue
        script.title = review["title"].strip()
        script.thumbnail_text = review["thumbnail_text"].strip()
        duplicate = _similar_title(script.title, used_titles, shorts.get("title_similarity", 0.75))
        if duplicate:
            print(f"Título demasiado parecido a \"{duplicate}\", se regenera")
            used_titles = [*used_titles, script.title]
            revision = f'The previous title was too similar to "{duplicate}". Choose different wording and a new angle.'
            continue
        return script
    raise RuntimeError(f"Gemini no generó un Short válido: {revision}")
