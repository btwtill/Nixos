// X11Copy — a rendered frame onto the window as a plain X11 image (see backend.hpp).
#include "backend.hpp"

#define GLFW_INCLUDE_NONE
#include <GLFW/glfw3.h>
#include <X11/Xlib.h>
#include <X11/Xutil.h>

#include <cstdlib>

// from GLFW's glfw3native.h, which would also want the Xrandr headers
extern "C" Display* glfwGetX11Display(void);
extern "C" ::Window glfwGetX11Window(GLFWwindow* window);

namespace homy
{
struct X11Copy::Impl
{
  Display* display = nullptr;
  ::Window window = 0;
  GC gc = nullptr;
  XImage* image = nullptr;
  int width = 0, height = 0;
};

X11Copy::X11Copy(GLFWwindow* window) : m_impl(std::make_unique<Impl>())
{
  m_impl->display = glfwGetX11Display();
  m_impl->window = glfwGetX11Window(window);
  m_impl->gc = XCreateGC(m_impl->display, m_impl->window, 0, nullptr);
}

X11Copy::~X11Copy()
{
  if (m_impl->image)
    XDestroyImage(m_impl->image);       // frees its pixel buffer too
  XFreeGC(m_impl->display, m_impl->gc);
}

void X11Copy::resize(int width, int height)
{
  if (m_impl->image)
    XDestroyImage(m_impl->image);
  XWindowAttributes attrs;
  XGetWindowAttributes(m_impl->display, m_impl->window, &attrs);
  m_impl->image = XCreateImage(m_impl->display, attrs.visual, attrs.depth, ZPixmap, 0,
                               static_cast<char*>(malloc(static_cast<size_t>(width) * height * 4)),
                               width, height, 32, 0);
  m_impl->width = width, m_impl->height = height;
}

void X11Copy::present(const std::vector<uint8_t>& rgbaBottomUp)
{
  const int w = m_impl->width, h = m_impl->height;
  if (!m_impl->image || rgbaBottomUp.size() < static_cast<size_t>(w) * h * 4)
    return;
  // RGBA, bottom row first → BGRX (little-endian 0xAARRGGBB), top row first
  auto* dst = reinterpret_cast<uint32_t*>(m_impl->image->data);
  for (int y = 0; y < h; ++y)
  {
    const uint8_t* src = rgbaBottomUp.data() + static_cast<size_t>(h - 1 - y) * w * 4;
    for (int x = 0; x < w; ++x, src += 4)
      *dst++ = 0xff000000u | (uint32_t(src[0]) << 16) | (uint32_t(src[1]) << 8) | src[2];
  }
  XPutImage(m_impl->display, m_impl->window, m_impl->gc, m_impl->image, 0, 0, 0, 0, w, h);
  XFlush(m_impl->display);
}
} // namespace homy
