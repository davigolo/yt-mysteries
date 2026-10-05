import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

FONT = Path(__file__).parent.parent / "fonts" / "Anton-Regular.ttf"
SIZE = (1080, 1920)
COLORS = [(255, 214, 0), (255, 255, 255)]


def _frame(path: Path, is_video: bool, workdir: Path) -> Image.Image:
    if not is_video:
        return Image.open(path).convert("RGB")
    still = workdir / "short_thumb_frame.jpg"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", "1", "-i", str(path), "-frames:v", "1", "-q:v", "2", str(still)],
        check=True,
    )
    return Image.open(still).convert("RGB")


def _wrap(text: str) -> list[str]:
    words = text.upper().split()
    if len(words) <= 2:
        return words
    splits = [(" ".join(words[:i]), " ".join(words[i:])) for i in range(1, len(words))]
    return list(min(splits, key=lambda pair: max(len(pair[0]), len(pair[1]))))


def _fit(lines: list[str], max_width: int, max_height: int) -> ImageFont.FreeTypeFont:
    for size in range(260, 60, -6):
        font = ImageFont.truetype(str(FONT), size)
        if max(font.getbbox(line)[2] for line in lines) <= max_width and size * 1.08 * len(lines) <= max_height:
            return font
    return ImageFont.truetype(str(FONT), 60)


def create_short_thumbnail(path: Path, is_video: bool, text: str, workdir: Path, out: Path) -> Path:
    frame = _frame(path, is_video, workdir)
    background = ImageOps.fit(frame, SIZE, Image.Resampling.LANCZOS)
    if frame.width > frame.height:
        blurred = background.filter(ImageFilter.GaussianBlur(40))
        fitted = ImageOps.fit(frame, (SIZE[0], int(SIZE[1] * 0.58)), Image.Resampling.LANCZOS)
        blurred.paste(fitted, (0, int(SIZE[1] * 0.36)))
        background = blurred

    shade = Image.new("L", SIZE)
    draw_shade = ImageDraw.Draw(shade)
    for y in range(SIZE[1]):
        top = max(0.0, 1 - y / (SIZE[1] * 0.45)) ** 0.8
        bottom = max(0.0, (y - SIZE[1] * 0.8) / (SIZE[1] * 0.2))
        draw_shade.line([(0, y), (SIZE[0], y)], fill=int(225 * max(top, bottom)))
    image = Image.composite(Image.new("RGB", SIZE, (0, 0, 0)), background, shade)

    lines = _wrap(text)
    margin = 70
    font = _fit(lines, SIZE[0] - 2 * margin, int(SIZE[1] * 0.32))
    draw = ImageDraw.Draw(image)
    line_height = int(font.size * 1.08)
    y = int(SIZE[1] * 0.08)
    for i, line in enumerate(lines):
        width = font.getbbox(line)[2]
        draw.text(((SIZE[0] - width) // 2, y), line, font=font, fill=COLORS[i % len(COLORS)],
                  stroke_width=10, stroke_fill=(0, 0, 0))
        y += line_height
    image.save(out, "JPEG", quality=90)
    return out
