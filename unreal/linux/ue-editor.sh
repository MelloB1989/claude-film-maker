#!/usr/bin/env bash
# Start the Unreal editor (installed as /usr/local/bin/ue-editor, run by ue-editor.service).
# From /etc/default/ue-editor: UE_ROOT (engine), UE_PROJECT (the .uproject), UE_MAP (a level to open, optional),
# UE_ARGS (more flags, optional) and UE_SDL, the display mode, in the order to try them:
#   default    no display at all, -RenderOffscreen, SDL picks its driver
#   offscreen  the same with SDL_VIDEODRIVER=offscreen (Epic's headless SDL driver)
#   xvfb       a virtual X server in memory (xvfb-run; no GPU needed for the window, rendering still on the GPU)
#   x11        the X server on DISPLAY (:0): the temporary desktop `film-ue desktop on` starts for a sign-in
set -euo pipefail
: "${UE_ROOT:?UE_ROOT unset}" "${UE_PROJECT:?UE_PROJECT unset}"
mode="${UE_SDL:-default}"
EDITOR=("$UE_ROOT/Engine/Binaries/Linux/UnrealEditor" "$UE_PROJECT")
# The .uproject path is passed straight to the engine binary, so its EngineAssociation (a Windows registry GUID on a
# launcher install) does not matter here. -stdout: the log also goes to the journal (journalctl -u ue-editor).
# -unattended: no modal dialogs (they would wait for a click forever); not on the sign-in desktop, where someone is.
COMMON=(-nosplash -NoLiveCoding -log -stdout -FullStdOutLogOutput)
# shellcheck disable=SC2206
EXTRA=(${UE_MAP:-} ${UE_ARGS:-})
# arguments for this one start only (film-ue editor restart --once-args ...: e.g. a single-use sign-in code)
ONCE="$HOME/.film-ue/ue-args-once"
if [ -f "$ONCE" ]; then
    read -r -a ONCE_ARGS < "$ONCE" || true
    rm -f "$ONCE"
    EXTRA+=("${ONCE_ARGS[@]}")
fi
# no desktop, no browser: a sign-in the engine starts (Epic's device-code page) is kept for `film-ue epic-login`
if [ -x /usr/local/bin/ue-epic-url ]; then export BROWSER=/usr/local/bin/ue-epic-url; fi
case "$mode" in
    default)
        unset DISPLAY WAYLAND_DISPLAY SDL_VIDEODRIVER
        exec "${EDITOR[@]}" "${EXTRA[@]}" -RenderOffscreen -unattended "${COMMON[@]}" ;;
    offscreen)
        unset DISPLAY WAYLAND_DISPLAY
        export SDL_VIDEODRIVER=offscreen
        exec "${EDITOR[@]}" "${EXTRA[@]}" -RenderOffscreen -unattended "${COMMON[@]}" ;;
    xvfb)
        unset WAYLAND_DISPLAY
        export SDL_VIDEODRIVER=x11
        exec xvfb-run -a -s "-screen 0 1920x1080x24" "${EDITOR[@]}" "${EXTRA[@]}" -unattended "${COMMON[@]}" ;;
    x11)
        unset BROWSER  # someone is at this desktop: the sign-in page opens in its browser
        export DISPLAY="${DISPLAY:-:0}" SDL_VIDEODRIVER=x11
        exec "${EDITOR[@]}" "${EXTRA[@]}" "${COMMON[@]}" ;;
    *)
        echo "UE_SDL=$mode: default, offscreen, xvfb or x11" >&2
        exit 2 ;;
esac
