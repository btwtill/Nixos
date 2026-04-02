from libqtile import bar, layout, widget            #type: ignore
from libqtile.config import Key, Group, Screen      #type: ignore
from libqtile.lazy import lazy                      #type: ignore

mod = "mod4"

keys = [
    Key([mod], "Return", lazy.spawn("xterm")),
    Key([mod], "q", lazy.shutdown()),
]

groups = [Group(i) for i in "123"]

layouts = [layout.MonadTall()]

screens = [
    Screen(
        top=bar.Bar(
            [widget.Clock(format="%Y-%m-%d %H:%M")],
            24,
        ),
    ),
]