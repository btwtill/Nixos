#!/usr/bin/env bash

setxkbmap de
# Plain UI grey as the X background. On the VM / Pi 5 the shell's Rive
# wallpaper covers it moments later; the Pi 3B+ keeps it.
xsetroot -solid "#1e1e1e"

# On-screen keyboard service (hidden until an app runs `osk show`)
if command -v osk &>/dev/null; then
  osk daemon &
fi
# Rive-drawn desktop surfaces — sidebar + wallpaper (pinned by the Qtile config)
if command -v homy-shell &>/dev/null; then
  homy-shell &
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
