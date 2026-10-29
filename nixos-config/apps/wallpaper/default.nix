{ pkgs ? import <nixpkgs> {} }:

# homy-wallpaper — sets the desktop background: what shows wherever the UI is
# transparent (the Rive sidebar, later the bars) and in the gaps between apps.
#
#   homy-wallpaper [IMAGE]
#
# Image: the argument, else ~/.config/homy/wallpaper.png / .jpg, else the
# bundled placeholder (default.png). Uses feh so the compositor (picom) sees it:
# feh publishes the image as the root pixmap, `xsetroot -solid` does not.
pkgs.writeShellApplication {
  name = "homy-wallpaper";
  runtimeInputs = [ pkgs.feh ];
  text = ''
    img="''${1:-}"
    for candidate in "$HOME/.config/homy/wallpaper.png" "$HOME/.config/homy/wallpaper.jpg"; do
      if [ -z "$img" ] && [ -f "$candidate" ]; then img="$candidate"; fi
    done
    img="''${img:-${./default.png}}"
    exec feh --no-fehbg --bg-fill "$img"
  '';
}
