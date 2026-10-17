import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import requests
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent
RAW_URL = "https://raw.githubusercontent.com/davigolo/yt-mysteries/main"
EDIT_URL = "https://studio.youtube.com/video/{}/edit"
LABEL_RE = "/(v[ií]deo relacionado|related video)/i"

FIELD_READY = "() => [...document.querySelectorAll('.label-text')].some(e => %s.test(e.textContent))" % LABEL_RE

OPEN_PICKER = """async () => {
  for (let i = 0; i < 40; i++) {
    const label = [...document.querySelectorAll('.label-text')].find(e => %s.test(e.textContent));
    if (label) {
      await new Promise(r => setTimeout(r, 2500));
      const trigger = label.closest('ytcp-dropdown-trigger');
      const current = trigger.innerText.replace(label.textContent, '').trim();
      return {found: true, current};
    }
    await new Promise(r => setTimeout(r, 500));
  }
  return {found: false, url: location.href};
}""" % LABEL_RE

OPEN_DIALOG = """async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const label = [...document.querySelectorAll('.label-text')].find(e => %s.test(e.textContent));
  const trigger = label.closest('ytcp-dropdown-trigger');
  trigger.scrollIntoView();
  trigger.click();
  for (let i = 0; i < 20; i++) {
    await sleep(500);
    if ([...document.querySelectorAll('ytcp-video-pick-dialog #inner-dialog')].some(d => d.offsetParent !== null)) {
      await sleep(2000);
      return true;
    }
  }
  return false;
}""" % LABEL_RE

CHOOSE = """async (title) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const norm = s => s.trim().toLowerCase();
  const dialog = [...document.querySelectorAll('ytcp-video-pick-dialog #inner-dialog')].find(d => d.offsetParent !== null);
  const card = dialog && [...dialog.querySelectorAll('ytcp-entity-card')]
    .find(c => norm(c.querySelector('.title')?.innerText || '') === norm(title));
  if (!card) return 'episodio no encontrado en el selector';
  card.click();
  await sleep(1500);
  const save = document.querySelector('ytcp-video-details-section #save');
  if (!save || save.getAttribute('aria-disabled') === 'true') return 'botón Guardar desactivado';
  save.click();
  for (let i = 0; i < 20; i++) {
    await sleep(500);
    if (save.getAttribute('aria-disabled') === 'true') return 'ok';
  }
  const dialogs = [...document.querySelectorAll('tp-yt-paper-dialog, ytcp-dialog, ytcp-confirmation-dialog, [role="dialog"], [role="alert"]')]
    .filter(d => d.offsetParent !== null)
    .map(d => d.innerText.replace(/\\s+/g, ' ').trim())
    .filter(Boolean);
  return 'no se confirmó el guardado' + (dialogs.length ? ' | diálogo: ' + dialogs.join(' / ').slice(0, 300) : '');
}"""


def _load(name: str, remote: bool = False) -> list[dict]:
    if remote:
        response = requests.get(f"{RAW_URL}/{name}", timeout=30)
        response.raise_for_status()
        return response.json()
    path = ROOT / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _recent(shorts: list[dict], days: int) -> list[dict]:
    since = (date.today() - timedelta(days=days)).isoformat()
    return [s for s in shorts if s.get("video_id") and s.get("date", "") >= since]


def _pick(page, title: str) -> str:
    if not page.evaluate(OPEN_DIALOG):
        return "no se abrió el selector"
    result = page.evaluate(CHOOSE, title)
    if result.startswith("episodio no encontrado"):
        search = page.locator("ytcp-video-pick-dialog #search-yours").first
        search.click()
        search.press_sequentially(title, delay=20)
        page.wait_for_timeout(3000)
        result = page.evaluate(CHOOSE, title)
    return result


def _linked_after_reload(page, video_id: str, title: str) -> bool:
    try:
        page.goto(EDIT_URL.format(video_id), wait_until="load", timeout=60000)
        page.wait_for_function(FIELD_READY, timeout=45000)
        state = page.evaluate(OPEN_PICKER)
    except PlaywrightError:
        return False
    return state["found"] and title.lower() in state["current"].lower()


def main() -> None:
    parser = argparse.ArgumentParser(description="Pone el episodio como 'Vídeo relacionado' de cada Short en YouTube Studio")
    session = parser.add_mutually_exclusive_group(required=True)
    session.add_argument("--state", type=Path, help="storage_state de Playwright con la sesión del canal")
    session.add_argument("--profile", type=Path, help="Perfil persistente de Chrome con la sesión del canal (ejecución en local)")
    parser.add_argument("--remote", action="store_true", help="Lee el historial de GitHub en vez del repo local")
    parser.add_argument("--login", action="store_true", help="Abre Studio con --profile para iniciar sesión y termina")
    parser.add_argument("--days", type=int, default=7, help="Revisa los Shorts de los últimos N días")
    parser.add_argument("--headed", action="store_true", help="Muestra el navegador (depuración local)")
    args = parser.parse_args()

    if args.login:
        if not args.profile:
            parser.error("--login requiere --profile")
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                str(args.profile), channel="chrome", headless=False, viewport={"width": 1400, "height": 1000},
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://studio.youtube.com/")
            print("Inicia sesión con el canal Unsolved Archives y cierra la ventana cuando veas su panel de Studio")
            page.wait_for_event("close", timeout=0)
            context.close()
        return

    episodes = {e["video_id"]: e["title"] for e in _load("history.json", args.remote) if e.get("video_id")}
    pending = [s for s in _recent(_load("shorts_history.json", args.remote), args.days) if s.get("episode_id") in episodes]
    if not pending:
        print("No hay Shorts recientes que enlazar")
        return

    failures = 0
    with sync_playwright() as p:
        if args.profile:
            browser = None
            context = p.chromium.launch_persistent_context(
                str(args.profile), channel="chrome", headless=not args.headed, viewport={"width": 1400, "height": 1000},
            )
        else:
            browser = p.chromium.launch(channel="chrome", headless=not args.headed)
            user_agent = f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{browser.version} Safari/537.36"
            context = browser.new_context(
                storage_state=str(args.state), viewport={"width": 1400, "height": 1000}, user_agent=user_agent,
            )
        page = context.new_page()
        try:
            for short in pending:
                title = episodes[short["episode_id"]]
                state, error = None, ""
                for _ in range(3):
                    try:
                        page.goto(EDIT_URL.format(short["video_id"]), wait_until="load", timeout=60000)
                        page.wait_for_function(FIELD_READY, timeout=45000)
                        state = page.evaluate(OPEN_PICKER)
                        break
                    except PlaywrightError as e:
                        error = e.message.splitlines()[0]
                if state is None:
                    print(f"{short['video_id']}: error de navegador ({error}) en {page.url[:70]}")
                    failures += 1
                    continue
                if not state["found"]:
                    print(f"{short['video_id']}: no se encontró el campo; la sesión puede haber caducado ({state.get('url', '')[:60]})")
                    failures += 1
                    break
                if title.lower() in state["current"].lower():
                    print(f"{short['video_id']} -> {title}: ya enlazado")
                    continue
                result = _pick(page, title)
                if _linked_after_reload(page, short["video_id"], title):
                    result = "ok (verificado al recargar)"
                elif result == "ok":
                    result = "Studio confirmó el guardado pero al recargar no aparece"
                print(f"{short['video_id']} -> {title}: {result}")
                failures += not result.startswith("ok")
        finally:
            if args.state:
                context.storage_state(path=str(args.state))
                os.chmod(args.state, 0o600)
            context.close()
            if browser:
                browser.close()
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
