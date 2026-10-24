# Package a launcher app folder (with manifest.json) so it can be installed
# per user, without a system rebuild:
#
#   nix profile install .#homy-hello      # install
#   nix profile remove homy-app-hello     # uninstall
#
# The app gets its own Python (pyqt6 + whatever `pythonPackages` adds), and
# "homy-python" at the start of the manifest's exec is pointed at it.
{ pkgs, src, pythonPackages ? (ps: [ ps.pyqt6 ]) }:

let
  manifest = builtins.fromJSON (builtins.readFile "${src}/manifest.json");
  pyEnv    = pkgs.python313.withPackages pythonPackages;
in
pkgs.runCommand "homy-app-${manifest.id}" { nativeBuildInputs = [ pkgs.jq ]; } ''
  dir=$out/share/homy/apps/${manifest.id}
  mkdir -p $dir
  cp -r ${src}/. $dir/
  chmod -R u+w $dir
  jq --arg py "${pyEnv}/bin/python" '.exec |= sub("^homy-python"; $py)' \
    ${src}/manifest.json > $dir/manifest.json
''
