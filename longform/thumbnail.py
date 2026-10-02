from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from longform import cache, magnific

FONT = Path(__file__).parent.parent / "fonts" / "Anton-Regular.ttf"
SIZE = (1280, 720)
TEXT_AREA = 0.55
COLORS = [(255, 214, 0), (255, 255, 255)]


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


def create_thumbnail(prompt: str, text: str, config: dict, workdir: Path, out: Path) -> Path:
    settings = config["thumbnail"]
    full_prompt = f"{prompt}. {settings['style']}"
    name = cache.key("thumb", full_prompt, settings["model"]) + ".jpg"
    background = cache.get(name)
    if not background:
        generated = magnific.generate(full_prompt, settings["model"], 2048, 1152, workdir / name)
        background = cache.put(name, generated)

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
    image.save(out, "JPEG", quality=90)
    return out
