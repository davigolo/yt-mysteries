import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal

from google.genai import errors


def report_status(
    status: Literal["uploaded", "published", "generated", "dry_run", "waiting", "blocked", "failed"],
    message: str, *, video_id: str = "", publish_at: datetime | None = None,
) -> None:
    print(f"Estado: {status} - {message}", flush=True)
    if os.environ.get("GITHUB_ACTIONS") == "true" and status in {"waiting", "blocked", "failed"}:
        level = "warning" if status == "waiting" else "error"
        escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::{level}::{escaped}", flush=True)
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as handle:
            handle.write(f"publication_status={status}\nvideo_id={video_id}\n")
            handle.write(f"publish_at={publish_at.isoformat() if publish_at else ''}\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as handle:
            handle.write(f"## Publication result: {status}\n\n{message}\n\n")
            if video_id:
                handle.write(f"Video: https://youtu.be/{video_id}\n\n")
            if publish_at:
                handle.write(f"Scheduled publication: {publish_at.isoformat()}\n\n")


def run_cli(command: Callable[[], None]) -> None:
    try:
        command()
    except Exception as error:
        if isinstance(error, errors.APIError) and error.code == 402:
            report_status(
                "blocked",
                "Gemini no tiene saldo prepago. Recarga el proyecto en https://ai.studio/projects "
                "y reintenta Episode; cambiar de modelo no soluciona la facturacion.",
            )
        else:
            report_status(
                "failed",
                f"El proceso ha fallado ({type(error).__name__}). Revisa el traceback y comprueba "
                "YouTube antes de reintentar para evitar subidas duplicadas.",
            )
        raise
