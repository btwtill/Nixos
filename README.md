# NixOS Network

## The beginning of a home journey and automation

---

## Quick Reference

### Rebuild & Deploy

| Target | Command |
|---|---|
| VM / running system | `sudo nixos-rebuild switch --flake .#vm` |
| Pi (on running Pi) | `sudo nixos-rebuild switch --flake .#pi` |
| Pi 5 (on running Pi 5) | `sudo nixos-rebuild switch --flake .#pi5` |
| Laptop | `sudo nixos-rebuild switch --flake .#laptop` |

### Pi SD Images

| Image | Command |
|---|---|
| Minimal (SSH only) | `nix build .#piImageMinimal` |
| Full config baked in | `nix build .#piImageFull` |
| Custom output path | `nix build .#piImageFull --out-link /path/to/link` |
| Print store path, no symlink | `nix build .#piImageFull --no-link --print-out-paths` |

Image file is at: `<result>/sd-image/*.img`

### Pi 5 SD Image

Build on an aarch64-linux machine — the VM. The VM config adds the
`nixos-raspberrypi` binary cache, so the Pi kernel is downloaded, not compiled
(rebuild the VM once after pulling this change).

```bash
# On the VM, in the flake folder
nix build .#pi5Image
cp result/sd-image/nixos-image-rpi5-kernel.img /mnt/mac/
```

Flash it with the macOS steps below, put the card in the Pi 5 and power on.
First boot grows the root partition to fill the card. Log in as `defaultUser` /
`password` (SSH: `ssh defaultUser@pi5.local`), then later updates go through
`sudo nixos-rebuild switch --flake .#pi5` on the Pi itself.

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

### Screenshots

`screenshot` is installed on vm, pi and pi5 (`nixos-config/apps/screenshot`).
It captures the whole screen and uses `DISPLAY=:0` by default, so it also
works over SSH.

```bash
# Save to ~/Pictures/screenshots/<date>_<time>.png (prints the path)
screenshot

# Save to a specific file
screenshot ~/Desktop/home-screen.png

# Write PNG to stdout (e.g. pipe it somewhere)
screenshot - > shot.png
```

Copy screenshots to the Mac (run on the Mac):

```bash
# Take a screenshot on the Pi 5 and save it straight to the Mac
ssh defaultUser@pi5.local screenshot - > pi5.png

# All saved screenshots
scp 'defaultUser@pi5.local:~/Pictures/screenshots/*.png' .
```

On the VM you can also save straight into the shared folder:
`screenshot /mnt/mac/screenshot.png`.

### App Menu & Installing Apps

The top menu button opens the app menu (group 9). Every app started there gets
its own view; the menu button brings you back. Apps can be added **without a
system rebuild** — each app is a folder with a `manifest.json`
(format: `nixos-config/apps/launcher/registry.py`). Ready-made apps live in
`nixos-config/app-store/` — nothing there is installed until you install it:

| App | What it is |
|---|---|
| `hello` | Minimal example — copy it to start a new app |
| `rive-test` | Rive prototype: plays a `.riv` (from `~/rive/`) with Rive's web runtime in QtWebEngine or Chromium, with FPS/GPU overlay |

```bash
# Sideload a folder or git repo (Python apps use "homy-python" in "exec")
homy-apps install ~/Nixos/nixos-config/app-store/hello
homy-apps install ~/Nixos/nixos-config/app-store/rive-test
homy-apps install https://github.com/<you>/<app>.git
homy-apps list
homy-apps remove hello

# Or as a Nix package in your user profile (survives rebuilds, can roll back)
nix profile install ~/Nixos/nixos-config#homy-hello
nix profile remove homy-app-hello
```

New apps show up in the menu within a few seconds.

Apps you're not looking at are **paused** (frozen, no CPU/GPU) and resume when
you switch back. An app that must keep working in the background (e.g. audio)
sets `"background": true` in its `manifest.json`.

### Rive Sidebar

The right-hand navigation is `homy-sidebar` (`nixos-config/apps/sidebar`): the
`SideBar` artboard of the Rive file **Neo_Button**, played with Rive's web runtime.
Qtile pins its window over the right bar (the old buttons underneath are the
fallback if it isn't running). Tapping a button switches the Qtile group; when
the group changes any other way, the matching button lights up.

Design → device:

```bash
# on the Mac: pull the latest from the Rive editor, build, copy into the repo
nixos-config/apps/sidebar/update-riv.sh --pull
git commit -am "sidebar: new design" && git push
# on the VM / Pi 5: pull, rebuild, reboot
```

To see its output, restart it by hand from a terminal on the device:
`pkill -f homy-sidebar; DISPLAY=:0 homy-sidebar`. Qtile logs where it pinned
the window: `grep homy ~/.local/share/qtile/qtile.log`.

### On-screen Keyboard

`osk` runs as a background service (started by Qtile's autostart) and types
into whatever text field has focus. Apps call it when a field needs typing —
the Wi-Fi app does this for passwords.

```bash
osk show      # show the keyboard (starts the service if needed)
osk hide
osk toggle
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