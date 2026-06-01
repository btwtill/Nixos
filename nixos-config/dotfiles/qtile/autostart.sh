#!/usr/bin/env bash

setxkbmap de
nitrogen --set-scaled "$HOME/wallpapers/background.jpg"
picom
unclutter -idle 1 -root &

if [ "$(hostname)" = "vm" ]; then
  xrandr --output Virtual-1 --mode 1360x768
fi
