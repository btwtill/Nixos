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
"""
from __future__ import annotations

import os
from pathlib import Path

# Let Chromium use the GPU even where its blocklist says otherwise.
BASE_FLAGS = ["--ignore-gpu-blocklist", "--enable-gpu-rasterization"]

# Kernel drivers of real GPUs that can share frames with Qt (dma_buf).
REAL_GPU_DRIVERS = {"v3d", "i915", "xe", "amdgpu", "radeon", "msm", "panfrost", "lima", "etnaviv"}


def gpu_available() -> bool:
    forced = os.environ.get("HOMY_WEB_GPU")
    if forced in ("0", "1"):
        return forced == "1"
    for node in Path("/sys/class/drm").glob("renderD*"):
        if (node / "device" / "driver").resolve().name in REAL_GPU_DRIVERS:
            return True
    return False


def configure() -> bool:
    """Set the environment for the chosen mode; returns True for GPU mode."""
    gpu = gpu_available()
    flags = list(BASE_FLAGS)
    if gpu:
        os.environ.setdefault("QSG_RHI_BACKEND", "opengl")
        os.environ.setdefault("QT_XCB_GL_INTEGRATION", "xcb_egl")
        flags.append("--disable-features=Vulkan")
    else:
        flags += ["--disable-gpu-compositing", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", " ".join(flags))
    return gpu
