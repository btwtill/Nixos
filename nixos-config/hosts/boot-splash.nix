{ pkgs, lib, ... }:

# A quiet boot: no kernel/systemd text, a splash graphic (apps/boot-splash)
# from early in the boot until the desktop starts.
{
  boot.plymouth = {
    enable = true;
    theme = "homy";
    themePackages = [ (pkgs.callPackage ../apps/boot-splash {}) ];
  };

  # Only errors reach the screen (nixos-raspberrypi sets 7: everything).
  boot.consoleLogLevel = lib.mkForce 3;
  boot.initrd.verbose = false;
  boot.kernelParams = [
    "quiet"
    "logo.nologo"                      # no Raspberry logos at the top
    "vt.global_cursor_default=0"       # no blinking text cursor
    "udev.log_level=3" "rd.udev.log_level=3"
    "systemd.show_status=auto" "rd.systemd.show_status=auto"   # service list only if something fails
    "plymouth.ignore-serial-consoles"  # the Pi's console=serial0 would otherwise keep the splash off the screen
  ];
}
