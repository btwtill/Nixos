{ pkgs ? import <nixpkgs> {} }:

# homy-theme — colour theme service (see main.py for the API).
# Python standard library only.
pkgs.stdenv.mkDerivation {
  pname   = "homy-theme";
  version = "0.1.0";

  src = ./.;

  installPhase = ''
    mkdir -p $out/bin $out/lib/homy-theme
    cp main.py themes.json $out/lib/homy-theme/

    cat > $out/bin/homy-theme <<EOF
    #!/bin/sh
    exec ${pkgs.python313}/bin/python $out/lib/homy-theme/main.py "\$@"
    EOF
    chmod +x $out/bin/homy-theme
  '';
}
