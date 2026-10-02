import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
OUTPUT = Path(__file__).parent.parent / ".yt.env"

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
credentials = flow.run_local_server(
    port=8765,
    open_browser=False,
    access_type="offline",
    prompt="consent",
    authorization_prompt_message="Abre esta URL para autorizar el canal:\n{url}\n",
)
OUTPUT.write_text(
    f"YT_CLIENT_ID={credentials.client_id}\n"
    f"YT_CLIENT_SECRET={credentials.client_secret}\n"
    f"YT_REFRESH_TOKEN={credentials.refresh_token}\n"
)
os.chmod(OUTPUT, 0o600)
print(f"Credenciales guardadas en {OUTPUT}. Súbelas con: gh secret set -f .yt.env")
