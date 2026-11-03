{ pkgs ? import <nixpkgs> {}
, rive ? pkgs.callPackage ./rive-runtime.nix {}
}:

# homy-hmi — Rive's native renderer on OpenGL ES in a window, driven over
# stdin/stdout (see hmi.cpp). GLFW opens the X11 window and the EGL context;
# OpenGL itself is loaded at runtime (glad), so libEGL/libGLESv2 come from the
# system's Mesa (/run/opengl-driver).
pkgs.clangStdenv.mkDerivation {
  pname   = "homy-hmi";
  version = "0.1.0";

  src = ./.;

  buildInputs = [ pkgs.glfw ];

  buildPhase = ''
    runHook preBuild
    $CXX -std=c++20 -O2 -fno-rtti -fno-exceptions \
      -DRIVE_DESKTOP_GL -DWITH_RIVE_TEXT -DWITH_RIVE_LAYOUT -DYOGA_EXPORT= -DNDEBUG -DRELEASE \
      -I${rive}/include \
      hmi.cpp -o homy-hmi \
      -L${rive}/lib -Wl,--start-group -lrive_pls_renderer -lrive -lrive_yoga -lrive_harfbuzz -lrive_sheenbidi -Wl,--end-group \
      -lglfw -ldl -lpthread
    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall
    install -Dm755 homy-hmi $out/bin/homy-hmi
    runHook postInstall
  '';
}
