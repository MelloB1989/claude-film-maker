#!/usr/bin/env bash
# Set up a Linux GPU box (Ubuntu 22.04, EC2 G6/Gr6 family) to run the Unreal editor with no desktop. Run as root; every
# step is idempotent, so a step can be rerun after a failure or a reboot. film-ue copies this file to the box and runs
# the steps over SSM (tools/filmtools/unreal/linuxbox.py); by hand: sudo bash setup.sh <step> [args].
#
#   volume [MOUNT]                 format (first time only) and mount the empty data disk at MOUNT (/srv/ue)
#   driver [BRANCH]                NVIDIA datacenter driver (580-server by default) + Vulkan; prints reboot=needed
#   engine S3_ROOT VERSION DEST    the engine from S3 with the build's ue-restore.sh (DEST e.g. /srv/ue/engine)
#   project S3_PREFIX DIR          the project folder from S3 (Content, Config, the .uproject; no Saved/DDC)
#   windisk [MOUNT]                mount a Windows volume (an EBS copy of a workstation's snapshot) read-only
#   project-copy SRC DIR           the project folder from a mounted disk (SRC e.g. /mnt/win/UEProjects/Name)
#   service ENGINE UPROJECT [MAP] [EPIC_S3]
#                                  /etc/default/ue-editor, /usr/local/bin/ue-editor + ue-epic, ue-editor.service
#                                  (enabled); EPIC_S3: where the Epic sign-in is kept (ue-epic.sh), restored now
#   epic restore|save|status|code  the editor user's Epic sign-in, from/to EPIC_S3 (ue-epic.sh)
#   mode default|offscreen|xvfb    the editor's display mode (ue-editor.sh), then restart it
#   desktop on|off                 a temporary desktop for one interactive step (a sign-in): Xorg on the GPU with a
#                                  virtual screen, openbox, a browser, x11vnc on 127.0.0.1:5900 (reached only through
#                                  an SSM port-forward), the editor restarted onto it; off puts it back offscreen
#   watchdog TTL_UNTIL IDLE_MIN STALL_MIN [PROJECT_DIR]
#                                  the box's watchdog (ue_watchdog.py, every minute): power off past TTL_UNTIL (epoch,
#                                  0 = none) or after IDLE_MIN idle minutes, restart an editor stalled STALL_MIN minutes
#   rhi PROJECT_DIR                the project targets Vulkan SM6 on Linux (Config/DefaultEngine.ini): without it the
#                                  editor runs VULKAN_SM5 and misses the SM6 DDC; prints rhi=set or rhi=ok
#   plugin TGZ ENGINE PROJECT_DIR  build a C++ plugin (a .tgz of its folder: NAME/NAME.uplugin, Source/) against the
#                                  restored engine and install it in PROJECT_DIR/Plugins (the editor loads it on its
#                                  next start). The engine is marked installed while UBT runs, so only the plugin's
#                                  modules compile (seconds) instead of the whole engine (the tarball has no engine
#                                  Intermediate: ~6000 actions); built in a scratch project, so a failed build never
#                                  leaves the real project unable to start
#   check                          GPU, Vulkan, engine binary, unit state, as key=value lines
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
UE_USER="${UE_USER:-ubuntu}"
export DEBIAN_FRONTEND=noninteractive

step_volume() {
    local mnt="${1:-/srv/ue}" root dev
    if mountpoint -q "$mnt"; then echo "volume: $mnt already mounted"; return; fi
    root="$(lsblk -no PKNAME "$(findmnt -no SOURCE /)")"
    # the data disk: a whole disk, not the root disk, with no partitions (EBS volumes show as nvme*n1 on Nitro)
    # never the instance store (g6/g5 local NVMe, model "Amazon EC2 NVMe Instance Storage"): a stop or a hibernate
    # wipes it, and /srv/ue then loses the engine, the project and every render (round 4, 06 Nov)
    dev="$(lsblk -dpno NAME,TYPE | awk '$2=="disk"{print $1}' | while read -r d; do
        [ "$(basename "$d")" = "$root" ] && continue
        case "$(cat "/sys/block/$(basename "$d")/device/model" 2>/dev/null)" in *"Instance Storage"*) continue ;; esac
        [ "$(lsblk -no NAME "$d" | wc -l)" -eq 1 ] && echo "$d"; done | head -1)"
    if [ -z "$dev" ]; then
        # no EBS data volume: a plain directory on the root EBS, which survives a stop
        mkdir -p "$mnt"; chown "$UE_USER:$UE_USER" "$mnt"
        echo "volume: no EBS data disk; $mnt is a directory on the root disk ($(df -h --output=avail / | tail -1 | tr -d ' ') free)"
        return
    fi
    blkid "$dev" >/dev/null 2>&1 || mkfs.ext4 -q -L ue-data "$dev"
    mkdir -p "$mnt"
    grep -q "LABEL=ue-data" /etc/fstab || echo "LABEL=ue-data $mnt ext4 defaults,noatime,nofail 0 2" >> /etc/fstab
    mount "$mnt"
    chown "$UE_USER:$UE_USER" "$mnt"
    echo "volume: $dev on $mnt"
}

step_driver() {
    local branch="${1:-580-server}"
    if nvidia-smi >/dev/null 2>&1; then
        echo "driver: $(nvidia-smi --query-gpu=name,driver_version --format=csv,noheader)"
    else
        apt-get update -qq
        apt-get install -y -qq ubuntu-drivers-common >/dev/null
        # the signed kernel modules for this kernel + the full userspace (GL/Vulkan ICD), not the headless compute set
        ubuntu-drivers install "nvidia:$branch"
        echo "driver: nvidia $branch installed; reboot needed"
    fi
    apt-get install -y -qq libvulkan1 vulkan-tools xdg-user-dirs >/dev/null
    # the modules must match the RUNNING kernel: ubuntu-drivers can pull modules for a newer kernel only (round 4:
    # modules for 6.8.0-1069 on a box still booted into 1066, so no GPU until linux-modules-nvidia-*-$(uname -r))
    nvidia-smi >/dev/null 2>&1 || apt-get install -y -qq "linux-modules-nvidia-$branch-$(uname -r)" >/dev/null 2>&1 && modprobe nvidia 2>/dev/null || true
    # headless: the packaged Vulkan ICD points at libGLX_nvidia, which fails without an X server
    # (ERROR_INCOMPATIBLE_DRIVER, the editor falls back to llvmpipe); the EGL library carries the same driver
    local icd=/usr/share/vulkan/icd.d/nvidia_icd.json
    if grep -q libGLX_nvidia "$icd" 2>/dev/null; then
        dpkg-divert --quiet --local --rename --add "$icd"
        sed 's/libGLX_nvidia.so.0/libEGL_nvidia.so.0/' "$icd.distrib" > "$icd"
        echo "driver: Vulkan ICD diverted to libEGL_nvidia (headless)"
    fi
    # the editor's shared libraries a minimal server image lacks (an installed or source-built Linux engine links
    # Slate/CEF against them: without libpango/libcairo UnrealEditor exits 127 before writing a log)
    apt-get install -y -qq libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgtk-3-0 libnss3 libxcomposite1 \
        libxdamage1 libxrandr2 libgbm1 libasound2 libatk1.0-0 libatk-bridge2.0-0 libxkbcommon0 libxss1 \
        libxtst6 libsecret-1-0 >/dev/null
    nvidia-smi >/dev/null 2>&1 || echo "reboot=needed"
}

step_engine() {
    local s3="$1" version="$2" dest="$3"
    if [ -x "$dest/Engine/Binaries/Linux/UnrealEditor" ]; then echo "engine: already at $dest"; return; fi
    command -v aws >/dev/null || { apt-get install -y -qq unzip curl >/dev/null
        curl -sSL https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o /tmp/awscli.zip
        unzip -qo /tmp/awscli.zip -d /tmp && /tmp/aws/install >/dev/null; }
    aws s3 cp --only-show-errors "$s3/tools/ue-restore.sh" /tmp/ue-restore.sh
    UE_S3="$s3" UE_USER="$UE_USER" bash /tmp/ue-restore.sh "$version" "$dest"
    echo "engine: $(cat "$dest/Engine/Build/Build.version" | tr -d '\n ' | head -c 200)"
    local missing
    missing="$(ldd "$dest/Engine/Binaries/Linux/UnrealEditor" 2>&1 | grep 'not found' || true)"
    [ -z "$missing" ] || echo "engine: missing libraries: $missing"
}

step_project() {
    local s3="$1" dir="$2"
    mkdir -p "$dir"
    chown "$UE_USER:$UE_USER" "$dir"
    runuser -u "$UE_USER" -- aws s3 sync --only-show-errors "$s3" "$dir" \
        --exclude 'Saved/*' --exclude 'DerivedDataCache/*' --exclude 'Intermediate/*' --exclude 'Binaries/*'
    echo "project: $(du -sh "$dir" | cut -f1) in $dir; $(ls "$dir"/*.uproject)"
}

step_windisk() {
    local mnt="${1:-/mnt/win}" part
    if mountpoint -q "$mnt"; then echo "windisk: $mnt already mounted"; return; fi
    command -v ntfs-3g >/dev/null || apt-get install -y -qq ntfs-3g >/dev/null
    # the largest NTFS partition on any disk: the Windows system volume
    part="$(lsblk -bprno NAME,FSTYPE,SIZE | awk '$2=="ntfs"{print $3, $1}' | sort -n | tail -1 | cut -d' ' -f2)"
    [ -n "$part" ] || { echo "windisk: no NTFS partition (is the snapshot's volume attached?)" >&2; exit 1; }
    mkdir -p "$mnt"
    ntfs-3g -o ro,uid="$(id -u "$UE_USER")",gid="$(id -g "$UE_USER")" "$part" "$mnt"
    echo "windisk: $part on $mnt (read-only)"
}

step_project-copy() {
    local src="$1" dir="$2"
    [ -n "$(ls "$src"/*.uproject 2>/dev/null)" ] || { echo "project-copy: no .uproject in $src" >&2; exit 1; }
    mkdir -p "$dir"
    chown "$UE_USER:$UE_USER" "$dir"
    command -v rsync >/dev/null || apt-get install -y -qq rsync >/dev/null
    runuser -u "$UE_USER" -- rsync -a --no-perms --chmod=ugo=rwX \
        --exclude /Saved/ --exclude /DerivedDataCache/ --exclude /Intermediate/ --exclude /Binaries/ "$src/" "$dir/"
    echo "project: $(du -sh "$dir" | cut -f1) in $dir; $(ls "$dir"/*.uproject)"
}

region() {  # the box's own region (IMDSv2), for the AWS CLI the unit runs (ue-epic save)
    local t
    t="$(curl -fsS -m 5 -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')"
    curl -fsS -m 5 -H "X-aws-ec2-metadata-token: $t" http://169.254.169.254/latest/meta-data/placement/region
}

step_service() {
    local engine="$1" uproject="$2" map="${3:-}" epic="${4:-}"
    cat > /etc/default/ue-editor <<EOF
UE_ROOT=$engine
UE_PROJECT=$uproject
UE_MAP=$map
UE_SDL=default
UE_ARGS=
EPIC_S3=$epic
AWS_DEFAULT_REGION=$(region || true)
EOF
    # xvfb: display mode "xvfb" (ue-editor.sh), if the offscreen ones fail; xdg-utils: how the engine opens a sign-in
    apt-get install -y -qq xvfb xauth xdg-utils >/dev/null
    install -m 755 "$HERE/ue-editor.sh" /usr/local/bin/ue-editor
    install -m 755 "$HERE/ue-epic.sh" /usr/local/bin/ue-epic
    ln -sf /usr/local/bin/ue-epic /usr/local/bin/ue-epic-url
    sed "s/@USER@/$UE_USER/g" "$HERE/ue-editor.service" > /etc/systemd/system/ue-editor.service
    systemctl daemon-reload
    systemctl enable ue-editor >/dev/null 2>&1
    echo "service: ue-editor enabled ($(systemctl is-active ue-editor || true))"
    step_epic restore
}

step_epic() {  # as the editor's user, with the unit's settings (EPIC_S3, AWS_DEFAULT_REGION)
    local what="${1:?epic restore|save|status|code|clear-code}" home
    install -m 755 "$HERE/ue-epic.sh" /usr/local/bin/ue-epic
    ln -sf /usr/local/bin/ue-epic /usr/local/bin/ue-epic-url
    home="$(getent passwd "$UE_USER" | cut -d: -f6)"
    # shellcheck disable=SC1091
    ( set -a; . /etc/default/ue-editor; set +a
      runuser -u "$UE_USER" -- env HOME="$home" EPIC_S3="${EPIC_S3:-}" AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-}" \
          /usr/local/bin/ue-epic "$what" )
}

step_mode() {
    local mode="${1:?mode default|offscreen|xvfb}"
    install -m 755 "$HERE/ue-editor.sh" /usr/local/bin/ue-editor
    sed -i "s/^UE_SDL=.*/UE_SDL=$mode/; /^DISPLAY=/d" /etc/default/ue-editor
    systemctl restart ue-editor
    echo "mode: $mode; editor restarted"
}

# KNOWN LIMIT (PoC, L4, 580.178.04-server, Vulkan ICD diverted to libEGL_nvidia for headless use): Xorg and VNC come
# up, but the editor cannot present to X: with the EGL ICD its first swapchain is "outdated" and it crashes, and the
# stock GLX ICD fails vkCreateInstance with VK_ERROR_INCOMPATIBLE_DRIVER. Check `vkcube` on :0 before relying on this.
step_desktop() {
    local what="${1:?desktop on|off}" drv bus pw
    if [ "$what" = off ]; then
        systemctl stop ue-vnc ue-xorg 2>/dev/null || true
        rm -f /root/vnc-pass
        sed -i 's/^UE_SDL=.*/UE_SDL=default/; /^DISPLAY=/d' /etc/default/ue-editor
        systemctl restart ue-editor
        echo "desktop: off; editor offscreen"
        return
    fi
    drv="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1 | cut -d. -f1)"
    apt-get install -y -qq xserver-xorg-core "xserver-xorg-video-nvidia-${drv}-server" openbox x11vnc xterm >/dev/null \
        || apt-get install -y -qq xserver-xorg-core "xserver-xorg-video-nvidia-${drv}" openbox x11vnc xterm >/dev/null
    if ! command -v firefox >/dev/null || snap list firefox >/dev/null 2>&1; then  # Mozilla's deb, not the snap
        install -d -m 755 /etc/apt/keyrings
        curl -fsSL https://packages.mozilla.org/apt/repo-signing-key.gpg -o /etc/apt/keyrings/packages.mozilla.org.asc
        echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" \
            > /etc/apt/sources.list.d/mozilla.list
        printf 'Package: *\nPin: origin packages.mozilla.org\nPin-Priority: 1000\n' > /etc/apt/preferences.d/mozilla
        apt-get update -qq && apt-get install -y -qq firefox >/dev/null
    fi
    # the GPU's PCI address, in Xorg's decimal bus:device:function form
    local _dom b d f
    IFS=':.' read -r _dom b d f <<<"$(nvidia-smi --query-gpu=pci.bus_id --format=csv,noheader | head -1)"
    bus="PCI:$((16#$b)):$((16#$d)):$((16#$f))"
    printf '%s\n' 'Section "Device"' '    Identifier "gpu"' '    Driver "nvidia"' "    BusID \"$bus\"" \
        '    Option "AllowEmptyInitialConfiguration" "True"' 'EndSection' 'Section "Screen"' '    Identifier "screen"' \
        '    Device "gpu"' '    DefaultDepth 24' '    SubSection "Display"' \
        '        Depth 24' '        Virtual 1920 1080' '    EndSubSection' 'EndSection' > /etc/X11/xorg-ue.conf
    printf '%s\n' '[Unit]' 'Description=Xorg on the GPU with a virtual screen (temporary desktop)' '[Service]' \
        'ExecStart=/usr/lib/xorg/Xorg :0 -config /etc/X11/xorg-ue.conf -nolisten tcp -noreset' \
        > /etc/systemd/system/ue-xorg.service
    printf '%s\n' '[Unit]' 'Description=openbox + x11vnc on 127.0.0.1:5900 (temporary desktop)' \
        'Requires=ue-xorg.service' 'After=ue-xorg.service' '[Service]' "User=$UE_USER" 'Environment=DISPLAY=:0' \
        "ExecStartPre=/bin/sh -c 'for i in \$(seq 30); do [ -S /tmp/.X11-unix/X0 ] && break; sleep 1; done; (openbox &)'" \
        "ExecStart=/usr/bin/x11vnc -display :0 -localhost -rfbport 5900 -forever -shared -rfbauth /home/$UE_USER/.film-ue/vncpass -quiet" \
        > /etc/systemd/system/ue-vnc.service
    install -d -o "$UE_USER" -g "$UE_USER" "/home/$UE_USER/.film-ue"
    pw="$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 8)"  # x11vnc reads at most 8 characters
    runuser -u "$UE_USER" -- x11vnc -storepasswd "$pw" "/home/$UE_USER/.film-ue/vncpass" >/dev/null 2>&1
    systemctl daemon-reload
    systemctl restart ue-xorg ue-vnc
    sed -i 's/^UE_SDL=.*/UE_SDL=x11/; /^DISPLAY=/d' /etc/default/ue-editor
    echo "DISPLAY=:0" >> /etc/default/ue-editor
    systemctl restart ue-editor
    # the password is never printed (command output lands in logs and messages): root reads it in their own session
    install -m 600 -o root -g root /dev/null /root/vnc-pass && printf '%s\n' "$pw" > /root/vnc-pass
    echo "desktop: on (Xorg :0 on $bus, x11vnc 127.0.0.1:5900); VNC password in /root/vnc-pass (sudo cat)"
}

step_watchdog() {
    local ttl="${1:-0}" idle="${2:-20}" stall="${3:-15}" project="${4:-}" token=""
    [ -n "$project" ] && token="$project/Saved/fmbridge.token"
    install -d /usr/local/lib/film-ue /etc/film-ue /var/lib/film-ue
    install -m 755 "$HERE/ue_watchdog.py" /usr/local/lib/film-ue/ue_watchdog.py
    install -m 644 "$HERE/ue-watchdog.service" /etc/systemd/system/ue-watchdog.service
    install -m 644 "$HERE/ue-watchdog.timer" /etc/systemd/system/ue-watchdog.timer
    python3 - "$ttl" "$idle" "$stall" "$token" <<'PY'
import json, sys
ttl, idle, stall, token = sys.argv[1:5]
path = "/etc/film-ue/watchdog.json"
try:
    cfg = json.load(open(path))
except (OSError, ValueError):
    cfg = {}
cfg.update(ttl_until=(int(ttl) or None), idle_min=int(idle), stall_min=int(stall))
if token:
    cfg["token"] = token
json.dump(cfg, open(path, "w"), indent=1)
PY
    mkdir -p /run/film-ue
    systemctl daemon-reload
    systemctl enable --now ue-watchdog.timer >/dev/null 2>&1
    echo "watchdog: ttl_until=$ttl idle_min=$idle stall_min=$stall ($(systemctl is-active ue-watchdog.timer))"
}

step_rhi() {
    local ini="${1:?rhi PROJECT_DIR}/Config/DefaultEngine.ini" sec="[/Script/LinuxTargetPlatform.LinuxTargetSettings]"
    mkdir -p "$(dirname "$ini")" && touch "$ini"
    if grep -qx '+TargetedRHIs=SF_VULKAN_SM6' "$ini"; then echo "rhi=ok"; return; fi
    if grep -qxF "$sec" "$ini"; then  # the section is there (with SM5, or other settings): add ours under its header
        sed -i "/^$(printf '%s' "$sec" | sed 's/[][\/.]/\\&/g')\$/a -TargetedRHIs=SF_VULKAN_SM5\n+TargetedRHIs=SF_VULKAN_SM6" "$ini"
    else
        printf '\n%s\n-TargetedRHIs=SF_VULKAN_SM5\n+TargetedRHIs=SF_VULKAN_SM6\n' "$sec" >> "$ini"
    fi
    chown "$UE_USER:$UE_USER" "$ini" 2>/dev/null || true
    echo "rhi=set"
}

step_plugin() {
    local tgz="${1:?plugin TGZ ENGINE PROJECT_DIR}" engine="${2:?}" project="${3:?}" name w log
    w="${PLUGIN_BUILD_DIR:-/srv/ue/pluginbuild}"
    rm -rf "$w" && mkdir -p "$w/Plugins" && tar -xzf "$tgz" -C "$w/Plugins"
    name="$(basename "$(ls -d "$w"/Plugins/*/ | head -1)")"
    [ -f "$w/Plugins/$name/$name.uplugin" ] || { echo "plugin: no $name.uplugin in $tgz" >&2; exit 1; }
    printf '{"FileVersion": 3, "EngineAssociation": "", "Plugins": [{"Name": "%s", "Enabled": true}]}\n' "$name" \
        > "$w/PluginBuild.uproject"
    chown -R "$UE_USER:$UE_USER" "$w"
    PLUGIN_MARK="$engine/Engine/Build/InstalledBuild.txt"  # global: the EXIT trap runs after the function returns
    # An installed engine loads its rules PRECOMPILED (UnrealBuildTool DynamicCompilation.cs: "Precompiled rules
    # assembly ... does not exist"), and a restored engine tarball has no Engine/Intermediate. Compile the rules once,
    # unmarked: QueryTargets builds only the C# rules assemblies (~1 min), not the engine (round 5, 0.4).
    if [ ! -f "$engine/Engine/Intermediate/Build/BuildRules/UE5Rules.dll" ] && [ ! -f "$PLUGIN_MARK" ]; then
        runuser -u "$UE_USER" -- "$engine/Engine/Build/BatchFiles/Linux/Build.sh" -Mode=QueryTargets \
            -Project="$w/PluginBuild.uproject" -Output="$w/querytargets.json" > "/tmp/plugin-rules-$name.log" 2>&1 \
            || { tail -20 "/tmp/plugin-rules-$name.log" >&2; echo "plugin: compiling the engine's build rules failed" >&2; exit 1; }
        [ -f "$engine/Engine/Intermediate/Build/BuildRules/UE5Rules.dll" ] \
            || { echo "plugin: no UE5Rules.dll after QueryTargets (log /tmp/plugin-rules-$name.log)" >&2; exit 1; }
    fi
    # ... and it has no generated (UHT) headers either (PrimaryAssetId.generated.h not found): run UHT over the engine
    # with -SkipBuild (UHT runs while the makefile is made, UEBuildTarget.cs; SkipBuild skips only the compile actions),
    # still unmarked. A few minutes, once per restored engine.
    if [ ! -f "$engine/Engine/Intermediate/Build/Linux/UnrealEditor/Inc/CoreUObject/UHT/PrimaryAssetId.generated.h" ] \
            && [ ! -f "$PLUGIN_MARK" ]; then
        runuser -u "$UE_USER" -- timeout 1500 "$engine/Engine/Build/BatchFiles/Linux/Build.sh" UnrealEditor Linux \
            Development -Project="$w/PluginBuild.uproject" -SkipBuild > "/tmp/plugin-uht-$name.log" 2>&1 \
            || { tail -20 "/tmp/plugin-uht-$name.log" >&2; echo "plugin: generating the engine's UHT headers failed" >&2; exit 1; }
    fi
    if [ -f "$PLUGIN_MARK" ]; then PLUGIN_MARK=""; else touch "$PLUGIN_MARK"; trap 'rm -f "${PLUGIN_MARK:-/nonexistent}"' EXIT; fi
    log=/tmp/plugin-build-$name.log
    if ! runuser -u "$UE_USER" -- timeout 1500 "$engine/Engine/Build/BatchFiles/Linux/Build.sh" UnrealEditor Linux \
            Development -Project="$w/PluginBuild.uproject" > "$log" 2>&1; then
        tail -30 "$log" >&2; echo "plugin: $name did not build (log: $log)" >&2; exit 1
    fi
    [ -z "$PLUGIN_MARK" ] || rm -f "$PLUGIN_MARK"
    rm -rf "$w/Plugins/$name/Intermediate" "${project:?}/Plugins/$name"
    mkdir -p "$project/Plugins" && cp -r "$w/Plugins/$name" "$project/Plugins/"
    chown -R "$UE_USER:$UE_USER" "$project/Plugins/$name"
    echo "plugin: $name built ($(grep -c '^\[' "$log") actions) into $project/Plugins/$name; restart the editor to load it"
}

step_check() {
    echo "gpu=$(nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null || echo none)"
    echo "vulkan=$(vulkaninfo --summary 2>/dev/null | awk -F= '/deviceName/{gsub(/^ +/,"",$2); print $2; exit}' || echo none)"
    echo "kernel=$(uname -r)"
    [ -f /etc/default/ue-editor ] && . /etc/default/ue-editor
    echo "engine=${UE_ROOT:-unset} $( [ -x "${UE_ROOT:-/nonexistent}/Engine/Binaries/Linux/UnrealEditor" ] && echo present || echo missing)"
    echo "project=${UE_PROJECT:-unset}"
    echo "service=$(systemctl is-active ue-editor 2>/dev/null || true)"
    echo "ram_gb=$(free -g | awk '/Mem:/{print $2}') disk_free=$(df -h --output=avail /srv/ue 2>/dev/null | tail -1 | tr -d ' ')"
}

cmd="${1:?usage: setup.sh volume|driver|engine|project|windisk|project-copy|service|epic|mode|desktop|watchdog|rhi|plugin|check ...}"
shift
"step_$cmd" "$@"
