{ config, pkgs, lib, ... }:

{
  nixpkgs.overlays = [
    (final: prev: {
      qtile-unwrapped = prev.qtile-unwrapped.overrideAttrs (_: {
        doCheck = false;
      });
    })
  ];

  # Pi 3B+ boot — no EFI, uses extlinux via U-Boot
  boot.loader.grub.enable = false;
  boot.loader.generic-extlinux-compatible.enable = true;
  boot.tmp.cleanOnBoot = true;

  services.displayManager.autoLogin.enable = true;
  services.displayManager.autoLogin.user = "defaultUser";

  services.xserver.displayManager.setupCommands = ''
    xrandr --output HDMI-1 --mode 1024x600
    unclutter -idle 0 -root &
  '';

  # Broadcom WiFi/BT firmware — without this WiFi dies after rebuild
  hardware.enableRedistributableFirmware = true;
  hardware.bluetooth.enable = true;
  hardware.bluetooth.powerOnBoot = true;

  # Host
  networking.hostName = "pi";
  networking.networkmanager.enable = true;
  time.timeZone = "Europe/Berlin";

  i18n.defaultLocale = "en_US.UTF-8";

  console = {
    font        = "Lat2-Terminus16";
    useXkbConfig = true;
  };

  # Enable X11 + Qtile
  services.xserver.enable = true;
  services.xserver.xkb.layout = "de";
  services.xserver.windowManager.qtile.enable = true;

  services.getty.autologinUser = "defaultUser";

  services.pipewire = {
    enable = true;
    alsa.enable = true;
    pulse.enable = true;
  };

  # Required for shairport-sync mDNS advertisement (AirPlay discovery)
  services.avahi = {
    enable = true;
    nssmdns4 = true;
    publish = {
      enable = true;
      addresses = true;
      workstation = true;
    };
  };

  # -------------------------------------------------------
  # AirPlay receiver — lets iPhone stream Apple Music to Pi
  # Name visible on iPhone: "Pi Music"
  # Metadata pipe: /tmp/shairport-sync-metadata
  # -------------------------------------------------------
  services.shairport-sync = {
    enable = true;
    openFirewall = true;
    arguments = "-o pipewire --name 'Pi Music'";
    settings = {
      metadata = {
        enabled = "yes";
        include_cover_art = "yes";
        pipe_name = "/tmp/shairport-sync-metadata";
        pipe_timeout = 5000;
      };
    };
  };

  # Run as defaultUser so it can reach the PipeWire session socket
  systemd.services.shairport-sync = {
    after = [ "pipewire.service" "pipewire-pulse.service" "network-online.target" ];
    wants = [ "pipewire.service" "pipewire-pulse.service" ];
    serviceConfig = {
      User = lib.mkForce "defaultUser";
      Group = lib.mkForce "users";
    };
    environment = {
      PIPEWIRE_RUNTIME_DIR    = "/run/user/1000";
      DBUS_SESSION_BUS_ADDRESS = "unix:path=/run/user/1000/bus";
    };
  };

  # Basic packages
  environment.systemPackages = with pkgs; [
    python313Packages.qtile
    alacritty
    rofi
    unclutter
    nitrogen
    mousepad
    librsvg
    git
    neovim
    ffmpeg
    (pkgs.callPackage ../../apps/music {})
    (pkgs.callPackage ../../apps/screenshot {})
  ];

  programs.thunar.enable = true;

  # -------------------------------------------------------
  # Home Assistant
  # Access at http://<pi-ip>:8123
  # Complete the onboarding wizard on first boot.
  # -------------------------------------------------------
  services.home-assistant = {
    enable       = true;
    openFirewall  = true;

    extraComponents = [
      "analytics"
      "google_translate"
      "met"
      "radio_browser"
      "shopping_list"
      "isal"
      "matter"
    ];

    config = {
      default_config = {};
    };
  };

  systemd.tmpfiles.rules = [
    "d /var/lib/matter-server 0750 root root -"
    "f ${config.services.home-assistant.configDir}/automations.yaml 0644 hass hass"
  ];

  # -------------------------------------------------------
  # Matter Server
  # HA connects to it at ws://localhost:5580.
  # After rebuild: HA → Settings → Devices → Add Integration
  # → Matter (BETA) → point it at ws://localhost:5580
  # -------------------------------------------------------
  virtualisation.podman = {
    enable       = true;
    dockerCompat  = true;
  };

  virtualisation.oci-containers = {
    backend = "podman";
    containers.matter-server = {
      image     = "ghcr.io/home-assistant-libs/python-matter-server:stable";
      autoStart = true;
      volumes   = [ "/var/lib/matter-server:/data" ];
      extraOptions = [
        "--network=host"
        "--privileged"
      ];
    };
  };

  systemd.services.podman-matter-server = {
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
  };

  # -------------------------------------------------------
  # WiFi credentials from USB stick
  # Label a USB stick "WIFI-CFG" and put a wifi.json on it:
  # { "ssid": "YourNetwork", "password": "yourpassword" }
  # -------------------------------------------------------
  systemd.services.wifi-from-usb = {
    description = "Configure WiFi credentials from USB stick";
    after = [ "NetworkManager.service" ];
    before = [ "network-online.target" ];
    wantedBy = [ "network-online.target" ];
    serviceConfig.Type = "oneshot";
    serviceConfig.RemainAfterExit = true;
    path = [ pkgs.jq pkgs.util-linux pkgs.networkmanager ];
    script = ''
      MOUNT=/mnt/wifi-cfg
      DEVICE=$(blkid -L "WIFI-CFG" 2>/dev/null)

      if [ -z "$DEVICE" ]; then
        echo "No WIFI-CFG USB stick found, skipping"
        exit 0
      fi

      mkdir -p "$MOUNT"
      mount -o ro "$DEVICE" "$MOUNT"

      SSID=$(jq -r '.ssid' "$MOUNT/wifi.json")
      PASS=$(jq -r '.password' "$MOUNT/wifi.json")

      umount "$MOUNT"

      if ! nmcli connection show "$SSID" &>/dev/null; then
        nmcli connection add \
          type wifi \
          ssid "$SSID" \
          wifi-sec.key-mgmt wpa-psk \
          wifi-sec.psk "$PASS" \
          connection.autoconnect yes
      fi

      nmcli connection up "$SSID" || true
    '';
  };

  # User
  users.users.defaultUser = {
    isNormalUser = true;
    extraGroups  = [ "wheel" ];
    initialPassword = "password";
  };

  security.sudo.wheelNeedsPassword = false;

  services.openssh.enable = true;

  nix.settings.experimental-features = [ "nix-command" "flakes" ];
  nix.settings.require-sigs = false;

  system.stateVersion = "25.05";
}
