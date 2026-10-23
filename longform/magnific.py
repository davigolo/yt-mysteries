import base64
import io
import os
import time
from pathlib import Path

import requests
from PIL import Image

API = "https://api.magnific.com/v1/ai"
ENDPOINTS = {
    "mystic": "mystic",
    "flux-2-turbo": "text-to-image/flux-2-turbo",
    "flux-2-pro": "text-to-image/flux-2-pro",
    "flux-2-klein": "text-to-image/flux-2-klein",
    "upscale": "image-upscaler-precision",
    "kling-v2-6-pro": "image-to-video/kling-v2-6-pro",
}
STATUS_ENDPOINTS = {"kling-v2-6-pro": "image-to-video/kling-v2-6"}
FLUX_PRO_MAX_SIDE = 1440
KLING_MAX_BYTES = 9 * 1024 * 1024
REFERENCE_MAX_BYTES = 3 * 1024 * 1024


def _headers() -> dict[str, str]:
    return {"x-magnific-api-key": os.environ["MAGNIFIC_API_KEY"], "Content-Type": "application/json"}


def _task(endpoint: str, payload: dict, out: Path, timeout: int = 300) -> Path:
    url = f"{API}/{ENDPOINTS[endpoint]}"
    status_url = f"{API}/{STATUS_ENDPOINTS.get(endpoint, ENDPOINTS[endpoint])}"
    for attempt in range(4):
        response = requests.post(url, headers=_headers(), json=payload, timeout=60)
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        time.sleep(15 * (attempt + 1))
    if not response.ok:
        raise RuntimeError(f"Magnific {endpoint} {response.status_code}: {response.text[:500]}")
    task_id = response.json()["data"]["task_id"]

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(4)
        try:
            status = requests.get(f"{status_url}/{task_id}", headers=_headers(), timeout=60)
        except requests.RequestException as e:
            print(f"Magnific: error de red consultando la tarea ({type(e).__name__}), reintento")
            continue
        if status.status_code in {429, 500, 502, 503, 504}:
            continue
        status.raise_for_status()
        data = status.json()["data"]
        if data["status"] == "COMPLETED" and data.get("generated"):
            result = requests.get(data["generated"][0], timeout=300)
            result.raise_for_status()
            out.write_bytes(result.content)
            return out
        if data["status"] == "FAILED":
            raise RuntimeError(f"Magnific {endpoint} falló: {data}")
    raise TimeoutError(f"Magnific {endpoint} no terminó en {timeout}s")


def _flux_pro_size(width: int, height: int) -> tuple[int, int]:
    scale = FLUX_PRO_MAX_SIDE / max(width, height)
    return int(width * scale) // 16 * 16, int(height * scale) // 16 * 16


def _encoded(path: Path, max_bytes: int | None = None) -> str:
    data = path.read_bytes()
    if max_bytes and len(data) > max_bytes:
        image = Image.open(path).convert("RGB")
        image.thumbnail((2048, 2048))
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=90)
        data = buffer.getvalue()
    return base64.b64encode(data).decode()


def generate(prompt: str, model: str, width: int, height: int, out: Path, references: list[Path] | None = None) -> Path:
    if model == "mystic":
        payload = {"prompt": prompt, "aspect_ratio": "widescreen_16_9", "resolution": "2k", "filter_nsfw": True}
    elif model == "flux-2-klein":
        payload = {
            "prompt": prompt, "resolution": "2k", "output_format": "jpeg",
            "aspect_ratio": "social_story_9_16" if height > width else "widescreen_16_9",
        }
        for i, reference in enumerate((references or [])[:4]):
            payload["input_image" if i == 0 else f"input_image_{i + 1}"] = _encoded(reference, REFERENCE_MAX_BYTES)
    elif model == "flux-2-pro":
        pro_width, pro_height = _flux_pro_size(width, height)
        payload = {"prompt": prompt, "width": pro_width, "height": pro_height}
        for i, reference in enumerate((references or [])[:4]):
            payload["input_image" if i == 0 else f"input_image_{i + 1}"] = _encoded(reference, REFERENCE_MAX_BYTES)
    else:
        payload = {"prompt": prompt, "image_size": {"width": width, "height": height}, "output_format": "jpeg"}
    return _task(model, payload, out)


def upscale(image: Path, out: Path) -> Path:
    payload = {"image": base64.b64encode(image.read_bytes()).decode(), "sharpen": 30, "smart_grain": 5, "ultra_detail": 20}
    return _task("upscale", payload, out)


def animate(image: Path, prompt: str, out: Path, seconds: int, portrait: bool, model: str = "kling-v2-6-pro") -> Path:
    payload = {
        "image": _encoded(image, KLING_MAX_BYTES),
        "prompt": prompt,
        "negative_prompt": (
            "faces, facial features, talking, text, letters, watermark, logo, morphing, distorted anatomy, "
            "extra limbs, fast camera shake, cartoon, modern objects"
        ),
        "cfg_scale": 0.5,
        "duration": "10" if seconds > 5 else "5",
        "aspect_ratio": "social_story_9_16" if portrait else "widescreen_16_9",
        "generate_audio": False,
    }
    return _task(model, payload, out, timeout=900)
