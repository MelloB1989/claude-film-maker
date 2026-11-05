#!/bin/bash
# Round 3's cut, ON THE GPU BOX (the orchestrator's rule: no bulk frame pulls to kali; frames stay on the box, only
# the MP4s and sheets come down). agent-07 runs it from the box's checkout of film/host-studio:
#
#   R3_PREVIEW=preview/<build> films/host-studio/reel/r3/cut.sh preview   # that build's preview pass
#   R3_PREVIEW=preview/<build> films/host-studio/reel/r3/cut.sh preview --scale 0.5 --name karma-r3-preview-960x540
#                                                          # the whole-reel 960x540 preview at its own size, + _45s
#   films/host-studio/reel/r3/cut.sh preview              # rough cut of the preview pass: 65 s + 45 s, 1080p, captions
#   films/host-studio/reel/r3/cut.sh final                # the finals (R3_FINAL, default final_c), shots not final yet filled from the preview
#   films/host-studio/reel/r3/cut.sh final --fill-from none   # the deliverables: every final must be in
#   films/host-studio/reel/r3/cut.sh check final_c         # per shot: frames present, size, luma (no encode)
#   films/host-studio/reel/r3/cut.sh sheet final_c S13     # a contact sheet of one shot (small: fine to bring down)
#
# Reads the passes where the r3 specs write them (R3_FRAMES, default /srv/ue/reel/r3/<pass>), the mixes from the
# repo (audio/mix), the captions' word times from vo.py's cues.json (out/host-studio/reel/vo/cues.json) when it is
# there, and writes to R3_CUT (default /srv/ue/reel/r3/cut): preview_<pass>_<n>.mp4 / _45s.mp4, or the deliverables
# (karma-reel[-45s]-1080p-*.mp4/.mov, .srt/.vtt, cut.json). No ffmpeg 6+ on the box: a static one (BtbN n8.1, sha256
# checked) goes to R3_TOOLS (default /srv/ue/tools/ffmpeg). Python through uv, as everything under tools/.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
REEL=$(dirname "$HERE")
ROOT=$(cd "$REEL/../../.." && pwd)
FRAMES=${R3_FRAMES:-/srv/ue/reel/r3}
OUT=${R3_CUT:-/srv/ue/reel/r3/cut}
TOOLS=${R3_TOOLS:-/srv/ue/tools/ffmpeg}
CUES=${R3_CUES:-$ROOT/out/host-studio/reel/vo/cues.json}
FINAL=${R3_FINAL:-final_c}       # the finals' pass under R3_FRAMES (agent-05's pick C; final/ is superseded)
PREVIEW=${R3_PREVIEW:-preview}   # the preview pass under R3_FRAMES: preview/<build> when each rebuild has its own
[ -d "$HOME/.local/bin" ] && export PATH="$HOME/.local/bin:$PATH"   # uv's default install

# cut.py's filter graph (overlay format=yuv444p10, ...) wants ffmpeg 6 or newer: an older system one (the box has 4.4)
# is passed over for the static build, tested end to end with cut.py
major=$(ffmpeg -version 2>/dev/null | sed -n 's/^ffmpeg version n\{0,1\}\([0-9]*\).*/\1/p' | head -1)
if ! command -v ffprobe >/dev/null || [ -z "$major" ] || [ "$major" -lt 6 ]; then
  if [ ! -x "$TOOLS/bin/ffmpeg" ]; then
    F=ffmpeg-n8.1-latest-linux64-gpl-8.1
    U=https://github.com/BtbN/FFmpeg-Builds/releases/download/latest
    tmp=$(mktemp -d)
    curl -sSfL -o "$tmp/$F.tar.xz" "$U/$F.tar.xz"
    curl -sSfL -o "$tmp/checksums.sha256" "$U/checksums.sha256"
    (cd "$tmp" && grep " $F.tar.xz\$" checksums.sha256 | sha256sum -c -)
    mkdir -p "$TOOLS"
    tar xJf "$tmp/$F.tar.xz" -C "$tmp"
    cp -r "$tmp/$F/bin" "$TOOLS/"
    rm -rf "$tmp"
  fi
  export PATH="$TOOLS/bin:$PATH"
fi
ffmpeg -hide_banner -version | head -1

cmd=${1:-preview}
shift || true
cd "$ROOT/tools"
asm=(uv run --with pillow python "$REEL/assemble.py" --out "$OUT" --frames-root "$FRAMES")
mix=(--mix "$REEL/audio/mix/mix.wav" --mix45 "$REEL/audio/mix/mix_45.wav")
cues=()
if [ -f "$CUES" ]; then cues=(--cues "$CUES"); else echo "no $CUES: captions timed from LINES"; fi
mkdir -p "$OUT"
case "$cmd" in
  preview) "${asm[@]}" --pass "$PREVIEW" check
           "${asm[@]}" --pass "$PREVIEW" preview "${mix[@]}" "${cues[@]}" "$@" ;;
  final)   "${asm[@]}" --pass "$FINAL" check
           "${asm[@]}" --pass "$FINAL" final "${mix[@]}" "${cues[@]}" --fill-from "$PREVIEW" "$@" ;;
  check)   "${asm[@]}" --pass "${1:-$FINAL}" check "${@:2}" ;;
  sheet)   "${asm[@]}" --pass "${1:-$FINAL}" sheet "${@:2}" ;;
  *) echo "usage: cut.sh preview|final|check <pass>|sheet <pass> <shot> [args]" >&2; exit 2 ;;
esac
ls -la "$OUT"
