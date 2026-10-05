import json
import random
from dataclasses import dataclass, field

from longform.gemini import Gemini

FORMATS = {
    "disappearance": "An unsolved disappearance of a person, group, ship or aircraft.",
    "enigma": "A historical enigma: an object, document, event or place that still has no accepted explanation.",
    "solved": "A decades-old cold case or mystery that was finally solved, building up to the reveal.",
    "lost": "A lost expedition, city, treasure or civilisation and the search for it.",
    "phenomenon": "A strange documented phenomenon or mass event from history and the theories behind it.",
}

TOPIC_PROMPT = """You are the showrunner of a long-form YouTube documentary channel about {niche}.
Audience: {audience}. Language: {language}.
Story type for the next episode: {format_rule}

Pick ONE real, well-documented case for a 12-14 minute episode.
Rules:
- The core events happened before 1990, so there is solid public documentation.
- Do not pick cases whose central figures are minors or that revolve around sexual violence.
- Do not pick cases that would require accusing living people who were never convicted.
- It must have a strong hook, twists and enough material for 6 chapters.
- Do NOT repeat any of these published topics: {history}

{insights}

Return ONLY JSON:
{{"topic": "case name in 3-8 words", "angle": "one sentence with the angle that makes this episode gripping"}}"""

RESEARCH_PROMPT = """Research this real case using web search: "{topic}".
Angle of the episode: {angle}

Write a factual research dossier in English for a documentary scriptwriter:
1. Precise timeline with dates and places.
2. Key people and their role (only facts on record).
3. Key evidence and documents.
4. Main theories, each attributed to who proposes it, and the evidence for and against.
5. What is confirmed vs disputed vs unknown. Mark uncertain claims explicitly.
6. Current status of the case.
7. Seven little-known but verified details that would surprise a viewer.
Do not invent anything. If sources disagree, say so."""

HOOK_RULES = """The cold open decides if the viewer stays. It has 90-130 words, split into 5-7 short scenes:
  1. Hook (first sentence, max 12 words): a startling, concrete, visual statement or contradiction that creates an
     instant question. NEVER start with a date, a year, "In", "On", "Back in", "Imagine" or background context.
     Good: "Ten letters carved in stone have beaten the men who broke Enigma."
  2. Escalation: two or three specific teasers of the most surprising things revealed later in the episode
     (a twist, a strange detail, a high-stakes consequence), without revealing the answers.
  3. The central question, stated plainly.
  4. A final short line that pulls the viewer in, right before the title card (e.g. "To understand why, we have to go
     back to ..."). No greetings, no channel name, no "in this video", no "let's dive in".
  The first scene's visual must be the most striking image of the whole episode, and never an "ai" image of writing."""

SCRIPT_PROMPT = """You are an award-winning scriptwriter for a faceless YouTube documentary channel about {niche}.
Audience: {audience}. Language: {language}. Tone: {tone}.

Write the full narration of an episode about "{topic}" ({angle}), using ONLY facts from this dossier:
<dossier>
{dossier}
</dossier>

Length: about {target_words} words in total (12-14 minutes). Structure:
- A cold open. {hook_rules}
- Then exactly {chapters} chapters, each with a short evocative title (2-5 words).
- End every chapter with an open loop that makes the viewer need the next one.
- The last chapter weighs the theories honestly and ends with a memorable final line. No calls to subscribe or like.
- Present theories as theories. Never state disputed claims as facts. Never describe gore or violence in detail.
- Spoken style: varied sentence length, concrete details, dates and names. Text only for narration: no stage
  directions, no emojis, no markdown.

Split the narration into scenes of 1-3 sentences (15-45 words). Each scene has ONE visual:
- "archive": a real historical photo, painting, map or document that probably exists on Wikimedia Commons.
  "query" = short English search query that ALWAYS includes the proper name of the person, place or object
  (e.g. "Mary Celeste painting", "Roanoke Island map 1585"). Without a proper name, use "ai" instead.
- "stock": generic atmospheric footage that exists on stock sites. "query" = 2-4 English words
  (e.g. "stormy sea night", "old typewriter", "foggy forest").
- "ai": an illustrative cinematic reconstruction. "query" = detailed English image prompt describing setting, era,
  objects, lighting and composition. Never show identifiable faces of real people (use silhouettes, backs, hands,
  distance), never gore. NEVER ask for anything with writing (inscriptions, letters, codes, signs, books, maps,
  documents with legible text): image AIs invent fake text. If the scene is about an inscription or document, use
  "archive" with its proper name instead.
Use roughly 30% archive, 25% stock and 45% ai, and avoid the same type more than 3 times in a row.

Return ONLY JSON:
{{
  "title": "YouTube title, max 70 characters, curiosity-driven but honest",
  "description": "2 short paragraphs that summarise the episode without spoiling the ending, naturally including the names, places, year and search terms people would type on YouTube to find this case",
  "tags": ["12-18 tags: case name, people, places, era and related searches"],
  "hashtags": ["3-5 case-specific hashtags without the # symbol and without spaces (e.g. 'DyatlovPass', 'ColdCase', 'Russia')"],
  "thumbnail_text": "2-4 punchy words for the thumbnail",
  "thumbnail_prompt": "English prompt for a dramatic thumbnail image of the case, no text, no real faces",
  "cold_open": [{{"narration": "...", "kind": "archive|stock|ai", "query": "..."}}],
  "chapters": [{{"title": "...", "scenes": [{{"narration": "...", "kind": "archive|stock|ai", "query": "..."}}]}}]
}}"""

MIN_WORDS = 1300


@dataclass
class Scene:
    narration: str
    kind: str
    query: str


@dataclass
class Chapter:
    title: str
    scenes: list[Scene]


@dataclass
class Script:
    topic: str
    format: str
    title: str
    description: str
    tags: list[str]
    thumbnail_text: str
    thumbnail_prompt: str
    chapters: list[Chapter]
    sources: list[dict] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)

    @property
    def words(self) -> int:
        return sum(len(s.narration.split()) for c in self.chapters for s in c.scenes)

    def to_json(self) -> str:
        return json.dumps(self, default=lambda o: o.__dict__, ensure_ascii=False, indent=2)

    @staticmethod
    def from_json(text: str) -> "Script":
        data = json.loads(text)
        data["chapters"] = [Chapter(c["title"], [Scene(**s) for s in c["scenes"]]) for c in data["chapters"]]
        return Script(**data)


def _pick_format(recent_formats: list[str], weights: dict[str, float]) -> str:
    options = [f for f in FORMATS if f not in recent_formats[-2:]] or list(FORMATS)
    return random.choices(options, weights=[weights.get(f, 1.0) for f in options])[0]


def _scenes(raw: list[dict]) -> list[Scene]:
    return [
        Scene(s["narration"].strip(), s.get("kind", "ai") if s.get("kind") in {"archive", "stock", "ai"} else "ai", s.get("query", ""))
        for s in raw if s.get("narration", "").strip()
    ]


def generate_script(config: dict, history: list[dict], insights: str = "", weights: dict[str, float] | None = None) -> Script:
    gemini = Gemini(config["script"]["models"])
    channel = config["channel"]
    video_format = _pick_format([h.get("format", "") for h in history], weights or {})

    pick = json.loads(gemini.json(TOPIC_PROMPT.format(
        **channel,
        format_rule=FORMATS[video_format],
        insights=insights,
        history="; ".join(h["topic"] for h in history[-300:]) or "none",
    ), temperature=1.0))
    print(f"Formato: {video_format}\nTema: {pick['topic']}\nÁngulo: {pick['angle']}")

    try:
        dossier, sources = gemini.grounded(RESEARCH_PROMPT.format(**pick))
    except RuntimeError as e:
        print(f"Búsqueda web de Gemini no disponible ({e.__cause__}); se investiga sin ella")
        dossier, sources = gemini.text(RESEARCH_PROMPT.replace("using web search", "from your knowledge").format(**pick)), []
    print(f"Investigación: {len(dossier.split())} palabras, {len(sources)} fuentes")

    for attempt in range(2):
        data = json.loads(gemini.json(SCRIPT_PROMPT.format(
            **channel,
            **pick,
            dossier=dossier,
            target_words=config["script"]["target_words"],
            chapters=config["script"]["chapters"],
            hook_rules=HOOK_RULES,
        ), temperature=0.8))
        chapters = [Chapter("", _scenes(data["cold_open"]))]
        chapters += [Chapter(c["title"].strip(), _scenes(c["scenes"])) for c in data["chapters"]]
        script = Script(
            topic=pick["topic"],
            format=video_format,
            title=data["title"][:100],
            description=data["description"],
            tags=data["tags"][:20],
            thumbnail_text=data["thumbnail_text"],
            thumbnail_prompt=data["thumbnail_prompt"],
            chapters=[c for c in chapters if c.scenes],
            sources=sources,
            hashtags=[str(h) for h in data.get("hashtags", [])][:5],
        )
        print(f"Guion: {script.words} palabras (~{script.words / 150:.1f} min), {len(script.chapters) - 1} capítulos")
        if script.words >= MIN_WORDS:
            return script
        print("Guion demasiado corto, se regenera")
    raise RuntimeError(f"El guion no alcanza {MIN_WORDS} palabras")
