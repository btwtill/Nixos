{ pkgs ? import <nixpkgs> {} }:

# homy-ui — everything graphical, in one place on the device:
#
#   share/homy/ui/riv/<surface>.riv         built from homy-design (./sync.sh)
#   share/homy/ui/runtime/{webgl2,canvas}/  Rive's web runtime (JS + WASM)
#
# Apps take what they need from here instead of bundling their own copies;
# it is also linked into /run/current-system/sw/share/homy/ui for app-store apps.
let
  riveVersion = "2.47.0";
  riveRuntime = name: hash: pkgs.fetchurl {
    url = "https://registry.npmjs.org/@rive-app/${name}/-/${name}-${riveVersion}.tgz";
    inherit hash;
  };
  # webgl2 is the Rive renderer (feathers, blend modes — what the designs use);
  # canvas is the lightweight fallback.
  runtimes = {
    webgl2 = riveRuntime "webgl2" "sha256-Wy73SaYIcsFXkWfeOpCXYiXaeFvVXaDxQ4hZD4VULMw=";
    canvas = riveRuntime "canvas" "sha256-5qViveyfEDatZBihihKF/XDr3FT8ByDAbEZllTzXqhE=";
  };
in
pkgs.runCommand "homy-ui-${riveVersion}" { } ''
  ui=$out/share/homy/ui
  mkdir -p $ui/riv $ui/runtime
  cp ${./riv}/*.riv $ui/riv/

  ${pkgs.lib.concatStrings (pkgs.lib.mapAttrsToList (name: tgz: ''
    mkdir -p $ui/runtime/${name} unpack-${name}
    tar -xzf ${tgz} -C unpack-${name}
    cp unpack-${name}/package/{rive.js,rive.wasm,rive_fallback.wasm} $ui/runtime/${name}/
  '') runtimes)}
''
