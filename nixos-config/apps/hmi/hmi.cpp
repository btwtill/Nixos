// homy-hmi — plays one artboard of a .riv file in a window, with Rive's native
// renderer on OpenGL ES (EGL). Knows nothing about Qtile or themes: whoever
// starts it drives it over stdin/stdout, one command per line.
//
//   homy-hmi --riv FILE [--artboard NAME] [--title TITLE] [--size WxH]
//            [--fit contain|layout|cover|fill] [--align center|topCenter]
//            [--background #RRGGBB] [--present gl|copy] [--msaa N]
//
// stdin                                   stdout
//   number <name> <value>                   ready <artboard> <GL renderer>
//   string <name> <text…>                   number <name> <value>   (a watched
//   color <ViewModel>/<name> <#RRGGBB[AA]>    number changed inside the file,
//   watch <name>                              e.g. a tap wrote activeIndex)
//   background <#RRGGBB>                    error <message>
//
// <name> is a property of the artboard's view model; color addresses a global
// view model (e.g. Theme/accent). Draws only while something changes.
//
// --present (or HOMY_HMI_PRESENT): how a finished frame reaches the window.
//   gl    swap the OpenGL ES window surface (default)
//   copy  render into an offscreen framebuffer on the GPU, read it back and
//         hand it to the window as a plain X11 image. For the Pi 5 under X11:
//         its GPU renders fine, but OpenGL ES window surfaces never show up
//         there (not even Mesa's es2gears). Costs a copy per changed frame.
// --msaa N (or HOMY_HMI_MSAA): give Rive a multisampled target with N samples.
//   Where the GPU has none of Rive's "interlock" modes (Pi 5: V3D), Rive draws
//   in depthStencil mode with MSAA and otherwise sets up the MSAA buffer itself.

#include "rive/animation/state_machine_instance.hpp"
#include "rive/artboard.hpp"
#include "rive/file.hpp"
#include "rive/layout.hpp"
#include "rive/renderer.hpp"
#include "rive/renderer/gl/render_context_gl_impl.hpp"
#include "rive/renderer/gl/render_target_gl.hpp"
#include "rive/renderer/render_context.hpp"
#include "rive/renderer/rive_renderer.hpp"
#include "rive/viewmodel/viewmodel_instance.hpp"
#include "rive/viewmodel/viewmodel_instance_color.hpp"
#include "rive/viewmodel/viewmodel_instance_number.hpp"
#include "rive/viewmodel/viewmodel_instance_string.hpp"

#include "glad_custom.h"
#define GLFW_INCLUDE_NONE
#include <GLFW/glfw3.h>
#include <X11/Xlib.h>
#include <X11/Xutil.h>
// from GLFW's glfw3native.h, which would also want the Xrandr headers
extern "C" Display* glfwGetX11Display(void);
extern "C" ::Window glfwGetX11Window(GLFWwindow* window);

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <fstream>
#include <functional>
#include <iostream>
#include <map>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

using namespace rive;

namespace
{
struct Options
{
  std::string riv, artboard, title = "Homy HMI";
  int width = 1024, height = 600;
  Fit fit = Fit::contain;
  Alignment align = Alignment::center;
  ColorInt background = 0xff1e1e1e;
  bool copyPresent = false;
  int msaa = 0;
};

void out(const std::string& line)
{
  std::cout << line << std::endl;   // endl flushes: the controller reads lines
}

// Startup progress on stderr (the controller only reads stdout), so a crash
// during setup shows how far it got.
void step(const std::string& what)
{
  std::cerr << "homy-hmi: " << what << std::endl;
}

bool parseColor(const std::string& hex, ColorInt* argb)
{
  if (hex.size() != 7 && hex.size() != 9)
    return false;
  if (hex[0] != '#')
    return false;
  unsigned long v = std::strtoul(hex.c_str() + 1, nullptr, 16);
  *argb = hex.size() == 9 ? ((v & 0xff) << 24) | (v >> 8)   // #RRGGBBAA
                          : 0xff000000 | v;                 // #RRGGBB
  return true;
}

Options parseArgs(int argc, char** argv)
{
  Options o;
  for (int i = 1; i + 1 < argc; i += 2)
  {
    std::string k = argv[i], v = argv[i + 1];
    if (k == "--riv") o.riv = v;
    else if (k == "--artboard") o.artboard = v;
    else if (k == "--title") o.title = v;
    else if (k == "--size") std::sscanf(v.c_str(), "%dx%d", &o.width, &o.height);
    else if (k == "--fit")
      o.fit = v == "layout" ? Fit::layout : v == "cover" ? Fit::cover
            : v == "fill" ? Fit::fill : Fit::contain;
    else if (k == "--align")
      o.align = v == "topCenter" ? Alignment::topCenter : Alignment::center;
    else if (k == "--background") parseColor(v, &o.background);
    else if (k == "--present") o.copyPresent = v == "copy";
    else if (k == "--msaa") o.msaa = std::atoi(v.c_str());
  }
  return o;
}

// stdin is read on its own thread; the render loop picks the lines up.
std::mutex g_inputMutex;
std::deque<std::string> g_input;

void readStdin()
{
  std::string line;
  while (std::getline(std::cin, line))
  {
    {
      std::lock_guard<std::mutex> lock(g_inputMutex);
      g_input.push_back(line);
    }
    glfwPostEmptyEvent();
  }
}
} // namespace

int main(int argc, char** argv)
{
  Options opt = parseArgs(argc, argv);
  if (const char* present = std::getenv("HOMY_HMI_PRESENT"))
    opt.copyPresent = opt.copyPresent || std::string(present) == "copy";
  if (const char* msaa = std::getenv("HOMY_HMI_MSAA"); msaa && !opt.msaa)
    opt.msaa = std::atoi(msaa);
  if (opt.riv.empty())
  {
    std::fprintf(stderr, "usage: homy-hmi --riv FILE [--artboard NAME] …\n");
    return 2;
  }
  std::ifstream in(opt.riv, std::ios::binary);
  std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(in)), {});
  if (bytes.empty())
  {
    out("error cannot read " + opt.riv);
    return 1;
  }

  // ── window + OpenGL ES 3 context via EGL (same path on the VM and the Pi) ──
  if (!glfwInit())
  {
    out("error glfwInit failed");
    return 1;
  }
  glfwWindowHint(GLFW_CONTEXT_CREATION_API, GLFW_EGL_CONTEXT_API);
  glfwWindowHint(GLFW_CLIENT_API, GLFW_OPENGL_ES_API);
  glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
  glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 0);
  glfwWindowHint(GLFW_DECORATED, GLFW_FALSE);
  glfwWindowHint(GLFW_RESIZABLE, GLFW_FALSE);
  glfwWindowHint(GLFW_STENCIL_BITS, 8);
  if (opt.msaa > 0 && !opt.copyPresent)
    glfwWindowHint(GLFW_SAMPLES, opt.msaa);
  GLFWwindow* window = glfwCreateWindow(opt.width, opt.height, opt.title.c_str(), nullptr, nullptr);
  if (!window)
  {
    out("error cannot create an OpenGL ES 3 window");
    return 1;
  }
  glfwMakeContextCurrent(window);
  step("window + OpenGL ES context created");
  glfwSwapInterval(1);
  if (!gladLoadCustomLoader(reinterpret_cast<GLADloadfunc>(glfwGetProcAddress)))
  {
    out("error cannot load OpenGL");
    return 1;
  }
  step(std::string("OpenGL loaded: ") + reinterpret_cast<const char*>(glGetString(GL_VERSION)) +
       " / " + reinterpret_cast<const char*>(glGetString(GL_RENDERER)));
  auto renderContext = gpu::RenderContextGLImpl::MakeContext();
  if (!renderContext)
  {
    out("error the Rive renderer cannot run on this GPU");
    return 1;
  }
  auto* glImpl = renderContext->static_impl_cast<gpu::RenderContextGLImpl>();

  step("Rive renderer ready");

  // ── the .riv: artboard, state machine, view model + global view models ────
  ImportResult result;
  rcp<File> file = File::import(Span<const uint8_t>(bytes.data(), bytes.size()),
                                renderContext.get(), &result);
  if (!file)
  {
    out("error cannot import " + opt.riv);
    return 1;
  }
  step("file imported");
  std::unique_ptr<ArtboardInstance> artboard =
      opt.artboard.empty() ? file->artboardDefault() : file->artboardNamed(opt.artboard);
  if (!artboard)
  {
    out("error no artboard '" + opt.artboard + "'");
    return 1;
  }
  step("artboard '" + artboard->name() + "'");
  std::unique_ptr<StateMachineInstance> machine = artboard->defaultStateMachine();
  if (!machine)
    machine = artboard->stateMachineAt(0);
  if (!machine)
  {
    out("error artboard has no state machine");
    return 1;
  }
  step("state machine '" + machine->name() + "'");
  rcp<ViewModelInstance> vmi = file->createDefaultViewModelInstance(artboard.get());
  step(vmi ? "view model instance created" : "artboard has no view model");
  std::map<std::string, rcp<ViewModelInstance>> globals;
  if (vmi)
    machine->setViewModelInstance(vmi);
  for (const std::string& name : file->globalViewModelNames())
  {
    step("global view model '" + name + "'");
    auto global = file->createDefaultViewModelInstance(file->viewModel(name));
    if (global && machine->setGlobalViewModelInstance(name, global))
      globals[name] = global;
  }
  step("binding");
  machine->bind();
  step("artboard, state machine and view models bound");

  // ── layout: artboard → window ─────────────────────────────────────────────
  // The window manager may resize the window (Qtile pins the sidebar), so the
  // sizes are re-read every frame.
  int fbWidth = 0, fbHeight = 0;
  rcp<gpu::FramebufferRenderTargetGL> renderTarget;
  // copy present: offscreen framebuffer + an X11 image of the same size
  GLuint fbo = 0, colorBuffer = 0, depthStencil = 0;
  GLuint resolveFbo = 0, resolveColor = 0;  // single-sampled copy of an MSAA fbo
  Display* xDisplay = opt.copyPresent ? glfwGetX11Display() : nullptr;
  ::Window xWindow = opt.copyPresent ? glfwGetX11Window(window) : 0;
  GC xGC = opt.copyPresent ? XCreateGC(xDisplay, xWindow, 0, nullptr) : nullptr;
  XImage* xImage = nullptr;
  std::vector<uint8_t> pixels;            // RGBA from the GPU, bottom row first
  if (opt.copyPresent)
    step("present: copy (offscreen framebuffer → X11 image)");
  if (opt.msaa > 0)
    step("MSAA target: " + std::to_string(opt.msaa) + " samples");
  // storage for the bound renderbuffer, multisampled if asked for
  auto storage = [&](GLenum format, int samples) {
    if (samples > 0)
      glRenderbufferStorageMultisample(GL_RENDERBUFFER, samples, format, fbWidth, fbHeight);
    else
      glRenderbufferStorage(GL_RENDERBUFFER, format, fbWidth, fbHeight);
  };
  auto resize = [&]() {
    int w, h, fw, fh;
    glfwGetWindowSize(window, &w, &h);
    glfwGetFramebufferSize(window, &fw, &fh);
    if (renderTarget && fw == fbWidth && fh == fbHeight && w == opt.width && h == opt.height)
      return false;
    opt.width = w, opt.height = h, fbWidth = fw, fbHeight = fh;
    if (opt.copyPresent)
    {
      if (fbo)
      {
        GLuint fbos[] = {fbo, resolveFbo}, rbs[] = {colorBuffer, depthStencil, resolveColor};
        glDeleteFramebuffers(2, fbos);
        glDeleteRenderbuffers(3, rbs);
      }
      glGenFramebuffers(1, &fbo);
      glGenRenderbuffers(1, &colorBuffer);
      glGenRenderbuffers(1, &depthStencil);
      glBindRenderbuffer(GL_RENDERBUFFER, colorBuffer);
      storage(GL_RGBA8, opt.msaa);
      glBindRenderbuffer(GL_RENDERBUFFER, depthStencil);
      storage(GL_DEPTH24_STENCIL8, opt.msaa);
      glBindFramebuffer(GL_FRAMEBUFFER, fbo);
      glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, colorBuffer);
      glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT, GL_RENDERBUFFER, depthStencil);
      if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE)
        out("error offscreen framebuffer incomplete");
      resolveFbo = 0, resolveColor = 0;
      if (opt.msaa > 0)
      {
        glGenFramebuffers(1, &resolveFbo);
        glGenRenderbuffers(1, &resolveColor);
        glBindRenderbuffer(GL_RENDERBUFFER, resolveColor);
        storage(GL_RGBA8, 0);
        glBindFramebuffer(GL_FRAMEBUFFER, resolveFbo);
        glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, resolveColor);
      }
      glBindFramebuffer(GL_FRAMEBUFFER, 0);
      pixels.assign(static_cast<size_t>(fbWidth) * fbHeight * 4, 0);
      if (xImage)
        XDestroyImage(xImage);             // frees its pixel buffer too
      XWindowAttributes attrs;
      XGetWindowAttributes(xDisplay, xWindow, &attrs);
      xImage = XCreateImage(xDisplay, attrs.visual, attrs.depth, ZPixmap, 0,
                            reinterpret_cast<char*>(malloc(static_cast<size_t>(fbWidth) * fbHeight * 4)),
                            fbWidth, fbHeight, 32, 0);
    }
    renderTarget = make_rcp<gpu::FramebufferRenderTargetGL>(fbWidth, fbHeight, fbo, opt.msaa);
    glViewport(0, 0, fbWidth, fbHeight);
    if (opt.fit == Fit::layout)
    {
      artboard->width(static_cast<float>(opt.width));
      artboard->height(static_cast<float>(opt.height));
    }
    return true;
  };
  resize();
  auto viewTransform = [&]() {
    // window coordinates → artboard; the framebuffer may be scaled (HiDPI)
    return computeAlignment(opt.fit, opt.align, AABB(0, 0, opt.width, opt.height),
                            artboard->bounds());
  };

  // ── input: pointer → the state machine's listeners ────────────────────────
  struct Ctx
  {
    StateMachineInstance* machine;
    std::function<Mat2D()> view;
    bool dirty = true;
  } ctx{machine.get(), viewTransform};
  glfwSetWindowUserPointer(window, &ctx);
  // exposed again (mapped, uncovered): an X11 image isn't kept by the server
  glfwSetWindowRefreshCallback(window, [](GLFWwindow* w) {
    static_cast<Ctx*>(glfwGetWindowUserPointer(w))->dirty = true;
  });
  glfwSetCursorPosCallback(window, [](GLFWwindow* w, double, double) {
    auto* c = static_cast<Ctx*>(glfwGetWindowUserPointer(w));
    double x, y;
    glfwGetCursorPos(w, &x, &y);
    c->machine->pointerMove(c->view().invertOrIdentity() *
                            Vec2D(static_cast<float>(x), static_cast<float>(y)));
    c->dirty = true;
  });
  glfwSetMouseButtonCallback(window, [](GLFWwindow* w, int button, int action, int) {
    if (button != GLFW_MOUSE_BUTTON_LEFT)
      return;
    auto* c = static_cast<Ctx*>(glfwGetWindowUserPointer(w));
    double x, y;
    glfwGetCursorPos(w, &x, &y);
    Vec2D p = c->view().invertOrIdentity() * Vec2D(static_cast<float>(x), static_cast<float>(y));
    if (action == GLFW_PRESS)
      c->machine->pointerDown(p);
    else
      c->machine->pointerUp(p);
    c->dirty = true;
  });

  // ── commands from the controller ──────────────────────────────────────────
  std::map<std::string, float> watched;   // name → last reported value
  auto numberProp = [&](const std::string& name) -> ViewModelInstanceNumber* {
    auto* v = vmi ? vmi->propertyValue(name) : nullptr;
    return v && v->is<ViewModelInstanceNumber>() ? v->as<ViewModelInstanceNumber>() : nullptr;
  };
  auto handle = [&](const std::string& line) {
    std::istringstream words(line);
    std::string cmd, name;
    words >> cmd >> name;
    if (cmd == "number")
    {
      float value = 0;
      words >> value;
      if (auto* p = numberProp(name))
      {
        p->propertyValue(value);
        if (watched.count(name))
          watched[name] = value;   // set by the controller: not reported back
      }
      else
        out("error no number property '" + name + "'");
    }
    else if (cmd == "string")
    {
      std::string text;
      std::getline(words >> std::ws, text);
      auto* v = vmi ? vmi->propertyValue(name) : nullptr;
      if (v && v->is<ViewModelInstanceString>())
        v->as<ViewModelInstanceString>()->propertyValue(text);
      else
        out("error no string property '" + name + "'");
    }
    else if (cmd == "color")
    {
      std::string hex;
      words >> hex;
      auto slash = name.find('/');
      ColorInt argb;
      if (slash == std::string::npos || !parseColor(hex, &argb))
        return out("error bad color command: " + line);
      auto it = globals.find(name.substr(0, slash));
      auto* v = it == globals.end() ? nullptr : it->second->propertyValue(name.substr(slash + 1));
      if (v && v->is<ViewModelInstanceColor>())
        v->as<ViewModelInstanceColor>()->propertyValue(static_cast<int>(argb));
      // tokens the file doesn't have are skipped silently, like the web shell did
    }
    else if (cmd == "watch")
    {
      if (auto* p = numberProp(name))
        watched[name] = p->propertyValue();
      else
        out("error no number property '" + name + "'");
    }
    else if (cmd == "background")
    {
      parseColor(name, &opt.background);
    }
    ctx.dirty = true;
  };

  std::thread(readStdin).detach();
  out("ready " + std::string(artboard->name()) + " " +
      reinterpret_cast<const char*>(glGetString(GL_RENDERER)));

  // ── loop: advance + draw while something moves, otherwise sleep ────────────
  auto last = std::chrono::steady_clock::now();
  bool animating = true;
  while (!glfwWindowShouldClose(window))
  {
    if (animating || ctx.dirty)
      glfwPollEvents();
    else
      glfwWaitEvents();   // woken by input, stdin (glfwPostEmptyEvent) or expose

    std::deque<std::string> lines;
    {
      std::lock_guard<std::mutex> lock(g_inputMutex);
      lines.swap(g_input);
    }
    for (const auto& line : lines)
      handle(line);

    if (resize())
      ctx.dirty = true;

    auto now = std::chrono::steady_clock::now();
    float elapsed = std::chrono::duration<float>(now - last).count();
    last = now;
    if (!animating && !ctx.dirty)
      continue;
    animating = machine->advanceAndApply(std::min(elapsed, 0.1f));
    ctx.dirty = false;

    for (auto& [name, lastValue] : watched)
    {
      auto* p = numberProp(name);
      if (p && p->propertyValue() != lastValue)
      {
        lastValue = p->propertyValue();
        std::ostringstream msg;
        msg << "number " << name << " " << lastValue;
        out(msg.str());
      }
    }

    glImpl->invalidateGLState();
    renderContext->beginFrame({
        .renderTargetWidth = static_cast<uint32_t>(fbWidth),
        .renderTargetHeight = static_cast<uint32_t>(fbHeight),
        .loadAction = gpu::LoadAction::clear,
        .clearColor = opt.background,
        .msaaSampleCount = static_cast<uint32_t>(opt.msaa),
    });
    RiveRenderer renderer(renderContext.get());
    renderer.save();
    renderer.transform(Mat2D::fromScale(static_cast<float>(fbWidth) / opt.width,
                                        static_cast<float>(fbHeight) / opt.height) *
                       viewTransform());
    artboard->draw(&renderer);
    renderer.restore();
    renderContext->flush({.renderTarget = renderTarget.get()});
    glImpl->unbindGLInternalResources();
    if (!opt.copyPresent)
    {
      glfwSwapBuffers(window);
      continue;
    }
    // GPU → memory (RGBA, bottom row first) → X11 image (BGRX, top row first)
    GLuint readFbo = fbo;
    if (resolveFbo)
    {
      // MSAA can't be read directly: resolve into the single-sampled copy
      glBindFramebuffer(GL_READ_FRAMEBUFFER, fbo);
      glBindFramebuffer(GL_DRAW_FRAMEBUFFER, resolveFbo);
      glBlitFramebuffer(0, 0, fbWidth, fbHeight, 0, 0, fbWidth, fbHeight, GL_COLOR_BUFFER_BIT, GL_NEAREST);
      glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0);
      readFbo = resolveFbo;
    }
    glBindFramebuffer(GL_READ_FRAMEBUFFER, readFbo);
    glReadPixels(0, 0, fbWidth, fbHeight, GL_RGBA, GL_UNSIGNED_BYTE, pixels.data());
    glBindFramebuffer(GL_READ_FRAMEBUFFER, 0);
    auto* dst = reinterpret_cast<uint32_t*>(xImage->data);
    for (int y = 0; y < fbHeight; ++y)
    {
      const uint8_t* src = pixels.data() + static_cast<size_t>(fbHeight - 1 - y) * fbWidth * 4;
      for (int x = 0; x < fbWidth; ++x, src += 4)
        *dst++ = 0xff000000u | (uint32_t(src[0]) << 16) | (uint32_t(src[1]) << 8) | src[2];
    }
    XPutImage(xDisplay, xWindow, xGC, xImage, 0, 0, 0, 0, fbWidth, fbHeight);
    XFlush(xDisplay);
  }
  glfwTerminate();
  return 0;
}
