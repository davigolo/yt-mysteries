import getpass
from pathlib import Path

import requests

GRAPH_URL = "https://graph.facebook.com/v24.0"
OUT = Path(__file__).resolve().parent.parent / ".fb.env"


def _get(path: str, **params) -> dict:
    response = requests.get(f"{GRAPH_URL}/{path}", params=params, timeout=30)
    data = response.json()
    if "error" in data:
        raise SystemExit(f"Error de Facebook: {data['error'].get('message')}")
    return data


def main() -> None:
    app_id = input("App ID: ").strip()
    app_secret = getpass.getpass("App secret: ").strip()
    short_token = getpass.getpass("User token del Graph API Explorer: ").strip()

    long_token = _get(
        "oauth/access_token",
        grant_type="fb_exchange_token",
        client_id=app_id,
        client_secret=app_secret,
        fb_exchange_token=short_token,
    )["access_token"]

    pages = _get("me/accounts", access_token=long_token, fields="id,name,access_token").get("data", [])
    if not pages:
        raise SystemExit("La cuenta no administra ninguna página o faltan permisos")
    for i, page in enumerate(pages):
        print(f"{i}: {page['name']} ({page['id']})")
    page = pages[int(input("Número de la página: ")) if len(pages) > 1 else 0]

    lines = [f"FB_PAGE_ID={page['id']}", f"FB_PAGE_TOKEN={page['access_token']}"]
    instagram = _get(page["id"], access_token=page["access_token"], fields="instagram_business_account{id,username}")
    if "instagram_business_account" in instagram:
        account = instagram["instagram_business_account"]
        lines.append(f"IG_USER_ID={account['id']}")
        print(f"Instagram vinculado: @{account.get('username')} ({account['id']})")
    else:
        print("La página no tiene una cuenta profesional de Instagram vinculada; no se publicará en Instagram")

    OUT.write_text("\n".join(lines) + "\n")
    OUT.chmod(0o600)
    print(f"Guardado en {OUT}. Súbelo con: gh secret set -f .fb.env")


if __name__ == "__main__":
    main()
