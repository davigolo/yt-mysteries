import html
import io
import math
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import Image, ImageStat

from longform import cache, magnific
from longform.gemini import Gemini
from longform.media import image_size
from longform.script import Scene
from longform.visual_plan import Shot, VisualPlan, pick_candidate, plan_visuals

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
PEXELS_URL = "https://api.pexels.com/videos/search"
USER_AGENT = "yt-mysteries/1.0 (https://github.com/davigolo; documentary video pipeline)"
FREE_LICENSES = re.compile(r"^(public domain|pd|cc0|cc by(-sa)? [0-9.]+)", re.IGNORECASE)
IMAGE_MIMES = {"image/jpeg", "image/png"}
PREVIEW_SIZE = 512
MAX_CANDIDATES = 6
GENERIC_WORDS = {"The", "A", "An", "Of", "In", "On", "And", "Old", "Historical", "Vintage", "Photo", "Map", "Painting", "Portrait"}


MIN_BRIGHTNESS = 62
MIN_GAMMA = 0.55


def _lift_shadows(path: Path) -> Path:
    image = Image.open(path).convert("RGB")
    brightness = ImageStat.Stat(image.convert("L")).mean[0]
    if 0 < brightness < MIN_BRIGHTNESS:
        gamma = max(math.log(MIN_BRIGHTNESS / 255) / math.log(brightness / 255), MIN_GAMMA)
        lut = [round(255 * (v / 255) ** gamma) for v in range(256)] * 3
        image.point(lut).save(path, "JPEG", quality=92)
    return path


@dataclass
class Visual:
    path: Path
    is_video: bool
    credit: str | None = None


class VisualSource:
    def __init__(self, config: dict, workdir: Path):
        self.config = config["visuals"]
        self.width = config["video"]["width"]
        self.height = config["video"]["height"]
        self.portrait = self.height > self.width
        self.workdir = workdir
        self.used: set[str] = set()
        self.ai_count = 0
        self.upscale_count = 0
        self.produced: list[Visual] = []
        models = config.get("script", {}).get("models")
        self.gemini = Gemini(models) if models and self.config.get("plan") else None
        self.plan: VisualPlan | None = None
        self.context = ""
        self.anchor_images: dict[str, Path] = {}

    def fetch(self, scenes: list[Scene], durations: list[float], context: str = "") -> list[Visual]:
        if self.gemini:
            try:
                return self._fetch_planned(scenes, durations, context)
            except Exception as e:
                print(f"\nPlan visual no disponible ({type(e).__name__}: {e}); se usan los visuales del guion")
                self.plan = None
        visuals = []
        for i, (scene, seconds) in enumerate(zip(scenes, durations)):
            visual = self._for_scene(scene, seconds)
            visuals.append(visual)
            self.produced.append(visual)
            print(f"\rVisuales: {i + 1}/{len(scenes)} (IA: {self.ai_count})", end="", flush=True)
        print()
        return visuals

    def _fetch_planned(self, scenes: list[Scene], durations: list[float], context: str) -> list[Visual]:
        self.context = context
        budget = self.config["max_ai_images"]
        anchors = self.config.get("plan_anchors", "2-4")
        max_anchors = int(str(anchors).split("-")[-1])
        self.plan = plan_visuals(
            self.gemini, [s.narration for s in scenes], [f"{s.kind}: {s.query}" for s in scenes], context,
            max_ai=max(budget - max_anchors, 0), anchors=anchors, archive=self.config.get("archive", True),
            stock=self.config.get("plan_stock", True),
            video_format="vertical YouTube Short" if self.portrait else "long-form YouTube episode",
        )
        counts = {k: sum(1 for s in self.plan.shots if s.source == k) for k in ("ai", "reuse", "stock", "archive")}
        print(f"Plan visual: {self.plan.era}, {self.plan.place}; {len(self.plan.anchors)} anclas, {counts}")
        visuals = []
        for i, (scene, shot, seconds) in enumerate(zip(scenes, self.plan.shots, durations)):
            visual = self._for_shot(scene, shot, seconds)
            visuals.append(visual)
            self.produced.append(visual)
            print(f"\rVisuales: {i + 1}/{len(scenes)} (IA: {self.ai_count})", end="", flush=True)
        print()
        return visuals

    def _for_shot(self, scene: Scene, shot: Shot, seconds: float) -> Visual:
        wanted = shot.prompt if shot.source == "ai" else shot.query or scene.query
        attempts = {
            "ai": [lambda: self._planned_ai(shot), lambda: self._anchor(shot.anchor)],
            "reuse": [lambda: self._anchor(shot.anchor)],
            "stock": [lambda: self._stock(shot.query or scene.query, seconds, scene.narration, wanted)],
            "archive": [lambda: self._archive(shot.query or scene.query, scene.narration, wanted)],
        }[shot.source]
        attempts += [lambda: self._anchor(shot.anchor), lambda: self._anchor(self._last_anchor())]
        for attempt in attempts:
            try:
                visual = attempt()
                if visual and self.produced and visual.path == self.produced[-1].path and shot.anchor:
                    visual = self._planned_ai(shot) or visual
                if visual:
                    return visual
            except Exception as e:
                print(f"\nVisual fallido ({shot.source}: {wanted[:60]}): {e}")
        if self.produced:
            return self.produced[-1]
        raise RuntimeError("No hay ningún visual disponible")

    def _last_anchor(self) -> str | None:
        return next(reversed(self.anchor_images), None) or next(iter(self.plan.anchors), None)

    def _anchor(self, anchor_id: str | None) -> Visual | None:
        if not anchor_id or anchor_id not in self.plan.anchors:
            return None
        if anchor_id not in self.anchor_images:
            visual = self._ai(self.plan.anchor_prompt(anchor_id))
            if not visual:
                return None
            self.anchor_images[anchor_id] = visual.path
        return Visual(self.anchor_images[anchor_id], False, None)

    def _planned_ai(self, shot: Shot) -> Visual | None:
        reference = self._anchor(shot.anchor)
        return self._ai(self.plan.shot_prompt(shot), [reference.path] if reference else None)

    def _vet(self, previews: list[bytes], narration: str, wanted: str) -> int:
        if not self.plan or not self.gemini:
            return 0
        return pick_candidate(self.gemini, self.plan, self.context, narration, wanted, previews)

    @staticmethod
    def _preview(url: str, headers: dict | None = None) -> bytes | None:
        try:
            response = requests.get(url, timeout=30, headers=headers)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content)).convert("RGB")
            image.thumbnail((PREVIEW_SIZE, PREVIEW_SIZE))
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=80)
            return buffer.getvalue()
        except (requests.RequestException, OSError):
            return None

    def _for_scene(self, scene: Scene, seconds: float) -> Visual:
        archive_ai = lambda: self._ai(f"historical scene evoking {scene.query}, no identifiable faces")
        archive = [lambda: self._archive(scene.query), archive_ai] if self.config.get("archive", True) else [
            archive_ai, lambda: self._stock(" ".join(scene.query.split()[:4]), seconds),
        ]
        attempts = {
            "archive": archive,
            "stock": [lambda: self._stock(scene.query, seconds), lambda: self._ai(scene.query)],
            "ai": [lambda: self._ai(scene.query), lambda: self._stock(" ".join(scene.query.split()[:4]), seconds)],
        }[scene.kind]
        for attempt in attempts:
            try:
                visual = attempt()
                if visual:
                    return visual
            except Exception as e:
                print(f"\nVisual fallido ({scene.kind}: {scene.query[:60]}): {e}")
        if self.produced:
            return random.choice(self.produced)
        visual = self._stock("dark foggy landscape", seconds)
        if not visual:
            raise RuntimeError("No hay ningún visual disponible")
        return visual

    def _download(self, url: str, suffix: str, headers: dict | None = None) -> Path:
        name = cache.key("dl", url) + suffix
        if cached := cache.get(name):
            return cached
        tmp = self.workdir / name
        with requests.get(url, stream=True, timeout=180, headers=headers) as r:
            r.raise_for_status()
            with tmp.open("wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        return cache.put(name, tmp)

    def _archive(self, query: str, narration: str = "", wanted: str = "") -> Visual | None:
        words = query.split()
        tokens = [w.strip(",.'\"()") for w in words]
        keywords = [t.lower() for t in tokens if t[:1].isupper() and t not in GENERIC_WORDS]
        if not keywords:
            return None
        required = min(2, len(keywords))
        for size in dict.fromkeys([len(words), 5, 4, 3, 2]):
            if size > len(words):
                continue
            visual = self._archive_search(" ".join(words[:size]), keywords, required, narration, wanted)
            if visual:
                return visual
        return None

    def _archive_search(self, query: str, keywords: list[str], required: int, narration: str, wanted: str) -> Visual | None:
        response = requests.get(COMMONS_API, headers={"User-Agent": USER_AGENT}, timeout=30, params={
            "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": 15,
            "gsrsearch": f"{query} filetype:bitmap", "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 2560,
        })
        response.raise_for_status()
        pages = sorted(response.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
        candidates = []
        for page in pages:
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata", {})
            license_name = meta.get("LicenseShortName", {}).get("value", "")
            url = info.get("thumburl") or info.get("url")
            title_words = set(re.findall(r"[a-z0-9]+", page["title"].lower()))
            if sum(k in title_words for k in keywords) < required:
                continue
            if (
                not url or url in self.used or info.get("mime") not in IMAGE_MIMES
                or info.get("width", 0) < 800 or not FREE_LICENSES.match(license_name)
            ):
                continue
            candidates.append((page, info, meta, license_name, url))
            if len(candidates) >= MAX_CANDIDATES:
                break
        if self.plan and candidates:
            previews = [self._preview(re.sub(r"/\d+px-", f"/{PREVIEW_SIZE}px-", c[4]), {"User-Agent": USER_AGENT}) for c in candidates]
            usable = [(c, p) for c, p in zip(candidates, previews) if p]
            choice = self._vet([p for _, p in usable], narration, wanted)
            candidates = [usable[choice][0]] if choice >= 0 else []
        for page, info, meta, license_name, url in candidates[:1]:
            self.used.add(url)
            path = self._download(url, Path(url).suffix.lower() or ".jpg", {"User-Agent": USER_AGENT})
            artist = re.sub(r"<[^>]+>", "", html.unescape(meta.get("Artist", {}).get("value", ""))).strip() or "Unknown"
            credit = f"{page['title'].removeprefix('File:')} - {artist} - {license_name} - {info.get('descriptionurl', '')}"
            return Visual(self._maybe_upscale(path), False, credit)
        return None

    def _maybe_upscale(self, path: Path) -> Path:
        threshold, limit = self.config["upscale_archive_below"], self.config["max_upscales"]
        if not threshold or self.upscale_count >= limit or image_size(path)[1] >= threshold:
            return path
        name = cache.key("upscale", path.name) + ".jpg"
        if cached := cache.get(name):
            return cached
        self.upscale_count += 1
        return cache.put(name, magnific.upscale(path, self.workdir / name))

    def _stock(self, query: str, seconds: float, narration: str = "", wanted: str = "") -> Visual | None:
        response = requests.get(
            PEXELS_URL,
            headers={"Authorization": os.environ["PEXELS_API_KEY"]},
            params={"query": query, "orientation": "portrait" if self.portrait else "landscape", "per_page": 15, "size": "large"},
            timeout=30,
        )
        response.raise_for_status()
        side, target = ("height", self.height) if self.portrait else ("width", self.width)
        candidates = []
        for video in response.json().get("videos", []):
            files = [f for f in video["video_files"] if (f.get(side) or 0) >= target and f.get("file_type") == "video/mp4"]
            if str(video["id"]) in self.used or not files or video["duration"] < min(seconds, 8):
                continue
            candidates.append((video, files))
            if len(candidates) >= MAX_CANDIDATES:
                break
        if self.plan and candidates:
            previews = [self._preview(video.get("image", "")) for video, _ in candidates]
            usable = [(c, p) for c, p in zip(candidates, previews) if p]
            choice = self._vet([p for _, p in usable], narration, wanted)
            candidates = [usable[choice][0]] if choice >= 0 else []
        for video, files in candidates[:1]:
            self.used.add(str(video["id"]))
            link = min(files, key=lambda f: f[side])["link"]
            return Visual(self._download(link, ".mp4"), True, None)
        return None

    def _ai(self, prompt: str, references: list[Path] | None = None) -> Visual | None:
        full_prompt = f"{prompt}. {self.config['ai_style']}"
        model = self.config.get("plan_model", self.config["ai_model"]) if self.plan else self.config["ai_model"]
        name = cache.key("ai", full_prompt, model, *(r.name for r in references or [])) + ".jpg"
        if cached := cache.get(name):
            return Visual(cached, False, None)
        if self.ai_count >= self.config["max_ai_images"]:
            return None
        out = _lift_shadows(magnific.generate(full_prompt, model, self.config["ai_width"], self.config["ai_height"], self.workdir / name, references))
        self.ai_count += 1
        return Visual(cache.put(name, out), False, None)
