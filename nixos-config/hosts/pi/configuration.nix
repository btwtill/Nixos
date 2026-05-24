{ config, pkgs, ... }:

{
  nixpkgs.overlays = [
    (final: prev: {
      qtile-unwrapped = prev.qtile-unwrapped.overrideAttrs (_: {
        doCheck = false;
      });
    })
  ];

  # Pi 3B+ boot — no EFI, uses extlinux via U-Boot
  boot.loader.grub.enable = false;
  boot.loader.generic-extlinux-compatible.enable = true;
  boot.tmp.cleanOnBoot = true;

  services.displayManager.autoLogin.enable = true;
  services.displayManager.autoLogin.user = "defaultUser";

  services.xserver.displayManager.setupCommands = ''
    xrandr --output HDMI-1 --mode 1024x600
    unclutter -idle 0 -root &
  '';

  # Broadcom WiFi/BT firmware — without this WiFi dies after rebuild
  hardware.enableRedistributableFirmware = true;

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
    rofi
    unclutter
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
  # Access at http://<pi-ip>:8123
  # Complete the onboarding wizard on first boot.
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
  # HA connects to it at ws://localhost:5580.
  # After rebuild: HA → Settings → Devices → Add Integration
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
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
  };

  # User
  users.users.defaultUser = {
    isNormalUser = true;
    extraGroups  = [ "wheel" ];
    initialPassword = "password";
  };

  security.sudo.wheelNeedsPassword = false;

  services.openssh.enable = true;

  nix.settings.experimental-features = [ "nix-command" "flakes" ];
  nix.settings.require-sigs = false;

  system.stateVersion = "25.05";
}
