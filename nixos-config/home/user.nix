{
  config, pkgs, ...
}:

{
  home.username = "defaultUser";            # Define Username for default user
  home.homeDirectory = "/home/defaultUser"; # Set default user directory on disk

  programs.git.enable = true;             # enable git usage
  programs.zsh.enable = true;             # enable z shell usage

  xdg.configFile."qtile".source = ../dotfiles/qtile;    # create symlink to qtile config
  xdg.configFile."picom".source = ../dotfiles/picom;    # create symlink to picom config

  home.file."wallpapers/background.jpg".source =
    ../dotfiles/wallpapers/background.png;
  # xdg.configFile."nvim".source = ../dotfiles/nvim;                          # create symlink to neavim config
  # xdg.configFile."zsh/.zshrc".source = ../dotfiles/zsh/.zshrc;              # create symlink to zshell config

  home.stateVersion = "25.05";             # Set current home version
}