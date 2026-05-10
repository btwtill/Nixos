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
