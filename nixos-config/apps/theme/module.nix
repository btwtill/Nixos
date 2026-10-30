{ pkgs, ... }:

# The theme service as a systemd user service (VM, Pi 5): starts with the
# user session, restarts if it ever exits. Logs: journalctl --user -u homy-theme
let
  homyTheme = pkgs.callPackage ./. {};
in
{
  environment.systemPackages = [ homyTheme ];

  systemd.user.services.homy-theme = {
    description = "Homy colour theme service";
    wantedBy = [ "default.target" ];
    serviceConfig = {
      ExecStart = "${homyTheme}/bin/homy-theme";
      Restart = "on-failure";
      RestartSec = 2;
    };
  };
}
