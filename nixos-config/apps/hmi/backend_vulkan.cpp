// Vulkan backend: Rive renders into an offscreen Vulkan image (no swapchain),
// reads it back and hands it to the window as an X11 image (X11Copy). For the
// Pi 5: its Vulkan driver (v3dv) is conformant, where Rive's OpenGL ES path
// draws broken geometry, and the X11 copy sidesteps its GPU → X11 window path.
// Built after Rive's own headless test window
// (tests/common/testing_window_vulkan_texture.cpp).
//
// The frame is rendered in X11's byte order (BGRA) and read straight out of
// the mapped readback buffer, so the only per-frame copy on the CPU is the one
// X11Copy makes of the rows that changed. HOMY_HMI_VK_FORMAT=rgba renders RGBA
// instead (converted per pixel), should a driver not take BGRA.
#include "backend.hpp"

#include "rive/renderer/vulkan/render_context_vulkan_impl.hpp"
#include "rive/renderer/vulkan/render_target_vulkan.hpp"
#include "rive_vk_bootstrap/vulkan_device.hpp"
#include "rive_vk_bootstrap/vulkan_headless_frame_synchronizer.hpp"
#include "rive_vk_bootstrap/vulkan_instance.hpp"

#define GLFW_INCLUDE_NONE
#include <GLFW/glfw3.h>

#include <cstdlib>
#include <cstring>

using namespace rive;

namespace homy
{
namespace
{
constexpr VkImageUsageFlags kUsage =
    VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT;

class VulkanBackend final : public Backend
{
public:
  VulkanBackend(GLFWwindow* window,
                const BackendOptions& opt,
                std::unique_ptr<rive_vkb::VulkanInstance> instance,
                std::unique_ptr<rive_vkb::VulkanDevice> device,
                std::unique_ptr<gpu::RenderContext> context)
      : m_instance(std::move(instance)), m_device(std::move(device)), m_context(std::move(context)),
        m_copy(window), m_msaa(opt.msaa)
  {
    const char* format = std::getenv("HOMY_HMI_VK_FORMAT");
    if (format && std::strcmp(format, "rgba") == 0)
      m_format = VK_FORMAT_R8G8B8A8_UNORM;
    step(std::string("present: Vulkan offscreen image (") +
         (m_format == VK_FORMAT_B8G8R8A8_UNORM ? "BGRA" : "RGBA") + ") → X11 image");
  }

  ~VulkanBackend() override
  {
    m_sync = nullptr;   // first: it waits for in-flight command buffers
    m_context.reset();
    m_target.reset();
  }

  gpu::RenderContext* context() override { return m_context.get(); }
  std::string deviceName() const override { return m_device->name() + " (Vulkan)"; }
  uint32_t msaaSampleCount() const override { return static_cast<uint32_t>(m_msaa); }

  void resize(int width, int height) override
  {
    const uint64_t frame = m_sync ? m_sync->currentFrameNumber() : 0;
    m_sync = rive_vkb::VulkanHeadlessFrameSynchronizer::Create(
        *m_instance, *m_device, ref_rcp(impl()->vulkanContext()),
        rive_vkb::VulkanHeadlessFrameSynchronizer::Options{
            .width = static_cast<uint32_t>(width),
            .height = static_cast<uint32_t>(height),
            .imageFormat = m_format,
            .imageUsageFlags = kUsage,
            .initialFrameNumber = frame,
        });
    if (!m_sync)
      out("error cannot create the offscreen Vulkan image");
    m_target = impl()->makeRenderTarget(width, height, m_format, kUsage);
    m_copy.resize(width, height);
  }

  void invalidate() override { m_copy.invalidate(); }

  bool finishFrame() override
  {
    if (!m_sync)
      return false;
    const double t0 = nowMs();
    if (!m_sync->isFrameStarted())
    {
      if (m_sync->beginFrame() != VK_SUCCESS)
        return fail("vkBeginFrame");
      m_target->setTargetImageView(m_sync->vkImageView(), m_sync->vkImage(), m_sync->lastAccess());
    }
    m_context->flush({
        .renderTarget = m_target.get(),
        .externalCommandBuffer = m_sync->currentCommandBuffer(),
        .currentFrameNumber = m_sync->currentFrameNumber(),
        .safeFrameNumber = m_sync->safeFrameNumber(),
    });
    auto lastAccess = m_target->targetLastAccess();
    m_sync->queueImageCopy(&lastAccess);
    if (m_sync->endFrame(lastAccess) != VK_SUCCESS)
      return fail("endFrame");
    const double t1 = nowMs();
    // blocks until the GPU has drawn the frame and copied it into the buffer
    rive_vkb::VulkanFrameSynchronizer::MappedPixelRead read;
    if (m_sync->waitForPixelRead(&read) != VK_SUCCESS)
      return fail("reading the frame back");
    const double t2 = nowMs();
    m_times.changed = m_copy.present({read.data, static_cast<int>(read.strideBytes),
                                      /*bgra*/ read.format == VK_FORMAT_B8G8R8A8_UNORM, /*bottomUp*/ false});
    m_sync->finishPixelRead();
    m_times.flush = t1 - t0, m_times.gpu = t2 - t1, m_times.present = nowMs() - t2;
    return true;
  }

private:
  gpu::RenderContextVulkanImpl* impl() const
  {
    return m_context->static_impl_cast<gpu::RenderContextVulkanImpl>();
  }
  bool fail(const std::string& what)
  {
    out("error Vulkan: " + what + " failed");
    return false;
  }

  std::unique_ptr<rive_vkb::VulkanInstance> m_instance;
  std::unique_ptr<rive_vkb::VulkanDevice> m_device;
  std::unique_ptr<gpu::RenderContext> m_context;
  std::unique_ptr<rive_vkb::VulkanHeadlessFrameSynchronizer> m_sync;
  rcp<gpu::RenderTargetVulkanImpl> m_target;
  X11Copy m_copy;
  VkFormat m_format = VK_FORMAT_B8G8R8A8_UNORM;
  int m_msaa = 0;
};
} // namespace

void vulkanWindowHints()
{
  glfwWindowHint(GLFW_CLIENT_API, GLFW_NO_API);   // a plain X11 window; Vulkan renders offscreen
}

std::unique_ptr<Backend> makeVulkanBackend(GLFWwindow* window, const BackendOptions& opt)
{
  auto instance = rive_vkb::VulkanInstance::Create({.appName = "homy-hmi"});
  if (!instance)
  {
    out("error no Vulkan instance (is a Vulkan driver installed?)");
    return nullptr;
  }
  auto device = rive_vkb::VulkanDevice::Create(*instance, {.headless = true});
  if (!device)
  {
    out("error no Vulkan device");
    return nullptr;
  }
  step("Vulkan device: " + device->name());
  auto context = gpu::RenderContextVulkanImpl::MakeContext(
      instance->vkInstance(), device->vkPhysicalDevice(), device->vkDevice(), device->vulkanFeatures(),
      instance->getVkGetInstanceProcAddrPtr());
  if (!context)
  {
    out("error the Rive renderer cannot run on this GPU (Vulkan)");
    return nullptr;
  }
  return std::make_unique<VulkanBackend>(window, opt, std::move(instance), std::move(device), std::move(context));
}
} // namespace homy
