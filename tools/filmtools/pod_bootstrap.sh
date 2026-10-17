#!/bin/bash
# Set up a fresh RunPod GPU pod (Ubuntu 22.04 + CUDA image) for Blender renders. Run on the pod as root:
#   ssh root@<pod> -p <port> 'bash -s' < tools/filmtools/pod_bootstrap.sh
# Installs Blender 5.2.2 under /opt and the X/GL libraries Blender links against even when headless, then prints the
# Cycles GPU devices it can see.
set -euo pipefail
BL=blender-5.2.2-linux-x64
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq libsm6 libice6 libgl1 libegl1 libxi6 libxxf86vm1 libxfixes3 libxrender1 libxkbcommon0 \
  xz-utils rsync ffmpeg >/dev/null
if [ ! -x /opt/$BL/blender ]; then
  curl -sSfL https://download.blender.org/release/Blender5.2/$BL.tar.xz | tar xJ -C /opt
fi
ln -sf /opt/$BL/blender /usr/local/bin/blender
blender --version | head -1
blender -b --factory-startup --python-expr '
import bpy
p = bpy.context.preferences.addons["cycles"].preferences
for t in ("OPTIX", "CUDA"):
    try:
        p.compute_device_type = t
        p.get_devices()
        print(t, [d.name for d in p.devices if d.type == t])
    except TypeError:
        pass
' 2>/dev/null | grep -E '^(OPTIX|CUDA)'
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
