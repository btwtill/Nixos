// OpenGL ES backend (EGL, through GLFW). Works on the VM (Mesa llvmpipe); on the
// Pi 5's V3D Rive's GL path draws broken geometry — use the Vulkan backend there.
#include "backend.hpp"

#include "rive/renderer/gl/render_context_gl_impl.hpp"
#include "rive/renderer/gl/render_target_gl.hpp"

#include "glad_custom.h"
#define GLFW_INCLUDE_NONE
#include <GLFW/glfw3.h>

#include <iostream>

using namespace rive;

namespace homy
{
namespace
{
void GLAD_API_PTR glDebug(GLenum, GLenum, GLuint, GLenum, GLsizei, const GLchar* message, const void*)
{
  std::cerr << "gl: " << message << std::endl;
}

class GLBackend final : public Backend
{
public:
  GLBackend(GLFWwindow* window, const BackendOptions& opt, std::unique_ptr<gpu::RenderContext> context)
      : m_window(window), m_opt(opt), m_context(std::move(context)),
        m_impl(m_context->static_impl_cast<gpu::RenderContextGLImpl>())
  {
    if (m_opt.copyPresent)
    {
      m_copy = std::make_unique<X11Copy>(window);
      step("present: copy (offscreen framebuffer → X11 image)");
    }
    if (m_opt.msaa > 0)
      step("MSAA target: " + std::to_string(m_opt.msaa) + " samples");
  }

  gpu::RenderContext* context() override { return m_context.get(); }
  std::string deviceName() const override
  {
    return reinterpret_cast<const char*>(glGetString(GL_RENDERER));
  }
  uint32_t msaaSampleCount() const override { return static_cast<uint32_t>(m_opt.msaa); }

  void resize(int width, int height) override
  {
    m_width = width, m_height = height;
    if (m_opt.copyPresent)
    {
      // offscreen framebuffer (multisampled if asked for) + its resolve target
      if (m_fbo)
      {
        GLuint fbos[] = {m_fbo, m_resolveFbo}, rbs[] = {m_color, m_depthStencil, m_resolveColor};
        glDeleteFramebuffers(2, fbos);
        glDeleteRenderbuffers(3, rbs);
      }
      glGenFramebuffers(1, &m_fbo);
      glGenRenderbuffers(1, &m_color);
      glGenRenderbuffers(1, &m_depthStencil);
      glBindRenderbuffer(GL_RENDERBUFFER, m_color);
      storage(GL_RGBA8, m_opt.msaa);
      glBindRenderbuffer(GL_RENDERBUFFER, m_depthStencil);
      storage(GL_DEPTH24_STENCIL8, m_opt.msaa);
      glBindFramebuffer(GL_FRAMEBUFFER, m_fbo);
      glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, m_color);
      glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT, GL_RENDERBUFFER, m_depthStencil);
      if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE)
        out("error offscreen framebuffer incomplete");
      m_resolveFbo = 0, m_resolveColor = 0;
      if (m_opt.msaa > 0)
      {
        glGenFramebuffers(1, &m_resolveFbo);
        glGenRenderbuffers(1, &m_resolveColor);
        glBindRenderbuffer(GL_RENDERBUFFER, m_resolveColor);
        storage(GL_RGBA8, 0);
        glBindFramebuffer(GL_FRAMEBUFFER, m_resolveFbo);
        glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, m_resolveColor);
      }
      glBindFramebuffer(GL_FRAMEBUFFER, 0);
      m_pixels.assign(static_cast<size_t>(width) * height * 4, 0);
      m_copy->resize(width, height);
    }
    m_target = make_rcp<gpu::FramebufferRenderTargetGL>(width, height, m_fbo, m_opt.msaa);
    glViewport(0, 0, width, height);
  }

  void prepareFrame() override { m_impl->invalidateGLState(); }

  bool finishFrame() override
  {
    m_context->flush({.renderTarget = m_target.get()});
    m_impl->unbindGLInternalResources();
    if (m_opt.glDebug)
      for (GLenum err; (err = glGetError()) != GL_NO_ERROR;)
        std::cerr << "gl: glGetError 0x" << std::hex << err << std::dec << std::endl;
    if (!m_opt.copyPresent)
    {
      glfwSwapBuffers(m_window);
      return true;
    }
    GLuint readFbo = m_fbo;
    if (m_resolveFbo)
    {
      // MSAA can't be read directly: resolve into the single-sampled copy
      glBindFramebuffer(GL_READ_FRAMEBUFFER, m_fbo);
      glBindFramebuffer(GL_DRAW_FRAMEBUFFER, m_resolveFbo);
      glBlitFramebuffer(0, 0, m_width, m_height, 0, 0, m_width, m_height, GL_COLOR_BUFFER_BIT, GL_NEAREST);
      glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0);
      readFbo = m_resolveFbo;
    }
    glBindFramebuffer(GL_READ_FRAMEBUFFER, readFbo);
    glReadPixels(0, 0, m_width, m_height, GL_RGBA, GL_UNSIGNED_BYTE, m_pixels.data());
    glBindFramebuffer(GL_READ_FRAMEBUFFER, 0);
    m_copy->present(m_pixels);
    return true;
  }

private:
  void storage(GLenum format, int samples)
  {
    if (samples > 0)
      glRenderbufferStorageMultisample(GL_RENDERBUFFER, samples, format, m_width, m_height);
    else
      glRenderbufferStorage(GL_RENDERBUFFER, format, m_width, m_height);
  }

  GLFWwindow* m_window;
  BackendOptions m_opt;
  std::unique_ptr<gpu::RenderContext> m_context;
  gpu::RenderContextGLImpl* m_impl;
  rcp<gpu::FramebufferRenderTargetGL> m_target;
  std::unique_ptr<X11Copy> m_copy;
  GLuint m_fbo = 0, m_color = 0, m_depthStencil = 0;
  GLuint m_resolveFbo = 0, m_resolveColor = 0;   // single-sampled copy of an MSAA fbo
  std::vector<uint8_t> m_pixels;                 // RGBA from the GPU, bottom row first
  int m_width = 0, m_height = 0;
};
} // namespace

void glWindowHints(const BackendOptions& opt)
{
  glfwWindowHint(GLFW_CONTEXT_CREATION_API, GLFW_EGL_CONTEXT_API);
  glfwWindowHint(GLFW_CLIENT_API, GLFW_OPENGL_ES_API);
  glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
  glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 0);
  glfwWindowHint(GLFW_STENCIL_BITS, 8);
  if (opt.msaa > 0 && !opt.copyPresent)
    glfwWindowHint(GLFW_SAMPLES, opt.msaa);
}

std::unique_ptr<Backend> makeGLBackend(GLFWwindow* window, const BackendOptions& opt)
{
  glfwMakeContextCurrent(window);
  glfwSwapInterval(1);
  if (!gladLoadCustomLoader(reinterpret_cast<GLADloadfunc>(glfwGetProcAddress)))
  {
    out("error cannot load OpenGL");
    return nullptr;
  }
  step(std::string("OpenGL loaded: ") + reinterpret_cast<const char*>(glGetString(GL_VERSION)) +
       " / " + reinterpret_cast<const char*>(glGetString(GL_RENDERER)));
  if (opt.glDebug)
  {
    GLint count = 0;
    glGetIntegerv(GL_NUM_EXTENSIONS, &count);
    std::string extensions;
    for (GLint i = 0; i < count; ++i)
      extensions += std::string(" ") + reinterpret_cast<const char*>(glGetStringi(GL_EXTENSIONS, i));
    step("GL extensions:" + extensions);
    if (GLAD_GL_KHR_debug)
    {
      glEnable(GL_DEBUG_OUTPUT_KHR);
      glEnable(GL_DEBUG_OUTPUT_SYNCHRONOUS_KHR);
      glDebugMessageControlKHR(GL_DONT_CARE, GL_DONT_CARE, GL_DONT_CARE, 0, nullptr, GL_TRUE);
      glDebugMessageCallbackKHR(&glDebug, nullptr);
      step("GL debug output on");
    }
    else
      step("no KHR_debug: only glGetError after each frame");
  }
  auto context = gpu::RenderContextGLImpl::MakeContext();
  if (!context)
  {
    out("error the Rive renderer cannot run on this GPU (OpenGL ES)");
    return nullptr;
  }
  return std::make_unique<GLBackend>(window, opt, std::move(context));
}
} // namespace homy
