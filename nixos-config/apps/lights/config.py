import json
from pathlib import Path

SECRETS_PATH = Path.home() / ".config" / "home-app" / "secrets.json"

try:
    _secrets = json.loads(SECRETS_PATH.read_text())
except Exception:
    _secrets = {}

HA_URL   = _secrets.get("ha_url",   "http://localhost:8123")
HA_TOKEN = _secrets.get("ha_token", "")

# Lights that get no live steps while a slider is dragged, only the final value
# (for a light that can fade but still can't follow a drag smoothly), e.g.
#   "lights_final_only": ["light.wohnzimmer_decke"]
LIGHTS_FINAL_ONLY = _secrets.get("lights_final_only", [])
