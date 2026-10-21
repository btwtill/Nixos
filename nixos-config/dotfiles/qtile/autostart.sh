#!/usr/bin/env bash

setxkbmap de
# nitrogen on pi / vm; feh on pi5 (nitrogen was dropped from newer nixpkgs)
if command -v nitrogen &>/dev/null; then
  nitrogen --set-scaled "$HOME/wallpapers/background.jpg"
else
  feh --bg-scale "$HOME/wallpapers/background.jpg"
fi
if command -v picom &>/dev/null; then
  picom &
fi
unclutter -idle 1 -root &

# if [ "$(hostname)" = "vm" ]; then
#   xrandr --output Virtual-1 --mode 1360x768
# fi
