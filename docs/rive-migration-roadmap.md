# Rive Migration Roadmap

Goal: replace the static PNG/SVG assets and the PyQt6 apps with one
fullscreen UI built from **Rive** scenes, backed by a Python service that owns
all logic and data.

Rive assets will arrive **step by step**. Every component ships first as a
**placeholder** and is swapped for the final design later without code changes.

Order of work: **migrate everything on the UTM VM first (placeholders for all
current functionality, Nix builds) → bring up the Pi 5 and measure when the
hardware is available → move the house from the Pi 3B+ to the Pi 5.**

Performance is measured only on real hardware (Pi 5). VM numbers are not
representative and are not used for decisions.

---

## Supported targets

| Target | Flake host | Role | How the UI runs | Status |
|---|---|---|---|---|
| UTM VM (aarch64) | `vm` | Development — full migration happens here first | Flutter Linux desktop build | **Supported** |
| Raspberry Pi 5 | `pi5` (new) | The device | flutter-pi (no X11) | **Supported** (once hardware is available) |
| Raspberry Pi 3B+ | `pi` | Current live device | Current PyQt apps | **Deprecated — frozen** |
| Mac (optional) | – | Fast design iteration | Flutter macOS build | Convenience only |

The VM already runs Home Assistant, the Matter server, AirPlay and the current
apps, so it is a full copy of the Pi setup and can host the whole migration.

### Screen resolutions

| Target | Resolution | Notes |
|---|---|---|
| Pi 5 display | **1024 × 600** | Reference size for all design work. **To be confirmed** on the real panel. |
| VM | larger / taller than the target | Cannot be set to exactly 1024 × 600 reliably. |

How both are handled:
- **Rive artboards use Rive Layouts** (responsive, flex-style) and are loaded with
  the layout fit, so each component adapts to the space it gets instead of
  being drawn for one fixed size.
- **Screens are composed at a reference size of 1024 × 600** in `homy-ui`.
  Component sizes in the contracts are given at that reference size.
- **In the VM, `homy-ui` runs in two modes**, chosen by a Nix setting:
  - `window` — a fixed 1024 × 600 window: shows exactly what the Pi 5 will show.
  - `fullscreen` — fills the VM screen: tests that layouts adapt to other sizes.
- If the confirmed Pi 5 resolution differs, only the reference size and the
  Nix setting change; the Rive files adapt.

### Pi 3B+ deprecation
- The `pi` host keeps running the current setup unchanged until the Pi 5 takes over (phase 6).
- No new features, no Rive work. Only fixes needed to keep the house running.
- After the move, the `pi` host is removed from the flake (it stays in git history).

---

## Target architecture

```
┌─────────────────────────── VM / Pi 5 ────────────────────────┐
│  Home Assistant ◄──WebSocket (push)──► homy-core (Python)     │
│                                        • one HA client        │
│                                        • lights layout/scenes │
│                                        • local WebSocket API  │
│                                               ▲               │
│                                               │ state / cmds  │
│                                               ▼               │
│                          homy-ui (one fullscreen app)         │
│                          • navigation (replaces Qtile groups) │
│                          • screens built from Rive artboards  │
│                          • fallback widget if .riv missing    │
└───────────────────────────────────────────────────────────────┘
```

- **homy-core** is the only thing that talks to Home Assistant and the only thing that writes data.
- **homy-ui** only renders state and sends commands.
- **.riv files** are the look. Code talks to them only through a documented
  **contract** (View Model properties + triggers/events).

### Decision: components in Rive, screens in Flutter
- Each component (LightIcon, LightToggle, BrightnessRing, …) is its own Rive artboard.
- `homy-ui` arranges the components into screens (top panel, side panel, main area).
- Screen-wide motion (side panel sliding in, page transitions) is done in Flutter;
  motion *inside* a component is done in Rive.
- Considered and rejected for now: whole screens as single Rive artboards with
  nested components — more designer control, but harder to grasp and to replace
  step by step.

---

## Phase overview

| # | Phase | Where | Result |
|---|---|---|---|
| 0 | VM foundation: toolchain & Nix builds | VM | Flutter + Rive build and run in the VM from the flake |
| 1 | Extract `homy-core` | VM | Data and HA logic in one service |
| 2 | Rive contracts & full placeholder set | VM (+ Mac) | Every component has a contract and a placeholder |
| 3 | `homy-ui` shell | VM | App with navigation, loader, overlay, runs as a session |
| 4 | Screen migration | VM | Home → Music → Lights with full current functionality |
| 5 | Pi 5 bring-up & performance | Pi 5 | `pi5` host, flutter-pi build, benchmark, fixes |
| 6 | Move house to Pi 5 | Pi 3B+ → Pi 5 | Pi 5 runs the home, Pi 3B+ retired |
| 7 | Final Rive art | continuous | Placeholders replaced one by one |
| 8 | Later features | – | SQLite store, HA scene mirror, secrets |

- Phases 1 and 2 can run in parallel.
- Phase 7 runs continuously from phase 2 onward.
- Phase 5 starts when the Pi 5 is available; by then the VM should be at phase 4.

---

## Phase 0 — VM foundation: toolchain & Nix builds

Everything needed to build and run the new UI from the flake.

### 0.1 Repo layout
- [ ] Agree on folders:
  ```
  nixos-config/
    services/homy-core/     # Python service (phase 1)
    modules/                # shared NixOS modules (homy-core, homy-ui)
  ui/
    app/                    # Flutter app (homy-ui)
    rive/
      contracts/            # contracts (phase 2)
      placeholders/         # placeholder .riv files
      final/                # final .riv files
  ```

### 0.2 Flutter + Rive in the VM
- [ ] Dev shell in `flake.nix` with Flutter and the Linux desktop build tools (`nix develop`).
- [ ] Check UTM display settings (`virtio-gpu-gl` if available) so Flutter can render; software rendering is fine for development.
- [ ] Spike: minimal Flutter app that loads one `.riv` (any Rive community file), binds one property and receives one event. Confirms the Rive runtime works in the VM.
- [ ] Spike includes one artboard built with **Rive Layouts**, shown in a 1024 × 600 window and then resized, to confirm it adapts.

### 0.3 Nix build
- [ ] Nix package for `homy-ui` (Linux desktop) using nixpkgs `buildFlutterApplication`, with a lockfile for Dart dependencies.
- [ ] `.riv` files from `ui/rive/` copied into the package.
- [ ] `nix build .#homy-ui` works; the `vm` host can install it.
- [ ] Keep the old apps installed on `vm` so both can be compared side by side.

### 0.4 Test data in the VM
- [ ] Give the VM's Home Assistant fake devices to work against, e.g. the **Demo** integration or template lights/weather/media player, so every screen has data without real hardware.

**Done when:** the spike app builds with `nix build` and shows a Rive file in the VM.

---

## Phase 1 — Extract `homy-core`

Does not depend on Rive.

- [ ] Create `nixos-config/services/homy-core/` (Python package).
- [ ] Merge the two copies of `ha_client.py` (`apps/home`, `apps/lights`) into one.
- [ ] Switch from polling to the Home Assistant **WebSocket API** (push updates).
- [ ] Move persistence out of the lights app:
  - [ ] lights layout (today `~/.local/share/lights-app/layout.json`)
  - [ ] scenes (today `~/.local/share/lights-app/scenes.json`)
  - [ ] new location: `/var/lib/homy/`, **atomic writes** (temp file → rename), `version` field
  - [ ] import the old files on first start (so the Pi 3B+ files can be copied over in phase 6)
  - [ ] reference lights by `entity_id`, not by name
- [ ] Local WebSocket API:
  - [ ] on connect: full snapshot (lights, layout, scenes, weather, media)
  - [ ] afterwards: change events only
  - [ ] commands: `light.set`, `light.place`, `scene.create`, `scene.update`, `scene.apply`, `scene.delete`
  - [ ] document the messages in `services/homy-core/API.md`
- [ ] Media state: take over what `apps/music` reads today (shairport-sync metadata pipe) and expose it over the API.
- [ ] Read the HA token from one place (`/var/lib/homy/secrets.json`).
- [ ] NixOS module (`modules/homy-core.nix`) + systemd service, enabled on `vm`.

**Done when:** `homy-core` runs on the VM and serves live HA and media state over its API.

---

## Phase 2 — Rive contracts & full placeholder set

Rive art is not finished yet, so every component first gets a **contract**
and a **placeholder**. The code is built against the contract; final art drops in later.

### 2.1 Conventions
- [ ] Loading order: `final/` → `placeholders/` → code-drawn **fallback widget**
      (grey box + label). A missing asset never crashes the app.
- [ ] Naming: artboards `PascalCase`, View Model properties `camelCase`,
      triggers/events prefixed `on` (e.g. `onTap`).
- [ ] One artboard per component, one View Model per artboard.
- [ ] Every artboard uses **Rive Layouts** so it adapts to its given size; the
      contract states the size at the 1024 × 600 reference plus a minimum size.

### 2.2 Contract template

```
Component:   LightToggle
Artboard:    LightToggle
Size:        88 × 48 at 1024 × 600 reference (min 66 × 36)
View Model:  LightToggleVM
  isOn        bool     (code → Rive)
  isDisabled  bool     (code → Rive)
Events:
  onToggle             (Rive → code)
Notes:       knob slides, glow fades in when isOn
```

### 2.3 Component inventory

Covers all current functionality, derived from the current PNG/SVG assets.

| Component | Used on | Replaces | Contract | Placeholder | Final |
|---|---|---|---|---|---|
| NavBar + NavButton | all | `qtile/icons/*_Button*.svg` | [ ] | [ ] | [ ] |
| WeatherIcon (`condition` enum, `size` default/mini) | Home | `weather/Dark_*` (30 PNGs) | [ ] | [ ] | [ ] |
| WeatherAttribute | Home | `weather/Attribute=*` | [ ] | [ ] | [ ] |
| LinearSlider | Home, Music | `sliders/*`, `VolumeSlider*` | [ ] | [ ] | [ ] |
| ArcSlider / BrightnessRing | Home, Lights | code-drawn ring | [ ] | [ ] | [ ] |
| MediaControls (play/back/forward) | Home, Music | `music/*_Button*` | [ ] | [ ] | [ ] |
| FloorplanButton | Home | `floorplanbutton_dark_*` | [ ] | [ ] | [ ] |
| Floorplan (background) | Home, Lights | `Floorplan_dark_small.png`, `floorplan.png` | [ ] | [ ] | [ ] |
| LightIcon (`isOn`, `isSelected`, `isMain`, `color`) | Lights | `Default_*`, `Selected_*` | [ ] | [ ] | [ ] |
| LightToggle | Lights | `LightToggle_*` | [ ] | [ ] | [ ] |
| ColorWheel + Picker | Lights | `ColorPicker.png`, `Picker.png` | [ ] | [ ] | [ ] |
| LightSidePanel (background + open/close) | Lights | `LightsSidePanelBackground.png` | [ ] | [ ] | [ ] |
| LightListItem | Lights | `LightListItemBackdrop.png` | [ ] | [ ] | [ ] |
| IconButton (add/remove/select all/settings) | Lights | `AddLight_*`, `RemoveLight_*`, `SelectAllLights_*`, `LightSettings_*` | [ ] | [ ] | [ ] |
| SceneTile + AddSceneTile | Lights | code-drawn tiles, `AddNewLightsScene_*` | [ ] | [ ] | [ ] |
| QuickPreset | Lights | `QuickPreset.png` | [ ] | [ ] | [ ] |
| Pager | Lights | `PagerPerl*` | [ ] | [ ] | [ ] |

### 2.4 Tasks
- [ ] Write a contract for every component above.
- [ ] Build placeholder `.riv` files in the Rive editor: plain shapes and text, **exact** names from the contract, a visible change for every property (e.g. colour flip for `isOn`).
- [ ] Code-drawn fallback widget for components without any `.riv` yet — this lets code work start before a placeholder exists.
- [ ] Contract check: a test loads every `.riv` and fails if a property or event from its contract is missing. Run it as part of `nix flake check`.
- [ ] Short designer guide: how to replace a placeholder (keep names, export to `final/`, run the check).

**Done when:** every component has a contract and a placeholder (or at least a fallback), and the check passes.

---

## Phase 3 — `homy-ui` shell (VM)

- [ ] Grow the phase 0 spike into `ui/app/`.
- [ ] `RiveComponent` wrapper: loads final → placeholder → fallback, binds View Model properties, forwards events.
- [ ] WebSocket client for `homy-core` with auto-reconnect and an "offline" state.
- [ ] Navigation with the NavBar (replaces Qtile groups 1/2/4 and the SVG bar).
- [ ] **Component page**: hidden debug screen listing every component with controls for its properties and a log of events — lets the designer check placeholders and final art.
- [ ] Small frame-time overlay (fps, median / p95 frame time), off by default. Not used for decisions in the VM, but ready for the Pi 5.
- [ ] Screens composed at the 1024 × 600 reference size and scaled to the actual window.
- [ ] Per-host settings from Nix: `homy-core` address, display mode (`window` / `fullscreen`), reference size (default 1024 × 600).
- [ ] NixOS module (`modules/homy-ui.nix`); on `vm`, a switch to start `homy-ui` instead of the old apps.

**Done when:** the shell with navigation, the component page and all placeholders runs on the VM from the flake.

---

## Phase 4 — Screen migration (VM)

One screen at a time, with placeholders or final art.

### 4.1 Home
- [ ] Weather (current + forecast)
- [ ] Brightness / other sliders
- [ ] Media controls + volume
- [ ] Floorplan button → opens Lights

### 4.2 Music
- [ ] Now playing (title, artist, cover)
- [ ] Play/pause, back, forward
- [ ] Volume

### 4.3 Lights (largest — split into steps)
- [ ] Floorplan with light icons (position from `homy-core`)
- [ ] Select / multi-select / select all
- [ ] Place, move, add, remove lights
- [ ] Side panel: toggle, brightness ring, colour wheel
- [ ] Scenes page: grid, create, apply, delete, quick access
- [ ] Pager + swipe between pages

**Parity checklist per screen:** everything the current PyQt app can do works,
live updates from Home Assistant, touch/mouse handling as good as before,
looks right in the 1024 × 600 window **and** in fullscreen on the VM.

**Done when:** the VM runs only `homy-ui` + `homy-core` with all current functionality; the old apps are no longer started on `vm`.

---

## Phase 5 — Pi 5 bring-up & performance

Starts when the Pi 5 is available.

### 5.1 Pi 5 host
NixOS on the Pi 5 needs a community flake (e.g. `nixos-raspberrypi`) for kernel and bootloader.
- [ ] Add the Pi 5 input to `flake.nix`.
- [ ] Create `hosts/pi5/` and `home/pi5/` from the `vm` config (it already has `homy-core` + `homy-ui`), plus the hardware parts from `pi` (boot, firmware, Wi-Fi/Bluetooth).
- [ ] Add a Pi 5 SD image build.
- [ ] Flash and check: boot, Wi-Fi, Bluetooth, audio, AirPlay, HA + Matter, display + touch.
- [ ] Confirm the real display resolution; update the reference size if it is not 1024 × 600.
- [ ] Add `pi5` rows to the README quick reference.
- [ ] Run as a **test device** with its own fresh HA — the Pi 3B+ keeps running the house.

### 5.2 flutter-pi build
- [ ] Nix package for `homy-ui` with **flutter-pi** (packaging may need to be written).
- [ ] Kiosk session: boots straight into `homy-ui`, no X11.
- [ ] Check which Rive renderer is used (the Pi 5 GPU supports OpenGL ES 3.1 / Vulkan).

### 5.3 Monitoring
- [ ] `modules/monitoring.nix`: `htop`, `btop`, `smem`, `vcgencmd`.
- [ ] Home Assistant **System Monitor** integration (RAM, CPU, load, temperature with history).
- [ ] README cheat sheet: `systemd-cgtop`, `smem -tk`, `podman stats`, `vcgencmd measure_temp`, `vcgencmd get_throttled`.

### 5.4 Benchmark
Procedure (profile build, never debug):
1. System booted, Home Assistant + Matter running, idle 2 min.
2. Busy scripted sequence on the Lights screen (all lights animating) for 60 s.
3. Record the values below. Measure while animating — an idle Rive screen correctly draws 0 fps.

| Metric | Pi 5 |
|---|---|
| Renderer used | |
| Median frame time (ms) | |
| p95 frame time (ms) | |
| Dropped frames / 60 s | |
| UI RAM (`smem` PSS) | |
| Free RAM with HA running | |
| CPU load | |
| Max temperature / throttled? | |
| Start time to first frame | |

- [ ] Fix or simplify components that are too expensive; note it in their contracts.
- [ ] Check cooling: if the Pi 5 throttles, add the active cooler / case fan.

**Done when:** the Pi 5 runs the full app from the flake with acceptable numbers.

---

## Phase 6 — Move the house to the Pi 5

The Pi 3B+ holds the live Home Assistant and Matter setup. Moving it must not lose devices or history.

- [ ] Back up the Pi 3B+ first:
  - [ ] Home Assistant config and database (`/var/lib/hass`)
  - [ ] Matter server data (`/var/lib/matter-server`) — **contains the Matter fabric**; without it every Matter device must be re-paired
  - [ ] lights layout and scenes (`~/.local/share/lights-app/*.json`)
  - [ ] HA token / secrets
- [ ] Stop HA + Matter on the Pi 3B+, restore the data on the Pi 5, start services.
- [ ] Check: all lights respond, automations run, scenes and layout imported by `homy-core`.
- [ ] Keep the Pi 3B+ SD card untouched for a few weeks as a fallback.
- [ ] Rollback on the Pi 5: boot the previous NixOS generation.
- [ ] After a stable week: remove the `pi` host, `piImageMinimal`/`piImageFull` and the PyQt apps (`apps/`) from the flake.

**Done when:** the Pi 5 runs the house and the Pi 3B+ is switched off.

---

## Phase 7 — Final Rive art (continuous)

Runs from phase 2 onward. For each component in the inventory:
1. Designer builds the final version against its contract.
2. Export to `ui/rive/final/<component>.riv`.
3. Run the contract check.
4. Check it on the component page in the VM (and on the Pi 5 once available).
5. Tick **Final** in the inventory table.

Priority suggestion: NavBar → LightIcon → LightToggle → BrightnessRing → WeatherIcon → the rest.

---

## Phase 8 — Later features

- [ ] Move storage from JSON files to SQLite (`/var/lib/homy/homy.db`) with a schema version.
- [ ] Mirror scenes into Home Assistant scenes (use them from the HA app, automations, voice).
- [ ] Mark lights that disappear from HA as `orphaned` instead of deleting them.
- [ ] Manage the HA token with sops-nix or agenix.
- [ ] Bring the `laptop` host up to date.
- [ ] Optional: reuse the Pi 3B+ (e.g. as a second, lighter display).

---

## Open questions

- Does Flutter render acceptably for development in UTM (hardware GL or software)? (phase 0)
- Is the Pi 5 NixOS community flake stable enough for daily use? (phase 5)
- Is the Pi 5 display really 1024 × 600? Working assumption until confirmed; layouts adapt either way.
- Lists that change length (lights, scenes): one Rive instance per item placed
  by code, or Rive list data binding? (phase 2)
- Who owns the contracts: design or code? Suggest: both review every change.
