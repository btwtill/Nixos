{ pkgs ? import <nixpkgs> {}
, rive ? pkgs.callPackage ./rive-runtime.nix {}
}:

# homy-hmi — Rive's native renderer in a window, driven over stdin/stdout (see
# hmi.cpp). Two GPU backends (backend.hpp): OpenGL ES through EGL, loaded at
# runtime (glad) from the system's Mesa, and Vulkan through the Vulkan loader
# (dlopen'ed by rive_vk_bootstrap, found through the rpath below; drivers from
# /run/opengl-driver). libX11 hands offscreen frames to the window (x11_copy.cpp).
pkgs.clangStdenv.mkDerivation {
  pname   = "homy-hmi";
  version = "0.2.0";

  src = ./.;

  buildInputs = [ pkgs.glfw pkgs.xorg.libX11 ];

  # keep symbols while the native path is new: backtraces with function names
  dontStrip = true;

  # C++17 like rive-runtime: with C++20, header-inline statics such as
  # ComponentBase::name()'s empty string become read-only constants, and the
  # library (C++17, initialising them at runtime) crashes writing to them.
  # The defines must match the ones rive-runtime was built with.
  buildPhase = ''
    runHook preBuild
    $CXX -std=c++17 -O2 -g -fno-rtti -fno-exceptions \
      -DRIVE_DESKTOP_GL -DWITH_RIVE_TEXT -DWITH_RIVE_LAYOUT -DYOGA_EXPORT= -DNDEBUG -DRELEASE \
      -DRIVE_VULKAN -DVK_NO_PROTOTYPES -DVMA_STATIC_VULKAN_FUNCTIONS=0 -DVMA_DYNAMIC_VULKAN_FUNCTIONS=1 \
      -DWITH_VULKAN_ATOMICS \
      -I${rive}/include -I${rive}/share/rive_vk_bootstrap/src \
      hmi.cpp backend_gl.cpp backend_vulkan.cpp x11_copy.cpp \
      ${rive}/share/rive_vk_bootstrap/src/*.cpp \
      -o homy-hmi \
      -L${rive}/lib -Wl,--start-group -lrive_pls_renderer -lrive -lrive_yoga -lrive_harfbuzz -lrive_sheenbidi -Wl,--end-group \
      -lglfw -lX11 -ldl -lpthread \
      -Wl,-rpath,${pkgs.vulkan-loader}/lib
    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall
    install -Dm755 homy-hmi $out/bin/homy-hmi
    runHook postInstall
  '';
}
