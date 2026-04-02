{ config, pkgs, ... }:

{
  imports = [
    <nixpkgs/nixos/modules/profiles/qemu-guest.nix>
  ];

  # Bootloader
  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;

  # Host
  networking.hostName = "vm";
  time.timeZone = "Europe/Berlin";

  # Enable X11 + Qtile
  services.xserver.enable = true;

  services.xserver.displayManager.startx.enable = true;

  services.xserver.windowManager.qtile.enable = true;

  # Basic packages for Qtile usability
  environment.systemPackages = with pkgs; [
    xterm
    dmenu
    git
    neovim
  ];

  # User
  users.users.yourusername = {
    isNormalUser = true;
    extraGroups = [ "wheel" ];
    initialPassword = "password";
  };

  # Enable sudo
  security.sudo.wheelNeedsPassword = false;

  # SSH (optional but useful)
  services.openssh.enable = true;

  system.stateVersion = "0426";
}