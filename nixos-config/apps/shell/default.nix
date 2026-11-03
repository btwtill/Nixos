{ pkgs ? import <nixpkgs> {}
, ui ? pkgs.callPackage ../../ui {}      # homy-ui: the .riv files
, hmi ? pkgs.callPackage ../hmi {}       # homy-hmi: Rive's native renderer
}:

# Homy shell — drives homy-hmi (one per surface) and connects it to Qtile and
# the theme service. Plain Python, no Qt. See main.py.
pkgs.stdenv.mkDerivation {
  pname   = "homy-shell";
  version = "0.4.0";

  src = ./.;

  installPhase = ''
    install -Dm644 main.py $out/lib/homy-shell/main.py
    mkdir -p $out/bin
    cat > $out/bin/homy-shell <<EOF
    #!/bin/sh
    export HOMY_UI_DIR="${ui}/share/homy/ui"
    export HOMY_HMI="${hmi}/bin/homy-hmi"
    exec ${pkgs.python3}/bin/python3 $out/lib/homy-shell/main.py "\$@"
    EOF
    chmod +x $out/bin/homy-shell
  '';
}
