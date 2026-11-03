{ pkgs ? import <nixpkgs> {}
, rive ? pkgs.callPackage ./rive-runtime.nix {}
}:

# homy-hmi — Rive's native renderer on OpenGL ES in a window, driven over
# stdin/stdout (see hmi.cpp). GLFW opens the X11 window and the EGL context;
# OpenGL itself is loaded at runtime (glad), so libEGL/libGLESv2 come from the
# system's Mesa (/run/opengl-driver). libX11 for --present copy (Pi 5).
pkgs.clangStdenv.mkDerivation {
  pname   = "homy-hmi";
  version = "0.1.0";

  src = ./.;

  buildInputs = [ pkgs.glfw pkgs.xorg.libX11 ];   # libX11: --present copy

  # keep symbols while the native path is new: backtraces with function names
  dontStrip = true;

  # C++17 like rive-runtime: with C++20, header-inline statics such as
  # ComponentBase::name()'s empty string become read-only constants, and the
  # library (C++17, initialising them at runtime) crashes writing to them.
  buildPhase = ''
    runHook preBuild
    $CXX -std=c++17 -O2 -g -fno-rtti -fno-exceptions \
      -DRIVE_DESKTOP_GL -DWITH_RIVE_TEXT -DWITH_RIVE_LAYOUT -DYOGA_EXPORT= -DNDEBUG -DRELEASE \
      -I${rive}/include \
      hmi.cpp -o homy-hmi \
      -L${rive}/lib -Wl,--start-group -lrive_pls_renderer -lrive -lrive_yoga -lrive_harfbuzz -lrive_sheenbidi -Wl,--end-group \
      -lglfw -lX11 -ldl -lpthread
    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall
    install -Dm755 homy-hmi $out/bin/homy-hmi
    runHook postInstall
  '';
}
