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
#   service ENGINE UPROJECT [MAP]  /etc/default/ue-editor, /usr/local/bin/ue-editor, ue-editor.service (enabled)
#   desktop on|off                 a temporary desktop for one interactive step (a sign-in): Xorg on the GPU with a
#                                  virtual screen, openbox, a browser, x11vnc on 127.0.0.1:5900 (reached only through
#                                  an SSM port-forward), the editor restarted onto it; off puts it back offscreen
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
    dev="$(lsblk -dpno NAME,TYPE | awk '$2=="disk"{print $1}' | while read -r d; do
        [ "$(basename "$d")" = "$root" ] && continue
        [ "$(lsblk -no NAME "$d" | wc -l)" -eq 1 ] && echo "$d"; done | head -1)"
    [ -n "$dev" ] || { echo "volume: no empty data disk found" >&2; exit 1; }
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

step_service() {
    local engine="$1" uproject="$2" map="${3:-}"
    cat > /etc/default/ue-editor <<EOF
UE_ROOT=$engine
UE_PROJECT=$uproject
UE_MAP=$map
UE_SDL=offscreen
UE_ARGS=
EOF
    install -m 755 "$HERE/ue-editor.sh" /usr/local/bin/ue-editor
    sed "s/@USER@/$UE_USER/g" "$HERE/ue-editor.service" > /etc/systemd/system/ue-editor.service
    systemctl daemon-reload
    systemctl enable ue-editor >/dev/null 2>&1
    echo "service: ue-editor enabled ($(systemctl is-active ue-editor || true))"
}

step_desktop() {
    local what="${1:?desktop on|off}" drv bus pw
    if [ "$what" = off ]; then
        systemctl stop ue-vnc ue-xorg 2>/dev/null || true
        sed -i 's/^UE_SDL=.*/UE_SDL=offscreen/; /^DISPLAY=/d' /etc/default/ue-editor
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
        '    Device "gpu"' '    DefaultDepth 24' '    Option "UseDisplayDevice" "None"' '    SubSection "Display"' \
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
    echo "desktop: on (Xorg :0 on $bus, x11vnc 127.0.0.1:5900)"
    echo "vnc_password=$pw"
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

cmd="${1:?usage: setup.sh volume|driver|engine|project|windisk|project-copy|service|desktop|check ...}"
shift
"step_$cmd" "$@"
