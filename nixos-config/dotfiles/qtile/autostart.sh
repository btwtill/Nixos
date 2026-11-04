#!/usr/bin/env bash

setxkbmap de
# Plain UI grey as the X background.
xsetroot -solid "#1e1e1e"

# On-screen keyboard service (hidden until an app runs `osk show`)
if command -v osk &>/dev/null; then
  osk daemon &
fi
# Rive HMI (homy-shell → homy-hmi): the whole screen, pinned by the Qtile config.
# Log: ~/.local/state/homy-shell.log
if command -v homy-shell &>/dev/null; then
  mkdir -p ~/.local/state
  homy-shell > ~/.local/state/homy-shell.log 2>&1 &
fi
if command -v picom &>/dev/null; then
  picom &
fi
# VM: the session half of the SPICE agent (clipboard ↔ the Mac). The system
# daemon runs as a service; desktops start this half via XDG autostart, which
# Qtile doesn't do.
if command -v spice-vdagent &>/dev/null; then
  spice-vdagent
fi
# Touch panel: hide the cursor the moment the screen is touched, start hidden,
# and otherwise hide it 0.1 s after the mouse stops (fractions of a second work).
unclutter --timeout 0.1 --hide-on-touch --start-hidden &

# if [ "$(hostname)" = "vm" ]; then
#   xrandr --output Virtual-1 --mode 1360x768
# fi
