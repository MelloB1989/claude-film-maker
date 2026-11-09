"""A stick-mannequin preview of the gesture performance, frame-synced to vo.wav (round 7, agent-10). It is NOT her:
bones as lines (her skeleton's proportions only), the desk, the mic. Front view (as from the lens) and side view;
the line's text and each gesture's label at its apex.

    python gesture/preview.py netflix --spans 0-8.17,43.33-48.42 --out /work/out/gesture_test.mp4  [--no-timing]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
EXPL = HERE.parent
sys.path.insert(0, str(HERE))
import evaluate as E  # noqa: E402
import seatkit as S  # noqa: E402

FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
W, H, DPI = 1280, 720, 100
CHAINS = [["pelvis", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_01", "neck_02", "head"]] + \
    [["spine_05", f"clavicle_{s}", f"upperarm_{s}", f"lowerarm_{s}", f"hand_{s}"] for s in "lr"] + \
    [[f"hand_{s}", f"{f}_01_{s}", f"{f}_02_{s}", f"{f}_03_{s}"] for s in "lr"
     for f in ("thumb", "index", "middle", "ring", "pinky")] + \
    [["pelvis", f"thigh_{s}", f"calf_{s}", f"foot_{s}"] for s in "lr"]


def frames(film, spans, fps, use_timing):
    tp = EXPL / "acting" / f"timing_{ {"netflix": "her", "whatsapp": "him"}[film]}.json"
    timing = json.loads(tp.read_text()) if use_timing and tp.exists() else None
    perf, cues, sheet = E.performer(film, timing)
    ev = perf.plan.events
    for a, b in spans:
        for i in range(int(round(a * fps)), int(round(b * fps))):
            t = i / fps
            F = perf.fk(perf.pose(t))
            A = {k: perf.actor(v[0]) for k, v in F.items()}
            yield t, A, perf, cues, ev


def draw(fig, axs, t, A, perf, cues, ev, label):
    st = perf.set
    for ax, (h, sgn), name in ((axs[0], (1, -1.0), "front"), (axs[1], (0, 1.0), "side")):
        ax.cla()
        ax.set_facecolor("#14161a")
        ax.set_xlim(-55, 55) if h == 1 else ax.set_xlim(-30, 80)
        ax.set_ylim(40, 140)
        ax.set_aspect("equal")
        ax.axis("off")
        X = lambda p: sgn * p[h]  # noqa: E731
        # desk top and the mic
        if h == 1:
            ax.plot([-55, 55], [st.desk_top] * 2, color="#7a5a3a", lw=6)
            if st.mic:
                ax.add_patch(plt.Circle((X(st.mic), st.mic[2]), st.mic_radius, color="#555", alpha=0.7))
        else:
            ax.plot([st.desk_near, st.desk_far], [st.desk_top] * 2, color="#7a5a3a", lw=6)
            if st.mic:
                ax.add_patch(plt.Circle((st.mic[0], st.mic[2]), st.mic_radius, color="#555", alpha=0.7))
        for ch in CHAINS:
            pts = [A[b] for b in ch if b in A]
            if len(pts) < 2:
                continue
            side = "r" if ch[-1].endswith("_r") else ("l" if ch[-1].endswith("_l") else "c")
            col = {"r": "#ffb347", "l": "#7ec8e3", "c": "#e8e8e8"}[side]
            lw = 1.2 if any(f in ch[-1] for f in ("thumb", "index", "middle", "ring", "pinky")) else 3.5
            ax.plot([X(p) for p in pts], [p[2] for p in pts], color=col, lw=lw, solid_capstyle="round")
        hd = A["head"]
        ax.add_patch(plt.Circle((X(hd), hd[2] + 9), 9, fill=False, color="#e8e8e8", lw=2.5))
        ax.text(0.02, 0.97, name, transform=ax.transAxes, color="#888", fontsize=9, va="top")
    line = next((ln for ln in cues["lines"] if ln["start"] - 0.2 <= t <= ln["end"] + 0.3), None)
    fig.texts.clear()
    fig.text(0.5, 0.06, line["text"] if line else "", color="#ddd", ha="center", fontsize=15)
    fig.text(0.02, 0.95, f"{label}   t {t:6.2f} s   f{int(round(t * cues['fps']))}", color="#888", fontsize=10)
    near = [e for e in ev if abs(t - e.stroke) < 0.2]
    if near:
        e = near[0]
        fig.text(0.5, 0.92, f"{e.kind.upper()}  ({e.hand})  '{e.word}'", color="#ffb347", ha="center", fontsize=14)
    fig.text(0.98, 0.95, "stick preview, not the presenter", color="#666", ha="right", fontsize=9)


def render(film, spans, out, fps=24, use_timing=True):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cues = json.loads((EXPL / "audio" / film / "cues.json").read_text())
    vo = EXPL / cues["vo"]
    fig, axs = plt.subplots(1, 2, figsize=(W / DPI, H / DPI), dpi=DPI, facecolor="#14161a")
    fig.subplots_adjust(0.02, 0.1, 0.98, 0.9, 0.05)
    label = "prosody timing" if use_timing else "sheet only"
    parts = []
    for k, (a, b) in enumerate(spans):
        part = out.with_name(f"{out.stem}_part{k}.mp4")
        cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}",
               "-r", str(fps), "-i", "-", "-ss", f"{a:.4f}", "-t", f"{b - a:.4f}", "-i", str(vo),
               "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
               "-c:a", "aac", "-b:a", "160k", "-shortest", str(part)]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for t, A, perf, cues_, ev in frames(film, [(a, b)], fps, use_timing):
            draw(fig, axs, t, A, perf, cues_, ev, label)
            fig.canvas.draw()
            p.stdin.write(np.asarray(fig.canvas.buffer_rgba()).tobytes())
        p.stdin.close()
        p.wait()
        parts.append(part)
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{q}'\n" for q in parts))
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                    str(out)], check=True)
    for q in parts:
        q.unlink()
    lst.unlink()
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("film", nargs="?", default="netflix")
    ap.add_argument("--spans", default="0-8.17,43.33-48.42")
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-timing", action="store_true")
    a = ap.parse_args()
    spans = [tuple(float(x) for x in s.split("-")) for s in a.spans.split(",")]
    print(render(a.film, spans, a.out, use_timing=not a.no_timing))
