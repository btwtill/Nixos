{ modulesPath, config, pkgs, lib, ... }:

{
  imports = [
    (modulesPath + "/profiles/qemu-guest.nix")
  ];

  nixpkgs.overlays = [
    (final: prev: {
      qtile-unwrapped = prev.qtile-unwrapped.overrideAttrs (_: {
        doCheck = false;
      });
    })
  ];

  # Bootloader
  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;

  # Host
  networking.hostName = "vm";
  networking.networkmanager.enable = true;
  time.timeZone = "Europe/Berlin";

  i18n.defaultLocale = "en_US.UTF-8";

  console = {
    font = "Lat2-Terminus16";
    useXkbConfig = true;
  };

  services.displayManager.autoLogin.enable = true;
  services.displayManager.autoLogin.user = "defaultUser";

  # Enable X11 + Qtile
  services.xserver.enable = true;
  services.xserver.xkb.layout = "de";

  services.xserver.windowManager.qtile.enable = true;

  services.getty.autologinUser = "defaultUser";

  # SPICE guest agent — enables clipboard sharing with the UTM host
  services.spice-vdagentd.enable = true;

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
  # AirPlay receiver — lets iPhone stream Apple Music to VM
  # Name visible on iPhone: "VM Music"
  # Metadata pipe: /tmp/shairport-sync-metadata
  # -------------------------------------------------------
  services.shairport-sync = {
    enable = true;
    openFirewall = true;
    arguments = "-o pipewire --name 'VM Music'";
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
    wants = [ "pipewire.service" "pipewire-pulse.service" "user@1000.service" ];
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

  # Basic packages for Qtile usability
  environment.systemPackages = with pkgs; [
    python313Packages.qtile
    alacritty
    chromium
    picom
    rofi
    nitrogen
    mousepad
    librsvg
    git
    neovim
    (pkgs.callPackage ../../apps/music {})
    (pkgs.callPackage ../../apps/home {})
    (pkgs.callPackage ../../apps/lights {})
    (pkgs.callPackage ../../apps/bluetooth {})
    (pkgs.callPackage ../../apps/wifi {})
    (pkgs.callPackage ../../apps/osk {})
    (pkgs.callPackage ../../apps/launcher {})
    (pkgs.callPackage ../../apps/rive-test {})   # Rive web-runtime prototype (app menu)
    xsetroot
    (pkgs.callPackage ../../apps/screenshot {})
    (pkgs.callPackage ../../apps/system {
      hostLabel = "UTM VM";
      extraServices = [
        { unit = "spice-vdagentd.service"; label = "SPICE agent"; }
      ];
    })
  ];

  programs.thunar.enable = true;

  # Launcher apps declared in Nix put a manifest under share/homy/apps;
  # link that into /run/current-system/sw so the app menu finds them.
  environment.pathsToLink = [ "/share/homy" ];

  # -------------------------------------------------------
  # Home Assistant
  # Access at http://localhost:8123 (from within the VM)
  # or http://<vm-ip>:8123 from the Mac browser.
  # Complete the onboarding wizard on first boot to create
  # your admin account — all further config via the UI.
  # The "demo" component auto-loads a set of fake lights,
  # switches, sensors, climate, media_player, etc. on boot —
  # no UI step needed — so apps can be developed against the
  # real REST + WebSocket API without physical hardware.
  # -------------------------------------------------------
  services.home-assistant = {
    enable = true;
    openFirewall = true;

    extraComponents = [
      # Required to complete the onboarding flow
      "analytics"
      "google_translate"
      "met"
      "radio_browser"
      "shopping_list"
      # Fast zlib compression (recommended by wiki)
      "isal"
      # Matter support for your smart devices
      "matter"
      # Fake lights/switches/sensors/etc. for developing against
      # the real REST + WebSocket API without physical hardware.
      "demo"
    ];

    config = {
      # default_config pulls in all base dependencies automatically —
      # no need to manually specify numpy, turbojpeg, hassil etc.
      default_config = {};
      demo = {};
    };
  };

  # -------------------------------------------------------
  # Matter Server
  # Bridges HA to your Matter smart devices over local
  # WiFi/Thread. HA connects to it at ws://localhost:5580.
  # After rebuild: HA → Settings → Devices → Add Integration
  # → Matter (BETA) → point it at ws://localhost:5580
  # -------------------------------------------------------
  virtualisation.podman = {
    enable      = true;
    dockerCompat = true;
  };

  virtualisation.oci-containers = {
    backend = "podman";
    containers.matter-server = {
      image     = "ghcr.io/home-assistant-libs/python-matter-server:stable";
      autoStart = true;
      volumes   = [ "/var/lib/matter-server:/data" ];
      extraOptions = [
        "--network=host"   # required for mDNS / Matter device discovery
        "--privileged"     # required for Matter commissioning
      ];
    };
  };

  systemd.tmpfiles.rules = [
    "d /var/lib/matter-server 0750 root root -"
    "f ${config.services.home-assistant.configDir}/automations.yaml 0644 hass hass"
  ];

  # User
  users.users.defaultUser = {
    isNormalUser = true;
    extraGroups  = [ "wheel" "networkmanager" ];   # networkmanager: Wi-Fi app may manage connections
    initialPassword = "password";
  };

  # Enable sudo
  security.sudo.wheelNeedsPassword = false;

  # Shared folder from UTM host via VirtFS (virtio-9p).
  # In UTM settings → Sharing → set mode to VirtFS and pick a Mac folder.
  # The folder appears at /mnt/mac inside the VM.
  fileSystems."/mnt/mac" = {
    device  = "share";
    fsType  = "9p";
    options = [ "trans=virtio" "version=9p2000.L" "nofail" "_netdev" ];
  };

  # SSH (optional but useful)
  services.openssh.enable = true;

  nix.settings.experimental-features = [ "nix-command" "flakes" ];

  # Binary cache for Raspberry Pi 5 kernels/firmware — lets the VM build
  # .#pi5Image without compiling the Pi kernel. Set at system level because
  # flake nixConfig is ignored for non-trusted users.
  nix.settings.extra-substituters = [ "https://nixos-raspberrypi.cachix.org" ];
  nix.settings.extra-trusted-public-keys = [
    "nixos-raspberrypi.cachix.org-1:4iMO9LXa8BqhU+Rpg6LQKiGa2lsNh/j2oiYLNOQ5sPI="
  ];

  system.stateVersion = "25.05";
}
