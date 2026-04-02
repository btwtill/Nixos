{
  description = "Nixos Config";           # Pure metadata - only general setup name

  inputs = {                                              # The components nixos will have to pull and make available for any system you want to build
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";  # Package directoy containing the nixos package univers (all packages you would want and more) and especially the sysetm packages

    home-manager = {                                      # A system that handles user configs declaratively
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";                 # Makes sure the home-manager system uses the same package managing version then the nixpkgs
    };

    disko = {                                             # Add the components that are needed to partition a target system disk
      url = "github:nix-community/disko";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, home-manager, ... }:         # Funktion that takes the system inputs and creates declared systems 
  let 
    # function to create different
    mkSystem = { system, hostname, extraModules ? [ ] }:
      nixpkgs.lib.nixosSystem {
        inherit system;

        modules = [
          ./hosts/${hostname}/configuration.nix

          # Home Manager (shared)
          home-manager.nixosModules.home-manager
          {
            home-manager.useGlobalPkgs = true;
            home-manager.users.yourusername =
              import ./home/user.nix;
          }
        ] ++ extraModules;
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
      };
    };

    diskoConfigurations = {
      vm = import ./hosts/VM/disko.nix;
    };
  };
}