{
  config, pkgs, ...
}:

{
  services.xserver.enable = true;
  services.xserver.windowManager.qtile.enable = true;

  environment.systemPackages = with pkgs; [
    git
    neovim
    zsh
    python313Packages.qtile
  ];

  users.users.defaultUser = {
    isNormalUser = true;
    extraGroups = [ "wheel" ];
  };
}