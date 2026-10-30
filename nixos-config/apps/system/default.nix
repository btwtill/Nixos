{ pkgs ? import <nixpkgs> {}
# Shown in the app header so it's obvious which machine you're looking at.
, hostLabel ? "unknown host"
# Host-specific systemd units appended to the shared list below.
# Each entry: { unit = "foo.service"; label = "Foo"; user = false; }
# user = true checks the unit with `systemctl --user` (e.g. PipeWire).
, extraServices ? []
# Our own PyQt apps — detected by their /lib/<name>/main.py command line.
, apps ? [ "home-app" "lights-app" "music-app" "bluetooth-app" "wifi-app" "osk" "homy-launcher" "homy-sidebar" "homy-theme" ]
}:

let
  python = pkgs.python313;
  pyEnv  = python.withPackages (ps: [ ps.pyqt6 ps.psutil ]);

  # Units every host runs (see hosts/*/configuration.nix).
  commonServices = [
    { unit = "home-assistant.service";       label = "Home Assistant"; }
    { unit = "podman-matter-server.service"; label = "Matter Server"; }
    { unit = "shairport-sync.service";       label = "AirPlay (shairport)"; }
    { unit = "avahi-daemon.service";         label = "Avahi (mDNS)"; }
    { unit = "NetworkManager.service";       label = "NetworkManager"; }
    { unit = "sshd.service";                 label = "SSH"; }
    { unit = "display-manager.service";      label = "Display Manager"; }
    { unit = "pipewire.service";             label = "PipeWire";    user = true; }
    { unit = "homy-theme.service";           label = "Theme service"; user = true; }
    { unit = "wireplumber.service";          label = "WirePlumber"; user = true; }
  ];

  hostConfig = pkgs.writeText "system-app-host.json" (builtins.toJSON {
    inherit hostLabel apps;
    services = commonServices ++ extraServices;
  });
in
pkgs.stdenv.mkDerivation {
  pname   = "system-app";
  version = "0.1.0";

  src = ./.;

  buildInputs = [ pyEnv ];

  installPhase = ''
    mkdir -p $out/bin $out/lib/system-app

    cp *.py       $out/lib/system-app/
    cp -r widgets $out/lib/system-app/
    cp ${hostConfig} $out/lib/system-app/host.json

    cat > $out/bin/system-app <<EOF
    #!/bin/sh
    exec ${pyEnv}/bin/python $out/lib/system-app/main.py "\$@"
    EOF
    chmod +x $out/bin/system-app
  '';
}
