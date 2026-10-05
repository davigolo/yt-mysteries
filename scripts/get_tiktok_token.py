import getpass
import secrets
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
SCOPES = "user.info.basic,video.publish"
OUT = Path(__file__).resolve().parent.parent / ".tiktok.env"


def main() -> None:
    client_key = input("Client key: ").strip()
    client_secret = getpass.getpass("Client secret: ").strip()
    redirect_uri = input("Redirect URI registrada en la app: ").strip()
    state = secrets.token_urlsafe(16)

    url = f"{AUTH_URL}?{urlencode({'client_key': client_key, 'scope': SCOPES, 'response_type': 'code', 'redirect_uri': redirect_uri, 'state': state})}"
    print(f"Abre esta URL, autoriza y pega aquí la URL a la que te redirige:\n{url}")
    webbrowser.open(url)
    query = parse_qs(urlparse(input("URL de redirección: ").strip()).query)
    if query.get("state", [""])[0] != state:
        raise SystemExit("El parámetro state no coincide; repite el proceso")
    if "code" not in query:
        raise SystemExit(f"TikTok no devolvió código: {query}")

    response = requests.post(
        TOKEN_URL,
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": query["code"][0],
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    body = response.json()
    if "refresh_token" not in body:
        raise SystemExit(f"Error de TikTok: {response.text[:500]}")
    if "video.publish" not in body.get("scope", ""):
        raise SystemExit(f"El token no incluye video.publish (scopes: {body.get('scope')})")

    OUT.write_text(
        f"TIKTOK_CLIENT_KEY={client_key}\nTIKTOK_CLIENT_SECRET={client_secret}\nTIKTOK_REFRESH_TOKEN={body['refresh_token']}\n"
    )
    OUT.chmod(0o600)
    print(f"Guardado en {OUT}. Súbelo con: gh secret set -f .tiktok.env")


if __name__ == "__main__":
    main()
