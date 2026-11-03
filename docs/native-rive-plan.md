# Native Rive HMI (branch `native-rive`)

Goal: the UI is drawn by Rive's native C++ runtime on OpenGL ES — no browser
engine. `main` stays deployable on the Pi 5 (icons without feathers) until this
branch works there.

## Why not QtWebEngine / Chromium

Measured on the Pi 5 (X11, Qtile), 2026-11-01:

| Setup | WebGL2 | On screen |
|---|---|---|
| QtWebEngine, default (desktop OpenGL 3.1) | refused: "ES3 is blocklisted/disabled/unsupported by driver" | yes — Rive falls back to canvas: no feathers, no button bodies |
| QtWebEngine, ANGLE on OpenGL ES 3.1 | yes (`V3D 7.1.10.2, OpenGL ES 3.1`) | nothing — also with CPU compositing, Qt on GLX, without picom |
| Mesa GL version override 4.3 / 3.3 | – | nothing |
| real Chromium window | ANGLE: "Could not create a backing OpenGL context" | nothing |

Rive's WebGL2 renderer is the only web renderer that draws feathers and blend
modes, which the designs rely on. Rive Test only looked fine with its sample
file (no feathers). Chromium also cost four to five processes and hundreds of MB.

## Target architecture: one HMI

```
homy-design/…/hmi.riv            ONE Rive file = the whole HMI: every component
  HMI artboard (screen size)       (IconButton, SideBar, bars, screens …) defined
    nested: SideBar, TopBar, …      once, composed with nested artboards; one
  global Theme view model           global Theme; one view model = the contract
  HMIInterface view model           between UI and backend

homy-hmi (C++, apps/hmi)         plays it: rive-runtime + OpenGL ES, one process,
                                   one GL context, draws only on change; speaks a
                                   line protocol on stdin/stdout

homy-shell (Python, apps/shell)  backend bridge: sets view model values, reacts
  later: per-domain services       to taps (Qtile groups, theme service, later
                                   Home Assistant, music, …)
```

Why one file is the right end state:

- **No more copying components between files.** The Rive library isn't
  available to us; today every surface file carries its own copy of IconButton
  and Theme. In one file they exist once.
- **One renderer, one window, one GL context.** No window juggling, no
  transparency, no compositor needed. On the Pi 5 the HMI can later run
  fullscreen directly on the display (DRM/KMS, no X11) — the most efficient
  and most robust way to drive that GPU.
- **Fonts and assets load once** instead of once per surface file.
- **The view model is the API.** Apps don't draw; they read and write
  properties (`sidebar.activeIndex`, `clock.time`, `lights.kitchen.on` …) through
  homy-shell. Designs can change completely without touching code as long as
  the property names stay.

Kept in mind: the editor file grows, so components stay separate artboards
(one per component, as now); screens are nested artboards inside HMI.

## The MVP on this branch: the sidebar only

| | |
|---|---|
| Rive | `ui/riv/sidebar.riv` (artboard SideBar) — until the HMI file exists |
| homy-hmi | one window "Homy Sidebar", OpenGL ES 3 via EGL (GLFW), Qtile pins it as before |
| homy-shell | plain Python (no Qt): starts homy-hmi, taps → Qtile groups, group changes → highlight, theme tokens → global Theme |
| top/bottom bar | Qtile's own SVG bars again (Rive bars come back inside the HMI) |
| removed | QtWebEngine shell (web pages, shell.js), webengine.py, Rive Test, the web runtime, topbar/bottombar/wallpaper .riv, Chromium |

Protocol (apps/hmi/hmi.cpp):

```
→ homy-hmi   number activeIndex 2 | string <name> <text> | color Theme/accent #RRGGBBAA
             watch activeIndex | background #RRGGBB
← homy-hmi   ready SideBar <GL renderer> | number activeIndex 3 | error <message>
```

Same build for the VM and the Pi 5: OpenGL ES through EGL — on the VM Mesa's
llvmpipe (software), on the Pi 5 the V3D GPU.

## Steps

1. **Build on the VM**: `nix build .#…homy-hmi` (rive-runtime via premake, all
   dependencies fetched by Nix). Expect a few rounds of build fixes.
2. **VM**: `homy-hmi --riv …/sidebar.riv --artboard SideBar --size 180x520`
   by hand → feathers visible? taps → `number activeIndex …`?
3. **VM**: rebuild the system on this branch → sidebar via homy-shell, taps
   switch groups, theme changes apply.
4. **Pi 5**: the same. This is the real test of OpenGL ES on the V3D.
5. **HMI file**: one `hmi.riv` with an HMI artboard (screen size) holding the
   SideBar; homy-hmi fullscreen behind the PyQt apps → then move the bars in.
6. **Pi 5 optimisation**: once the whole UI lives in the HMI, homy-hmi runs on
   DRM/KMS directly (no X11, no Qtile) as a kiosk.
