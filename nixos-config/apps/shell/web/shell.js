// Shared by every shell surface page (sidebar.html, wallpaper.html, …):
// loads one artboard of a .riv from the homy-ui package, keeps its colours in
// sync with the homy-theme service, and talks to main.py through the console.
//
//   startSurface({ riv, artboard, fit, alignment, onLoad(r) })
//   onTheme((tokens, r) => …)   extra theme handling for this surface
//   emit(kind, data)            message to main.py ("homy:<kind> <json>")
//
// The renderer is webgl2 — the only Rive renderer that draws feathers and blend
// modes; canvas is the fallback when the page has no WebGL2 at all.

const params = new URLSearchParams(location.search);
const hasWebGL2 = !!document.createElement("canvas").getContext("webgl2");
const renderer = params.get("renderer") === "canvas" || !hasWebGL2 ? "canvas" : "webgl2";
const THEME_EVENTS = "http://127.0.0.1:47820/events";

const emit = (kind, data) => console.log("homy:" + kind + " " + JSON.stringify(data ?? null));

let surfaceRive = null;
let theme = null;
const themeHooks = [];

// "#RRGGBB" or "#RRGGBBAA" (alpha last, like CSS)
function setColor(prop, hex) {
  if (!prop || !/^#[0-9a-f]{6}([0-9a-f]{2})?$/i.test(hex)) return;
  const v = parseInt(hex.slice(1, 7), 16);
  const a = hex.length === 9 ? parseInt(hex.slice(7, 9), 16) : 255;
  prop.argb(a, (v >> 16) & 255, (v >> 8) & 255, v & 255);
}

// Tokens go into the file's global Theme view model by name (tokens the file
// doesn't have are skipped), then each surface's own hooks run.
function applyTheme() {
  if (!surfaceRive || !theme) return;
  const global = surfaceRive.globalViewModelInstance("Theme");
  if (global) {
    for (const [name, hex] of Object.entries(theme.tokens)) setColor(global.color(name), hex);
  }
  for (const hook of themeHooks) hook(theme.tokens, surfaceRive);
}

function onTheme(hook) {
  themeHooks.push(hook);
}

new EventSource(THEME_EVENTS).onmessage = (e) => {
  theme = JSON.parse(e.data);
  applyTheme();
  emit("theme", theme.id);
};

function loadScript(src) {
  return new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = ok;
    s.onerror = () => fail(new Error("cannot load " + src));
    document.head.appendChild(s);
  });
}

function startSurface({ riv, artboard, fit = "contain", alignment = "center", onLoad }) {
  const canvas = document.getElementById("c");
  const src = `riv/${riv}.riv`;
  loadScript(`vendor/${renderer}/rive.js`).then(() => {
    rive.RuntimeLoader.setWasmUrl(`vendor/${renderer}/rive.wasm`);
    rive.RuntimeLoader.setWasmFallbackUrl(`vendor/${renderer}/rive_fallback.wasm`);
    rive.Rive.suppressDeprecationWarnings = ["default-state-machine"];
    const fits = { contain: rive.Fit.Contain, cover: rive.Fit.Cover, fill: rive.Fit.Fill, layout: rive.Fit.Layout };
    const aligns = { center: rive.Alignment.Center, topCenter: rive.Alignment.TopCenter };
    const layout = new rive.Layout({ fit: fits[fit], alignment: aligns[alignment] });

    // Pass 1 reads the artboard's state machine name; pass 2 starts it by name,
    // which is what wires up taps (Rive listeners) and data binding.
    const probe = new rive.Rive({
      src, canvas, artboard, autoplay: false,
      onLoadError: () => emit("error", `could not load ${src}`),
      onLoad: () => {
        const machine = probe.stateMachineNames[0];
        probe.cleanup();
        const r = new rive.Rive({
          src, canvas, artboard, layout, stateMachine: machine, autoplay: true, autoBind: true,
          onLoad: () => {
            surfaceRive = r;
            r.resizeDrawingSurfaceToCanvas();
            if (onLoad) onLoad(r);
            applyTheme();
            const gl = document.createElement("canvas").getContext("webgl2");
            const ext = gl && gl.getExtension("WEBGL_debug_renderer_info");
            emit("loaded", { riv, artboard, renderer, machine,
                             gpu: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : (gl ? "webgl2" : "none") });
          },
        });
      },
    });
  }).catch((e) => emit("error", String(e)));
}

window.addEventListener("resize", () => surfaceRive && surfaceRive.resizeDrawingSurfaceToCanvas());
