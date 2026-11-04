import argparse
import json
from pathlib import Path

import yaml
from googleapiclient.discovery import build

from longform.publish import fetch_statuses, pending, publish_due
from longform.run_status import report_status, run_cli
from longform.upload import credentials
from main import _load_env

ROOT = Path(__file__).parent
HISTORY = ROOT / "history.json"
SHORTS_HISTORY = ROOT / "shorts_history.json"


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def main() -> None:
    _load_env()
    parser = argparse.ArgumentParser(description="Pasa a público los vídeos que llevan el tiempo configurado en oculto")
    parser.add_argument("--dry-run", action="store_true", help="Muestra qué se publicaría sin cambiar nada")
    args = parser.parse_args()

    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    after_hours = config["publish"]["after_hours"]
    episodes, shorts = pending(_load(HISTORY)), pending(_load(SHORTS_HISTORY))
    youtube = build("youtube", "v3", credentials=credentials(), cache_discovery=False)
    statuses = fetch_statuses(
        youtube, [e["video_id"] for e in episodes] + [s["video_id"] for s in shorts] + [s["episode_id"] for s in shorts],
    )
    overrides = {"selfDeclaredMadeForKids": False, "containsSyntheticMedia": config["upload"]["contains_synthetic_media"]}
    limit = config["publish"]["max_per_run"]
    published = publish_due(
        youtube, episodes, statuses, after_hours, overrides, limit, dry_run=args.dry_run,
        weekdays=config["publish"]["episode_weekdays"], tz=config["publish"]["timezone"],
    )
    published += publish_due(
        youtube, shorts, statuses, after_hours, overrides, limit - published, requires="episode_id", dry_run=args.dry_run,
    )
    if args.dry_run:
        report_status("dry_run", f"Se publicarian {published} videos legacy; no se ha cambiado su privacidad.")
    elif published:
        report_status("published", f"{published} videos legacy confirmados como publicos en YouTube.")
    else:
        report_status(
            "waiting",
            "No se ha publicado ningun video legacy en esta ejecucion. Los videos programados con "
            "publishAt los publica YouTube; esta ejecucion no confirma nuevas subidas.",
        )


if __name__ == "__main__":
    run_cli(main)
