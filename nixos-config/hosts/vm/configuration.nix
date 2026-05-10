{ modulesPath, config, pkgs, ... }:

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

  # Enable X11 + Qtile
  services.xserver.enable = true;
  services.xserver.xkb.layout = "de";

  services.xserver.windowManager.qtile.enable = true;

  services.getty.autologinUser = "defaultUser";

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
  ];

  programs.thunar.enable = true;

  # -------------------------------------------------------
  # Home Assistant
  # Accessible at http://localhost:8123 after first boot.
  # Complete the onboarding wizard there to create your
  # admin account and connect your Matter devices.
  # -------------------------------------------------------
  services.home-assistant = {
    enable      = true;
    openFirewall = true;         # opens TCP 8123

    # Minimal declarative config — everything else is
    # configured through the HA web UI and stored in
    # /var/lib/hass (outside the Nix store, writable).
    config = {
      homeassistant = {
        name        = "Home";
        unit_system = "metric";
        time_zone   = "Europe/Berlin";
        currency    = "EUR";
        country     = "DE";
      };
      http     = {};   # web UI + REST API on port 8123
      api      = {};   # enables /api/* endpoints for our apps
      frontend = {};   # Lovelace dashboard

      # Disable all analytics / telemetry — no data leaves the network
      analytics = {};
    };

    # Extra HA integrations that need Python packages baked in.
    # matter  — connects to python-matter-server for Matter devices
    # light   — light entity platform
    # climate — thermostat entity platform
    extraPackages = python3Packages: with python3Packages; [
      numpy       # required — used by many core integrations
      pillow      # required — image handling in frontend
      sqlalchemy  # required — recorder / history database
      aiosqlite   # required — async SQLite access
      turbojpeg   # required by ai_task component (2026.x+)
    ];

    extraComponents = [
      "ai_task"       # loaded by default in 2026.x — needs turbojpeg
      "conversation"  # always loaded by HA — must be here so hassil is bundled
      "recorder"      # history DB — pulls in sqlalchemy/aiosqlite
      "history"
      "logbook"
      "matter"
      "light"
      "climate"
      "sensor"
      "switch"
      "automation"
      "script"
    ];
  };

  # -------------------------------------------------------
  # Matter Server
  # Bridges Home Assistant to Matter smart devices (lights,
  # thermostats etc.) over WiFi/Thread via WebSocket on
  # port 5580.  HA connects to it at ws://localhost:5580.
  # -------------------------------------------------------
  virtualisation.podman = {
    enable       = true;
    dockerCompat = true;   # lets you use `docker` CLI if needed
  };

  virtualisation.oci-containers = {
    backend = "podman";
    containers.matter-server = {
      image     = "ghcr.io/home-assistant-libs/python-matter-server:stable";
      autoStart = true;
      volumes   = [ "/var/lib/matter-server:/data" ];
      # host networking is required for mDNS / Matter device discovery
      extraOptions = [
        "--network=host"
        "--privileged"
      ];
    };
  };

  # Ensure the Matter server data directory exists before the container starts
  systemd.tmpfiles.rules = [
    "d /var/lib/matter-server 0750 root root -"
  ];

  # User
  users.users.defaultUser = {
    isNormalUser = true;
    extraGroups  = [ "wheel" ];
    initialPassword = "password";
  };

  # Enable sudo
  security.sudo.wheelNeedsPassword = false;

  # Block Home Assistant's outbound update-check calls.
  # Uncomment once HA is confirmed working — the xt_owner kernel module
  # must be available (it is on real hardware, may be absent in the VM).
  # networking.firewall.extraCommands = ''
  #   iptables -A OUTPUT -m owner --uid-owner hass -d version.home-assistant.io -j DROP
  #   iptables -A OUTPUT -m owner --uid-owner hass -d analytics.home-assistant.io -j DROP
  # '';

  # SSH (optional but useful)
  services.openssh.enable = true;

  system.stateVersion = "25.05";
}
