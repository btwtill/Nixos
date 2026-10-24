{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python313;
  # Also the runtime for sideloaded Python apps (`homy-python` in a manifest),
  # so keep the common libraries an app is likely to want in here —
  # including QtWebEngine for web / Rive based apps (see app-store/rive-test).
  pyEnv  = python.withPackages (ps: [ ps.pyqt6 ps.pyqt6-webengine ps.psutil ps.requests ]);
in
pkgs.stdenv.mkDerivation {
  pname   = "homy-launcher";
  version = "0.1.0";

  src = ./.;

  buildInputs = [ pyEnv ];

  installPhase = ''
    mkdir -p $out/bin $out/lib/homy-launcher
    cp *.py $out/lib/homy-launcher/

    cat > $out/bin/homy-launcher <<EOF
    #!/bin/sh
    exec ${pyEnv}/bin/python $out/lib/homy-launcher/main.py "\$@"
    EOF

    cat > $out/bin/homy-apps <<EOF
    #!/bin/sh
    export PATH="${pkgs.git}/bin:\$PATH"
    exec ${pyEnv}/bin/python $out/lib/homy-launcher/homy_apps.py "\$@"
    EOF

    cat > $out/bin/homy-python <<EOF
    #!/bin/sh
    exec ${pyEnv}/bin/python "\$@"
    EOF

    chmod +x $out/bin/*
  '';
}
