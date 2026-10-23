{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python313;
  pyEnv  = python.withPackages (ps: [ ps.pyqt6 ]);
  # busctl (device list from BlueZ) + bluetoothctl (pair / connect / …)
  path   = pkgs.lib.makeBinPath [ pkgs.systemd pkgs.bluez ];
in
pkgs.stdenv.mkDerivation {
  pname   = "bluetooth-app";
  version = "0.1.0";

  src = ./.;

  buildInputs = [ pyEnv ];

  installPhase = ''
    mkdir -p $out/bin $out/lib/bluetooth-app
    cp *.py $out/lib/bluetooth-app/
    cp ${../common}/ui_kit.py $out/lib/bluetooth-app/

    cat > $out/bin/bluetooth-app <<EOF
    #!/bin/sh
    export PATH="${path}:\$PATH"
    exec ${pyEnv}/bin/python $out/lib/bluetooth-app/main.py "\$@"
    EOF
    chmod +x $out/bin/bluetooth-app
  '';
}
