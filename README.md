# NixOS Network

## The beginning of a home journey and automation

---

## Quick Reference

### Rebuild & Deploy

| Target | Command |
|---|---|
| VM / running system | `sudo nixos-rebuild switch --flake .#vm` |
| Pi (on running Pi) | `sudo nixos-rebuild switch --flake .#pi` |
| Laptop | `sudo nixos-rebuild switch --flake .#laptop` |

### Pi SD Images

| Image | Command |
|---|---|
| Minimal (SSH only) | `nix build .#piImageMinimal` |
| Full config baked in | `nix build .#piImageFull` |
| Custom output path | `nix build .#piImageFull --out-link /path/to/link` |
| Print store path, no symlink | `nix build .#piImageFull --no-link --print-out-paths` |

Image file is at: `<result>/sd-image/*.img`

### Flashing (macOS)

```bash
# Find your SD card
diskutil list

# Unmount it (replace diskN with your disk number)
diskutil unmountDisk /dev/diskN

# Flash
sudo dd if=/path/to/nixos-image.img of=/dev/rdiskN bs=4m status=progress
```

Note the `r` prefix in `/dev/rdiskN` — raw device is significantly faster on macOS.

### Maintenance

```bash
# Garbage collect old generations
nix-collect-garbage -d

# Garbage collect with sudo (clears system generations too)
sudo nix-collect-garbage -d

# Check disk usage of the Nix store
nix path-info --all | wc -l
du -sh /nix/store
```

### Nix Store

```bash
# Find what's in the store for a specific build
nix path-info .#piImageFull

# Inspect a flake's outputs
nix flake show

# Update all flake inputs
nix flake update
```

---

## Installation

### VM

#### Partitioning

- Create your VM with the correct ISO image attached
- Load DE keys

```bash
sudo loadkeys de
```

- Switch to root

```bash
sudo -i
```

- Clone the repo

```bash
cd /tmp
git clone https://github.com/btwtill/Nixos
```

- Partition the disk with disko

```bash
sudo nix --experimental-features "nix-command flakes" run github:nix-community/disko -- --mode destroy,format,mount ./Nixos/nixos-config/hosts/vm/disko.nix
```

#### NixOS Install

- Create tmp directory for install

```bash
mkdir -p /mnt/tmp
```

- Install the flake config

```bash
TMPDIR=/mnt/tmp nixos-install --flake /tmp/Nixos/nixos-config#vm
```

### Pi

Flash a pre-built image (see Pi SD Images above) — no manual partitioning needed.

Default credentials after first boot:
- User: `defaultUser`
- Password: `password`
- SSH enabled on port 22