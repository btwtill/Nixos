"""Home app configuration — edit this file to customise lights and sliders."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

ASSETS = Path(__file__).parent / "assets"


# ── Home Assistant ──────────────────────────────────────────────────────────
# Connection details are kept out of git. Create this file on the machine
# running home-app (it is never read from the repo / Nix store):
#
#   ~/.config/home-app/secrets.json
#   {
#     "ha_url":   "http://<vm-ip>:8123",
#     "ha_token": "<long-lived access token, from your HA profile page>"
#   }

SECRETS_PATH = Path.home() / ".config" / "home-app" / "secrets.json"


def _load_secrets() -> dict:
    try:
        return json.loads(SECRETS_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


_secrets = _load_secrets()

HA_URL   = _secrets.get("ha_url", "http://localhost:8123")
HA_TOKEN = _secrets.get("ha_token", "")

# Entity controlled by the brightness slider (top-right arc slider).
LIGHT_ENTITY = "light.ceiling_lights"   # ← change to your real/demo entity id

# How often to poll Home Assistant for external state changes (ms).
HA_POLL_INTERVAL_MS = 3000


# ── Lights ────────────────────────────────────────────────────────────────────

@dataclass
class LightConfig:
    """One controllable light shown on the floorplan.

    position  : (x, y) in widget pixels where the button is centred.
                Matches the coordinate space of floorplan_bg.png when it is
                stretched to fill the 521×245 floorplan widget.
    icon_default / icon_on : paths relative to assets/floorplan/
    icon_size : (w, h) of the button image in pixels
    """
    name: str
    position: tuple[int, int]
    icon_default: str = "floorplan/floorplanbutton_dark_default.png"
    icon_on:      str = "floorplan/floorplanbutton_dark_selected.png"
    icon_size: tuple[int, int] = (70, 70)


LIGHTS: list[LightConfig] = [
    # ── Add / remove lights here ──────────────────────────────────────────────
    LightConfig("Living Room", (120,  80)),
    LightConfig("Kitchen",     (300,  60)),
    LightConfig("Bedroom",     (420, 150)),
    LightConfig("Bathroom",    (200, 180)),
    # ─────────────────────────────────────────────────────────────────────────
]


# ── Arc sliders ───────────────────────────────────────────────────────────────

@dataclass
class ArcSliderConfig:
    """Geometry and appearance of a circular arc slider.

    Angle convention
    ----------------
    0° = 12 o'clock (top), positive angles go *clockwise*.
    The arc sweeps clockwise from start_angle to end_angle.

    Default layout — 270° arc, gap at bottom:
        start_angle = 225  →  7:30 position  (handle at value = 0)
        end_angle   = 135  →  4:30 position  (handle at value = 1)

    fill_color
    ----------
    str  → solid hex colour, e.g. "#C8B09A"
    list → gradient as [(stop 0-1, hex), …], e.g. for a cold→hot ramp.
           Gradient is drawn as 90 short arc segments with colour interpolation.

    Images (paths relative to assets/)
    ------------------------------------
    bg_image     : decorative backdrop drawn behind the arc
    handle_image : drag handle, centred on the arc at the current value
    """
    center: tuple[float, float]          # circle centre within the widget (px)
    radius: float
    start_angle: float                   # 0% position  (0=top, CW+)
    end_angle:   float                   # 100% position
    track_width: float = 10.0
    track_color: str   = "#252525"
    fill_color: Union[str, list] = "#C8B09A"
    bg_image:     str = ""
    handle_image: str = ""
    handle_size: tuple[int, int] = (26, 26)
    clockwise: bool = True
    bg_offset: tuple[int, int] = (0, 0)   # (dx, dy) applied to the backdrop image


LIGHT_SLIDER = ArcSliderConfig(
    center=(146, 122),          # circle centre inside the 293×245 widget cell
    radius=85,
    start_angle=-25,
    end_angle=-300,
    track_width=10,
    track_color="",
    fill_color="#C8B09A",       # warm beige
    bg_image="sliders/sliderbackdrop_dark.png",
    handle_image="sliders/sliderknob_dark.png",
    handle_size=(40, 40),
    clockwise=False,
    bg_offset=(0, 4),
)

TEMP_SLIDER = ArcSliderConfig(
    center=(146, 122),
    radius=85,
    start_angle=-25,
    end_angle=-300,
    track_width=10,
    track_color="",
    fill_color=[                # blue (cold) → purple → red (hot)
        (0.00, "#3860FF"),
        (0.40, "#7030CC"),
        (0.75, "#CC3020"),
        (1.00, "#FF1008"),
    ],
    bg_image="sliders/sliderbackdrop_dark.png",
    handle_image="sliders/sliderknob_dark.png",
    handle_size=(40, 40),
    clockwise=False,
    bg_offset=(0, 4),
)
