import hashlib
import shutil
from pathlib import Path

CACHE = Path(__file__).parent.parent / "cache"


def key(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).hexdigest()[:20]


def get(name: str) -> Path | None:
    path = CACHE / name
    return path if path.exists() and path.stat().st_size > 0 else None


def put(name: str, source: Path) -> Path:
    CACHE.mkdir(exist_ok=True)
    target = CACHE / name
    shutil.copyfile(source, target)
    return target
