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
};

// glfwWindowHint()s each backend needs before glfwCreateWindow
void glWindowHints(const BackendOptions&);
void vulkanWindowHints();

std::unique_ptr<Backend> makeGLBackend(GLFWwindow*, const BackendOptions&);
std::unique_ptr<Backend> makeVulkanBackend(GLFWwindow*);

// Hands RGBA pixels (bottom row first, as GL and Rive's Vulkan readback give
// them) to the window as an X11 image. Works where the GPU's own way onto an
// X11 window doesn't (Pi 5).
class X11Copy
{
public:
  explicit X11Copy(GLFWwindow*);
  ~X11Copy();
  void resize(int width, int height);
  void present(const std::vector<uint8_t>& rgbaBottomUp);

private:
  struct Impl;
  std::unique_ptr<Impl> m_impl;
};

void step(const std::string& what);   // startup progress on stderr
void out(const std::string& line);    // protocol line on stdout
} // namespace homy
