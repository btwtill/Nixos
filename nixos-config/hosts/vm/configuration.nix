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

  # SPICE guest agent — enables clipboard sharing with the UTM host
  services.spice-vdagentd.enable = true;

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
  # Access at http://localhost:8123 (from within the VM)
  # or http://<vm-ip>:8123 from the Mac browser.
  # Complete the onboarding wizard on first boot to create
  # your admin account — all further config via the UI.
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
    ];

    config = {
      # default_config pulls in all base dependencies automatically —
      # no need to manually specify numpy, turbojpeg, hassil etc.
      default_config = {};
    };
  };

  # Prevent HA from failing on first boot because automations.yaml
  # doesn't exist yet (created empty, HA populates it via the UI)
  systemd.tmpfiles.rules = [
    "f ${config.services.home-assistant.configDir}/automations.yaml 0644 hass hass"
  ];

  # User
  users.users.defaultUser = {
    isNormalUser = true;
    extraGroups  = [ "wheel" ];
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

  system.stateVersion = "25.05";
}
