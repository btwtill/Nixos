#!/usr/bin/env bash

setxkbmap de
# Desktop background — shows behind the transparent Rive UI and between apps.
# homy-wallpaper (VM, Pi 5) uses ~/.config/homy/wallpaper.png if present; the
# Pi 3B+ keeps the solid UI grey.
if command -v homy-wallpaper &>/dev/null; then
  homy-wallpaper
else
  xsetroot -solid "#1e1e1e"
fi

# On-screen keyboard service (hidden until an app runs `osk show`)
if command -v osk &>/dev/null; then
  osk daemon &
fi
# Rive-drawn navigation sidebar (pinned over the right bar by the Qtile config)
if command -v homy-sidebar &>/dev/null; then
  homy-sidebar &
fi
if command -v picom &>/dev/null; then
  picom &
fi
# Touch panel: hide the cursor the moment the screen is touched, start hidden,
# and otherwise hide it 0.1 s after the mouse stops (fractions of a second work).
unclutter --timeout 0.1 --hide-on-touch --start-hidden &

# if [ "$(hostname)" = "vm" ]; then
#   xrandr --output Virtual-1 --mode 1360x768
# fi
