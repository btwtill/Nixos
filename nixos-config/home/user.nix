{
  config, pkgs, ...
}:

{
  home.username = "defaultUser";
  home.homeDirectory = "/home/defaultUser";

  programs.git.enable = true;
  programs.zsh.enable = true;

  xdg.configFile."qtile/config.py".source = ../dotfiles/qtile/config.py;
  xdg.configFile."nvim".source = ../dotfiles/nvim;
  xdg.configFile."zsh/.zshrc".source = ../dotfiles/zsh/.zshrc;

  home.stateVersion = "0326";
}