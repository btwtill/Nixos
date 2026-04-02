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
            home-manager.users.yourusername = import ./home/user.nix;
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
        diskoConfig = ./hosts/vm/disko.nix;  # ← wired into nixosSystem for mounts
      };
    };

    # ↓ This is what your nix run command actually reads
    diskoConfigurations = {
      vm = import ./hosts/vm/disko.nix;
    };
  };
}