#!/usr/bin/env bash

setxkbmap de
# Solid desktop background in the exact UI grey. It shows in the gaps around
# windows; drawing the wallpaper image there came out one shade darker
# (#1d1d1d) and showed as a dark frame around the apps.
xsetroot -solid "#1e1e1e"

# On-screen keyboard service (hidden until an app runs `osk show`)
if command -v osk &>/dev/null; then
  osk daemon &
fi
if command -v picom &>/dev/null; then
  picom &
fi
unclutter -idle 1 -root &

# if [ "$(hostname)" = "vm" ]; then
#   xrandr --output Virtual-1 --mode 1360x768
# fi
