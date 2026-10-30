{ pkgs ? import <nixpkgs> {}
, ui ? pkgs.callPackage ../../ui {}    # homy-ui: the .riv files + Rive web runtime
}:

# Homy shell — the Rive-drawn desktop surfaces (sidebar, wallpaper, later the
# bars) in one process sharing one Chromium. See main.py.
let
  pyEnv = pkgs.python313.withPackages (ps: [ ps.pyqt6 ps.pyqt6-webengine ]);
in
pkgs.stdenv.mkDerivation {
  pname   = "homy-shell";
  version = "0.3.0";

  src = ./.;

  buildInputs = [ pyEnv ];

  installPhase = ''
    lib=$out/lib/homy-shell
    mkdir -p $out/bin $lib/web
    cp main.py $lib/
    cp web/*.html web/*.js $lib/web/
    cp ${../common}/webengine.py $lib/

    cat > $out/bin/homy-shell <<EOF
    #!/bin/sh
    export HOMY_UI_DIR="${ui}/share/homy/ui"
    exec ${pyEnv}/bin/python $lib/main.py "\$@"
    EOF
    chmod +x $out/bin/homy-shell
  '';
}
