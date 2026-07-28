{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python313;
  pyEnv  = python.withPackages (ps: [ ps.pyqt6 ]);
in
pkgs.stdenv.mkDerivation {
  pname   = "home-app";
  version = "0.1.0";

  src = ./.;

  # wrapQtAppsHook auto-sets QT_PLUGIN_PATH so Qt discovers the SVG image
  # plugin at runtime, allowing QPixmap to load .svg files without any
  # extra Python imports.
  nativeBuildInputs = [ pkgs.qt6.wrapQtAppsHook ];
  buildInputs = [ pyEnv pkgs.qt6.qtsvg ];

  installPhase = ''
    mkdir -p $out/bin $out/lib/home-app

    cp *.py           $out/lib/home-app/
    cp -r widgets     $out/lib/home-app/
    cp -r assets      $out/lib/home-app/

    cat > $out/bin/home-app <<EOF
    #!/bin/sh
    exec ${pyEnv}/bin/python $out/lib/home-app/main.py "\$@"
    EOF
    chmod +x $out/bin/home-app
  '';
}
