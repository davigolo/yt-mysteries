import json
import re
from dataclasses import dataclass, field
from uuid import uuid4

from longform.gemini import Gemini
from longform.series import (
    MICRONICHES, Series, active_series, choose_series, microniche_scope, neighbor_microniches, series_rule,
)

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
{availability}
{revision}

The locked microniche is mandatory. If you cannot find a suitable, documented, unused case inside it, return
exhausted=true with a specific reason instead of inventing evidence, repeating a case or changing the microniche.

Return ONLY JSON:
{{"exhausted": false, "exhaustion_reason": "", "microniche": "the locked microniche id", "topic": "case name in 3-8 words, empty if exhausted", "angle": "one sentence with the new, specific angle that a viewer has not seen in other videos about this case", "country": "ISO 3166 alpha-2 country code, e.g. US"}}"""

AVAILABILITY_PROMPT = """Search the web for suitable UNUSED cases for this locked documentary microniche:
{series_rule}
Country requirement: {country_rule}
Already covered cases (exclude the same incident under any alternative name): {history}

Find up to three DISTINCT real cases with core events before 1990, enough documented evidence for a full investigation
and a genuinely new concrete angle. Exclude central figures who are minors, sexual violence, accusations against living
unconvicted people and cases outside the locked boundaries. Give source links and explain how each fits.
If you cannot find one, explain the specific evidence or scope limitation. Do not claim to have proved that no case exists.
Do not silently widen the microniche or invent a case to fill the quota."""

TOPIC_FIT_PROMPT = """Check a proposed documentary against its researched dossier.
{series_rule}
Country requirement: {country_rule}
Proposed case: {topic}
Proposed angle: {angle}
Already covered cases (including other names for the same incident): {history}
Dossier:
{dossier}

Return eligible=true ONLY if the dossier supports the core premise and shows this is a distinct, unused case inside the
locked microniche and country requirement. Its events must be before 1990, central figures must not be minors, and it
must not revolve around sexual violence or accuse a living unconvicted person. A token mention of a note, vessel or
expedition does not make an unrelated case fit. Do not invent a missing clue or unresolved fate to make it fit.
Return ONLY JSON: {{"eligible": true, "reason": "specific explanation"}}"""

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
  2. Within the first 50 spoken words (about 20 seconds at 150 words per minute), show the actual evidence behind
     {title_promise} AND the title you return. Identify the tangible object, message or recorded observation and what
     is unusual about it. Give one source-supported detail now, not just a promise to reveal it later.
     Defer names, dates and biography unless essential to understanding that evidence.
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
Treat individual best or worst episodes as limited observations, not universal formulas or guarantees of improvement.
Apply relevant feedback within the locked microniche; a weaker opening is not a reason to change the series.
{series_rule}
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
Opening excerpt:
<opening>
{opening}
</opening>
Opening requirements for this format:
{opening_rule}

Check that:
1. Every factual statement in the narration is supported by the source, and disputed claims remain attributed.
   A missing weapon is not proof that a weapon never existed; a theory is not an established event.
2. The narration delivers exactly what the title and the thumbnail text promise, without exaggeration.
3. Title and thumbnail text speak to the viewer's curiosity about the case, not about tools or the channel (no AI).
4. Both are specific and tangible: a concrete detail that feels new, never a generic statement.
5. The opening meets ALL the format requirements above. Check the returned title and thumbnail too, not just the
   original packaging. No greeting, channel introduction, empty suspense or unnecessary names, dates or biography.
   The investigation must continue after the hook, not restart with a second introduction or chronological rewind.
Set opening_valid=false if the evidence or title connection is delayed, the anomaly is unsupported or the opening
needs rewriting. A title correction alone must not conceal a weak opening. In issue, identify the missing evidence
or delayed promise and give a concrete narration revision. Never invent evidence, amplify uncertainty into
impossibility, withhold the promised detail for a click or prescribe engagement tricks.
If the narration is unsupported, set narration_supported=false and explain what must change. Do not hide that by
rewriting the title. If only the packaging fails, return corrected packaging that the narration fully delivers.
Always return a title of at most 60 characters, no colon, never "The Mystery of"; thumbnail text of 2-4 words that
complements the title. If an image idea was provided, return an aligned English thumbnail_prompt, one clear subject,
no text or recognizable real faces. Set promise_delivered=true only if the narration delivers the returned packaging's
specific promise. For a Short, that detail must be delivered BEFORE the final CTA; otherwise set promise_delivered=false.

Return ONLY JSON:
{{"narration_supported": true, "promise_delivered": true, "opening_valid": true, "issue": "empty if no problem, otherwise the problem and concrete narration fix", "title": "...", "thumbnail_text": "...", "thumbnail_prompt": "aligned image idea, or empty for Shorts"}}"""

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
    microniche: str = ""
    series_id: str = ""
    series_reason: str = ""

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


def _watch_next(history: list[dict], series: Series) -> dict:
    published = [h for h in history if h.get("video_id")]
    related = (
        [h for h in published if h.get("series_id") == series.series_id and h.get("microniche") == series.microniche]
        or [h for h in published if h.get("microniche") == series.microniche]
        or [h for h in published if not h.get("microniche") and h.get("format") == MICRONICHES[series.microniche]["format"]]
    )
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
    *, short: bool = False,
) -> dict:
    opening = "\n".join(narration.splitlines()[:2]) if short else " ".join(narration.split()[:50])
    opening_rule = (
        "The first beat is at most 8 words and states a concrete, source-verifiable anomaly, not generic suspense. "
        "The next beat provides evidence connecting it to the title, not a larger unsupported promise. "
        "The specific payoff must arrive before the final CTA and loop; the Short must stand on its own."
        if short else
        "Within the first 50 spoken words, identify the tangible evidence and deliver a source-supported detail "
        "that substantiates the title's central promise. This word budget estimates 20 seconds at 150 words per "
        "minute; it is not measured audio timing. Do not accept a promise of later evidence as delivery."
    )
    data = json.loads(gemini.json(PACKAGING_PROMPT.format(
        title=title, thumbnail_text=thumbnail_text, thumbnail_prompt=thumbnail_prompt, narration=narration, source=source,
        opening=opening, opening_rule=opening_rule,
    ), temperature=0.3))
    if not all(isinstance(data.get(key), bool) for key in ("narration_supported", "promise_delivered", "opening_valid")):
        raise RuntimeError("La revisión no ha confirmado las fuentes, la promesa y la apertura")
    if not data["narration_supported"] or not data["promise_delivered"] or not data["opening_valid"]:
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


def _pick_case(
    gemini: Gemini, config: dict, history: list[dict], insights: str, series: Series, episodes: list[dict],
) -> tuple[Series, dict, str, list[dict]]:
    settings = config["script"]["microniche"]
    current = active_series(history)
    previous = current[-1]["microniche"] if current else None
    origin = previous or series.microniche
    candidates = [series.microniche] + [
        name for name in neighbor_microniches(origin, history, episodes, settings)
        if name != previous and name != series.microniche
    ]
    covered = "; ".join(h["topic"] for h in history) or "none"
    country_rule = _country_rule(history, config["script"].get("country_focus", ""))
    normalized = {re.sub(r"\W+", " ", h["topic"]).strip().casefold() for h in history}
    transition_reason = ""
    for name in candidates:
        selected = series if name == series.microniche else Series(name, uuid4().hex, transition_reason)
        scope = series_rule(name, history)
        availability, revision, confirmed_exhausted = "", "", False
        for _ in range(3):
            pick = json.loads(gemini.json(TOPIC_PROMPT.format(
                **config["channel"], format_rule=FORMATS[MICRONICHES[name]["format"]],
                series_rule=scope, insights=insights, country_rule=country_rule, history=covered,
                availability=availability, revision=revision,
            ), temperature=0.8))
            if not isinstance(pick.get("exhausted"), bool):
                raise RuntimeError("El selector de temas no ha indicado si encontró un caso válido")
            if pick["exhausted"]:
                reason = str(pick.get("exhaustion_reason") or "").strip()
                if not reason:
                    raise RuntimeError("El selector declaró agotamiento sin explicar el motivo")
                if not availability:
                    evidence, evidence_sources = gemini.grounded(AVAILABILITY_PROMPT.format(
                        series_rule=scope, country_rule=country_rule, history=covered,
                    ))
                    if not evidence.strip() or not evidence_sources:
                        raise RuntimeError("No hay fuentes de búsqueda para justificar abandonar el micronicho")
                    availability = f"Web search for unused cases; evaluate these findings before giving up:\n{evidence}"
                    print(f"Se revisa la disponibilidad de casos de {name} con fuentes antes de cambiar")
                    continue
                transition_reason = (
                    f"Adjacent pivot from {origin}: no suitable unused case was found in {name} "
                    f"even after a sourced search: {reason}"
                )
                print(f"Cambio editorial de micronicho: {transition_reason}")
                confirmed_exhausted = True
                break
            topic = pick.get("topic")
            if (
                pick.get("microniche") != name or not isinstance(topic, str) or not topic.strip()
                or re.sub(r"\W+", " ", topic).strip().casefold() in normalized
                or not isinstance(pick.get("angle"), str) or not pick["angle"].strip()
                or (config["script"].get("country_focus") and pick.get("country") != config["script"]["country_focus"])
            ):
                revision = "Return a distinct unused case, the exact locked microniche id and the required country code."
                print(f"Tema fuera de las reglas de la serie {name}; se vuelve a seleccionar")
                continue
            try:
                dossier, sources = gemini.grounded(RESEARCH_PROMPT.format(**pick))
            except RuntimeError as e:
                print(f"Búsqueda web de Gemini no disponible ({e.__cause__}); se investiga sin ella")
                dossier = gemini.text(RESEARCH_PROMPT.replace("using web search", "from your knowledge").format(**pick))
                sources = []
            fit = json.loads(gemini.json(TOPIC_FIT_PROMPT.format(
                series_rule=scope, country_rule=country_rule, topic=topic, angle=pick["angle"],
                history=covered, dossier=dossier,
            ), temperature=0.2))
            if not isinstance(fit.get("eligible"), bool):
                raise RuntimeError("No se ha confirmado el encaje del caso con el micronicho")
            if fit["eligible"]:
                return selected, pick, dossier, sources
            revision = f'Reject "{topic}" and choose another case. Dossier-based scope check: {fit.get("reason", "")}'
            print(f"Caso rechazado para {name}: {revision}")
        if not confirmed_exhausted:
            raise RuntimeError(f"No se encontró un caso válido para {name}; eso no demuestra que el micronicho esté agotado")
    raise RuntimeError("No se encontraron casos adecuados en el micronicho ni en sus vecinos; se requiere revisión editorial")


def generate_script(
    config: dict, history: list[dict], insights: str = "", episode_performance: list[dict] | None = None,
) -> Script:
    gemini = Gemini(config["script"]["models"])
    channel = config["channel"]
    episodes = episode_performance or []
    series = choose_series(history, episodes, config["script"]["microniche"])
    series, pick, dossier, sources = _pick_case(gemini, config, history, insights, series, episodes)
    video_format = MICRONICHES[series.microniche]["format"]
    watch_next = _watch_next(history, series)
    print(f"Micronicho: {series.microniche}\nDecisión: {series.reason}\nTema: {pick['topic']}\nÁngulo: {pick['angle']}")
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
            series_rule=microniche_scope(series.microniche),
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
            microniche=series.microniche,
            series_id=series.series_id,
            series_reason=series.reason,
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
            if review["narration_supported"] and review["promise_delivered"] and review["opening_valid"]:
                script.title = review["title"].strip()
                script.thumbnail_text = review["thumbnail_text"].strip()
                script.thumbnail_prompt = review["thumbnail_prompt"].strip()
                return script
            issues.append(f"Source, promise or opening issue: {review.get('issue') or 'check the evidence, opening and payoff'}")
        revision = "Fix these problems from the previous draft:\n" + "\n".join(issues)
        print(f"Guion rechazado; se regenera: {revision}")
    raise RuntimeError(f"Gemini no generó un episodio válido: {revision}")
