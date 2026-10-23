{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python313;
  pyEnv  = python.withPackages (ps: [ ps.pyqt6 ]);
in
pkgs.stdenv.mkDerivation {
  pname   = "wifi-app";
  version = "0.1.0";

  src = ./.;

  buildInputs = [ pyEnv ];

  # nmcli comes from the system's NetworkManager (must match the running
  # daemon), osk from the osk package — both are on the system PATH.
  installPhase = ''
    mkdir -p $out/bin $out/lib/wifi-app
    cp *.py $out/lib/wifi-app/
    cp ${../common}/ui_kit.py $out/lib/wifi-app/

    cat > $out/bin/wifi-app <<EOF
    #!/bin/sh
    exec ${pyEnv}/bin/python $out/lib/wifi-app/main.py "\$@"
    EOF
    chmod +x $out/bin/wifi-app
  '';
}
