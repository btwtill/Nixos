from libqtile import bar, layout, widget, hook      #type: ignore
from libqtile.config import Group, Screen, Key  #type: ignore
from libqtile.lazy import lazy  #type: ignore
from libqtile.utils import guess_terminal  #type: ignore
from libqtile.widget import base  #type: ignore
from libqtile.log_utils import logger  #type: ignore
from collections import deque
import cairocffi  #type: ignore
import subprocess
import threading
import io
import os

mod = "mod4"
terminal = guess_terminal()

mouse = []

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
        ("icon_size", 80, "Icon render size in pixels"),
        ("margin",    15, "Margin around icon"),
        ("background", None, "Background color (None = bar background)"),
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

    def _load_svg(self, path):
        try:
            result = subprocess.run(
                [
                    "rsvg-convert",
                    "-w", str(self.icon_size),
                    "-h", str(self.icon_size),
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
        return self.icon_size + self.margin * 2

    def draw(self):
        self.drawer.clear(self.background or self.bar.background)
        surf = self._surf_pressed if self._pressed else self._surf_normal
        if surf:
            ctx = self.drawer.ctx
            ctx.save()
            # Centre the icon horizontally within the bar width
            x = (self.bar.width - self.icon_size) / 2
            ctx.translate(x, self.margin)
            ctx.set_source_surface(surf, 0, 0)
            ctx.paint()
            ctx.restore()
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
    ("1", terminal),   # home: master left
    ("1", terminal),   # home: right top
    ("1", terminal),   # home: right bottom
    ("2", terminal),   # group 2
    ("3", terminal),   # group 3
    ("4", terminal),   # group 4
]

_startup_queue = deque(group for group, _ in startup_layout)

@hook.subscribe.client_new
def assign_startup_group(client):
    if _startup_queue:
        client.togroup(_startup_queue.popleft())

# ----------------------
# Groups
# ----------------------
groups = [
    Group("1", layout="monadtall"),
    Group("2", layout="monadtall"),
    Group("3", layout="monadtall"),
    Group("4", layout="monadtall"),
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
    "margin": 15,
    "ratio": 0.67,
}

layouts = [
    layout.MonadTall(**layout_theme),
    layout.Max(),
    layout.Floating(border_width=0),
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
screens = [
    Screen(
        right=bar.Bar(
            [
                # --- GROUPS ---
                widget.Spacer(),
                SvgButton(icon("Home_Icon_V002.svg"), icon("Home_Icon_Highlighted.svg"),
                    lazy.group["1"].toscreen()),
                widget.Spacer(),
                SvgButton(icon("LightBulb_Icon.svg"), icon("LightBulb_Icon_Highlighted.svg"),
                    lazy.group["2"].toscreen()),
                widget.Spacer(),
                SvgButton(icon("Heiz_Icon.svg"), icon("Heiz_Icon_Highlighted.svg"),
                    lazy.group["3"].toscreen()),
                widget.Spacer(),
                SvgButton(icon("Info_Icon.svg"), icon("Info_Icon_Highlighted.svg"),
                    lazy.group["4"].toscreen()),

                # larger gap separates navigation from system controls
                widget.Spacer(),
                widget.Spacer(),

                SvgButton(icon("Shutdown_Icon.svg"),  icon("Shutdown_Icon_Highlighted.svg"),
                    lazy.spawn("systemctl poweroff")),
                widget.Spacer(),
            ],
            180,
            background=colors["bg"],
        ),
    ),
]

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
            subprocess.Popen([cmd])
            time.sleep(0.25)

    threading.Thread(target=_spawn_startup, daemon=True).start()
