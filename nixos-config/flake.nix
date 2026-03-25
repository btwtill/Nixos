{
  description = "Nixos Config";           # Pure metadata - only general setup name

  inputs = {                                              # The components nixos will have to pull and make available for any system you want to build
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";  # Package directoy containing the nixos package univers (all packages you would want and more) and especially the sysetm packages

    home-manager = {                                      # A sysetm that handles user configs declaratively
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs"                  # Makes sure the home-manager system uses the same package managing version then the nixpkgs
    };
  };

  outputs = { self, nixpkgs, home-manager, ... }:         # Funktion that takes the sysetm inputs and creates declared systems 
  let 
      system = "x86_64-linux";                            # States that the target host will be a x86 architecture
  in {
    nixosConfigurations.laptop = nixpkgs.lib.nixosSystem {  # Give the system a name -> important for the nix building command to specify what sysetm you want to build
      inherit system;

      modules = [                                         # This is the part where the home manager builds together the whole user configuration based on your files and config structure setups
        ./hosts/laptop/configuration.nix

        home-manager.nixosModules.home-manager
        {
          home-manager.useGlobalPkgs = true;              # Allow packages to be reused and no duplicates
          home-manager.useUserPkgs = true;                # Allows the home manager to install packages

          home-manager.users.defaultUser = import ./home/user.nix     # Sets up the dotconfig fiels
        }
      ]
    }
  }

}