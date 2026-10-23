{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python313;
  pyEnv  = python.withPackages (ps: [ ps.pyqt6 ]);
  # busctl (MPRIS control of shairport) + wpctl (volume)
  path   = pkgs.lib.makeBinPath [ pkgs.systemd pkgs.wireplumber ];
in
pkgs.stdenv.mkDerivation {
  pname   = "home-app";
  version = "0.1.0";

  src = ./.;

  buildInputs = [ pyEnv ];

  installPhase = ''
    mkdir -p $out/bin $out/lib/home-app

    cp *.py           $out/lib/home-app/
    cp -r widgets     $out/lib/home-app/
    cp -r assets      $out/lib/home-app/
    cp ${../common}/airplay.py $out/lib/home-app/

    cat > $out/bin/home-app <<EOF
    #!/bin/sh
    export PATH="${path}:\$PATH"
    exec ${pyEnv}/bin/python $out/lib/home-app/main.py "\$@"
    EOF
    chmod +x $out/bin/home-app
  '';
}
