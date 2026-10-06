import argparse
import json
import sys
from pathlib import Path

import requests
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent
RAW = "https://raw.githubusercontent.com/davigolo/yt-mysteries/main/{}"
CHROME_DIR = Path.home() / ".config" / "google-chrome"
STATE = Path.home() / ".local" / "state" / "yt-mysteries" / "related_done.json"
EDIT_URL = "https://studio.youtube.com/video/{}/edit"
LABEL_RE = "/(v[ií]deo relacionado|related video)/i"

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
    try:
        response = requests.get(RAW.format(name), timeout=30)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        return json.loads((ROOT / name).read_text(encoding="utf-8"))


def _cdp_endpoint() -> str | None:
    port_file = CHROME_DIR / "DevToolsActivePort"
    if not port_file.exists():
        return None
    port, path = port_file.read_text().split()[:2]
    return f"ws://127.0.0.1:{port}{path}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Pone el episodio como 'Vídeo relacionado' de cada Short en YouTube Studio")
    parser.add_argument("--limit", type=int, default=10, help="Máximo de Shorts a procesar en esta ejecución")
    args = parser.parse_args()

    episodes = {e["video_id"]: e["title"] for e in _load("history.json") if e.get("video_id")}
    done = set(json.loads(STATE.read_text())) if STATE.exists() else set()
    pending = [s for s in _load("shorts_history.json") if s.get("video_id") and s["video_id"] not in done]
    pending = [s for s in pending if s.get("episode_id") in episodes][: args.limit]
    if not pending:
        print("Todos los Shorts tienen ya su vídeo relacionado")
        return
    endpoint = _cdp_endpoint()
    if not endpoint:
        print("Chrome no está abierto con la depuración remota activada (chrome://inspect/#remote-debugging)")
        sys.exit(1)

    failures = 0
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(endpoint, timeout=90000)
        except PlaywrightError as e:
            print(f"No se pudo conectar con Chrome ({e.message.splitlines()[0]})")
            sys.exit(1)
        context = browser.contexts[0]
        page = context.new_page()
        try:
            for short in pending:
                title = episodes[short["episode_id"]]
                page.goto(EDIT_URL.format(short["video_id"]), wait_until="domcontentloaded")
                state = page.evaluate(OPEN_PICKER)
                if not state["found"]:
                    print(f"{short['video_id']}: no se encontró el campo (¿canal activo distinto de Unsolved Archives? {state.get('url')})")
                    failures += 1
                    continue
                if state["current"].lower() == title.lower():
                    result = "ok"
                else:
                    result = page.evaluate(PICK, title)
                print(f"{short['video_id']} -> {title}: {result}")
                if result == "ok":
                    done.add(short["video_id"])
                    STATE.parent.mkdir(parents=True, exist_ok=True)
                    STATE.write_text(json.dumps(sorted(done)))
                else:
                    failures += 1
        finally:
            page.close()
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
