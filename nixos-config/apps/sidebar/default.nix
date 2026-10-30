{ pkgs ? import <nixpkgs> {}
, ui ? pkgs.callPackage ../../ui {}    # homy-ui: the .riv files + Rive web runtime
}:

# Homy sidebar — Qtile's right-hand navigation, drawn by Rive (ui/riv/sidebar.riv).
let
  pyEnv = pkgs.python313.withPackages (ps: [ ps.pyqt6 ps.pyqt6-webengine ]);
in
pkgs.stdenv.mkDerivation {
  pname   = "homy-sidebar";
  version = "0.2.0";

  src = ./.;

  buildInputs = [ pyEnv ];

  installPhase = ''
    lib=$out/lib/homy-sidebar
    mkdir -p $out/bin $lib/web
    cp main.py $lib/
    cp web/index.html $lib/web/
    cp ${../common}/webengine.py $lib/

    cat > $out/bin/homy-sidebar <<EOF
    #!/bin/sh
    export HOMY_UI_DIR="${ui}/share/homy/ui"
    exec ${pyEnv}/bin/python $lib/main.py "\$@"
    EOF
    chmod +x $out/bin/homy-sidebar
  '';
}
