# Home Assistant Bridge (Blender add-on)

Live-links lights from a [Home Assistant](https://www.home-assistant.io/) server
to lights in your Blender scene. When a real light's color or brightness changes
in Home Assistant, the mapped Blender light follows it in near real time.

## Requirements

- **Blender 4.2+** (installed as an *Extension*).
- A **Home Assistant** server reachable from this machine.
- A **Long-lived access token**: in Home Assistant, click your user (bottom-left)
  → *Security* tab → **Long-lived access tokens** → *Create Token*.

No external Python packages are required — only the standard library.

## Install

1. Zip the `HomeAssistantBridge` folder (it must contain `blender_manifest.toml`
   and `__init__.py` at the top level of the zip).
2. In Blender: *Edit → Preferences → Get Extensions →* the drop-down arrow
   (top-right) → **Install from Disk…** → pick the zip.
   (Or `Add-ons → Install from Disk…` on legacy builds.)
3. Enable it. A **HA Bridge** tab appears in the 3D Viewport sidebar (press `N`).

## Usage

1. **Connection** — enter your Server URL (e.g. `http://homeassistant.local:8123`)
   and paste the token. Click **Refresh** to pull the light list.
2. On the **left**, pick a Home Assistant light.
3. On the **right**, pick a scene **Collection**, then a **light object** inside it.
4. Click **Link Selected** to create a mapping. Repeat for as many lights as you like.
5. Select a mapping in the list to tweak:
   - **Max Power** — the Blender light power (Watts) at full HA brightness.
   - **Color / Brightness** — toggle which properties are driven.
6. Click **Start Live Sync**. The Blender lights now track Home Assistant.

## How it works

- HA states are polled over the REST API (`GET /api/states`, filtered to `light.*`)
  on a background thread so the UI never blocks.
- A `bpy.app.timers` callback on the main thread applies the cached states:
  - `rgb_color` (0–255 sRGB) → light color, converted to linear.
  - `brightness` (0–255) → light power, scaled by *Max Power*.
  - `state: off` → power 0.
- Adjust the poll **Interval** (default 1 s) to trade latency for network load.

## Notes / limitations

- Uses `rgb_color`; color-temperature-only lights won't drive color (brightness
  still works).
- The token is stored in the .blend file (as a masked field) — treat the file
  accordingly.
- For a self-signed HTTPS HA instance, use the `http://` LAN URL or add a proper
  certificate; `urllib` verifies TLS by default.
