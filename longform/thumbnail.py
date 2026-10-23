import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from longform import cache, magnific
from longform.gemini import Gemini

FONT = Path(__file__).parent.parent / "fonts" / "Anton-Regular.ttf"
SIZE = (1280, 720)
TEXT_AREA = 0.55
COLORS = [(255, 214, 0), (255, 255, 255)]
VARIATIONS = [
    "",
    "tight close-up of the key object, strong rim light, shallow depth of field",
    "wide establishing view of the place at dusk, a single small human silhouette for scale, glowing light source",
    "low-angle dramatic composition, cold blue shadows with one warm light accent",
]
PICK_PROMPT = """You are a YouTube packaging expert for a mystery documentary channel watched by adults 45+, mostly on TV
and desktop. Video title: "{title}". Thumbnail text: "{text}".
These are {count} thumbnail candidates, numbered 0 to {last} in order. Pick the one most likely to earn the click while
staying honest: one instantly readable focal subject even at small size, strong contrast, clean space behind the text,
an intriguing concrete detail that complements the title, no clutter, no AI artifacts (warped hands, melted objects,
fake lettering, faces). Return ONLY JSON: {{"choice": <index>, "reason": "..."}}"""


def _wrap(text: str) -> list[str]:
    words = text.upper().split()
    if len(words) <= 2:
        return words if len(" ".join(words)) > 12 else [" ".join(words)]
    splits = [(" ".join(words[:i]), " ".join(words[i:])) for i in range(1, len(words))]
    return list(min(splits, key=lambda pair: max(len(pair[0]), len(pair[1]))))


def _fit_font(lines: list[str], max_width: int, max_height: int) -> ImageFont.FreeTypeFont:
    for size in range(190, 40, -4):
        font = ImageFont.truetype(str(FONT), size)
        widths = [font.getbbox(line)[2] for line in lines]
        if max(widths) <= max_width and size * 1.05 * len(lines) <= max_height:
            return font
    return ImageFont.truetype(str(FONT), 40)


def _background(prompt: str, config: dict, workdir: Path) -> Path:
    settings = config["thumbnail"]
    full_prompt = f"{prompt}. {settings['style']}"
    name = cache.key("thumb", full_prompt, settings["model"]) + ".jpg"
    if cached := cache.get(name):
        return cached
    return cache.put(name, magnific.generate(full_prompt, settings["model"], 2048, 1152, workdir / name))


def _compose(background: Path, text: str, out: Path) -> Path:
    image = ImageOps.fit(Image.open(background).convert("RGB"), SIZE, Image.Resampling.LANCZOS)
    shade = Image.new("L", SIZE)
    shade_draw = ImageDraw.Draw(shade)
    for x in range(SIZE[0]):
        shade_draw.line([(x, 0), (x, SIZE[1])], fill=int(235 * max(0.0, 1 - x / (SIZE[0] * 0.8)) ** 0.6))
    image = Image.composite(Image.new("RGB", SIZE, (0, 0, 0)), image, shade)

    lines = _wrap(text)
    margin = 60
    font = _fit_font(lines, int(SIZE[0] * TEXT_AREA) - margin, SIZE[1] - 2 * margin)
    draw = ImageDraw.Draw(image)
    line_height = int(font.size * 1.05)
    y = (SIZE[1] - line_height * len(lines)) // 2
    for i, line in enumerate(lines):
        draw.text((margin, y), line, font=font, fill=COLORS[i % len(COLORS)], stroke_width=6, stroke_fill=(0, 0, 0))
        y += line_height
    image.save(out, "JPEG", quality=95)
    return out


def _pick(candidates: list[Path], title: str, text: str, config: dict) -> int:
    previews = []
    for path in candidates:
        image = Image.open(path).convert("RGB")
        image.thumbnail((640, 360))
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=85)
        previews.append(buffer.getvalue())
    data = json.loads(Gemini(config["script"]["models"]).json_with_images(PICK_PROMPT.format(
        title=title, text=text, count=len(previews), last=len(previews) - 1,
    ), previews))
    choice = data.get("choice", 0)
    print(f"Miniatura elegida: {choice} ({data.get('reason', '')})")
    return choice if isinstance(choice, int) and 0 <= choice < len(candidates) else 0


def create_thumbnail(prompt: str, text: str, config: dict, workdir: Path, out: Path, title: str = "") -> Path:
    count = max(1, min(config["thumbnail"].get("candidates", 1), len(VARIATIONS)))
    prompts = [f"{prompt}, {v}" if v else prompt for v in VARIATIONS[:count]]
    with ThreadPoolExecutor(count) as pool:
        futures = [pool.submit(_background, p, config, workdir) for p in prompts]
    backgrounds = []
    for future in futures:
        try:
            backgrounds.append(future.result())
        except Exception as e:
            print(f"Fondo de miniatura fallido: {e}")
    if not backgrounds:
        raise RuntimeError("No se pudo generar ningún fondo de miniatura")
    candidates = [_compose(b, text, workdir / f"thumbnail_{i}.jpg") for i, b in enumerate(backgrounds)]
    choice = 0
    if len(candidates) > 1:
        try:
            choice = _pick(candidates, title, text, config)
        except Exception as e:
            print(f"No se pudo elegir miniatura con Gemini ({e}); se usa la primera")
    out.write_bytes(candidates[choice].read_bytes())
    return out
