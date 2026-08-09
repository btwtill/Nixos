import json
from pathlib import Path

SECRETS_PATH = Path.home() / ".config" / "home-app" / "secrets.json"

try:
    _secrets = json.loads(SECRETS_PATH.read_text())
except Exception:
    _secrets = {}

HA_URL   = _secrets.get("ha_url",   "http://localhost:8123")
HA_TOKEN = _secrets.get("ha_token", "")
