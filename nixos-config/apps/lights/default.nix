{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python313;
  pyEnv  = python.withPackages (ps: [ ps.pyqt6 ]);
in
pkgs.stdenv.mkDerivation {
  pname   = "lights-app";
  version = "0.1.0";

  src = ./.;

  buildInputs = [ pyEnv ];

  installPhase = ''
    mkdir -p $out/bin $out/lib/lights-app

    cp *.py $out/lib/lights-app/

    cat > $out/bin/lights-app <<EOF
    #!/bin/sh
    exec ${pyEnv}/bin/python $out/lib/lights-app/main.py "\$@"
    EOF
    chmod +x $out/bin/lights-app
  '';
}
