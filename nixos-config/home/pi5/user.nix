{ config, pkgs, ... }:

{
  home.username = "defaultUser";
  home.homeDirectory = "/home/defaultUser";

  programs.git.enable = true;
  programs.zsh.enable = true;

  xdg.configFile."qtile".source = ../../dotfiles/qtile;
  xdg.configFile."picom".source = ../../dotfiles/picom/pi;   # same compositor settings as the Pi 3B+

  home.file."wallpapers/background.jpg".source =
    ../../dotfiles/wallpapers/background.png;

  home.stateVersion = "26.05";
}
