import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent
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

PICK = """async (title) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const label = [...document.querySelectorAll('.label-text')].find(e => %s.test(e.textContent));
  const trigger = label.closest('ytcp-dropdown-trigger');
  trigger.scrollIntoView();
  trigger.click();
  let dialog;
  for (let i = 0; i < 20 && !dialog; i++) {
    await sleep(500);
    dialog = [...document.querySelectorAll('ytcp-video-pick-dialog #inner-dialog')].find(d => d.offsetParent !== null);
  }
  if (!dialog) return 'no se abrió el selector';
  const search = dialog.querySelector('#search-yours');
  if (search) {
    search.focus();
    search.value = title;
    search.dispatchEvent(new Event('input', {bubbles: true}));
  }
  const norm = s => s.trim().toLowerCase();
  let card;
  for (let i = 0; i < 20 && !card; i++) {
    await sleep(500);
    card = [...dialog.querySelectorAll('ytcp-entity-card')].find(c => norm(c.querySelector('.title')?.innerText || '') === norm(title));
  }
  if (!card) return 'episodio no encontrado en el selector';
  card.click();
  await sleep(1500);
  const save = document.querySelector('ytcp-video-details-section #save');
  if (!save || save.getAttribute('aria-disabled') === 'true') {
    return norm(trigger.innerText).includes(norm(title)) ? 'ok' : 'botón Guardar desactivado';
  }
  save.click();
  for (let i = 0; i < 20; i++) {
    await sleep(500);
    if (save.getAttribute('aria-disabled') === 'true') return 'ok';
  }
  return 'no se confirmó el guardado';
}""" % LABEL_RE


def _load(name: str) -> list[dict]:
    path = ROOT / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _recent(shorts: list[dict], days: int) -> list[dict]:
    since = (date.today() - timedelta(days=days)).isoformat()
    return [s for s in shorts if s.get("video_id") and s.get("date", "") >= since]


def main() -> None:
    parser = argparse.ArgumentParser(description="Pone el episodio como 'Vídeo relacionado' de cada Short en YouTube Studio")
    parser.add_argument("--state", type=Path, required=True, help="storage_state de Playwright con la sesión del canal")
    parser.add_argument("--days", type=int, default=3, help="Revisa los Shorts de los últimos N días")
    parser.add_argument("--headed", action="store_true", help="Muestra el navegador (depuración local)")
    args = parser.parse_args()

    episodes = {e["video_id"]: e["title"] for e in _load("history.json") if e.get("video_id")}
    pending = [s for s in _recent(_load("shorts_history.json"), args.days) if s.get("episode_id") in episodes]
    if not pending:
        print("No hay Shorts recientes que enlazar")
        return

    failures = 0
    with sync_playwright() as p:
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
                result = page.evaluate(PICK, title)
                print(f"{short['video_id']} -> {title}: {result}")
                failures += result != "ok"
        finally:
            context.storage_state(path=str(args.state))
            os.chmod(args.state, 0o600)
            browser.close()
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
