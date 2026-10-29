{ config, pkgs, lib, ... }:

# Raspberry Pi 5 — same setup as the Pi 3B+ (Qtile + PyQt apps, HA, Matter,
# AirPlay, Bluetooth). Kernel, firmware, bootloader and the SD-card layout
# come from the nixos-raspberrypi modules imported in flake.nix, so there is
# no extlinux, no Broadcom firmware hack and no disko config here.

{
  nixpkgs.overlays = [
    (final: prev: {
      qtile-unwrapped = prev.qtile-unwrapped.overrideAttrs (_: {
        doCheck = false;
      });
    })
  ];

  # Pi 5 boot — firmware loads the kernel directly; keeps one boot entry per
  # NixOS generation (recommended for new Pi 5 installs).
  boot.loader.raspberry-pi.bootloader = "kernel";
  boot.tmp.cleanOnBoot = true;

  # The image modules enable ZFS; not used here — smaller image, no warning.
  boot.supportedFilesystems.zfs = lib.mkForce false;

  # Flash the .img directly, no .zst to unpack first.
  sdImage.compressImage = false;

  hardware.enableRedistributableFirmware = true;
  hardware.bluetooth.enable = true;
  hardware.bluetooth.powerOnBoot = true;

  services.displayManager.autoLogin.enable = true;
  services.displayManager.autoLogin.user = "defaultUser";

  # Host
  networking.hostName = "pi5";
  networking.networkmanager.enable = true;
  time.timeZone = "Europe/Berlin";

  i18n.defaultLocale = "en_US.UTF-8";

  console = {
    font        = "Lat2-Terminus16";
    useXkbConfig = true;
  };

  # Enable X11 + Qtile
  services.xserver.enable = true;
  services.xserver.xkb.layout = "de";
  services.xserver.windowManager.qtile.enable = true;

  services.getty.autologinUser = "defaultUser";

  # The Pi 5 has no 3.5 mm jack — audio goes out over HDMI or a USB/I2S DAC.
  services.pipewire = {
    enable = true;
    alsa.enable = true;
    pulse.enable = true;
  };

  # Required for shairport-sync mDNS advertisement (AirPlay discovery)
  services.avahi = {
    enable = true;
    nssmdns4 = true;
    publish = {
      enable = true;
      addresses = true;
      workstation = true;
    };
  };

  # -------------------------------------------------------
  # AirPlay receiver — lets iPhone stream Apple Music to Pi 5
  # Name visible on iPhone: "Pi5 Music"
  # Metadata pipe: /tmp/shairport-sync-metadata
  # -------------------------------------------------------
  services.shairport-sync = {
    enable = true;
    openFirewall = true;
    arguments = "-o pipewire --name 'Pi5 Music'";
    settings = {
      metadata = {
        enabled = "yes";
        include_cover_art = "yes";
        pipe_name = "/tmp/shairport-sync-metadata";
        pipe_timeout = 5000;
      };
      # MPRIS on the session bus, where the music and home apps look for it
      # (play/pause/skip, now-playing + cover for any number of apps).
      general = {
        mpris_service_bus = "session";
        dbus_service_bus  = "session";
      };
    };
  };

  # Run as defaultUser so it can reach the PipeWire session socket
  systemd.services.shairport-sync = {
    # pipewire.service is a user unit, so ordering on it does nothing here;
    # user@1000 is what provides the session bus and PipeWire socket.
    after = [ "pipewire.service" "pipewire-pulse.service" "network-online.target" "user@1000.service" ];
    wants = [ "pipewire.service" "pipewire-pulse.service" "network-online.target" "user@1000.service" ];
    serviceConfig = {
      User = lib.mkForce "defaultUser";
      Group = lib.mkForce "users";
    };
    environment = {
      PIPEWIRE_RUNTIME_DIR    = "/run/user/1000";
      DBUS_SESSION_BUS_ADDRESS = "unix:path=/run/user/1000/bus";
    };
  };

  fonts.packages = with pkgs; [
    inter
  ];

  # Basic packages
  environment.systemPackages = with pkgs; [
    python313Packages.qtile
    alacritty
    rofi
    unclutter-xfixes   # hides the cursor on touch (see autostart.sh)
    feh
    mousepad
    librsvg
    git
    neovim
    ffmpeg
    (pkgs.callPackage ../../apps/music {})
    (pkgs.callPackage ../../apps/screenshot {})
    (pkgs.callPackage ../../apps/home {})
    (pkgs.callPackage ../../apps/lights {})
    (pkgs.callPackage ../../apps/bluetooth {})
    (pkgs.callPackage ../../apps/wifi {})
    (pkgs.callPackage ../../apps/osk {})
    (pkgs.callPackage ../../apps/launcher {})
    (pkgs.callPackage ../../apps/sidebar {})   # Rive navigation sidebar (right edge)
    chromium   # for web/Rive apps from the app store (e.g. app-store/rive-test)
    xsetroot
    (pkgs.callPackage ../../apps/system {
      hostLabel = "Raspberry Pi 5";
      extraServices = [
        { unit = "bluetooth.service"; label = "Bluetooth"; }
      ];
    })
  ];

  programs.thunar.enable = true;

  # Launcher apps declared in Nix put a manifest under share/homy/apps;
  # link that into /run/current-system/sw so the app menu finds them.
  environment.pathsToLink = [ "/share/homy" ];

  # -------------------------------------------------------
  # Home Assistant
  # Access at http://<pi5-ip>:8123
  # Complete the onboarding wizard on first boot.
  # Runs as a test instance — the Pi 3B+ keeps running the house.
  # -------------------------------------------------------
  services.home-assistant = {
    enable = true;

    extraComponents = [
      "analytics"
      "google_translate"
      "met"
      "radio_browser"
      "shopping_list"
      "isal"
      "matter"
    ];

    config = {
      default_config = {};
    };
  };

  # services.home-assistant.openFirewall no longer works (the port isn't
  # known at eval time), so open the default frontend port directly.
  networking.firewall.allowedTCPPorts = [ 8123 ];

  systemd.tmpfiles.rules = [
    "d /var/lib/matter-server 0750 root root -"
    "f ${config.services.home-assistant.configDir}/automations.yaml 0644 hass hass"
  ];

  # -------------------------------------------------------
  # Matter Server
  # HA connects to it at ws://localhost:5580.
  # After first boot: HA → Settings → Devices → Add Integration
  # → Matter (BETA) → point it at ws://localhost:5580
  # -------------------------------------------------------
  virtualisation.podman = {
    enable       = true;
    dockerCompat  = true;
  };

  virtualisation.oci-containers = {
    backend = "podman";
    containers.matter-server = {
      image     = "ghcr.io/home-assistant-libs/python-matter-server:stable";
      autoStart = true;
      volumes   = [ "/var/lib/matter-server:/data" ];
      extraOptions = [
        "--network=host"
        "--privileged"
      ];
    };
  };

  systemd.services.podman-matter-server = {
    after  = [ "network-online.target" "nss-lookup.target" ];
    wants  = [ "network-online.target" ];
    serviceConfig.RestartSec = "30s";
  };

  # User
  users.users.defaultUser = {
    isNormalUser = true;
    extraGroups  = [ "wheel" "networkmanager" ];   # networkmanager: Wi-Fi app may manage connections
    initialPassword = "password";
  };

  security.sudo.wheelNeedsPassword = false;

  services.openssh.enable = true;

  nix.settings.experimental-features = [ "nix-command" "flakes" ];
  nix.settings.require-sigs = false;

  system.stateVersion = "26.05";
}
