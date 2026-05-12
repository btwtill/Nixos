{ ... }:

{
  disko.devices = {
    disk.main = {
      type   = "disk";
      device = "/dev/mmcblk0";   # SD card on Pi 4

      content = {
        type = "gpt";

        partitions = {

          boot = {
            size     = "512M";
            type     = "EF00";   # FAT32 — Pi firmware reads this
            priority = 1;

            content = {
              type       = "filesystem";
              format     = "vfat";
              mountpoint = "/boot";
            };
          };

          root = {
            size     = "100%";
            priority = 2;

            content = {
              type       = "filesystem";
              format     = "ext4";
              mountpoint = "/";
            };
          };

        };
      };
    };
  };
}
