{
  config, pkgs, ...
}:

{
  home.username = "defaultUser";            # Define Username for default user
  home.homeDirectory = "/home/defaultUser"; # Set default user directory on disk

  programs.git.enable = true;             # enable git usage
  programs.zsh.enable = true;             # enable z shell usage

  xdg.configFile."qtile/config.py".source = ../dotfiles/qtile/config.py;    # create symlink to qtile config
  xdg.configFile."nvim".source = ../dotfiles/nvim;                          # create symlink to neavim config
  xdg.configFile."zsh/.zshrc".source = ../dotfiles/zsh/.zshrc;              # create symlink to zshell config

  home.stateVersion = "0326";             # Set current home version
}