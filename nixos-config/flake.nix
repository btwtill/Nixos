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

  # ↓ disko explicitly destructured
  outputs = { self, nixpkgs, home-manager, disko, ... }:
  let
    mkSystem = { system, hostname, diskoConfig ? null, extraModules ? [] }:
      nixpkgs.lib.nixosSystem {
        inherit system;

        modules = [
          ./hosts/${hostname}/configuration.nix

          disko.nixosModules.disko

          home-manager.nixosModules.home-manager
          {
            home-manager.useGlobalPkgs = true;
            home-manager.users.defaultUser = import ./home/user.nix;
          }
        ]
        # ↓ Only add the disko config module if one was provided for this host
        ++ (if diskoConfig != null then [ diskoConfig ] else [])
        ++ extraModules;
      };
  in {
    nixosConfigurations = {

      laptop = mkSystem {
        system = "x86_64-linux";
        hostname = "laptop";
      };

      vm = mkSystem {
        system = "aarch64-linux";
        hostname = "vm";
        diskoConfig = ./hosts/vm/disko.nix;
      };

      pi = mkSystem {
        system = "aarch64-linux";
        hostname = "pi";
        diskoConfig = ./hosts/pi/disko.nix;
      };
    };

    # ↓ This is what your nix run command actually reads
    diskoConfigurations = {
      vm = import ./hosts/vm/disko.nix;
      pi = import ./hosts/pi/disko.nix;
    };

    packages.aarch64-linux.piImage =
      (nixpkgs.lib.nixosSystem {
        system = "aarch64-linux";
        modules = [
          "${nixpkgs}/nixos/modules/installer/sd-card/sd-image-aarch64.nix"
          {
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
            sdImage.compressImage = false;
            system.stateVersion = "25.05";
          }
        ];
      }).config.system.build.sdImage;
  };
}