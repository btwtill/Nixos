{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python313;
  pyEnv  = python.withPackages (ps: [ ps.pyqt6 ]);
  # xdotool sends the key presses to the focused window
  path   = pkgs.lib.makeBinPath [ pkgs.xdotool ];
in
pkgs.stdenv.mkDerivation {
  pname   = "osk";
  version = "0.1.0";

  src = ./.;

  buildInputs = [ pyEnv ];

  installPhase = ''
    mkdir -p $out/bin $out/lib/osk
    cp *.py $out/lib/osk/

    cat > $out/bin/osk <<EOF
    #!/bin/sh
    export PATH="${path}:\$PATH"
    exec ${pyEnv}/bin/python $out/lib/osk/main.py "\$@"
    EOF
    chmod +x $out/bin/osk
  '';
}
