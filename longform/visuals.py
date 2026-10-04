import html
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path

import requests

from longform import cache, magnific
from longform.media import image_size
from longform.script import Scene

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
PEXELS_URL = "https://api.pexels.com/videos/search"
USER_AGENT = "yt-mysteries/1.0 (https://github.com/davigolo; documentary video pipeline)"
FREE_LICENSES = re.compile(r"^(public domain|pd|cc0|cc by(-sa)? [0-9.]+)", re.IGNORECASE)
IMAGE_MIMES = {"image/jpeg", "image/png"}
GENERIC_WORDS = {"The", "A", "An", "Of", "In", "On", "And", "Old", "Historical", "Vintage", "Photo", "Map", "Painting", "Portrait"}


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

    def fetch(self, scenes: list[Scene], durations: list[float]) -> list[Visual]:
        visuals = []
        for i, (scene, seconds) in enumerate(zip(scenes, durations)):
            visual = self._for_scene(scene, seconds)
            visuals.append(visual)
            self.produced.append(visual)
            print(f"\rVisuales: {i + 1}/{len(scenes)} (IA: {self.ai_count})", end="", flush=True)
        print()
        return visuals

    def _for_scene(self, scene: Scene, seconds: float) -> Visual:
        attempts = {
            "archive": [lambda: self._archive(scene.query), lambda: self._ai(f"historical scene evoking {scene.query}, no identifiable faces")],
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

    def _archive(self, query: str) -> Visual | None:
        words = query.split()
        tokens = [w.strip(",.'\"()") for w in words]
        keywords = [t.lower() for t in tokens if t[:1].isupper() and t not in GENERIC_WORDS]
        if not keywords:
            return None
        required = min(2, len(keywords))
        for size in dict.fromkeys([len(words), 5, 4, 3, 2]):
            if size > len(words):
                continue
            visual = self._archive_search(" ".join(words[:size]), keywords, required)
            if visual:
                return visual
        return None

    def _archive_search(self, query: str, keywords: list[str], required: int) -> Visual | None:
        response = requests.get(COMMONS_API, headers={"User-Agent": USER_AGENT}, timeout=30, params={
            "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": 15,
            "gsrsearch": f"{query} filetype:bitmap", "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 2560,
        })
        response.raise_for_status()
        pages = sorted(response.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
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

    def _stock(self, query: str, seconds: float) -> Visual | None:
        response = requests.get(
            PEXELS_URL,
            headers={"Authorization": os.environ["PEXELS_API_KEY"]},
            params={"query": query, "orientation": "portrait" if self.portrait else "landscape", "per_page": 15, "size": "large"},
            timeout=30,
        )
        response.raise_for_status()
        side, target = ("height", self.height) if self.portrait else ("width", self.width)
        for video in response.json().get("videos", []):
            files = [f for f in video["video_files"] if (f.get(side) or 0) >= target and f.get("file_type") == "video/mp4"]
            if str(video["id"]) in self.used or not files or video["duration"] < min(seconds, 8):
                continue
            self.used.add(str(video["id"]))
            link = min(files, key=lambda f: f[side])["link"]
            return Visual(self._download(link, ".mp4"), True, None)
        return None

    def _ai(self, prompt: str) -> Visual | None:
        full_prompt = f"{prompt}. {self.config['ai_style']}"
        name = cache.key("ai", full_prompt, self.config["ai_model"]) + ".jpg"
        if cached := cache.get(name):
            return Visual(cached, False, None)
        if self.ai_count >= self.config["max_ai_images"]:
            return None
        out = magnific.generate(full_prompt, self.config["ai_model"], self.config["ai_width"], self.config["ai_height"], self.workdir / name)
        self.ai_count += 1
        return Visual(cache.put(name, out), False, None)
