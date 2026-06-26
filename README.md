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

Copy the image to the shared folder — run this **on the VM**, treating the symlink as a regular directory path:

```bash
cp <path-to-symlink>/sd-image/*.img <path-to-write-img-file>
```

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

### Debugging After a Rebuild

```bash
# Show all errors from the current boot
journalctl -b -p err

# Show failed systemd services
systemctl --failed

# Follow the live journal (useful right after boot)
journalctl -f

# Inspect a specific failing service
journalctl -b -u <service-name>

# Show last boot's errors (useful if system crashes on boot)
journalctl -b -1 -p err
```

**Qtile / X11 logs:**
```bash
# Qtile log (errors, widget failures, config issues)
cat ~/.local/share/qtile/qtile.log

# Follow Qtile log live
tail -f ~/.local/share/qtile/qtile.log

# X server log (display/driver errors)
cat ~/.local/share/xorg/Xorg.0.log | grep EE

# Picom errors
journalctl -b --user -u picom
```

**Home Assistant / Matter:**
```bash
# Home Assistant service status
systemctl status home-assistant.service

# Home Assistant live logs
journalctl -u home-assistant.service -f

# Matter server container status (podman-backed oci-container)
systemctl status podman-matter-server.service

# Matter server container logs
journalctl -u podman-matter-server.service -f

# Or inspect the container directly via podman
podman ps
podman logs -f matter-server
```

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

#### WiFi Setup (first boot only)

WiFi credentials are not stored in the repo. Connect once after flashing — the connection persists across all future rebuilds, only lost when reflashing.

**Option A — interactive TUI (easiest):**
```bash
nmtui
```
Navigate to "Activate a connection" → select your network → enter password.

**Option B — command line:**
```bash
# List available networks
nmcli device wifi list

# Connect
sudo nmcli device wifi connect "YOUR_SSID" password "YOUR_PASSWORD"
```

Verify it connected:
```bash
nmcli connection show
ip addr
```

#### SSH — Remove stale host key (after reflashing)

Reflashing changes the Pi's host key, causing SSH to refuse the connection. Remove the old entry with:

```bash
ssh-keygen -R <pi-ip>
```