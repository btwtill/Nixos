from libqtile import bar, layout, widget, hook, qtile  # type: ignore
from libqtile.config import Group, Screen, Click, Drag  # type: ignore
from libqtile.lazy import lazy  # type: ignore
import subprocess
import os

mod = "mod4"

# ----------------------
# Groups = Screens
# ----------------------
groups = [
    Group("1", label="HOME"),
    Group("2", label="MEDIA"),
    Group("3", label="NAV"),
    Group("4", label="SYS"),
]

# ----------------------
# Layouts
# ----------------------
layouts = [
    layout.MonadTall(
        ratio=0.6,
        border_width=0,
        margin=0
    ),
    layout.Max(),
    layout.Floating(border_width=0)
]

# ----------------------
# Assign fixed layouts per group
# ----------------------
@hook.subscribe.setgroup
def set_group_layout():
    name = qtile.current_group.name

    if name == "1":
        qtile.current_group.layout = "monadtall"
    elif name in ["2", "3"]:
        qtile.current_group.layout = "max"
    elif name == "4":
        qtile.current_group.layout = "floating"

# ----------------------
# Touch-friendly mouse
# ----------------------
mouse = [
    Drag([], "Button1", lazy.window.set_position_floating()),
    Drag([], "Button3", lazy.window.set_size_floating()),
    Click([], "Button1", lazy.window.bring_to_front()),
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
        left=bar.Bar(
            [
                # --- NAVIGATION ---
                widget.TextBox("🏠", fontsize=32,
                    mouse_callbacks={"Button1": go("1")}),

                widget.TextBox("🎵", fontsize=32,
                    mouse_callbacks={"Button1": go("2")}),

                widget.TextBox("🧭", fontsize=32,
                    mouse_callbacks={"Button1": go("3")}),

                widget.TextBox("⚙️", fontsize=32,
                    mouse_callbacks={"Button1": go("4")}),

                widget.Spacer(length=20),

                # --- APPS ---
                widget.TextBox("🌐", fontsize=30,
                    mouse_callbacks={"Button1": spawn("firefox")}),

                widget.TextBox("📁", fontsize=30,
                    mouse_callbacks={"Button1": spawn("thunar")}),

                widget.TextBox("🖥", fontsize=30,
                    mouse_callbacks={"Button1": spawn("alacritty")}),

                widget.Spacer(),

                # --- WINDOW CONTROL ---
                widget.TextBox("⛶", fontsize=28,
                    mouse_callbacks={"Button1": lazy.window.toggle_fullscreen()}),

                widget.TextBox("✕", fontsize=28,
                    mouse_callbacks={"Button1": lazy.window.kill()}),

                widget.Spacer(length=20),

                # --- CLOCK ---
                widget.Clock(format="%H:%M"),
            ],
            100,
            background="#1e1e1e",
        ),
    ),
]

# ----------------------
# Autostart
# ----------------------
@hook.subscribe.startup_once
def autostart():
    subprocess.Popen([
        "picom",
        "--config",
        os.path.expanduser("~/.config/picom/picom.conf")
    ])

# ----------------------
# Manage new windows (merged logic)
# ----------------------
@hook.subscribe.client_new
def manage_client(client):
    wm_class = client.get_wm_class()

    # if wm_class:
    #     lowered = [w.lower() for w in wm_class]

    #     if "firefox" in lowered:
    #         client.togroup("1")
    #     elif "vlc" in lowered:
    #         client.togroup("2")

    # fullscreen behavior for MEDIA + NAV
    # if client.group and client.group.name in ["2", "3"]:
    #     client.toggle_fullscreen()

# ----------------------
# Misc
# ----------------------
follow_mouse_focus = True
bring_front_click = True
cursor_warp = False