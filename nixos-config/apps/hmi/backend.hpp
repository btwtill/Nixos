// How homy-hmi gets Rive frames onto its window: an OpenGL ES backend
// (backend_gl.cpp) and a Vulkan backend (backend_vulkan.cpp), plus the X11
// copy that both can use to hand a frame to the window as a plain image.
#pragma once

#include "rive/renderer/render_context.hpp"

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

struct GLFWwindow;

namespace homy
{
struct BackendOptions
{
  bool copyPresent = false;   // GL: render offscreen, hand the frame over as an X11 image
  int msaa = 0;               // GL: give Rive a multisampled target with this many samples
  bool glDebug = false;       // GL: print extensions + driver messages to stderr
};

// Where the last finishFrame() spent its time (ms), for HOMY_HMI_STATS.
struct FrameTimes
{
  double flush = 0;     // Rive's flush: the frame's commands to the GPU
  double gpu = 0;       // waiting for the GPU to finish + reading the frame back
  double present = 0;   // onto the window
  double changed = 1;   // share of the window that changed (copy present; else 1)
};

class Backend
{
public:
  virtual ~Backend() = default;
  virtual rive::gpu::RenderContext* context() = 0;
  virtual std::string deviceName() const = 0;
  virtual uint32_t msaaSampleCount() const { return 0; }
  // the window's framebuffer size changed (also called once at the start)
  virtual void resize(int width, int height) = 0;
  // called before RenderContext::beginFrame
  virtual void prepareFrame() {}
  // flush Rive's frame and get it onto the window
  virtual bool finishFrame() = 0;
  // the window lost what it showed (exposed): hand the next frame over in full
  virtual void invalidate() {}
  const FrameTimes& frameTimes() const { return m_times; }

protected:
  FrameTimes m_times;
};

// glfwWindowHint()s each backend needs before glfwCreateWindow
void glWindowHints(const BackendOptions&);
void vulkanWindowHints();

std::unique_ptr<Backend> makeGLBackend(GLFWwindow*, const BackendOptions&);
std::unique_ptr<Backend> makeVulkanBackend(GLFWwindow*);

// Hands a rendered frame to the window as an X11 image. Works where the GPU's
// own way onto an X11 window doesn't (Pi 5). The image lives in memory shared
// with the X server (MIT-SHM), and only the rectangle that differs from the
// previous frame is handed over: a button animating costs a button's worth of
// pixels, not the whole screen.
class X11Copy
{
public:
  struct Frame
  {
    const uint8_t* pixels;   // 4 bytes per pixel
    int strideBytes;
    bool bgra;               // byte order B,G,R,A (what X11 wants) instead of R,G,B,A
    bool bottomUp;           // bottom row first (OpenGL)
  };

  explicit X11Copy(GLFWwindow*);
  ~X11Copy();
  void resize(int width, int height);
  void invalidate();               // next present(): the whole frame
  double present(const Frame&);    // returns the share of the window that changed (0…1)

private:
  struct Impl;
  std::unique_ptr<Impl> m_impl;
};

double nowMs();                       // monotonic clock, for FrameTimes
void step(const std::string& what);   // startup progress on stderr
void out(const std::string& line);    // protocol line on stdout
} // namespace homy
