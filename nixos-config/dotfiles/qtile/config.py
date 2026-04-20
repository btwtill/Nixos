from libqtile import bar, layout, widget, hook, qtile  # type: ignore
from libqtile.config import Group, Screen, Click, Drag  # type: ignore
from libqtile.lazy import lazy  # type: ignore
from libqtile.config import Key #type: ignore
from libqtile.utils import guess_terminal #type: ignore
import subprocess
import os

mod = "mod4"
terminal = guess_terminal()
mouse = [
    Click([], "Button1", lazy.window.focus()),
]

# ----------------------
# Color Tokens
# ----------------------

colors = {
    "bg": "#1e1e1e",
    "fg": "#ffffff",
    "accent": "#3daee9",
}

# ----------------------
# Key Bindings
# ----------------------
keys = [
    Key([mod], "x", lazy.window.kill()),
    Key([mod], "Return", lazy.spawn(terminal)),
    Key([mod], "f", lazy.window.toggle_fullscreen())
]

# ----------------------
# Groups = Screens
# ----------------------
groups = [
    Group("1", layout="monadtall"),
    Group("2", layout="monadtall"),
    Group("3", layout="monadtall"),
    Group("4", layout="monadtall"),
]

# ----------------------
# Layouts
# ----------------------

layout_theme = {
    "border_width": 3,
    "margin": 15,
    "border_focus": colors["accent"],
    "border_normal": colors["fg"],
    "single_border_width": 3
}

layouts = [
    layout.MonadTall(**layout_theme),
    layout.Max(),
    layout.Floating(),
]

# ----------------------
# Widget Defaults (BIG UI)
# ----------------------
widget_defaults = dict(
    font="sans",
    fontsize=26,
    padding=10,
)

# ----------------------
# Helper functions
# ----------------------
def go(group):
    return lazy.group[group].toscreen()

def spawn(cmd):
    return lazy.spawn(cmd)

# ----------------------
# Sidebar (Main UI)
# ----------------------
screens = [
    Screen(
        top=bar.Bar(
            [
                # --- NAVIGATION ---
                widget.TextBox("1", fontsize=32,
                    mouse_callbacks={"Button1": go("1")}),

                widget.TextBox("2", fontsize=32,
                    mouse_callbacks={"Button1": go("2")}),

                widget.TextBox("3", fontsize=32,
                    mouse_callbacks={"Button1": go("3")}),

                widget.TextBox("4", fontsize=32,
                    mouse_callbacks={"Button1": go("4")}),

                widget.Spacer(length=20),

                widget.TextBox("Terminal", fontsize=30,
                    mouse_callbacks={"Button1": spawn(terminal)}),

                widget.Spacer(),

                # --- WINDOW CONTROL ---
                widget.TextBox("Full", fontsize=28,
                    mouse_callbacks={"Button1": lazy.window.toggle_fullscreen()}),

                widget.TextBox("Close", fontsize=28,
                    mouse_callbacks={"Button1": lazy.window.kill()}),

                widget.Spacer(length=20),

                # --- CLOCK ---
                widget.Clock(format="%H:%M"),

                widget.Spacer(),

                widget.TextBox("sleep", fontsize=28,
                    mouse_callbacks={"Button1": lazy.spawn("xset dpms force off")}),

                widget.TextBox("reboot", fontsize=28,
                    mouse_callbacks={"Button1": lazy.spawn("systemctl reboot")}),

                widget.TextBox("shutdown", fontsize=28,
                    mouse_callbacks={"Button1": lazy.spawn("systemctl poweroff")})
            ],
            100,
            background= colors["bg"],
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
        subprocess.Popen([home])
    else:
        print("Autostart script not found!")
