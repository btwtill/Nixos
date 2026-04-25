from libqtile import bar, layout, widget, hook      #type: ignore
from libqtile.config import Group, Screen, Click, Drag, Key  #type: ignore
from libqtile.lazy import lazy  #type: ignore
from libqtile.utils import guess_terminal  #type: ignore
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
    Key([mod], "f", lazy.window.toggle_fullscreen()),
]

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
# Layouts
# ----------------------
layout_theme = {
    "border_width": 3,
    "margin": 15,
    "border_focus": colors["accent"],
    "border_normal": colors["fg"],
    "single_border_width": 3,
}

layouts = [
    layout.MonadTall(**layout_theme),
    layout.Max(),
    layout.Floating(),
]

# ----------------------
# Widget Defaults
# ----------------------
widget_defaults = dict(
    font="sans",
    fontsize=26,
    padding=10,
)

# ----------------------
# Helper functions — return plain callables, not lazy
# ----------------------
def go(group_name):
    def _inner(qtile):
        qtile.groups_map[group_name].toscreen()
    return _inner

def spawn_cmd(cmd):
    def _inner(qtile):
        qtile.spawn(cmd)
    return _inner

def kill_window(qtile):
    if qtile.current_window:
        qtile.current_window.kill()

def toggle_fullscreen(qtile):
    if qtile.current_window:
        qtile.current_window.toggle_fullscreen()

# ----------------------
# Screens
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
                    mouse_callbacks={"Button1": spawn_cmd(terminal)}),

                widget.Spacer(),

                # --- WINDOW CONTROL ---
                widget.TextBox("Full", fontsize=28,
                    mouse_callbacks={"Button1": toggle_fullscreen}),

                widget.TextBox("Close", fontsize=28,
                    mouse_callbacks={"Button1": kill_window}),

                widget.Spacer(length=20),

                # --- CLOCK ---
                widget.Clock(format="%H:%M"),

                widget.Spacer(),

                widget.TextBox("sleep", fontsize=28,
                    mouse_callbacks={"Button1": spawn_cmd("xset dpms force off")}),

                widget.TextBox("reboot", fontsize=28,
                    mouse_callbacks={"Button1": spawn_cmd("systemctl reboot")}),

                widget.TextBox("shutdown", fontsize=28,
                    mouse_callbacks={"Button1": spawn_cmd("systemctl poweroff")}),
            ],
            100,
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
        subprocess.Popen([home])
    else:
        print("Autostart script not found!")