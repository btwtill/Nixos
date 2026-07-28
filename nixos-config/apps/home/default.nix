{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python313;
  pyEnv  = python.withPackages (ps: [ ps.pyqt6 ]);
in
pkgs.stdenv.mkDerivation {
  pname   = "home-app";
  version = "0.1.0";

  src = ./.;

  # librsvg pre-converts all weather SVGs to PNGs at build time so
  # QPixmap can load them without any Qt SVG plugin at runtime.
  nativeBuildInputs = [ pkgs.librsvg ];
  buildInputs = [ pyEnv ];

  installPhase = ''
    mkdir -p $out/bin $out/lib/home-app

    cp *.py           $out/lib/home-app/
    cp -r widgets     $out/lib/home-app/
    cp -r assets      $out/lib/home-app/

    # Convert weather SVGs → PNGs so QPixmap can load them without a Qt SVG plugin.
    for svg in assets/weather/*.svg; do
      name=$(basename "$svg" .svg)
      out_path="$out/lib/home-app/assets/weather/$name.png"
      if echo "$name" | grep -q "_Mini$"; then
        rsvg-convert -w 32 -h 32 "$svg" -o "$out_path"
      else
        rsvg-convert -w 216 -h 216 "$svg" -o "$out_path"
      fi
    done

    cat > $out/bin/home-app <<EOF
    #!/bin/sh
    exec ${pyEnv}/bin/python $out/lib/home-app/main.py "\$@"
    EOF
    chmod +x $out/bin/home-app
  '';
}
