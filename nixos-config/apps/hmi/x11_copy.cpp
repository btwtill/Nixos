// X11Copy — a rendered frame onto the window as an X11 image (see backend.hpp).
#include "backend.hpp"

#define GLFW_INCLUDE_NONE
#include <GLFW/glfw3.h>
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/extensions/XShm.h>
#include <sys/ipc.h>
#include <sys/shm.h>

#include <algorithm>
#include <cstdlib>
#include <cstring>

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
  XImage* image = nullptr;      // what the window shows; rows of 0xffRRGGBB
  XShmSegmentInfo shm{};
  bool shared = false;          // image->data is shared with the X server
  bool full = true;             // the window has nothing (valid) yet
  int width = 0, height = 0;
  std::vector<uint32_t> row;    // one converted row of the new frame

  void destroyImage()
  {
    if (!image)
      return;
    if (shared)
    {
      XShmDetach(display, &shm);
      image->data = nullptr;            // not malloc'ed: XDestroyImage must not free it
      XDestroyImage(image);
      shmdt(shm.shmaddr);
    }
    else
      XDestroyImage(image);             // frees its pixel buffer too
    image = nullptr;
  }
};

X11Copy::X11Copy(GLFWwindow* window) : m_impl(std::make_unique<Impl>())
{
  m_impl->display = glfwGetX11Display();
  m_impl->window = glfwGetX11Window(window);
  m_impl->gc = XCreateGC(m_impl->display, m_impl->window, 0, nullptr);
}

X11Copy::~X11Copy()
{
  m_impl->destroyImage();
  XFreeGC(m_impl->display, m_impl->gc);
}

void X11Copy::resize(int width, int height)
{
  Impl& m = *m_impl;
  m.destroyImage();
  XWindowAttributes attrs;
  XGetWindowAttributes(m.display, m.window, &attrs);
  const size_t bytes = static_cast<size_t>(width) * height * 4;

  // Shared memory: the X server reads the pixels where they are, instead of
  // the whole frame travelling through the X11 socket.
  m.shared = false;
  if (XShmQueryExtension(m.display))
  {
    m.image = XShmCreateImage(m.display, attrs.visual, attrs.depth, ZPixmap, nullptr, &m.shm, width, height);
    if (m.image)
    {
      m.shm.shmid = shmget(IPC_PRIVATE, static_cast<size_t>(m.image->bytes_per_line) * height, IPC_CREAT | 0600);
      void* memory = m.shm.shmid < 0 ? reinterpret_cast<void*>(-1) : shmat(m.shm.shmid, nullptr, 0);
      if (memory != reinterpret_cast<void*>(-1))
      {
        m.shm.shmaddr = m.image->data = static_cast<char*>(memory);
        m.shm.readOnly = False;
        m.shared = XShmAttach(m.display, &m.shm) != 0;
        XSync(m.display, False);
      }
      if (m.shm.shmid >= 0)
        shmctl(m.shm.shmid, IPC_RMID, nullptr);   // freed once both sides have detached
      if (!m.shared)
      {
        if (memory != reinterpret_cast<void*>(-1))
          shmdt(memory);
        m.image->data = nullptr;
        XDestroyImage(m.image);
        m.image = nullptr;
      }
    }
  }
  if (!m.image)
    m.image = XCreateImage(m.display, attrs.visual, attrs.depth, ZPixmap, 0,
                           static_cast<char*>(malloc(bytes)), width, height, 32, 0);
  step(m.shared ? "X11 image: shared memory (MIT-SHM)" : "X11 image: through the socket (no MIT-SHM)");
  std::memset(m.image->data, 0, static_cast<size_t>(m.image->bytes_per_line) * height);
  m.row.assign(static_cast<size_t>(width), 0);
  m.width = width, m.height = height;
  m.full = true;
}

void X11Copy::invalidate() { m_impl->full = true; }

double X11Copy::present(const Frame& frame)
{
  Impl& m = *m_impl;
  const int w = m.width, h = m.height;
  if (!m.image || !frame.pixels)
    return 0;
  // Row by row: the new row → `row` (as 0xffRRGGBB; one pass over the GPU's
  // memory), compared with what the window shows, copied only where it differs.
  uint32_t* row = m.row.data();
  int x0 = w, x1 = -1, y0 = h, y1 = -1;
  for (int y = 0; y < h; ++y)
  {
    const uint8_t* src = frame.pixels + static_cast<size_t>(frame.bottomUp ? h - 1 - y : y) * frame.strideBytes;
    if (frame.bgra)
      std::memcpy(row, src, static_cast<size_t>(w) * 4);
    else
      for (int x = 0; x < w; ++x, src += 4)
        row[x] = 0xff000000u | (uint32_t(src[0]) << 16) | (uint32_t(src[1]) << 8) | src[2];
    auto* shown = reinterpret_cast<uint32_t*>(m.image->data + static_cast<size_t>(y) * m.image->bytes_per_line);
    if (std::memcmp(row, shown, static_cast<size_t>(w) * 4) == 0)
      continue;
    int a = 0, b = w - 1;
    while (row[a] == shown[a])
      ++a;
    while (row[b] == shown[b])
      --b;
    std::memcpy(shown + a, row + a, static_cast<size_t>(b - a + 1) * 4);
    x0 = std::min(x0, a), x1 = std::max(x1, b);
    y0 = std::min(y0, y), y1 = y;
  }
  if (m.full)
    x0 = 0, y0 = 0, x1 = w - 1, y1 = h - 1, m.full = false;
  if (y1 < 0)
    return 0;   // nothing changed
  const int cw = x1 - x0 + 1, ch = y1 - y0 + 1;
  if (m.shared)
    XShmPutImage(m.display, m.window, m.gc, m.image, x0, y0, x0, y0, cw, ch, False);
  else
    XPutImage(m.display, m.window, m.gc, m.image, x0, y0, x0, y0, cw, ch);
  // Wait until the server has taken the pixels: with shared memory it reads
  // them when it gets to the request, and the next frame must not be written
  // into the image before that (half-old, half-new frames on screen).
  XSync(m.display, False);
  return static_cast<double>(cw) * ch / (static_cast<double>(w) * h);
}
} // namespace homy
