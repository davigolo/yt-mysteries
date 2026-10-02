import base64
import os
import time
from pathlib import Path

import requests

API = "https://api.magnific.com/v1/ai"
ENDPOINTS = {
    "mystic": "mystic",
    "flux-2-turbo": "text-to-image/flux-2-turbo",
    "flux-2-pro": "text-to-image/flux-2-pro",
    "upscale": "image-upscaler-precision",
}


def _headers() -> dict[str, str]:
    return {"x-magnific-api-key": os.environ["MAGNIFIC_API_KEY"], "Content-Type": "application/json"}


def _task(endpoint: str, payload: dict, out: Path, timeout: int = 300) -> Path:
    url = f"{API}/{ENDPOINTS[endpoint]}"
    for attempt in range(4):
        response = requests.post(url, headers=_headers(), json=payload, timeout=60)
        if response.status_code not in {429, 500, 502, 503}:
            break
        time.sleep(15 * (attempt + 1))
    if not response.ok:
        raise RuntimeError(f"Magnific {endpoint} {response.status_code}: {response.text[:500]}")
    task_id = response.json()["data"]["task_id"]

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(4)
        try:
            status = requests.get(f"{url}/{task_id}", headers=_headers(), timeout=60)
        except requests.RequestException as e:
            print(f"Magnific: error de red consultando la tarea ({type(e).__name__}), reintento")
            continue
        if status.status_code in {429, 500, 502, 503}:
            continue
        status.raise_for_status()
        data = status.json()["data"]
        if data["status"] == "COMPLETED" and data.get("generated"):
            image = requests.get(data["generated"][0], timeout=120)
            image.raise_for_status()
            out.write_bytes(image.content)
            return out
        if data["status"] == "FAILED":
            raise RuntimeError(f"Magnific {endpoint} falló: {data}")
    raise TimeoutError(f"Magnific {endpoint} no terminó en {timeout}s")


def generate(prompt: str, model: str, width: int, height: int, out: Path) -> Path:
    if model == "mystic":
        payload = {"prompt": prompt, "aspect_ratio": "widescreen_16_9", "resolution": "2k", "filter_nsfw": True}
    else:
        payload = {"prompt": prompt, "image_size": {"width": width, "height": height}, "output_format": "jpeg"}
    return _task(model, payload, out)


def upscale(image: Path, out: Path) -> Path:
    payload = {"image": base64.b64encode(image.read_bytes()).decode(), "sharpen": 30, "smart_grain": 5, "ultra_detail": 20}
    return _task("upscale", payload, out)
