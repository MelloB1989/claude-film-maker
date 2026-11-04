#!/usr/bin/env bash
# Start the Unreal editor (installed as /usr/local/bin/ue-editor, run by ue-editor.service).
# From /etc/default/ue-editor: UE_ROOT (engine), UE_PROJECT (the .uproject), UE_MAP (a level to open, optional),
# UE_ARGS (more flags, optional), UE_SDL: "offscreen" (the default: no display at all) or "x11" with DISPLAY=:0 (the
# temporary desktop `film-ue desktop on` starts for a one-off interactive step such as a sign-in).
set -euo pipefail
: "${UE_ROOT:?UE_ROOT unset}" "${UE_PROJECT:?UE_PROJECT unset}"
export SDL_VIDEODRIVER="${UE_SDL:-offscreen}"
if [ "$SDL_VIDEODRIVER" = offscreen ]; then
    unset DISPLAY WAYLAND_DISPLAY
    # -RenderOffscreen: Vulkan with no window. -unattended: no modal dialogs (they would wait for a click forever).
    MODE="-RenderOffscreen -unattended"
else
    # on the temporary desktop someone is there to answer: dialogs (a sign-in) must show
    export DISPLAY="${DISPLAY:-:0}"
    MODE=""
fi
# The .uproject path is passed straight to the engine binary, so its EngineAssociation (a Windows registry GUID on a
# launcher install) does not matter here. -stdout: the log also goes to the journal (journalctl -u ue-editor).
# shellcheck disable=SC2086
exec "$UE_ROOT/Engine/Binaries/Linux/UnrealEditor" "$UE_PROJECT" ${UE_MAP:-} \
    $MODE -nosplash -NoLiveCoding -log -stdout -FullStdOutLogOutput ${UE_ARGS:-}
