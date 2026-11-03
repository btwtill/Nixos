// homy-hmi — plays one artboard of a .riv file in a window, with Rive's native
// renderer on OpenGL ES (EGL). Knows nothing about Qtile or themes: whoever
// starts it drives it over stdin/stdout, one command per line.
//
//   homy-hmi --riv FILE [--artboard NAME] [--title TITLE] [--size WxH]
//            [--fit contain|layout|cover|fill] [--align center|topCenter]
//            [--background #RRGGBB]
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

#include <chrono>
#include <cstdio>
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
  std::unique_ptr<StateMachineInstance> machine = artboard->defaultStateMachine();
  if (!machine)
    machine = artboard->stateMachineAt(0);
  if (!machine)
  {
    out("error artboard has no state machine");
    return 1;
  }
  rcp<ViewModelInstance> vmi = file->createDefaultViewModelInstance(artboard.get());
  std::map<std::string, rcp<ViewModelInstance>> globals;
  if (vmi)
    machine->setViewModelInstance(vmi);
  for (const std::string& name : file->globalViewModelNames())
  {
    auto global = file->createDefaultViewModelInstance(file->viewModel(name));
    if (global && machine->setGlobalViewModelInstance(name, global))
      globals[name] = global;
  }
  machine->bind();
  step("artboard, state machine and view models bound");

  // ── layout: artboard → window ─────────────────────────────────────────────
  // The window manager may resize the window (Qtile pins the sidebar), so the
  // sizes are re-read every frame.
  int fbWidth = 0, fbHeight = 0;
  rcp<gpu::FramebufferRenderTargetGL> renderTarget;
  auto resize = [&]() {
    int w, h, fw, fh;
    glfwGetWindowSize(window, &w, &h);
    glfwGetFramebufferSize(window, &fw, &fh);
    if (renderTarget && fw == fbWidth && fh == fbHeight && w == opt.width && h == opt.height)
      return false;
    opt.width = w, opt.height = h, fbWidth = fw, fbHeight = fh;
    renderTarget = make_rcp<gpu::FramebufferRenderTargetGL>(fbWidth, fbHeight, 0, 0);
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
    glfwSwapBuffers(window);
  }
  glfwTerminate();
  return 0;
}
