import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import yaml

from main import _load_env
from longform.insights import (
    MIN_ENGAGED_VIEWS,
    MIN_EPISODE_VIEWS,
    MIN_VIEWS,
    PERFORMANCE_METRICS,
    RETENTION_TARGET,
    SETTLE_DAYS,
    SHORT_RETENTION_TARGET,
    _score,
    fetch_performance,
)
from longform.upload import credentials

PACIFIC = ZoneInfo("America/Los_Angeles")
DEFAULT_SINCE = "2026-10-21"
DEFAULT_ROLLOUT_ID = "retention-2026-10-21"
MANUAL_CHECKS = [
    "Impresiones y CTR: revisión manual en YouTube Studio; no disponibles en este informe API.",
    "Se quedaron viendo / deslizaron: revisión manual en Studio; engaged views / views no es una tasa de swipe.",
    "No se mide conversión de Shorts a episodios ni se atribuyen causas al bajo alcance.",
]


def parse_date(value):
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except ValueError:
        raise argparse.ArgumentTypeError("Usa una fecha válida YYYY-MM-DD.") from None


def read_history(name):
    path = ROOT / name
    if not path.exists():
        raise ValueError(f"Missing history: {name}")
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError(f"Invalid history: {name}")
    return entries


def read_reporting_config():
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}
    reporting = config.get("reporting") or {}
    rollout_id = reporting.get("rollout_id", DEFAULT_ROLLOUT_ID)
    if not isinstance(rollout_id, str) or not rollout_id.strip():
        raise ValueError("reporting.rollout_id must be a nonempty string")
    batch_size = reporting.get("batch_size", 4)
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 3:
        raise ValueError("reporting.batch_size must be an integer >= 3")
    return {
        "rollout_id": rollout_id,
        "since": parse_date(reporting.get("since", DEFAULT_SINCE)),
        "batch_size": batch_size,
    }


def error_label(error):
    if isinstance(error, HttpError):
        return f"HTTP {error.resp.status}"
    return type(error).__name__


def duration_seconds(value):
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", value)
    if not match or not any(match.groups()):
        raise ValueError("Invalid video duration")
    hours, minutes, seconds = (float(x or 0) for x in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def query(analytics, start, end, **kwargs):
    return analytics.reports().query(
        ids="channel==MINE", startDate=start, endDate=end, **kwargs,
    ).execute()


def retention_points(analytics, youtube, rows, start, end):
    results = {}
    ids = [row["video_id"] for row in rows if row["views"] >= MIN_EPISODE_VIEWS]
    durations = {}
    for offset in range(0, len(ids), 50):
        try:
            response = youtube.videos().list(
                part="contentDetails", id=",".join(ids[offset:offset + 50]),
            ).execute()
            durations.update({
                video["id"]: duration_seconds(video["contentDetails"]["duration"])
                for video in response.get("items", [])
            })
        except Exception as error:
            for video_id in ids[offset:offset + 50]:
                results[video_id] = {"status": "unavailable", "reason": error_label(error)}
    for video_id in ids:
        if video_id in results:
            continue
        duration = durations.get(video_id)
        if not duration:
            results[video_id] = {"status": "unavailable", "reason": "No duration returned by YouTube Data"}
            continue
        try:
            response = query(
                analytics, start, end, dimensions="elapsedVideoTimeRatio",
                filters=f"video=={video_id}", metrics="audienceWatchRatio",
                sort="elapsedVideoTimeRatio", maxResults=200,
            )
            curve = response.get("rows", [])
            points = []
            for seconds in (30, 60):
                if seconds > duration or not curve:
                    continue
                position, ratio = min(curve, key=lambda row: abs(row[0] - seconds / duration))
                points.append({
                    "target_seconds": seconds,
                    "sample_seconds": round(position * duration, 2),
                    "audience_watch_ratio": ratio,
                })
            results[video_id] = {
                "status": "available" if points else "unavailable",
                "reason": None if points else "No retention samples returned",
                "duration_seconds": duration,
                "points": points,
            }
        except Exception as error:
            results[video_id] = {"status": "unavailable", "reason": error_label(error)}
    return results


def format_report(rows, since, short, rollout_id=DEFAULT_ROLLOUT_ID, batch_size=4):
    minimum = MIN_VIEWS if short else MIN_EPISODE_VIEWS
    eligible = [
        row for row in rows
        if row["views"] >= minimum and (not short or row["engaged_views"] >= MIN_ENGAGED_VIEWS)
    ]
    for row in rows:
        row["subscribers_per_1000_engaged"] = (
            round(row["subscribers"] / row["engaged_views"] * 1000, 3)
            if row["engaged_views"] else None
        )
    new = [
        row for row in rows
        if row.get("pipeline_revision") == rollout_id
        and datetime.fromisoformat(row["published_at"].replace("Z", "+00:00")).astimezone(PACIFIC).date() >= since
    ]
    new_ids = {row["video_id"] for row in new}
    qualified = sum(row["video_id"] in new_ids for row in eligible)
    ranked = sorted(eligible, key=_score if short else lambda row: row["retention"], reverse=True)
    views = sum(row["views"] for row in rows)
    engaged = sum(row["engaged_views"] for row in rows)
    subscribers = sum(row["subscribers"] for row in rows)
    return {
        "mature_with_data_count": len(rows),
        "eligible_count": len(eligible),
        "minimum_views": minimum,
        "minimum_engaged_views": MIN_ENGAGED_VIEWS if short else None,
        "retention_target_percent": SHORT_RETENTION_TARGET if short else RETENTION_TARGET,
        "totals_for_mature_rows": {
            "views": views, "engaged_views": engaged, "subscribers_gained": subscribers,
            "subscribers_per_1000_engaged": round(subscribers / engaged * 1000, 3) if engaged else None,
        },
        "batch": {
            "since": since.isoformat(),
            "rollout_id": rollout_id,
            "target_size": batch_size,
            "mature_with_data_count": len(new),
            "eligible_count": qualified,
            "status": f"ready_{batch_size}" if qualified >= batch_size else "initial_3" if qualified >= 3 else "waiting",
            "remaining_to_3": max(0, 3 - qualified),
            "remaining_to_target": max(0, batch_size - qualified),
            "video_ids": [row["video_id"] for row in new],
            "ranked_video_ids": [row["video_id"] for row in ranked if row["video_id"] in new_ids],
        },
        "ranking_method": "existing_80pct_retention_20pct_subscriber_yield" if short else "average_view_percentage",
        "ranked_video_ids": [row["video_id"] for row in ranked],
        "videos": rows,
    }


def generate_report(since, include_retention=True, reporting=None):
    reporting = reporting or read_reporting_config()
    rollout_id = reporting["rollout_id"]
    batch_size = reporting["batch_size"]
    today = date.today()
    start = (today - timedelta(days=90)).isoformat()
    episodes = read_history("history.json")
    shorts = read_history("shorts_history.json")
    analytics = build("youtubeAnalytics", "v2", credentials=credentials(), cache_discovery=False)
    latest = query(
        analytics, start, today.isoformat(), metrics=PERFORMANCE_METRICS,
        dimensions="day", sort="-day", maxResults=1,
    )
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "batch_since": since.isoformat(),
        "pipeline_revision": rollout_id,
        "batch_size": batch_size,
        "analytics_timezone": str(PACIFIC),
        "analytics_end": None,
        "performance_window": {"start": start, "end": None, "lookback_from_run_days": 90},
        "settle_days": SETTLE_DAYS,
        "coverage": {
            name: {
                "history_entries": len(entries),
                "history_video_ids": len({row["video_id"] for row in entries if row.get("video_id")}),
                "status": "not_queried",
            }
            for name, entries in (("longs", episodes), ("shorts", shorts))
        },
        "manual_checks": MANUAL_CHECKS,
        "limitations": [
            "Los historiales locales delimitan el inventario; vídeos ausentes no se contabilizan.",
            "Maduro con datos no incluye vídeos que Analytics omita o publique sin filas.",
            f"Readiness exige pipeline_revision == {rollout_id}, publicación desde {since.isoformat()}, "
            f"3 muestras elegibles por formato para lectura inicial y {batch_size} para completar el lote; no prueba causalidad.",
            "Vídeos sin etiqueta o con otra revisión no pertenecen al lote nuevo, aunque se publiquen después del despliegue.",
            "Subs/engaged mide suscriptores ganados, no netos ni conversión a largos.",
            "Curvas 30/60 s: muestras API más cercanas; pueden incluir repeticiones y no representan espectadores únicos.",
        ],
        "periods": {},
    }
    if not latest.get("rows"):
        report["status"] = "analytics_unavailable"
        report["formats"] = {
            "longs": format_report([], since, False, rollout_id, batch_size),
            "shorts": format_report([], since, True, rollout_id, batch_size),
        }
        return report
    end = latest["rows"][0][0]
    report["analytics_end"] = end
    report["performance_window"]["end"] = end
    report["mature_published_on_or_before"] = (date.fromisoformat(end) - timedelta(days=SETTLE_DAYS)).isoformat()
    performance = fetch_performance(episodes + shorts, days=90, min_views=0)
    cuts = {row["analytics_end"] for row in performance}
    if cuts and cuts != {end}:
        raise ValueError("Analytics cutoff changed during report; rerun for a consistent report")
    episode_ids = {row["video_id"] for row in episodes if row.get("video_id")}
    short_ids = {row["video_id"] for row in shorts if row.get("video_id")}
    if episode_ids & short_ids:
        raise ValueError("A video belongs to both format histories")
    longs = [row for row in performance if row["video_id"] in episode_ids]
    short_rows = [row for row in performance if row["video_id"] in short_ids]
    report["formats"] = {
        "longs": format_report(longs, since, False, rollout_id, batch_size),
        "shorts": format_report(short_rows, since, True, rollout_id, batch_size),
    }
    for name, history_ids, rows in (("longs", episode_ids, longs), ("shorts", short_ids, short_rows)):
        observed = {row["video_id"] for row in rows}
        report["coverage"][name].update({
            "status": "queried",
            "mature_video_ids_with_data": len(observed),
            "without_mature_performance_ids": sorted(history_ids - observed),
            "absence_reason": "Not distinguished: non-public, not yet mature, or no Analytics rows; not assumed to have zero views",
        })
    for days in (28, 90):
        period_start = (date.fromisoformat(end) - timedelta(days=days - 1)).isoformat()
        response = query(
            analytics, period_start, end, dimensions="creatorContentType",
            metrics="views,engagedViews,estimatedMinutesWatched,averageViewPercentage,averageViewDuration,subscribersGained,subscribersLost",
        )
        headers = [column["name"] for column in response.get("columnHeaders", [])]
        report["periods"][str(days)] = {
            "start": period_start, "end": end,
            "status": "available" if response.get("rows") else "no_data",
            "scope": "All channel content, not limited to mature videos or local histories",
            "rows": [dict(zip(headers, row)) for row in response.get("rows", [])],
        }
    report["long_retention"] = (
        retention_points(
            analytics,
            build("youtube", "v3", credentials=credentials(), cache_discovery=False),
            longs, start, end,
        )
        if include_retention else {"status": "unavailable", "reason": "Disabled with --no-retention"}
    )
    report["status"] = "available"
    return report


def markdown_text(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def render_summary(report):
    lines = [
        "# Informe diario del canal",
        f"- Consulta UTC: {report['generated_at_utc']}",
        f"- Corte Analytics (Pacífico): {report['analytics_end'] or 'sin datos disponibles'}",
        f"- Ventana de vídeos maduros: {report['performance_window']['start']} → {report['analytics_end'] or 'no disponible'}.",
        f"- Lote nuevo desde {report['batch_since']}; madurez: {SETTLE_DAYS} días respecto al corte.",
        f"- Cohorte obligatoria: pipeline_revision = `{markdown_text(report['pipeline_revision'])}`; "
        f"objetivo por formato: {report['batch_size']} vídeos elegibles.",
        f"- Publicación máxima elegible (Pacífico): {report.get('mature_published_on_or_before', 'no disponible')}.",
        "- Sin proyecciones ni resultados futuros.",
    ]
    for days, period in report["periods"].items():
        lines += [
            f"## Canal completo: {days} días ({period['start']} → {period['end']})",
            "Incluye contenido inmaduro; no es la muestra del ranking.",
            "| Formato | Vistas | Engaged | Minutos | % visto | Media s | Subs + / − |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for row in period["rows"]:
            lines.append(
                f"| {markdown_text(row['creatorContentType'])} | {row['views']} | {row['engagedViews']} | "
                f"{row['estimatedMinutesWatched']} | {row['averageViewPercentage']:.2f} | "
                f"{row['averageViewDuration']} | {row['subscribersGained']} / {row['subscribersLost']} |"
            )
        if not period["rows"]:
            lines.append("- Sin filas disponibles; no se interpretan como ceros.")
    for name, data in report["formats"].items():
        batch = data["batch"]
        totals = data["totals_for_mature_rows"]
        lines += [
            f"## {'Shorts' if name == 'shorts' else 'Largos'} maduros",
            f"- Con datos: {data['mature_with_data_count']}; elegibles: {data['eligible_count']}.",
            f"- Totales maduros: {totals['views']} vistas, {totals['engaged_views']} engaged, "
            f"{totals['subscribers_gained']} suscriptores ganados; "
            f"subs/1.000 engaged: {totals['subscribers_per_1000_engaged'] if totals['subscribers_per_1000_engaged'] is not None else 'N/D'}.",
            f"- Mínimos: {data['minimum_views']} vistas; engaged: {data['minimum_engaged_views'] or 'sin mínimo adicional'}.",
            f"- Lote nuevo: {batch['mature_with_data_count']} maduros con datos; {batch['eligible_count']} elegibles. "
            f"Estado: **{batch['status']}**. Faltan {batch['remaining_to_3']} para 3 y "
            f"{batch['remaining_to_target']} para {batch['target_size']}.",
            f"- Cobertura: {report['coverage'][name]['history_video_ids']} IDs en historial; "
            f"estado: {report['coverage'][name]['status']}. "
            "Ausencias pueden ser privacidad, inmadurez o filas no devueltas; no equivalen a cero vistas.",
        ]
        if batch["status"] == "waiting":
            lines.append("- Lote nuevo insuficiente: no hay resultados suficientes para evaluar los cambios.")
        by_id = {row["video_id"]: row for row in data["videos"]}
        ranked = data["ranked_video_ids"]
        best = ranked[:3]
        worst = [video_id for video_id in reversed(ranked) if video_id not in best][:3]
        lines += [
            "Ranking relativo, no prueba de éxito; objetivo interno: "
            f"{data['retention_target_percent']} % visto. Subs/1.000 engaged no es conversión a episodios.",
            "| Grupo | Vídeo | Vistas | Engaged | % visto | Media s | Subs + | Subs/1.000 engaged |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
        for group, ids in (("Mayor puntuación", best), ("Menor puntuación", worst)):
            for video_id in ids:
                row = by_id[video_id]
                rate = row["subscribers_per_1000_engaged"]
                lines.append(
                    f"| {group} | [{markdown_text(row['title'])}](https://youtu.be/{video_id}) | "
                    f"{row['views']} | {row['engaged_views']} | {row['retention']:.2f} | "
                    f"{row['average_seconds']:.1f} | {row['subscribers']} | {rate if rate is not None else 'N/D'} |"
                )
        if len(ranked) < 4:
            lines.append("- Menos de cuatro vídeos elegibles: comparación especialmente frágil.")
        lines += [
            "### Cohorte nueva etiquetada",
            "| Vídeo | Vistas | Engaged | % visto | Media s |",
            "|---|---:|---:|---:|---:|",
        ]
        for video_id in batch["ranked_video_ids"]:
            row = by_id[video_id]
            lines.append(
                f"| [{markdown_text(row['title'])}](https://youtu.be/{video_id}) | "
                f"{row['views']} | {row['engaged_views']} | {row['retention']:.2f} | {row['average_seconds']:.1f} |"
            )
        if not batch["ranked_video_ids"]:
            lines.append("- Sin vídeos elegibles con la revisión requerida y fecha válida; no se compara el rollout.")
    lines.append("## Curvas de largos: 30/60 segundos aproximados")
    retention = report.get("long_retention", {})
    if not retention or "status" in retention:
        lines.append(f"- No disponible: {retention.get('reason', 'sin muestra madura con datos')}.")
    else:
        for video_id, curve in retention.items():
            if curve["status"] != "available":
                lines.append(f"- {video_id}: no disponible ({curve['reason']}).")
                continue
            points = "; ".join(
                f"{point['target_seconds']} s (muestra {point['sample_seconds']} s): "
                f"{point['audience_watch_ratio'] * 100:.1f} %"
                for point in curve["points"]
            )
            lines.append(f"- {video_id}: {points}.")
    lines += ["## Revisión manual y límites", *[f"- {item}" for item in report["manual_checks"] + report["limitations"]]]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Read-only YouTube Analytics report; no AI calls or channel mutations.")
    parser.add_argument("--since", type=parse_date, help="Override reporting.since (YYYY-MM-DD)")
    parser.add_argument("--output", type=Path, default=ROOT / "build/channel_report.json")
    parser.add_argument("--no-retention", action="store_true")
    args = parser.parse_args()
    _load_env()
    reporting = read_reporting_config()
    report = generate_report(
        args.since or reporting["since"], include_retention=not args.no_retention, reporting=reporting,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = render_summary(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as handle:
            handle.write(summary)
    print(summary)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Channel report failed ({error_label(error)}); no channel changes were made.", file=sys.stderr)
        sys.exit(1)
