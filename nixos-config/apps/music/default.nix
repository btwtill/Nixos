{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python313;
  pyEnv  = python.withPackages (ps: [ ps.pyqt6 ]);
  # busctl (MPRIS control of shairport) + wpctl (volume)
  path   = pkgs.lib.makeBinPath [ pkgs.systemd pkgs.wireplumber ];
in
pkgs.stdenv.mkDerivation {
  pname   = "music-app";
  version = "0.2.0";

  src = ./.;

  buildInputs = [ pyEnv ];

  installPhase = ''
    mkdir -p $out/bin $out/lib/music-app
    cp *.py $out/lib/music-app/
    cp ${../common}/airplay.py $out/lib/music-app/

    cat > $out/bin/music-app <<EOF
    #!/bin/sh
    export PATH="${path}:\$PATH"
    exec ${pyEnv}/bin/python $out/lib/music-app/main.py "\$@"
    EOF
    chmod +x $out/bin/music-app
  '';
}
