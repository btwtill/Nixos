// homy-hmi — plays one artboard of a .riv file in a window, with Rive's native
// renderer. Knows nothing about Qtile or themes: whoever starts it drives it
// over stdin/stdout, one command per line.
//
//   homy-hmi --riv FILE [--artboard NAME] [--title TITLE] [--size WxH]
//            [--fit contain|layout|cover|fill|none] [--align center|topCenter]
//            [--background #RRGGBB] [--backend gl|vulkan] [--present gl|copy] [--msaa N]
//
// stdin                                   stdout
//   number <path> <value>                   ready <artboard> <GPU>
//   string <path> <text…>                   number <path> <value>   (a watched
//   color <ViewModel>/<name> <#RRGGBB[AA]>    number changed inside the file,
//   watch <path>                              e.g. a tap wrote activeIndex)
//   background <#RRGGBB>                    error <message>
//
// <path> is a property of the artboard's view model; a slash descends into a
// nested view model (sidebar/activeIndex). color addresses a global view model
// (e.g. Theme/accent). Draws only while something changes.
//
// --backend (or HOMY_HMI_BACKEND): which GPU API Rive draws with (backend.hpp).
//   gl      OpenGL ES via EGL (default). The VM.
//   vulkan  Vulkan, offscreen, handed to the window as an X11 image. The Pi 5:
//           Rive's OpenGL ES path draws broken geometry on its V3D.
// GL only:
//   --present copy (HOMY_HMI_PRESENT=copy): render offscreen, hand the frame
//     to the window as an X11 image instead of swapping the GL window surface.
//
// How Rive draws (its "interlock mode", printed once at the start). Rive picks
// the best the GPU offers; these force another one, to compare their speed:
//   --msaa N (HOMY_HMI_MSAA): a multisampled target with N samples (mode msaa).
//   HOMY_HMI_CLOCKWISE=1: the clockwise modes, where the GPU has them.
//   HOMY_HMI_NO_RASTER_ORDERING=1: atomic mode instead of raster ordering.
// HOMY_HMI_BENCH=1: redraw every frame even when nothing moves, so the stats
//   measure the cost of a full frame without anyone tapping.
//   HOMY_HMI_GLDEBUG=1: GL extensions + driver messages + glGetError on stderr.
//
// --fps N (HOMY_HMI_FPS, default 60): at most N frames per second while
//   something animates; input in between is collected into the next frame.
// HOMY_HMI_STATS=1: every 2 s of animation one line on stderr saying where the
//   frames' time went: "stats: 58 fps, frame 9.1 ms (max 14.0): advance 0.4,
//   draw 1.9, flush 0.8, gpu 3.1, present 2.9; changed 4%".

#include "backend.hpp"

#include "rive/animation/state_machine_instance.hpp"
#include "rive/artboard.hpp"
#include "rive/file.hpp"
#include "rive/layout.hpp"
#include "rive/renderer.hpp"
#include "rive/renderer/render_context.hpp"
#include "rive/renderer/rive_renderer.hpp"
#include "rive/viewmodel/viewmodel_instance.hpp"
#include "rive/viewmodel/viewmodel_instance_color.hpp"
#include "rive/viewmodel/viewmodel_instance_number.hpp"
#include "rive/viewmodel/viewmodel_instance_string.hpp"
#include "rive/viewmodel/viewmodel_instance_viewmodel.hpp"

#define GLFW_INCLUDE_NONE
#include <GLFW/glfw3.h>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
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
using homy::out;
using homy::step;

namespace homy
{
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

double nowMs()
{
  return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
} // namespace homy

namespace
{
struct Options
{
  std::string riv, artboard, title = "Homy HMI";
  int width = 1024, height = 600;
  Fit fit = Fit::contain;
  Alignment align = Alignment::center;
  ColorInt background = 0xff1e1e1e;
  bool vulkan = false;
  int fps = 60;
  bool stats = false;
  bool clockwise = false, noRasterOrdering = false, bench = false;
  homy::BackendOptions backend;
};

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
            : v == "fill" ? Fit::fill : v == "none" ? Fit::none : Fit::contain;
    else if (k == "--align")
      o.align = v == "topCenter" ? Alignment::topCenter : Alignment::center;
    else if (k == "--background") parseColor(v, &o.background);
    else if (k == "--backend") o.vulkan = v == "vulkan";
    else if (k == "--present") o.backend.copyPresent = v == "copy";
    else if (k == "--msaa") o.backend.msaa = std::atoi(v.c_str());
    else if (k == "--fps") o.fps = std::atoi(v.c_str());
  }
  auto env = [](const char* name) { const char* v = std::getenv(name); return std::string(v ? v : ""); };
  o.vulkan = o.vulkan || env("HOMY_HMI_BACKEND") == "vulkan";
  o.backend.copyPresent = o.backend.copyPresent || env("HOMY_HMI_PRESENT") == "copy";
  if (!o.backend.msaa)
    o.backend.msaa = std::atoi(env("HOMY_HMI_MSAA").c_str());
  o.backend.glDebug = !env("HOMY_HMI_GLDEBUG").empty();
  if (!env("HOMY_HMI_FPS").empty())
    o.fps = std::atoi(env("HOMY_HMI_FPS").c_str());
  if (o.fps < 1)
    o.fps = 60;
  o.stats = !env("HOMY_HMI_STATS").empty();
  o.bench = !env("HOMY_HMI_BENCH").empty();
  o.stats = o.stats || o.bench;
  o.clockwise = !env("HOMY_HMI_CLOCKWISE").empty();
  o.noRasterOrdering = !env("HOMY_HMI_NO_RASTER_ORDERING").empty();
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

// "a/b/c": through nested view models a and b to the property c
ViewModelInstanceValue* propertyAt(rcp<ViewModelInstance> vmi, const std::string& path)
{
  std::string::size_type start = 0, slash;
  while (vmi && (slash = path.find('/', start)) != std::string::npos)
  {
    auto* nested = vmi->propertyValue(path.substr(start, slash - start));
    vmi = nested && nested->is<ViewModelInstanceViewModel>()
              ? nested->as<ViewModelInstanceViewModel>()->referenceViewModelInstance()
              : nullptr;
    start = slash + 1;
  }
  return vmi ? vmi->propertyValue(path.substr(start)) : nullptr;
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

  // ── window + GPU backend ──────────────────────────────────────────────────
  if (!glfwInit())
  {
    out("error glfwInit failed");
    return 1;
  }
  if (opt.vulkan)
    homy::vulkanWindowHints();
  else
    homy::glWindowHints(opt.backend);
  glfwWindowHint(GLFW_DECORATED, GLFW_FALSE);
  glfwWindowHint(GLFW_RESIZABLE, GLFW_FALSE);
  GLFWwindow* window = glfwCreateWindow(opt.width, opt.height, opt.title.c_str(), nullptr, nullptr);
  if (!window)
  {
    out(std::string("error cannot create a window for ") + (opt.vulkan ? "Vulkan" : "OpenGL ES 3"));
    return 1;
  }
  step(std::string("window created, backend ") + (opt.vulkan ? "Vulkan" : "OpenGL ES"));
  std::unique_ptr<homy::Backend> backend =
      opt.vulkan ? homy::makeVulkanBackend(window, opt.backend) : homy::makeGLBackend(window, opt.backend);
  if (!backend)
    return 1;
  gpu::RenderContext* renderContext = backend->context();
  step("Rive renderer ready");

  // ── the .riv: artboard, state machine, view model + global view models ────
  ImportResult result;
  rcp<File> file = File::import(Span<const uint8_t>(bytes.data(), bytes.size()), renderContext, &result);
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
  auto resize = [&]() {
    int w, h, fw, fh;
    glfwGetWindowSize(window, &w, &h);
    glfwGetFramebufferSize(window, &fw, &fh);
    if (fbWidth && fw == fbWidth && fh == fbHeight && w == opt.width && h == opt.height)
      return false;
    opt.width = w, opt.height = h, fbWidth = fw, fbHeight = fh;
    backend->resize(fbWidth, fbHeight);
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
    bool exposed = false;
  } ctx{machine.get(), viewTransform};
  glfwSetWindowUserPointer(window, &ctx);
  // exposed again (mapped, uncovered): an X11 image isn't kept by the server
  glfwSetWindowRefreshCallback(window, [](GLFWwindow* w) {
    auto* c = static_cast<Ctx*>(glfwGetWindowUserPointer(w));
    c->dirty = c->exposed = true;
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
  std::map<std::string, float> watched;   // path → last reported value
  auto numberProp = [&](const std::string& path) -> ViewModelInstanceNumber* {
    auto* v = propertyAt(vmi, path);
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
      auto* v = propertyAt(vmi, name);
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
  out("ready " + std::string(artboard->name()) + " " + backend->deviceName());

  // ── loop: advance + draw while something moves, otherwise sleep ────────────
  // At most opt.fps frames per second: input and commands arriving in between
  // are applied right away and drawn with the next frame.
  const double frameInterval = 1.0 / opt.fps;
  double nextFrame = 0;                 // glfwGetTime() the next frame may start at
  double lastAdvance = glfwGetTime();   // … the state machine was last advanced at
  bool animating = true;
  bool modeReported = false;
  struct
  {
    int frames = 0;
    double since = 0, span = 0, last = 0, advance = 0, draw = 0, flush = 0, gpu = 0, present = 0, changed = 0, total = 0, worst = 0;
  } stats;
  while (!glfwWindowShouldClose(window))
  {
    if (!animating && !ctx.dirty)
    {
      glfwWaitEvents();   // woken by input, stdin (glfwPostEmptyEvent) or expose
      lastAdvance = glfwGetTime();   // time spent idle is not animation time
    }
    else if (double wait = nextFrame - glfwGetTime(); wait > 0.0005)
      glfwWaitEventsTimeout(wait);
    else
      glfwPollEvents();

    std::deque<std::string> lines;
    {
      std::lock_guard<std::mutex> lock(g_inputMutex);
      lines.swap(g_input);
    }
    for (const auto& line : lines)
      handle(line);

    if (resize())
      ctx.dirty = true;
    if (!animating && !ctx.dirty)
      continue;
    const double frameStart = glfwGetTime();
    if (frameStart < nextFrame - 0.0005)
      continue;   // woken early: keep collecting input until the frame is due
    nextFrame = frameStart + frameInterval;
    const float elapsed = static_cast<float>(frameStart - lastAdvance);
    lastAdvance = frameStart;

    const double t0 = homy::nowMs();
    animating = machine->advanceAndApply(std::min(elapsed, 0.1f)) || opt.bench;
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

    const double t1 = homy::nowMs();
    if (ctx.exposed)
    {
      backend->invalidate();
      ctx.exposed = false;
    }
    backend->prepareFrame();
    renderContext->beginFrame({
        .renderTargetWidth = static_cast<uint32_t>(fbWidth),
        .renderTargetHeight = static_cast<uint32_t>(fbHeight),
        .loadAction = gpu::LoadAction::clear,
        .clearColor = opt.background,
        .msaaSampleCount = backend->msaaSampleCount(),
        .disableRasterOrdering = opt.noRasterOrdering,
        .clockwiseFillOverride = opt.clockwise,
    });
    if (!modeReported)
    {
      modeReported = true;
      const char* mode = "?";
      switch (renderContext->frameInterlockMode())
      {
        case gpu::InterlockMode::rasterOrdering: mode = "rasterOrdering"; break;
        case gpu::InterlockMode::atomics: mode = "atomics"; break;
        case gpu::InterlockMode::clockwise: mode = "clockwise"; break;
        case gpu::InterlockMode::clockwiseAtomic: mode = "clockwiseAtomic"; break;
        case gpu::InterlockMode::depthStencil: mode = "msaa (depthStencil)"; break;
      }
      const gpu::PlatformFeatures& f = renderContext->platformFeatures();
      step(std::string("Rive draw mode: ") + mode + "  (GPU offers:" +
           (f.supportsRasterOrderingMode ? " rasterOrdering" : "") + (f.supportsAtomicMode ? " atomics" : "") +
           (f.supportsClockwiseMode ? " clockwise" : "") +
           (f.supportsClockwiseAtomicMode ? " clockwiseAtomic" : "") + " msaa)");
    }
    RiveRenderer renderer(renderContext);
    renderer.save();
    renderer.transform(Mat2D::fromScale(static_cast<float>(fbWidth) / opt.width,
                                        static_cast<float>(fbHeight) / opt.height) *
                       viewTransform());
    artboard->draw(&renderer);
    renderer.restore();
    const double t2 = homy::nowMs();
    backend->finishFrame();

    if (opt.stats)
    {
      const double t3 = homy::nowMs();
      const homy::FrameTimes& f = backend->frameTimes();
      if (stats.frames == 0)
        stats.since = t0;
      else
        stats.span += std::min(t0 - stats.last, 100.0);   // pauses don't count against the frame rate
      stats.last = t0;
      ++stats.frames;
      stats.advance += t1 - t0, stats.draw += t2 - t1;
      stats.flush += f.flush, stats.gpu += f.gpu, stats.present += f.present, stats.changed += f.changed;
      stats.total += t3 - t0, stats.worst = std::max(stats.worst, t3 - t0);
      if (t3 - stats.since >= 2000)
      {
        const double n = stats.frames;
        if (stats.frames >= 10)   // not for a lone frame now and then (the clock)
        {
          char line[256];
          std::snprintf(line, sizeof line,
                        "stats: %.0f fps, frame %.1f ms (max %.1f): advance %.1f, draw %.1f, flush %.1f, "
                        "gpu %.1f, present %.1f; changed %.0f%%",
                        stats.span > 0 ? (n - 1) * 1000 / stats.span : 0.0, stats.total / n, stats.worst, stats.advance / n,
                        stats.draw / n, stats.flush / n, stats.gpu / n, stats.present / n,
                        100 * stats.changed / n);
          step(line);
        }
        stats = {};
      }
    }
  }
  backend.reset();
  glfwTerminate();
  return 0;
}
