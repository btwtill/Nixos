{ pkgs ? import <nixpkgs> {} }:

# Rive prototype app — shows up in the app menu twice:
#   "Rive Test"            QtWebEngine in a frameless PyQt window
#   "Rive Test (Chromium)" separate Chromium window in app mode
let
  pyEnv = pkgs.python313.withPackages (ps: [ ps.pyqt6 ps.pyqt6-webengine ]);

  # Rive's official web runtimes (JS + WASM), bundled so it works offline.
  riveVersion = "2.47.0";
  riveRuntime = name: hash: pkgs.fetchurl {
    url = "https://registry.npmjs.org/@rive-app/${name}/-/${name}-${riveVersion}.tgz";
    inherit hash;
  };
  canvas = riveRuntime "canvas" "sha256-5qViveyfEDatZBihihKF/XDr3FT8ByDAbEZllTzXqhE=";
  webgl2 = riveRuntime "webgl2" "sha256-Wy73SaYIcsFXkWfeOpCXYiXaeFvVXaDxQ4hZD4VULMw=";

  # Public Rive sample, used until a file is put into ~/rive/
  sample = pkgs.fetchurl {
    url  = "https://cdn.rive.app/animations/vehicles.riv";
    hash = "sha256-RrslDN4LAiOhX63awz0I+gDUtqzrwuToJzka4BE3aKM=";
  };
in
pkgs.stdenv.mkDerivation {
  pname   = "rive-test";
  version = "0.1.0";

  src = ./.;

  buildInputs = [ pyEnv ];

  installPhase = ''
    lib=$out/lib/rive-test
    mkdir -p $out/bin $lib/web
    cp main.py $lib/
    cp web/index.html $lib/web/
    cp ${sample} $lib/web/sample.riv

    for rt in canvas:${canvas} webgl2:${webgl2}; do
      name=''${rt%%:*}; tgz=''${rt#*:}
      mkdir -p $lib/web/vendor/$name tmp-$name
      tar -xzf $tgz -C tmp-$name
      cp tmp-$name/package/{rive.js,rive.wasm,rive_fallback.wasm} $lib/web/vendor/$name/
    done

    cat > $out/bin/rive-test <<EOF
    #!/bin/sh
    export PATH="${pkgs.chromium}/bin:\$PATH"
    exec ${pyEnv}/bin/python $lib/main.py "\$@"
    EOF
    chmod +x $out/bin/rive-test

    # App menu entries (see apps/launcher/registry.py)
    mkdir -p $out/share/homy/apps/rive-test $out/share/homy/apps/rive-test-chromium
    cat > $out/share/homy/apps/rive-test/manifest.json <<EOF
    { "id": "rive-test", "name": "Rive Test", "exec": "$out/bin/rive-test", "category": "System" }
    EOF
    cat > $out/share/homy/apps/rive-test-chromium/manifest.json <<EOF
    { "id": "rive-test-chromium", "name": "Rive Test (Chromium)", "exec": "$out/bin/rive-test --chromium", "category": "System" }
    EOF
  '';
}
