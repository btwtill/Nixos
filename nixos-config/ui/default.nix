{ pkgs ? import <nixpkgs> {} }:

# homy-ui — the Rive files, in one place on the device:
#
#   share/homy/ui/riv/<surface>.riv         built from homy-design (./sync.sh)
#
# homy-hmi (apps/hmi) plays them; it is also linked into
# /run/current-system/sw/share/homy/ui.
pkgs.runCommand "homy-ui" { } ''
  mkdir -p $out/share/homy/ui/riv
  cp ${./riv}/*.riv $out/share/homy/ui/riv/
''
