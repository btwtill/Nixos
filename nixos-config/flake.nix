{
  description = "Nixos Config";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    disko = {
      url = "github:nix-community/disko";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # Raspberry Pi 5 — vendor kernel, firmware, bootloader, SD image.
    # pi5 uses this flake's own nixpkgs (a NixOS release) so the kernel
    # comes from its binary cache instead of being compiled locally.
    nixos-raspberrypi.url = "github:nvmd/nixos-raspberrypi/main";

    # home-manager matching the release nixpkgs pi5 is built on.
    home-manager-pi5 = {
      url = "github:nix-community/home-manager/release-26.05";
      inputs.nixpkgs.follows = "nixos-raspberrypi/nixpkgs";
    };
  };

  # Prebuilt Pi kernels/firmware. Used automatically when the user running
  # `nix build` is trusted (root, or in nix.settings.trusted-users).
  nixConfig = {
    extra-substituters = [ "https://nixos-raspberrypi.cachix.org" ];
    extra-trusted-public-keys = [
      "nixos-raspberrypi.cachix.org-1:4iMO9LXa8BqhU+Rpg6LQKiGa2lsNh/j2oiYLNOQ5sPI="
    ];
  };

  outputs = inputs@{ self, nixpkgs, home-manager, disko, nixos-raspberrypi, home-manager-pi5, ... }:
  let
    mkSystem = { system, hostname, homeConfig, diskoConfig ? null, extraModules ? [] }:
      nixpkgs.lib.nixosSystem {
        inherit system;
        modules = [
          ./hosts/${hostname}/configuration.nix
          disko.nixosModules.disko
          home-manager.nixosModules.home-manager
          {
            home-manager.useGlobalPkgs = true;
            home-manager.users.defaultUser = import homeConfig;
          }
        ]
        ++ (if diskoConfig != null then [ diskoConfig ] else [])
        ++ extraModules;
      };

    # Shared base for all Pi SD images — adds the sd-image module on top of
    # whatever modules are passed in.
    mkPiImage = modules:
      (nixpkgs.lib.nixosSystem {
        system = "aarch64-linux";
        modules = [
          "${nixpkgs}/nixos/modules/installer/sd-card/sd-image-aarch64.nix"
          { sdImage.compressImage = false; }
        ] ++ modules;
      }).config.system.build.sdImage;

    # The full Pi config modules (no disko — SD image handles partitioning).
    piModules = [
      ./hosts/pi/configuration.nix
      home-manager.nixosModules.home-manager
      {
        home-manager.useGlobalPkgs = true;
        home-manager.users.defaultUser = import ./home/pi/user.nix;
      }
    ];

    # Pi 5: built with nixos-raspberrypi's helper (adds kernel, firmware and
    # bootloader). The sd-image module defines the SD-card layout, so the same
    # config is both the flashable image and the `nixos-rebuild` target.
    pi5 = nixos-raspberrypi.lib.nixosSystem {
      specialArgs = inputs;
      modules = [
        nixos-raspberrypi.nixosModules.raspberry-pi-5.base
        nixos-raspberrypi.nixosModules.raspberry-pi-5.display-vc4
        nixos-raspberrypi.nixosModules.raspberry-pi-5.bluetooth
        nixos-raspberrypi.nixosModules.sd-image
        ./hosts/pi5/configuration.nix
        home-manager-pi5.nixosModules.home-manager
        {
          home-manager.useGlobalPkgs = true;
          home-manager.users.defaultUser = import ./home/pi5/user.nix;
        }
      ];
    };

  in {
    nixosConfigurations = {

      laptop = mkSystem {
        system = "x86_64-linux";
        hostname = "laptop";
        homeConfig = ./home/laptop/user.nix;
      };

      vm = mkSystem {
        system = "aarch64-linux";
        hostname = "vm";
        homeConfig = ./home/vm/user.nix;
        diskoConfig = ./hosts/vm/disko.nix;
      };

      # Deploy target — use with: nixos-rebuild switch --flake .#pi
      pi = mkSystem {
        system = "aarch64-linux";
        hostname = "pi";
        homeConfig = ./home/pi/user.nix;
        diskoConfig = ./hosts/pi/disko.nix;
      };

      # Raspberry Pi 5 — on the running Pi: nixos-rebuild switch --flake .#pi5
      inherit pi5;
    };

    # ↓ This is what your nix run command actually reads
    diskoConfigurations = {
      vm = import ./hosts/vm/disko.nix;
      pi = import ./hosts/pi/disko.nix;
    };

    packages.aarch64-linux = {

      # Minimal flash image — SSH + basic boot only, no user config.
      # Build: nix build .#piImageMinimal
      piImageMinimal = mkPiImage [{
        boot.loader.grub.enable = false;
        boot.loader.generic-extlinux-compatible.enable = true;
        networking.hostName = "pi";
        networking.networkmanager.enable = true;
        services.openssh.enable = true;
        users.users.defaultUser = {
          isNormalUser = true;
          extraGroups = [ "wheel" ];
          initialPassword = "password";
        };
        security.sudo.wheelNeedsPassword = false;
        nix.settings.experimental-features = [ "nix-command" "flakes" ];
        system.stateVersion = "25.05";
      }];

      # Full flash image — all config baked in, ready to flash and boot.
      # Build: nix build .#piImageFull
      piImageFull = mkPiImage piModules;

      # Raspberry Pi 5 image — full config baked in, ready to flash and boot.
      # Build (on an aarch64-linux machine, e.g. the VM): nix build .#pi5Image
      pi5Image = pi5.config.system.build.sdImage;

      # Example launcher app, installable per user without a rebuild:
      #   nix profile install .#homy-hello   /   nix profile remove homy-app-hello
      homy-hello = import ./apps/launcher/mk-homy-app.nix {
        pkgs = nixpkgs.legacyPackages.aarch64-linux;
        src  = ./apps/launcher/examples/hello;
      };
    };
  };
}