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
{series_rule}

Pick ONE real, well-documented case for a 12-14 minute episode.
Rules:
- The core events happened before 1990, so there is solid public documentation.
- Do not pick cases whose central figures are minors or that revolve around sexual violence.
- Do not pick cases that would require accusing living people who were never convicted.
- It must have a strong hook, twists and enough material for 6 chapters.
- Prefer cases built around ONE tangible, eerie detail that can be stated in a single sentence: an unbroken code or
  inscription, a last note or message, an object left behind, an empty place where people vanished. That detail is what
  makes the Shorts and the thumbnail work.
- Be specific, never generic: a broad subject ("life in ancient Rome", "famous disappearances") or a case that big
  channels have covered hundreds of times (Roanoke, Mary Celeste, Amelia Earhart, D.B. Cooper, the Zodiac) only works
  with a genuinely new angle: a new piece of evidence, a forgotten document, a detail almost nobody mentions.
- {country_rule}
- Do NOT repeat any of these published topics: {history}

{insights}

Return ONLY JSON:
{{"topic": "case name in 3-8 words", "angle": "one sentence with the new, specific angle that a viewer has not seen in other videos about this case", "country": "ISO 3166 alpha-2 code of the country where the case happened, e.g. US"}}"""

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

HOOK_RULES = """The cold open has 40-60 words TOTAL, split into 3-5 short scenes (roughly 20-25 seconds):
  1. Hook (first sentence, max 12 words): a startling, concrete, visual statement or contradiction that creates an
     instant question. NEVER start with a date, a year, "In", "On", "Back in", "Imagine" or background context.
     The first scene contains ONLY that sentence. Use a documented contradiction, not a vague claim of impossibility.
     Good: "Ten letters carved in stone have beaten the men who broke Enigma."
  2. Within the next two scenes, show the actual evidence behind {title_promise}. Give the viewer one verified detail
     immediately, rather than a list of things you will reveal later.
  3. State ONE clear question raised by that evidence, then move straight into investigating it.
  No greetings, channel name, trailer montage, title-card announcement, "in this video", "let's dive in",
  "to understand why" or "we must go back". Do not restart the story after the opening.
  The first scene's visual must be the most striking image of the whole episode, and never an "ai" image of writing."""

SCRIPT_PROMPT = """You are an award-winning scriptwriter for a faceless YouTube documentary channel about {niche}.
Audience: {audience}. Language: {language}. Tone: {tone}.

Write the full narration of an episode about "{topic}" ({angle}), using ONLY facts from this dossier:
<dossier>
{dossier}
</dossier>

Channel feedback to apply to this narration, not just the topic selection:
{insights}
Treat Shorts examples as hypotheses about clarity and curiosity, not proof that a long documentary will retain viewers.
{revision}

Length: about {target_words} words in total (12-14 minutes). Structure:
- A cold open. {hook_rules}
- Then exactly {chapters} chapters, each with a short evocative title (2-5 words).
- Chapter 1 continues the opening investigation with the first concrete evidence; no second introduction or long
  chronological rewind. Add only the background needed to understand the next clue, when that clue appears.
- Deliver a new verified clue, a resolved small question or an evidence-based reversal roughly every 30-45 seconds.
  Do not repeat the central mystery, list promises or stretch the same detail to reach the word count.
- End every chapter with an open loop that makes the viewer need the next one.
- The narrator has a personality: {host}. Once in the middle and once in the last chapter, add 1-3 sentences of
  first-person opinion, clearly framed as such ("What I keep coming back to is...", "If you ask me..."). Never more.
- The last chapter weighs the theories honestly and ends with a memorable final line. No calls to subscribe or like.
{watch_next_rule}
- Present theories as theories. Never state disputed claims as facts. Never describe gore or violence in detail.
- American English: US spelling (color, center), US customary units (miles, feet, pounds, degrees Fahrenheit) and US
  date format ("October 4, 1931").
- Spoken style: varied sentence length, concrete details, dates and names. Text only for narration: no stage
  directions, no emojis, no markdown.

After the shorter cold open, split chapters into scenes of 1-2 sentences (15-35 words). Each scene has ONE visual:
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
  "title": "YouTube title, max 60 characters, curiosity-driven but honest, and fully delivered by the narration. Speak to what the viewer wants to know, never to the tools or the channel (never mention AI). Build it around the single most intriguing concrete detail of the case (e.g. 'The Cipher That Mourned a Living Woman', 'The Gold Hunter's Final Chilling Note'). Never use the 'Case Name: Subtitle' pattern, never a colon, never start with 'The Mystery of'",
  "description": "2 short paragraphs that summarise the episode without spoiling the ending, naturally including the names, places, year and search terms people would type on YouTube to find this case",
  "tags": ["12-18 tags: case name, people, places, era and related searches"],
  "hashtags": ["3-5 case-specific hashtags without the # symbol and without spaces (e.g. 'DyatlovPass', 'ColdCase', 'Russia')"],
  "thumbnail_text": "2-4 punchy words for the thumbnail that complement the title (never repeat it), open a question and never reveal the answer (e.g. 'NOBODY CAME BACK', 'WHO WROTE THIS?')",
  "thumbnail_prompt": "English prompt for a dramatic thumbnail image built around that same concrete detail (the object, place or message), one clear subject, no text, no real faces",
  "cold_open": [{{"narration": "...", "kind": "archive|stock|ai", "query": "..."}}],
  "chapters": [{{"title": "...", "scenes": [{{"narration": "...", "kind": "archive|stock|ai", "query": "..."}}]}}]
}}"""

PACKAGING_PROMPT = """You are an evidence and packaging editor. Match the promise to what the viewer actually receives.

Title: "{title}"
Thumbnail text: "{thumbnail_text}"
Thumbnail image idea (empty for Shorts): "{thumbnail_prompt}"
Only permitted source material:
<source>
{source}
</source>
Narration:
<narration>
{narration}
</narration>

Check that:
1. Every factual statement in the narration is supported by the source, and disputed claims remain attributed.
   A missing weapon is not proof that a weapon never existed; a theory is not an established event.
2. The narration delivers exactly what the title and the thumbnail text promise, without exaggeration.
3. Title and thumbnail text speak to the viewer's curiosity about the case, not about tools or the channel (no AI).
4. Both are specific and tangible: a concrete detail that feels new, never a generic statement.
If the narration is unsupported, set narration_supported=false and explain what must change. Do not hide that by
rewriting the title. If only the packaging fails, return corrected packaging that the narration fully delivers.
Always return a title of at most 60 characters, no colon, never "The Mystery of"; thumbnail text of 2-4 words that
complements the title. If an image idea was provided, return an aligned English thumbnail_prompt, one clear subject,
no text or recognizable real faces. Set promise_delivered=true only if the narration delivers the returned packaging's
specific promise. For a Short, that detail must be delivered BEFORE the final CTA; otherwise set promise_delivered=false.

Return ONLY JSON:
{{"narration_supported": true, "promise_delivered": true, "issue": "empty if no problem, otherwise the problem in one sentence", "title": "...", "thumbnail_text": "...", "thumbnail_prompt": "aligned image idea, or empty for Shorts"}}"""

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
    country: str = ""
    watch_next: dict = field(default_factory=dict)

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


UNDERPERFORMING_WEIGHT = 0.7
MIN_SERIES_BEFORE_EARLY_ROTATION = 3


def _streak(recent_formats: list[str]) -> int:
    count = 0
    for name in reversed(recent_formats):
        if name != recent_formats[-1]:
            break
        count += 1
    return count


def _pick_format(recent_formats: list[str], weights: dict[str, float], series_length: int = 1) -> str:
    recent_formats = [f for f in recent_formats if f in FORMATS]
    if recent_formats:
        current, streak = recent_formats[-1], _streak(recent_formats)
        underperforming = streak >= MIN_SERIES_BEFORE_EARLY_ROTATION and weights.get(current, 1.0) < UNDERPERFORMING_WEIGHT
        if streak < series_length and not underperforming:
            return current
    options = [f for f in FORMATS if f not in recent_formats[-1:]] or list(FORMATS)
    return random.choices(options, weights=[weights.get(f, 1.0) for f in options])[0]


def _series_rule(history: list[dict], video_format: str) -> str:
    series = []
    for entry in reversed(history):
        if entry.get("format") != video_format:
            break
        series.append(entry["topic"])
    if not series:
        return ""
    return (
        "This episode continues the channel's current series. Pick a case that the same viewer who watched these would "
        f"click next (same kind of mystery, same audience), without repeating them: {'; '.join(reversed(series))}"
    )


def _watch_next(history: list[dict], video_format: str) -> dict:
    published = [h for h in history if h.get("video_id")]
    related = [h for h in published if h.get("format") == video_format] or published
    if not related:
        return {}
    pick = related[-1]
    return {"video_id": pick["video_id"], "title": pick["title"], "topic": pick["topic"]}


def _watch_next_rule(watch_next: dict) -> str:
    if not watch_next:
        return ""
    return (
        f'- The very last scene (after the memorable line) is one sentence that bridges to another episode of the channel, '
        f'"{watch_next["title"]}" about {watch_next["topic"]}: connect it to what the viewer just felt and open a new '
        "question about it, without spoiling it (e.g. \"If this case stays with you, there is another file where ... \"). "
        "Never ask to subscribe or like."
    )


def review_packaging(
    gemini: Gemini, title: str, thumbnail_text: str, narration: str, source: str, thumbnail_prompt: str = "",
) -> dict:
    data = json.loads(gemini.json(PACKAGING_PROMPT.format(
        title=title, thumbnail_text=thumbnail_text, thumbnail_prompt=thumbnail_prompt, narration=narration, source=source,
    ), temperature=0.3))
    if not all(isinstance(data.get(key), bool) for key in ("narration_supported", "promise_delivered")):
        raise RuntimeError("La revisión no ha confirmado las fuentes y la entrega de la promesa")
    if not data["narration_supported"] or not data["promise_delivered"]:
        return data
    corrected_title, corrected_text = data.get("title"), data.get("thumbnail_text")
    if (
        not isinstance(corrected_title, str) or not 1 <= len(corrected_title.strip()) <= 60
        or ":" in corrected_title or corrected_title.lower().startswith("the mystery of")
        or not isinstance(corrected_text, str) or not 2 <= len(corrected_text.split()) <= 4
        or (thumbnail_prompt and (
            not isinstance(data.get("thumbnail_prompt"), str) or not data["thumbnail_prompt"].strip()
        ))
    ):
        raise RuntimeError("La revisión ha devuelto un título o una miniatura fuera de las reglas")
    if corrected_title != title:
        print(f"Packaging corregido: {title} -> {corrected_title}")
    return data


def _scenes(raw: list[dict]) -> list[Scene]:
    return [
        Scene(s["narration"].strip(), s.get("kind", "ai") if s.get("kind") in {"archive", "stock", "ai"} else "ai", s.get("query", ""))
        for s in raw if s.get("narration", "").strip()
    ]


US_CASES_IN_A_ROW = 2


def _country_rule(history: list[dict], focus: str = "") -> str:
    if focus:
        return f"This episode's case MUST have happened in this country (ISO code {focus}): the channel focuses on one audience."
    recent = [h.get("country", "") for h in history[-US_CASES_IN_A_ROW:]]
    if len(recent) < US_CASES_IN_A_ROW or any(c != "US" for c in recent):
        return "This episode's case MUST have happened in the United States: most of the audience is American."
    return (
        "Most of the audience is American: prefer cases in the United States or involving Americans; otherwise the UK, "
        "Canada or Australia."
    )


def generate_script(config: dict, history: list[dict], insights: str = "", weights: dict[str, float] | None = None) -> Script:
    gemini = Gemini(config["script"]["models"])
    channel = config["channel"]
    video_format = _pick_format(
        [h.get("format", "") for h in history], weights or {}, config["script"].get("series_length", 1),
    )
    watch_next = _watch_next(history, video_format)

    pick = json.loads(gemini.json(TOPIC_PROMPT.format(
        **channel,
        format_rule=FORMATS[video_format],
        series_rule=_series_rule(history, video_format),
        insights=insights,
        country_rule=_country_rule(history, config["script"].get("country_focus", "")),
        history="; ".join(h["topic"] for h in history[-300:]) or "none",
    ), temperature=1.0))
    print(f"Formato: {video_format}\nTema: {pick['topic']}\nÁngulo: {pick['angle']}")

    try:
        dossier, sources = gemini.grounded(RESEARCH_PROMPT.format(**pick))
    except RuntimeError as e:
        print(f"Búsqueda web de Gemini no disponible ({e.__cause__}); se investiga sin ella")
        dossier, sources = gemini.text(RESEARCH_PROMPT.replace("using web search", "from your knowledge").format(**pick)), []
    print(f"Investigación: {len(dossier.split())} palabras, {len(sources)} fuentes")

    revision = ""
    for attempt in range(3):
        data = json.loads(gemini.json(SCRIPT_PROMPT.format(
            **{**channel, "host": channel.get("host", "a calm, curious documentary narrator")},
            **pick,
            dossier=dossier,
            target_words=config["script"]["target_words"],
            chapters=config["script"]["chapters"],
            hook_rules=HOOK_RULES.replace("{title_promise}", "the single most intriguing concrete detail of the case"),
            watch_next_rule=_watch_next_rule(watch_next),
            insights=insights or "No eligible analytics yet. Do not invent performance claims.",
            revision=revision,
        ), temperature=0.8))
        chapters = [Chapter("", _scenes(data["cold_open"]))]
        chapters += [Chapter(c["title"].strip(), _scenes(c["scenes"])) for c in data["chapters"]]
        script = Script(
            topic=pick["topic"],
            format=video_format,
            title=data["title"].strip(),
            description=data["description"],
            tags=data["tags"][:20],
            thumbnail_text=data["thumbnail_text"],
            thumbnail_prompt=data["thumbnail_prompt"],
            chapters=[c for c in chapters if c.scenes],
            sources=sources,
            hashtags=[str(h) for h in data.get("hashtags", [])][:5],
            country=str(pick.get("country", "")).upper()[:2],
            watch_next=watch_next,
        )
        print(f"Guion: {script.words} palabras (~{script.words / 150:.1f} min), {len(script.chapters) - 1} capítulos")
        cold_words = sum(len(s.narration.split()) for s in chapters[0].scenes)
        issues = []
        if script.words < MIN_WORDS:
            issues.append(f"The episode needs at least {MIN_WORDS} words; it had {script.words}.")
        if not 40 <= cold_words <= 60 or not 3 <= len(chapters[0].scenes) <= 5:
            issues.append(f"The cold open needs 40-60 words in 3-5 scenes; it had {cold_words} words.")
        if chapters[0].scenes and len(chapters[0].scenes[0].narration.split()) > 12:
            issues.append("The first scene must be a single hook of at most 12 words.")
        if len(script.chapters) != config["script"]["chapters"] + 1:
            issues.append(f"Use a cold open and exactly {config['script']['chapters']} nonempty chapters.")
        if not issues:
            narration = "\n".join(s.narration for c in script.chapters for s in c.scenes)
            source = dossier
            if watch_next:
                source += (
                    "\nApproved next-episode metadata, only for the final recommendation, not evidence for this case:\n"
                    + json.dumps(watch_next, ensure_ascii=False)
                )
            review = review_packaging(
                gemini, script.title, script.thumbnail_text, narration, source, script.thumbnail_prompt,
            )
            if review["narration_supported"] and review["promise_delivered"]:
                script.title = review["title"].strip()
                script.thumbnail_text = review["thumbnail_text"].strip()
                script.thumbnail_prompt = review["thumbnail_prompt"].strip()
                return script
            issues.append(f"Source or promise issue: {review.get('issue', 'check the source material and payoff')}")
        revision = "Fix these problems from the previous draft:\n" + "\n".join(issues)
        print(f"Guion rechazado; se regenera: {revision}")
    raise RuntimeError(f"Gemini no generó un episodio válido: {revision}")
