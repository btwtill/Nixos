{ ... }:

{
  disko.devices = {
    disk.main = {
      type = "disk";
      device = "/dev/vda";

      content = {
        type = "gpt";

        partitions = {

          ESP = {
            size = "512M";
            type = "EF00";
            priority = 1;          # ← ensure ESP is created first

            content = {
              type = "filesystem";
              format = "vfat";
              mountpoint = "/boot";
              mountOptions = [ "umask=0077" ];  # ← recommended for EFI security
            };
          };

          swap = {
            size = "2G";
            priority = 2;          # ← created second

            content = {
              type = "swap";
              discardPolicy = "both";  # ← good practice for VM swap
            };
          };

          root = {
            size = "100%";
            priority = 3;          # ← fills remaining space last

            content = {
              type = "filesystem";
              format = "ext4";
              mountpoint = "/";
            };
          };

        };
      };
    };
  };
}