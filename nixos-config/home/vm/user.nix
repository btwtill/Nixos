{ config, pkgs, ... }:

{
  home.username = "defaultUser";
  home.homeDirectory = "/home/defaultUser";

  programs.git.enable = true;
  programs.zsh.enable = true;

  xdg.configFile."qtile".source = ../../dotfiles/qtile;
  xdg.configFile."picom".source = ../../dotfiles/picom/vm;

  programs.alacritty = {
    enable = true;
    settings = {
      colors.primary.background = "#1e1e1e";
    };
  };

  home.file."wallpapers/background.jpg".source =
    ../../dotfiles/wallpapers/background.png;

  home.stateVersion = "25.05";
}
