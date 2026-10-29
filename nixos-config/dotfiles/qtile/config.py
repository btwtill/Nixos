from libqtile import bar, layout, widget, hook, qtile      #type: ignore
from libqtile.config import Group, Screen, Key  #type: ignore
from libqtile.lazy import lazy  #type: ignore
from libqtile.utils import guess_terminal  #type: ignore
from libqtile.widget import base  #type: ignore
from libqtile.log_utils import logger  #type: ignore
from collections import deque
import cairocffi  #type: ignore
import subprocess
import threading
import shlex
import io
import os
import signal
import urllib.parse
import urllib.request

import socket
_hostname = socket.gethostname()

mod = "mod4"
terminal = guess_terminal()

mouse = []

# Per-host display sizing
ICON_SIZE   = 104
ICON_MARGIN = 0
BAR_WIDTH   = 180

# ----------------------
# Icons
# Drop your .svg files into ~/.config/qtile/icons/
# Each button needs two files: name.svg and name_pressed.svg
# ----------------------
ICONS_DIR = os.path.expanduser("~/.config/qtile/icons/")

def icon(name):
    return os.path.join(ICONS_DIR, name)

# ----------------------
# Color Tokens
# ----------------------
colors = {
    "bg": "#1e1e1e",
    "fg": "#ffffff",
    "accent": "#3daee9",
}

# ----------------------
# SvgButton — custom widget with press/release visual feedback
# ----------------------
class SvgButton(base._Widget):
    defaults = [
        ("icon_size",   ICON_SIZE,   "Icon size in pixels (width and height when icon_width/icon_height are not set)"),
        ("icon_width",  None,        "Icon render width in pixels (overrides icon_size)"),
        ("icon_height", None,        "Icon render height in pixels (overrides icon_size)"),
        ("margin",      ICON_MARGIN, "Margin around icon"),
        ("background",  None,        "Background color (None = bar background)"),
    ]

    def __init__(self, icon_normal, icon_pressed, callback, **config):
        # Route callback through Qtile's own mouse_callbacks machinery so
        # lazy calls are dispatched correctly without X11 re-entrancy issues.
        mc = config.pop("mouse_callbacks", {})
        mc["Button1"] = callback
        config["mouse_callbacks"] = mc

        base._Widget.__init__(self, bar.CALCULATED, **config)
        self.add_defaults(SvgButton.defaults)
        self._path_normal  = icon_normal
        self._path_pressed = icon_pressed
        self._pressed      = False
        self._surf_normal  = None
        self._surf_pressed = None

    def _iw(self):
        return self.icon_width if self.icon_width is not None else self.icon_size

    def _ih(self):
        return self.icon_height if self.icon_height is not None else self.icon_size

    def _load_svg(self, path):
        try:
            result = subprocess.run(
                [
                    "rsvg-convert",
                    "-w", str(self._iw()),
                    "-h", str(self._ih()),
                    path,
                ],
                capture_output=True,
                check=True,
            )
            return cairocffi.ImageSurface.create_from_png(io.BytesIO(result.stdout))
        except Exception as e:
            logger.warning("SvgButton: could not load %s — %s", path, e)
            return None

    def _configure(self, qtile, bar):
        base._Widget._configure(self, qtile, bar)
        self._surf_normal  = self._load_svg(self._path_normal)
        self._surf_pressed = self._load_svg(self._path_pressed)
        logger.warning(
            "SvgButton [%s]: normal=%s pressed=%s",
            self._path_normal,
            "OK" if self._surf_normal  else "FAILED",
            "OK" if self._surf_pressed else "FAILED",
        )

    def calculate_length(self):
        # Horizontal bars (top/bottom): length = widget width.
        # Vertical bars (left/right):   length = widget height.
        if self.bar.horizontal:
            return self._iw() + self.margin * 2
        return self._ih() + self.margin * 2

    def draw(self):
        self.drawer.clear(self.background or self.bar.background)
        surf = self._surf_pressed if self._pressed else self._surf_normal
        if surf:
            ctx = self.drawer.ctx
            ctx.save()
            if self.bar.horizontal:
                x = self.margin
                y = (self.bar.size - self._ih()) / 2
            else:
                x = (self.bar.width - self._iw()) / 2
                y = self.margin
            ctx.translate(x, y)
            ctx.set_source_surface(surf, 0, 0)
            ctx.paint()
            ctx.restore()
        if self.bar.horizontal:
            self.drawer.draw(
                offsetx=self.offsetx,
                offsety=self.offsety,
                width=self.calculate_length(),
                height=self.bar.size,
            )
        else:
            self.drawer.draw(
                offsetx=self.offsetx,
                offsety=self.offsety,
                width=self.width,
                height=self.calculate_length(),
            )

    def button_press(self, x, y, button):
        if button == 1:
            self._pressed = True
            self.draw()
        super().button_press(x, y, button)  # fires mouse_callbacks via Qtile's dispatcher

    def button_release(self, _x, _y, button):
        if button == 1:
            self._pressed = False
            self.draw()

# ----------------------
# Startup Layout
# Each entry is (group_name, command).
# Replace terminal with a specific app path when ready.
# ----------------------
startup_layout = [
    ("1", "home-app"),    # group 1 — home control UI
    ("2", "lights-app"),  # group 2 — lights control UI
    ("3", terminal),      # group 3
    ("4", "music-app"),   # group 4 — music player
    ("5", terminal),      # group 5 - terminal
    ("6", "system-app"),  # group 6 — services / resources monitor
    ("7", "bluetooth-app"), # group 7 — Bluetooth devices
    ("8", "wifi-app"),    # group 8 — Wi-Fi networks
    ("9", "homy-launcher"), # group 9 — app menu (top menu button)
]

# Named apps get a fixed group regardless of spawn order.
# Key = window title (client.name), set via setWindowTitle() in each Qt app.
_NAMED_GROUPS = {
    "Home":   "1",
    "Lights": "2",
    "Music":  "4",
    "System": "6",
    "Bluetooth": "7",
    "Wi-Fi":  "8",
    "Apps":   "9",
}

# Unnamed windows (terminals) fill remaining groups in order.
_startup_queue = deque(["3", "5"])

# ----------------------
# Launcher apps — every app started from the app menu gets its own group
# "app:<id>", created when its window appears and removed when it closes.
# The launcher starts apps with HOMY_APP_ID set; it's read from /proc.
# ----------------------
LAUNCHER_GROUP = "9"

def _app_env(client) -> dict:
    """HOMY_* variables of the process that owns the window."""
    try:
        with open(f"/proc/{client.get_pid()}/environ", "rb") as f:
            pairs = (v.split(b"=", 1) for v in f.read().split(b"\0") if v.startswith(b"HOMY_"))
            return {k.decode(): val.decode() for k, val in pairs}
    except Exception:
        return {}

def _homy_app_id(client):
    return _app_env(client).get("HOMY_APP_ID")

def _to_app_group(client, app_id):
    name = f"app:{app_id}"
    qtile.add_group(name, layout="monadtall")   # no-op if it already exists
    client.togroup(name)
    return qtile.groups_map[name]

# ----------------------
# Pause hidden launcher apps — while an app's group is off screen its whole
# process tree is frozen (SIGSTOP: no CPU, no GPU, no rendering) and resumed
# (SIGCONT) when it's shown again. Apps that must keep working in the
# background set "background": true in their manifest (HOMY_APP_BACKGROUND=1).
# ----------------------
_paused: dict = {}   # group name -> pids we stopped

def _process_tree(root: int) -> list:
    children: dict = {}
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            try:
                with open(f"/proc/{entry}/stat") as f:
                    ppid = int(f.read().rsplit(")", 1)[1].split()[1])
                children.setdefault(ppid, []).append(int(entry))
            except (OSError, ValueError, IndexError):
                pass
    tree, todo = [], [root]
    while todo:
        pid = todo.pop()
        tree.append(pid)
        todo.extend(children.get(pid, []))
    return tree

def _signal_all(pids, sig):
    for pid in pids:
        try:
            os.kill(pid, sig)
        except OSError:
            pass

def _set_paused(group, paused: bool):
    if not paused:
        _signal_all(_paused.pop(group.name, []), signal.SIGCONT)
        return
    if group.name in _paused or not group.windows:
        return
    if any(_app_env(w).get("HOMY_APP_BACKGROUND") == "1" for w in group.windows):
        return
    pids = []
    for w in group.windows:
        try:
            pids += _process_tree(w.get_pid())
        except Exception:
            pass
    _signal_all(pids, signal.SIGSTOP)
    _paused[group.name] = pids
    logger.warning("homy: paused %s (%d processes)", group.name, len(pids))

@hook.subscribe.startup
def resume_all_apps():
    """After a Qtile restart the list of paused apps is gone — wake every
    launcher app so nothing stays frozen."""
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/environ", "rb") as f:
                if b"HOMY_APP_ID=" in f.read():
                    _signal_all(_process_tree(int(entry)), signal.SIGCONT)
        except OSError:
            pass

@hook.subscribe.setgroup
def pause_hidden_apps():
    for g in list(qtile.groups):
        if g.name.startswith("app:"):
            _set_paused(g, paused=g.screen is None)

@hook.subscribe.client_killed
def remove_empty_app_group(client):
    group = client.group
    if group is None or not group.name.startswith("app:"):
        return

    def cleanup():
        g = qtile.groups_map.get(group.name)
        if g is not None and not g.windows:
            _signal_all(_paused.pop(g.name, []), signal.SIGCONT)
            if qtile.current_group is g:
                qtile.groups_map[LAUNCHER_GROUP].toscreen()   # back to the app menu
            qtile.delete_group(g.name)

    qtile.call_later(0.2, cleanup)

def _show_launcher(qtile):
    """Menu button. Safety net first: an app window sitting in the menu's own
    group (it missed its app group) would cover the menu — move it out."""
    launcher = qtile.groups_map[LAUNCHER_GROUP]
    for w in list(launcher.windows):
        app_id = _homy_app_id(w)
        if app_id:
            logger.warning("homy: moving %r out of the app menu into app:%s", w.name, app_id)
            _to_app_group(w, app_id)
    launcher.toscreen()

# ----------------------
# Homy sidebar (apps/sidebar) — the Rive-drawn navigation over the right bar.
# Its window is pinned there as a static (untiled) window; the right bar below
# keeps reserving the space and its buttons are the fallback if it isn't running.
# Group changes are reported to it so it highlights the matching button.
# ----------------------
SIDEBAR_TITLE = "Homy Sidebar"
SIDEBAR_URL   = "http://127.0.0.1:47811/group?name="

@hook.subscribe.setgroup
def notify_sidebar():
    name = qtile.current_group.name

    def send():
        try:
            urllib.request.urlopen(SIDEBAR_URL + urllib.parse.quote(name), timeout=0.5).close()
        except Exception:
            pass                                   # sidebar not running (yet)

    threading.Thread(target=send, daemon=True).start()

@hook.subscribe.client_new
def assign_startup_group(client):
    if client.name == SIDEBAR_TITLE:
        screen = qtile.current_screen
        client.static(screen.index, x=screen.x + screen.width - BAR_WIDTH, y=screen.y + BAR_HEIGHT,
                      width=BAR_WIDTH, height=screen.height - 2 * BAR_HEIGHT)
        logger.warning("homy: sidebar pinned over the right bar")
        return
    app_id = _homy_app_id(client)
    if app_id:
        group = _to_app_group(client, app_id)
        group.toscreen()
        logger.warning("homy: %r (pid %s) -> %s", client.name, client.get_pid(), group.name)
        return
    if client.name in _NAMED_GROUPS:
        client.togroup(_NAMED_GROUPS[client.name])
    elif _startup_queue:
        client.togroup(_startup_queue.popleft())

# ----------------------
# Groups
# ----------------------
groups = [
    Group("1", layout="monadtall"),
    Group("2", layout="monadtall"),
    Group("3", layout="monadtall"),
    Group("4", layout="monadtall"),
    Group("5", layout="monadtall"),
    Group("6", layout="monadtall"),
    Group("7", layout="monadtall"),
    Group("8", layout="monadtall"),
    Group("9", layout="monadtall"),
]

# ----------------------
# Key Bindings
# ----------------------
keys = [
    Key([mod], "x",      lazy.window.kill()),
    Key([mod], "Return", lazy.spawn(terminal)),
    Key([mod], "f",      lazy.window.toggle_fullscreen()),
    Key([mod], "h",      lazy.layout.left()),
    Key([mod], "l",      lazy.layout.right()),
    Key([mod], "j",      lazy.layout.down()),
    Key([mod], "k",      lazy.layout.up()),
]

for i in groups:
    keys.extend([
        Key([mod], i.name,           lazy.group[i.name].toscreen()),
        Key([mod, "shift"], i.name,  lazy.window.togroup(i.name, switch_group=True)),
    ])

# ----------------------
# Layouts — borderless for clean touch UI
# ----------------------
layout_theme = {
    "border_width": 0,
    "border_focus":  "#000000",
    "border_normal": "#000000",
    "margin": 15,
    "ratio": 0.67,
}

layouts = [
    layout.MonadTall(**layout_theme),
    layout.Max(),
    layout.Floating(border_width=0, border_focus="#000000", border_normal="#000000"),
]

# ----------------------
# Widget Defaults
# ----------------------
widget_defaults = dict(
    font="sans",
    fontsize=26,
    padding=12,
)

# ----------------------
# Screens — right sidebar with SVG icon buttons
#
# Icon files needed in ~/.config/qtile/icons/:
#   group1.svg / group1_pressed.svg
#   group2.svg / group2_pressed.svg
#   group3.svg / group3_pressed.svg
#   group4.svg / group4_pressed.svg
#   terminal.svg  / terminal_pressed.svg
#   fullscreen.svg / fullscreen_pressed.svg
#   close.svg     / close_pressed.svg
#   sleep.svg     / sleep_pressed.svg
#   reboot.svg    / reboot_pressed.svg
#   power.svg     / power_pressed.svg
# ----------------------
BAR_HEIGHT = 40
BTN_W      = 95
BTN_H      = 40

screens = [
    Screen(
        top=bar.Bar(
            [
                SvgButton(icon("Terminal_Button.svg"), icon("Terminal_Button_Highlighted.svg"),
                    lazy.group["5"].toscreen(),
                    icon_width=BTN_W, icon_height=BTN_H),
                widget.Spacer(),
                SvgButton(icon("Menu_Button.svg"), icon("Menu_Button_Highlighted.svg"),
                    lazy.function(_show_launcher),
                    icon_width=375, icon_height=40),
                widget.Spacer(),
                SvgButton(icon("WifiButton.svg"), icon("WifiButtonPushed.svg"),
                    lazy.group["8"].toscreen(),
                    icon_width=BTN_W, icon_height=BTN_H),
            ],
            BAR_HEIGHT,
            background=colors["bg"],
        ),
        bottom=bar.Bar(
            [
                SvgButton(icon("Bluetooth_Button.svg"), icon("Bluetooth_Button_Highlighted.svg"),
                    lazy.group["7"].toscreen(),
                    icon_width=BTN_W, icon_height=BTN_H),
                SvgButton(icon("SystemButton.svg"), icon("SystemButtonPushed.svg"),
                    lazy.group["6"].toscreen(),
                    icon_width=BTN_W, icon_height=BTN_H),
                widget.Spacer(),
            ],
            BAR_HEIGHT,
            background=colors["bg"],
        ),
        right=bar.Bar(
            [
                SvgButton(icon("Home_Button.svg"), icon("Home_Button_Highlighted.svg"),
                    lazy.group["1"].toscreen()),
                SvgButton(icon("LightBulb_Button.svg"), icon("LightBulb_Button_Highlighted.svg"),
                    lazy.group["2"].toscreen()),
                SvgButton(icon("Heiz_Button.svg"), icon("Heiz_Button_Highlighted.svg"),
                    lazy.group["3"].toscreen()),
                SvgButton(icon("Music_Button.svg"), icon("Music_Button_Highlighted.svg"),
                    lazy.group["4"].toscreen()),
                SvgButton(icon("Shutdown_Button.svg"), icon("Shutdown_Button_Highlighted.svg"),
                    lazy.spawn("systemctl poweroff")),
            ],
            BAR_WIDTH,
            background=colors["bg"],
        ),
    ),
]

# ----------------------
# Floating layout — must be set as a module-level variable; the Floating
# entry in the layouts list above does NOT control floating window borders.
# ----------------------
floating_layout = layout.Floating(
    border_width=0,
    border_focus="#000000",
    border_normal="#000000",
)

# ----------------------
# General Settings
# ----------------------
follow_mouse_focus = True
bring_front_click = True
cursor_warp = False
auto_fullscreen = True
focus_on_window_activation = "smart"
reconfigure_screens = True

# ----------------------
# Autostart
# ----------------------
@hook.subscribe.startup_once
def autostart():
    home = os.path.expanduser("~/.config/qtile/autostart.sh")
    if os.path.exists(home):
        subprocess.Popen(["bash", home])

    def _spawn_startup():
        import time
        time.sleep(1)
        for _, cmd in startup_layout:
            # One missing app (not installed on this host) must not stop the rest.
            try:
                subprocess.Popen(shlex.split(cmd))
            except OSError as e:
                logger.warning("startup: could not start %s — %s", cmd, e)
            time.sleep(0.25)

    threading.Thread(target=_spawn_startup, daemon=True).start()
