{ modulesPath, config, pkgs, ... }:

{
  nixpkgs.overlays = [
    (final: prev: {
      qtile-unwrapped = prev.qtile-unwrapped.overrideAttrs (_: {
        doCheck = false;
      });
    })
  ];

  # Pi 4 boot — no EFI, uses extlinux via U-Boot
  boot.loader.grub.enable = false;
  boot.loader.generic-extlinux-compatible.enable = true;

  # Host
  networking.hostName = "pi";
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

  # Basic packages
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
    ffmpeg
  ];

  programs.thunar.enable = true;

  # -------------------------------------------------------
  # Home Assistant
  # -------------------------------------------------------
  services.home-assistant = {
    enable       = true;
    openFirewall  = true;

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

  systemd.tmpfiles.rules = [
    "d /var/lib/matter-server 0750 root root -"
    "f ${config.services.home-assistant.configDir}/automations.yaml 0644 hass hass"
  ];

  # -------------------------------------------------------
  # Matter Server
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

  # User
  users.users.defaultUser = {
    isNormalUser = true;
    extraGroups  = [ "wheel" ];
    initialPassword = "password";
  };

  security.sudo.wheelNeedsPassword = false;

  services.openssh.enable = true;

  system.stateVersion = "25.05";
}
