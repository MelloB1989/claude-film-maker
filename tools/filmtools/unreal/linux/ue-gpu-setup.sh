#!/bin/bash
# Prepare an Ubuntu 22.04 NVIDIA GPU instance (g6/g5/g4dn) to run the Unreal editor offscreen on Vulkan:
# the NVIDIA 580 server driver from Ubuntu's prebuilt, signed kernel modules (no DKMS build), its Vulkan ICD (switched
# to the EGL library, which works without an X server),
# vulkan-tools, and the libraries the editor loads at runtime; then checks nvidia-smi and vulkaninfo (RT extensions).
#
#   sudo bash ue-gpu-setup.sh            (UE_NVIDIA=580 by default; agent research: avoid 570 and 595)
set -uo pipefail
V=${UE_NVIDIA:-580}
export DEBIAN_FRONTEND=noninteractive
t0=$(date +%s)
apt-get -o DPkg::Lock::Timeout=900 update -qq
apt-get -o DPkg::Lock::Timeout=900 install -y -qq --no-install-recommends "linux-modules-nvidia-$V-server-$(uname -r)" "nvidia-utils-$V-server" \
  "libnvidia-gl-$V-server" "nvidia-compute-utils-$V-server" vulkan-tools libvulkan1 mesa-vulkan-drivers- \
  libnss3 libatk1.0-0 libatk-bridge2.0-0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 libxkbcommon0 \
  libxcursor1 libxi6 libsdl2-2.0-0 zstd jq unzip >/dev/null
modprobe nvidia; modprobe nvidia_uvm || true; modprobe nvidia_drm modeset=1 || true
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
nvidia-smi -pm 1 >/dev/null || true
# Headless (no X server): the packaged Vulkan ICD points at libGLX_nvidia, whose vkCreateInstance fails without a
# display (ERROR_INCOMPATIBLE_DRIVER). The EGL library carries the same Vulkan driver and works headless.
icd=/usr/share/vulkan/icd.d/nvidia_icd.json
if grep -q libGLX_nvidia "$icd" 2>/dev/null; then
  dpkg-divert --quiet --local --rename --add "$icd"
  sed 's/libGLX_nvidia.so.0/libEGL_nvidia.so.0/' "$icd.distrib" > "$icd"
fi
echo "vulkan:"; vulkaninfo --summary 2>/dev/null | grep -E 'apiVersion|driverVersion|deviceName|driverName' | sed 's/^/  /'
for e in VK_KHR_ray_tracing_pipeline VK_KHR_acceleration_structure VK_KHR_ray_query VK_KHR_deferred_host_operations; do
  vulkaninfo 2>/dev/null | grep -q "$e" && echo "  $e: yes" || echo "  $e: MISSING"
done
echo "gpu setup done in $(( $(date +%s) - t0 ))s"
