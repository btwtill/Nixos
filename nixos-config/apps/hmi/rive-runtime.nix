{ pkgs ? import <nixpkgs> {} }:

# Rive's C++ runtime + its GPU renderer (OpenGL / OpenGL ES), as static
# libraries and headers for homy-hmi. Upstream builds with premake and fetches
# its dependencies from GitHub at configure time; here Nix fetches them up
# front and premake finds them in $DEPENDENCIES (build/dependency.lua skips any
# dependency whose folder already exists).
#
# Built with text (harfbuzz, sheenbidi) and layout (yoga); without image
# decoders, audio output, scripting, Vulkan — and without LTO, so the static
# libraries hold machine code any linker can use (with LTO they hold LLVM
# bitcode: "archive has no index").
let
  gh = owner: repo: rev: hash: pkgs.fetchFromGitHub { inherit owner repo rev hash; };

  # folder name = "<owner>_<repo>_<tag>", as dependency.github() names them
  deps = {
    "rive-app_harfbuzz_rive_13.1.1"         = gh "rive-app" "harfbuzz" "rive_13.1.1" "sha256-7TE3qdjVK+QYPLdGHtsfcqjEmbjPiegWK6u0RAeLhs8=";
    "Tehreer_SheenBidi_v2.6"                = gh "Tehreer" "SheenBidi" "v2.6" "sha256-ybHM+/ZBf3QIJax41CsiiEaRN4kZvattT4o1U7vJsPQ=";
    "rive-app_miniaudio_rive_changes_11"    = gh "rive-app" "miniaudio" "rive_changes_11" "sha256-9xdqwRk/qPxNe2SdggKueMb17N2ifwOCL/NHdazatqQ=";
    "rive-app_yoga_rive_yoga_dee88d2dfcad"  = gh "rive-app" "yoga" "rive_yoga_dee88d2dfcad" "sha256-Jt5ipTMYYXCXHWi07VkdS78F+DbsbSD/XRQ1R2ajixE=";
    "dabeaz_ply_3.11"                       = gh "dabeaz" "ply" "3.11" "sha256-PEwIgmM7DQHy6FOhcUwkricrdW3wZe3ggSQnUvgKISo=";
  };

  # only the libraries homy-hmi links, not upstream's sample apps
  premakeFile = pkgs.writeText "premake5_homy.lua" ''
    dofile('rive_build_config.lua')
    dofile('premake5_pls_renderer.lua')
    dofile(RIVE_RUNTIME_DIR .. '/premake5_v2.lua')
  '';
  libs = [ "rive" "rive_pls_renderer" "rive_harfbuzz" "rive_sheenbidi" "rive_yoga" ];
in
pkgs.clangStdenv.mkDerivation {
  pname   = "rive-runtime";
  version = "unstable-2026-11-03";

  src = gh "rive-app" "rive-runtime" "65860c42ccfbe9cbbd5f1079d7104d871e8a22f9"
    "sha256-hWT9ChKp9UIYamGar/+GJcFvqq+18QS6ElKJKksvOyU=";

  nativeBuildInputs = with pkgs; [ premake5 python3 gnumake which ];

  configurePhase = ''
    runHook preConfigure
    mkdir deps
    ${pkgs.lib.concatStrings (pkgs.lib.mapAttrsToList (name: src: ''
      cp -r ${src} deps/${name}
    '') deps)}
    chmod -R u+w deps
    export DEPENDENCIES=$PWD/deps
    export PREMAKE_PATH=$PWD/build
    cp ${premakeFile} renderer/premake5_homy.lua
    cd renderer
    premake5 --file=premake5_homy.lua --config=release --out=out/release \
      --with_rive_text --with_rive_layout --no-rive-decoders --no-lto gmake
    runHook postConfigure
  '';

  buildPhase = ''
    runHook preBuild
    # one premake configuration ("default"); release was chosen by --config above
    make -C out/release -j$NIX_BUILD_CORES ${pkgs.lib.concatStringsSep " " libs}
    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall
    mkdir -p $out/lib $out/include
    find out/release -name '*.a' -exec cp {} $out/lib/ \;
    for a in $out/lib/*.a; do ranlib "$a"; done      # symbol index for the linker
    cp -r ../include/. $out/include/                 # runtime: rive/…
    cp -r include/. $out/include/                    # renderer: rive/renderer/…
    cp -r glad/include/. $out/include/               # glad/, EGL/, KHR/
    cp glad/glad_custom.h $out/include/                # included as "glad_custom.h"
    runHook postInstall
  '';
}
