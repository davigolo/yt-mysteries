import json
from dataclasses import dataclass, field

from longform.gemini import Gemini

SOURCES = {"ai", "reuse", "stock", "archive"}

PLAN_PROMPT = """You are the director of photography of a faceless documentary {format} about: {context}
Your job is VISUAL CONTINUITY: the viewer must feel one coherent story filmed in one real place and era, never a random
slideshow. Viral channels in this niche do it with: a literal match between every line and what is on screen, the same
recurring locations, people and objects, establishing shot followed by details, and one consistent period look.

Narration units (index: text | writer's first visual idea):
{units}

1. Write a visual bible: era, place, a one-sentence "look" shared by every image (film stock, palette, lighting) that is
   authentic for that era and place, and the recurring characters (wardrobe, build, age; ALWAYS seen from behind, in
   silhouette, from a distance or only their hands; never a face).
2. Define {anchors} ANCHORS: the recurring locations and key objects of the story (the eerie object or place of the
   title and hook MUST be an anchor) (e.g. "the rocky trail in the canyon
   where he was last seen", "the lead masks lying on the grass"). Each anchor is generated once and used as the visual
   reference of every shot that happens there, so the place, the light and the people stay the same.
3. Give EVERY unit one shot, in order:
   - "source": "ai" (a new image generated from its anchor reference), "reuse" (show the anchor image itself again),
     "stock" or "archive".
   - At most {max_ai} units in total may be "ai" (anchors are generated apart). Use "ai" for the units with the most
     concrete, important content; use "reuse" when the line happens in a place already shown.
   {stock_rule}
   {archive_rule}
   - The first two units must be two DIFFERENT images, and two consecutive units never show the same image.
   - "anchor": id of the anchor this shot happens in or shows (required for ai and reuse).
   - "framing": wide, medium, close-up or extreme close-up. Start a place with a wide shot, then go closer. Never the
     same anchor and framing twice in a row.
   - "prompt" (ai only): what the image shows, LITERALLY matching the concrete nouns and actions of the line (if the
     line says "a skull beneath a desert tree", show that skull under that tree; if it says "cruzeiros", show 1960s
     Brazilian cruzeiro banknotes). Every object, vehicle, garment and building must be authentic for the era and place:
     name the era on every object in the prompt (e.g. "a 1960s steel wristwatch") and keep the landscape and vegetation
     of the real place. Never illustrate a word metaphorically. No legible text, no faces, no gore.

Return ONLY JSON:
{{"bible": {{"era": "...", "place": "...", "look": "...", "characters": [{{"id": "c1", "description": "..."}}]}},
  "anchors": [{{"id": "a1", "description": "detailed English image prompt of the location or object, with era-authentic details", "characters": ["c1"]}}],
  "shots": [{{"i": 0, "source": "ai|reuse|stock|archive", "anchor": "a1", "framing": "wide", "prompt": "...", "query": "..."}}]}}"""

PICK_PROMPT = """These are {count} candidate images (numbered 0 to {last} in order) for one shot of a documentary.
Story: {context}. Era and place: {era}, {place}.
Narration at this moment: "{narration}"
What the shot should show: {wanted}

Pick a candidate ONLY if it clearly shows that. REJECT every candidate with anything that breaks the era or place: modern
vehicles, phones, computers, modern clothing, safety vests, modern money, modern buildings or streets, logos, readable
modern text, or a landscape or vegetation different from the real place (e.g. pine forest for a tropical hill, green
forest for a desert). Reject metaphorical, unrelated or generic content. When in doubt, return -1.
Return ONLY JSON: {{"choice": <index or -1 if none fits>, "reason": "..."}}"""


@dataclass
class Shot:
    source: str
    anchor: str | None
    framing: str
    prompt: str
    query: str


@dataclass
class VisualPlan:
    era: str
    place: str
    look: str
    characters: dict[str, str]
    anchors: dict[str, dict]
    shots: list[Shot] = field(default_factory=list)

    def anchor_prompt(self, anchor_id: str) -> str:
        anchor = self.anchors[anchor_id]
        people = "; ".join(self.characters[c] for c in anchor.get("characters", []) if c in self.characters)
        return ". ".join(p for p in (anchor["description"], people and f"People: {people}", self._setting()) if p)

    def shot_prompt(self, shot: Shot) -> str:
        anchor = self.anchors.get(shot.anchor or "", {})
        people = "; ".join(self.characters[c] for c in anchor.get("characters", []) if c in self.characters)
        reference = "Same place, light, palette and people as the reference image, seen from a new angle" if shot.anchor in self.anchors else ""
        return ". ".join(p for p in (f"{shot.framing} shot: {shot.prompt}", reference, people and f"People: {people}", self._setting()) if p)

    def _setting(self) -> str:
        return f"{self.era}, {self.place}. {self.look}"


def _units(narrations: list[str], hints: list[str]) -> str:
    return "\n".join(f"{i}: {n} | {h}" for i, (n, h) in enumerate(zip(narrations, hints)))


def plan_visuals(
    gemini: Gemini, narrations: list[str], hints: list[str], context: str, max_ai: int, anchors: str, archive: bool,
    stock: bool, video_format: str,
) -> VisualPlan:
    stock_rule = (
        '- "stock" ONLY for timeless atmosphere with no people, vehicles, buildings, devices, money or text, and only when '
        'it matches the landscape of the real place: fog, storm clouds, rain, waves, fire, a candle flame, the night sky. '
        '"query" = 2-4 literal English words. Prefer "reuse" whenever the line is about something concrete.'
        if stock else '- Never use "stock".'
    )
    archive_rule = (
        '- "archive" ONLY for real photos, maps or documents of the actual named people, places or records of this case; '
        '"query" = short English search query that always includes the proper name.'
        if archive else '- Never use "archive".'
    )
    data = json.loads(gemini.json(PLAN_PROMPT.format(
        format=video_format, context=context, units=_units(narrations, hints), anchors=anchors, max_ai=max_ai,
        archive_rule=archive_rule, stock_rule=stock_rule,
    ), temperature=0.4))
    bible = data["bible"]
    anchor_ids = {a["id"]: a for a in data["anchors"] if a.get("id") and a.get("description")}
    by_index = {s.get("i"): s for s in data["shots"] if isinstance(s.get("i"), int)}
    shots = []
    for i in range(len(narrations)):
        raw = by_index.get(i, {})
        source = raw.get("source") if raw.get("source") in SOURCES else "reuse"
        if (source == "archive" and not archive) or (source == "stock" and not stock):
            source = "reuse"
        anchor = raw.get("anchor") if raw.get("anchor") in anchor_ids else None
        if source in {"ai", "reuse"} and not anchor and anchor_ids:
            anchor = shots[-1].anchor if shots and shots[-1].anchor else next(iter(anchor_ids))
        if source == "reuse" and shots and shots[-1].source == "reuse" and shots[-1].anchor == anchor:
            source = "ai"
        shots.append(Shot(source, anchor, raw.get("framing", "medium"), raw.get("prompt") or narrations[i], raw.get("query", "")))
    return VisualPlan(
        era=bible.get("era", ""), place=bible.get("place", ""), look=bible.get("look", ""),
        characters={c["id"]: c["description"] for c in bible.get("characters", []) if c.get("id") and c.get("description")},
        anchors=anchor_ids, shots=shots,
    )


def pick_candidate(gemini: Gemini, plan: VisualPlan, context: str, narration: str, wanted: str, previews: list[bytes]) -> int:
    if not previews:
        return -1
    data = json.loads(gemini.json_with_images(PICK_PROMPT.format(
        count=len(previews), last=len(previews) - 1, context=context, era=plan.era, place=plan.place,
        narration=narration, wanted=wanted,
    ), previews))
    choice = data.get("choice", -1)
    return choice if isinstance(choice, int) and 0 <= choice < len(previews) else -1
