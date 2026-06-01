{ pkgs ? import <nixpkgs> {} }:

pkgs.writeShellScriptBin "screenshot" ''
  set -e

  DISPLAY=''${DISPLAY:-:0}
  export DISPLAY

  if [ "$1" = "-" ]; then
    ${pkgs.maim}/bin/maim
  else
    DEST=''${1:-$HOME/Pictures/screenshots/$(${pkgs.coreutils}/bin/date +%Y%m%d_%H%M%S).png}
    ${pkgs.coreutils}/bin/mkdir -p "$(${pkgs.coreutils}/bin/dirname "$DEST")"
    ${pkgs.maim}/bin/maim "$DEST"
    echo "$DEST"
  fi
''
