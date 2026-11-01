"""QtWebEngine setup for Rive (web runtime) apps — call configure() before
creating the QApplication.

How Chromium's frames reach the Qt window (see QtWebEngine's rhi_gpu_info.cpp
and native_skia_output_device_opengl.cpp):
  GPU       rendered on the GPU and shared with Qt as dma_buf. Needs a real GPU
            driver, Qt on OpenGL *via EGL* (GLX can't import dma_buf) and
            Chromium kept off Vulkan.
  software  Chromium composites on the CPU and hands Qt plain pixels — no
            dma_buf, so it works where the GPU path leaves the window empty
            (the UTM VM: "dma_buf acquisition failure"). WebGL stays available,
            rendered on the CPU by SwiftShader: Rive's WebGL2 renderer is the
            only one that draws feathers and blend modes, which the designs use.
HOMY_WEB_GPU=1/0 forces either mode.

Raspberry Pi (Broadcom v3d/vc4): Chromium's default GL path goes through the
driver's desktop OpenGL (3.1 on the Pi 5), which can't provide ES 3 — WebGL2
fails ("ES3 is blocklisted/disabled/unsupported by driver") and Rive falls back
to canvas, without feathers. Through ANGLE on the driver's OpenGL ES 3.1 it
works, so those drivers get --use-gl=angle --use-angle=gles-egl.
"""
from __future__ import annotations

import os
from pathlib import Path

# Let Chromium use the GPU even where its blocklist says otherwise.
# --process-per-site: pages of one site share one renderer process instead of
# one each — the shell's surfaces all come from 127.0.0.1:47811, so they run in
# a single renderer (each costs ~40–80 MB otherwise).
BASE_FLAGS = ["--ignore-gpu-blocklist", "--enable-gpu-rasterization", "--process-per-site"]

# Kernel drivers of real GPUs that can share frames with Qt (dma_buf).
REAL_GPU_DRIVERS = {"v3d", "i915", "xe", "amdgpu", "radeon", "msm", "panfrost", "lima", "etnaviv"}
# GPUs whose WebGL2 needs Chromium on their OpenGL ES (see above).
GLES_DRIVERS = {"v3d", "vc4"}


def gpu_drivers() -> set[str]:
    return {(node / "device" / "driver").resolve().name for node in Path("/sys/class/drm").glob("renderD*")}


def gpu_available() -> bool:
    forced = os.environ.get("HOMY_WEB_GPU")
    if forced in ("0", "1"):
        return forced == "1"
    return bool(gpu_drivers() & REAL_GPU_DRIVERS)


def configure() -> bool:
    """Set the environment for the chosen mode; returns True for GPU mode."""
    gpu = gpu_available()
    flags = list(BASE_FLAGS)
    if gpu:
        os.environ.setdefault("QSG_RHI_BACKEND", "opengl")
        os.environ.setdefault("QT_XCB_GL_INTEGRATION", "xcb_egl")
        flags.append("--disable-features=Vulkan")
        if gpu_drivers() & GLES_DRIVERS:
            flags += ["--use-gl=angle", "--use-angle=gles-egl"]
    else:
        flags += ["--disable-gpu-compositing", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", " ".join(flags))
    return gpu
