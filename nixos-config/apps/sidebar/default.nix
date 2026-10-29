{ pkgs ? import <nixpkgs> {} }:

# Homy sidebar — Qtile's right-hand navigation, drawn by Rive (sidebar.riv).
let
  pyEnv = pkgs.python313.withPackages (ps: [ ps.pyqt6 ps.pyqt6-webengine ]);

  # Rive's official web runtimes (JS + WASM), bundled so nothing is downloaded.
  riveVersion = "2.47.0";
  riveRuntime = name: hash: pkgs.fetchurl {
    url = "https://registry.npmjs.org/@rive-app/${name}/-/${name}-${riveVersion}.tgz";
    inherit hash;
  };
  canvas = riveRuntime "canvas" "sha256-5qViveyfEDatZBihihKF/XDr3FT8ByDAbEZllTzXqhE=";
  webgl2 = riveRuntime "webgl2" "sha256-Wy73SaYIcsFXkWfeOpCXYiXaeFvVXaDxQ4hZD4VULMw=";
in
pkgs.stdenv.mkDerivation {
  pname   = "homy-sidebar";
  version = "0.1.0";

  src = ./.;

  buildInputs = [ pyEnv ];

  installPhase = ''
    lib=$out/lib/homy-sidebar
    mkdir -p $out/bin $lib/web
    cp main.py sidebar.riv $lib/
    cp web/index.html $lib/web/
    cp ${../common}/webengine.py $lib/

    for rt in canvas:${canvas} webgl2:${webgl2}; do
      name=''${rt%%:*}; tgz=''${rt#*:}
      mkdir -p $lib/vendor/$name tmp-$name
      tar -xzf $tgz -C tmp-$name
      cp tmp-$name/package/{rive.js,rive.wasm,rive_fallback.wasm} $lib/vendor/$name/
    done

    cat > $out/bin/homy-sidebar <<EOF
    #!/bin/sh
    exec ${pyEnv}/bin/python $lib/main.py "\$@"
    EOF
    chmod +x $out/bin/homy-sidebar
  '';
}
