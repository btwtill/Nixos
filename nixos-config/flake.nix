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
  };

  outputs = { self, nixpkgs, home-manager, disko, ... }:
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
    };
  };
}