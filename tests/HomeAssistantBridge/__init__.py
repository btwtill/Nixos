"""Home Assistant Bridge – live-link Home Assistant lights to Blender lights.

Fetches light states from a Home Assistant server over its REST API and drives
the color / power of Blender lights so the scene follows what the real lights do.

Design notes
------------
* Network I/O happens on a background thread (``_poll_loop``) so the Blender UI
  never blocks on a slow request.
* The fetched states are stashed in ``_latest_states`` behind a lock.
* A ``bpy.app.timers`` callback (``_sync_timer``) runs on the *main* thread and
  is the only place that touches ``bpy`` data, which is the supported pattern.
"""

import json
import threading
import urllib.request
import urllib.error

import bpy
from bpy.props import (
    StringProperty,
    FloatProperty,
    BoolProperty,
    EnumProperty,
    PointerProperty,
    CollectionProperty,
    IntProperty,
)
from bpy.types import PropertyGroup, Panel, Operator, UIList

# ---------------------------------------------------------------------------
# Module-level live-sync state (kept out of bpy data on purpose)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_latest_states = {}          # entity_id -> HA state dict
_poll_thread = None
_poll_stop = threading.Event()
_poll_cfg = {"url": "", "token": "", "interval": 1.0}
_live_active = False
_status = "Idle"

# EnumProperty item lists must be kept alive by a Python reference, otherwise
# Blender can crash / show garbage. We hold them in globals.
_ha_light_items = []
_collection_light_items = []


# ---------------------------------------------------------------------------
# Networking helpers (stdlib only)
# ---------------------------------------------------------------------------

def _http_get(base_url, token, path, timeout=5):
    # Blender text fields commonly pick up a trailing newline/space on paste,
    # which makes Home Assistant reject an otherwise-valid token with a 401.
    base_url = (base_url or "").strip()
    token = (token or "").strip()
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_lights(base_url, token, timeout=5):
    """Return {entity_id: state_dict} for every ``light.*`` entity."""
    data = _http_get(base_url, token, "/api/states", timeout=timeout)
    return {
        s["entity_id"]: s
        for s in data
        if isinstance(s, dict) and str(s.get("entity_id", "")).startswith("light.")
    }


def _set_status(text):
    global _status
    _status = text


# ---------------------------------------------------------------------------
# Color / value mapping
# ---------------------------------------------------------------------------

def _srgb_to_linear(c):
    c = max(0.0, min(1.0, c / 255.0))
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _apply_state(light_data, state, mapping):
    """Write a single HA ``state`` onto a Blender light datablock."""
    attrs = state.get("attributes", {}) or {}
    is_on = state.get("state") == "on"

    if mapping.use_color:
        rgb = attrs.get("rgb_color")
        if rgb and len(rgb) == 3:
            light_data.color = (
                _srgb_to_linear(rgb[0]),
                _srgb_to_linear(rgb[1]),
                _srgb_to_linear(rgb[2]),
            )

    if mapping.use_brightness:
        if not is_on:
            light_data.energy = 0.0
        else:
            brightness = attrs.get("brightness")
            frac = (brightness / 255.0) if brightness is not None else 1.0
            light_data.energy = mapping.max_power * frac


# ---------------------------------------------------------------------------
# Background poller + main-thread applier
# ---------------------------------------------------------------------------

def _poll_loop():
    while not _poll_stop.is_set():
        cfg = dict(_poll_cfg)
        if not cfg["url"] or not cfg["token"]:
            _set_status("Missing URL or token")
        else:
            try:
                states = _fetch_lights(cfg["url"], cfg["token"], timeout=5)
                with _lock:
                    _latest_states.clear()
                    _latest_states.update(states)
                _set_status("Connected ({} lights)".format(len(states)))
            except urllib.error.HTTPError as e:
                _set_status("HTTP {} – check token".format(e.code))
            except Exception as e:  # noqa: BLE001 - surface anything to the panel
                _set_status("Error: {}".format(e))
        _poll_stop.wait(max(0.1, cfg["interval"]))


def _sync_timer():
    """Runs on the main thread; applies cached states to mapped lights."""
    if not _live_active:
        return None  # unregister

    with _lock:
        states = dict(_latest_states)

    for scene in bpy.data.scenes:
        settings = getattr(scene, "ha_bridge", None)
        if settings is None:
            continue
        for m in settings.mappings:
            st = states.get(m.ha_entity_id)
            if not st:
                continue
            obj = bpy.data.objects.get(m.object_name)
            if obj is None or obj.type != "LIGHT":
                continue
            _apply_state(obj.data, st, m)

    return max(0.1, _poll_cfg["interval"])


def _start_live(settings):
    global _poll_thread, _live_active
    _poll_cfg["url"] = settings.url
    _poll_cfg["token"] = settings.token
    _poll_cfg["interval"] = settings.interval

    _poll_stop.clear()
    _poll_thread = threading.Thread(target=_poll_loop, name="HA-Bridge-Poll", daemon=True)
    _poll_thread.start()

    _live_active = True
    if not bpy.app.timers.is_registered(_sync_timer):
        bpy.app.timers.register(_sync_timer)
    _set_status("Live sync started")


def _stop_live():
    global _live_active, _poll_thread
    _live_active = False
    _poll_stop.set()
    if _poll_thread is not None:
        _poll_thread.join(timeout=2.0)
        _poll_thread = None
    _set_status("Stopped")


# ---------------------------------------------------------------------------
# EnumProperty item callbacks
# ---------------------------------------------------------------------------

def _enum_ha_lights(self, context):
    global _ha_light_items
    if not _ha_light_items:
        return [("NONE", "<press Refresh>", "No lights fetched yet")]
    return _ha_light_items


def _enum_collection_lights(self, context):
    global _collection_light_items
    coll = self.collection
    items = []
    if coll is not None:
        for obj in coll.all_objects:
            if obj.type == "LIGHT":
                items.append((obj.name, obj.name, "Blender light object"))
    if not items:
        items = [("NONE", "<no lights in collection>", "")]
    _collection_light_items = items
    return _collection_light_items


# ---------------------------------------------------------------------------
# Property groups
# ---------------------------------------------------------------------------

class HABridgeMapping(PropertyGroup):
    ha_entity_id: StringProperty(name="HA Entity")
    ha_name: StringProperty(name="HA Name")
    object_name: StringProperty(name="Blender Light")
    max_power: FloatProperty(
        name="Max Power",
        description="Blender light power (W) at full HA brightness",
        default=1000.0,
        min=0.0,
    )
    use_color: BoolProperty(name="Color", default=True)
    use_brightness: BoolProperty(name="Brightness", default=True)


class HABridgeSettings(PropertyGroup):
    url: StringProperty(
        name="Server URL",
        description="Home Assistant base URL",
        default="http://homeassistant.local:8123",
        maxlen=1024,
    )
    token: StringProperty(
        name="Token",
        description="Long-lived access token",
        subtype="PASSWORD",
        # Blender's text field truncates pasted input to a ~128-byte buffer
        # unless maxlen is set explicitly. HA tokens are ~180 chars, so without
        # this the signature chunk of the JWT gets clipped and HA returns 401.
        maxlen=2048,
    )
    interval: FloatProperty(
        name="Interval (s)",
        description="How often to poll Home Assistant",
        default=1.0,
        min=0.1,
        max=60.0,
    )
    ha_light: EnumProperty(name="HA Light", items=_enum_ha_lights)
    collection: PointerProperty(name="Collection", type=bpy.types.Collection)
    blender_light: EnumProperty(name="Scene Light", items=_enum_collection_lights)
    mappings: CollectionProperty(type=HABridgeMapping)
    active_mapping: IntProperty(default=0)


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class HA_OT_refresh(Operator):
    bl_idname = "ha_bridge.refresh"
    bl_label = "Refresh Lights"
    bl_description = "Fetch the list of lights from Home Assistant"

    def execute(self, context):
        global _ha_light_items
        s = context.scene.ha_bridge
        if not s.url or not s.token:
            self.report({"ERROR"}, "Set the Server URL and Token first")
            return {"CANCELLED"}

        # Diagnostics printed to the System Console (Window > Toggle System Console)
        tok = (s.token or "").strip()
        print("=" * 60)
        print("[HA Bridge] Refresh requested")
        print("[HA Bridge] URL:          {!r}".format((s.url or "").strip()))
        print("[HA Bridge] Token length: {}  (a real HA token is ~180 chars)".format(len(tok)))
        if tok:
            print("[HA Bridge] Token starts: {!r}  ends: {!r}".format(tok[:6], tok[-6:]))
            print("[HA Bridge] Dot-chunks:   {}  (a JWT should have 3)".format(tok.count(".") + 1))
        try:
            states = _fetch_lights(s.url, s.token, timeout=8)
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                body = "<no body>"
            print("[HA Bridge] HTTP {} from HA. Response body: {}".format(e.code, body))
            print("=" * 60)
            self.report({"ERROR"}, "HTTP {} – see System Console".format(e.code))
            _set_status("HTTP {} – {}".format(e.code, body[:60]))
            return {"CANCELLED"}
        except Exception as e:  # noqa: BLE001
            print("[HA Bridge] Connection error: {!r}".format(e))
            print("=" * 60)
            self.report({"ERROR"}, "Connection failed: {}".format(e))
            _set_status("Error: {}".format(e))
            return {"CANCELLED"}
        print("[HA Bridge] Success – {} lights returned".format(len(states)))
        print("=" * 60)

        with _lock:
            _latest_states.clear()
            _latest_states.update(states)

        items = []
        for entity_id, st in sorted(states.items()):
            friendly = (st.get("attributes", {}) or {}).get("friendly_name", entity_id)
            items.append((entity_id, friendly, entity_id))
        _ha_light_items = items or [("NONE", "<no lights found>", "")]
        _set_status("Found {} lights".format(len(states)))
        self.report({"INFO"}, "Found {} lights".format(len(states)))
        return {"FINISHED"}


class HA_OT_add_mapping(Operator):
    bl_idname = "ha_bridge.add_mapping"
    bl_label = "Add Mapping"
    bl_description = "Link the selected HA light to the selected scene light"

    def execute(self, context):
        s = context.scene.ha_bridge
        if s.ha_light in ("", "NONE"):
            self.report({"ERROR"}, "Pick a Home Assistant light")
            return {"CANCELLED"}
        if s.blender_light in ("", "NONE"):
            self.report({"ERROR"}, "Pick a scene light from the collection")
            return {"CANCELLED"}

        for m in s.mappings:
            if m.ha_entity_id == s.ha_light and m.object_name == s.blender_light:
                self.report({"WARNING"}, "That mapping already exists")
                return {"CANCELLED"}

        friendly = s.ha_light
        st = None
        with _lock:
            st = _latest_states.get(s.ha_light)
        if st:
            friendly = (st.get("attributes", {}) or {}).get("friendly_name", s.ha_light)

        m = s.mappings.add()
        m.ha_entity_id = s.ha_light
        m.ha_name = friendly
        m.object_name = s.blender_light
        s.active_mapping = len(s.mappings) - 1
        return {"FINISHED"}


class HA_OT_paste_token(Operator):
    bl_idname = "ha_bridge.paste_token"
    bl_label = "Paste Token from Clipboard"
    bl_description = (
        "Read the token straight from the system clipboard, bypassing the "
        "Blender text field (which truncates long pasted strings)"
    )

    def execute(self, context):
        s = context.scene.ha_bridge
        clip = (context.window_manager.clipboard or "").strip()
        s.token = clip
        print("[HA Bridge] Clipboard token length: {}  chunks: {}".format(
            len(clip), clip.count(".") + 1))
        if len(clip) < 100 or clip.count(".") != 2:
            self.report({"WARNING"},
                        "Clipboard has {} chars / {} chunks — copy the FULL token first".format(
                            len(clip), clip.count(".") + 1))
        else:
            self.report({"INFO"}, "Token set: {} chars".format(len(clip)))
        return {"FINISHED"}


class HA_OT_remove_mapping(Operator):
    bl_idname = "ha_bridge.remove_mapping"
    bl_label = "Remove Mapping"

    index: IntProperty(default=-1)

    def execute(self, context):
        s = context.scene.ha_bridge
        idx = self.index if self.index >= 0 else s.active_mapping
        if 0 <= idx < len(s.mappings):
            s.mappings.remove(idx)
            s.active_mapping = min(s.active_mapping, len(s.mappings) - 1)
        return {"FINISHED"}


class HA_OT_toggle_live(Operator):
    bl_idname = "ha_bridge.toggle_live"
    bl_label = "Toggle Live Sync"

    def execute(self, context):
        s = context.scene.ha_bridge
        if _live_active:
            _stop_live()
        else:
            if not s.url or not s.token:
                self.report({"ERROR"}, "Set the Server URL and Token first")
                return {"CANCELLED"}
            _start_live(s)
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

class HA_UL_mappings(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        row = layout.row(align=True)
        row.label(text=item.ha_name or item.ha_entity_id, icon="OUTLINER_OB_LIGHT")
        row.label(text="", icon="FORWARD")
        row.label(text=item.object_name, icon="LIGHT")
        op = row.operator("ha_bridge.remove_mapping", text="", icon="X", emboss=False)
        op.index = index


class HA_PT_panel(Panel):
    bl_label = "Home Assistant Bridge"
    bl_idname = "HA_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "HA Bridge"

    def draw(self, context):
        layout = self.layout
        s = context.scene.ha_bridge

        box = layout.box()
        box.label(text="Connection", icon="URL")
        box.prop(s, "url")
        row = box.row(align=True)
        row.prop(s, "token")
        row.operator("ha_bridge.paste_token", text="", icon="PASTEDOWN")
        row = box.row(align=True)
        row.prop(s, "interval")
        row.operator("ha_bridge.refresh", text="Refresh", icon="FILE_REFRESH")
        box.label(text="Status: " + _status)

        layout.separator()
        split = layout.split(factor=0.5)

        left = split.column()
        left.label(text="Home Assistant", icon="HOME")
        left.prop(s, "ha_light", text="")

        right = split.column()
        right.label(text="Blender Scene", icon="SCENE_DATA")
        right.prop(s, "collection", text="")
        right.prop(s, "blender_light", text="")

        layout.operator("ha_bridge.add_mapping", text="Link Selected", icon="LINKED")

        layout.separator()
        layout.label(text="Mappings", icon="PRESET")
        layout.template_list(
            "HA_UL_mappings", "", s, "mappings", s, "active_mapping", rows=3
        )

        if 0 <= s.active_mapping < len(s.mappings):
            m = s.mappings[s.active_mapping]
            col = layout.box().column(align=True)
            col.prop(m, "max_power")
            row = col.row(align=True)
            row.prop(m, "use_color", toggle=True)
            row.prop(m, "use_brightness", toggle=True)

        layout.separator()
        row = layout.row()
        row.scale_y = 1.4
        if _live_active:
            row.operator("ha_bridge.toggle_live", text="Stop Live Sync", icon="PAUSE")
        else:
            row.operator("ha_bridge.toggle_live", text="Start Live Sync", icon="PLAY")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_classes = (
    HABridgeMapping,
    HABridgeSettings,
    HA_OT_refresh,
    HA_OT_add_mapping,
    HA_OT_paste_token,
    HA_OT_remove_mapping,
    HA_OT_toggle_live,
    HA_UL_mappings,
    HA_PT_panel,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ha_bridge = PointerProperty(type=HABridgeSettings)


def unregister():
    _stop_live()
    if bpy.app.timers.is_registered(_sync_timer):
        bpy.app.timers.unregister(_sync_timer)
    del bpy.types.Scene.ha_bridge
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
