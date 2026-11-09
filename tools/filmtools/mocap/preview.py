"""A stick preview of an mp2mh build beside its source (docs/MOCAP_PILOT.md): the source video (or MediaPipe's overlay)
on the left; on the right her skeleton's arm track (gesturekit.track_doc: bones and fingertips, actor frame) as
seen from the lens (front), with the desk top and the mic, a close-up of both hands, and each hand's named shape.
Not her: lines only, so no face data. Needs numpy + matplotlib (a dev tool, not the retarget).

    python -m filmtools.mocap.preview TRACK.json SHAPES.json SOURCE.mp4 OUT.mp4 [--ffmpeg PATH] [--sheet OUT.png]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

FINGERS = ("thumb", "index", "middle", "ring", "pinky")
DESK_TOP, DESK_Y, MIC = 71.0, (-55.0, 55.0), (28.45, -14.76, 110.63)


def chains(s: str) -> list:
    out = [["spine_05", f"clavicle_{s}", f"upperarm_{s}", f"lowerarm_{s}", f"hand_{s}"]]
    for f in FINGERS:
        out.append([f"hand_{s}", f"{f}_01_{s}", f"{f}_02_{s}", f"{f}_03_{s}", f"{f}_tip_{s}"])
    return out


SPINE = ["spine_03", "spine_05", "neck_01", "head"]


def front(p):
    """actor (x fwd, y her right, z up) -> the lens's view: her right on the picture's left."""
    return -p[1], p[2]


def draw(ax, P: dict, lim, lw=2.0, label=None):
    ax.set_xlim(*lim[0])
    ax.set_ylim(*lim[1])
    ax.set_aspect("equal")
    ax.axis("off")
    ax.plot([-DESK_Y[0], -DESK_Y[1]], [DESK_TOP, DESK_TOP], color="#a0743c", lw=3)
    mx, mz = front(MIC)
    ax.add_patch(plt.Circle((mx, mz), 4.5, color="#888", alpha=0.6))
    pts = [front(P[b]) for b in SPINE if b in P]
    if pts:
        ax.plot(*zip(*pts), color="#333", lw=lw)
    if "head" in P:
        hx, hz = front(P["head"])
        ax.add_patch(plt.Circle((hx, hz + 9), 10, fill=False, color="#333", lw=lw))
    for s, col in (("l", "#1f77b4"), ("r", "#d62728")):
        for ch in chains(s):
            pts = [front(P[b]) for b in ch if b in P]
            if len(pts) > 1:
                ax.plot(*zip(*pts), color=col, lw=lw if "clavicle" in ch[1] else lw * 0.7)
    if label:
        ax.text(0.02, 0.02, label, transform=ax.transAxes, fontsize=11, family="monospace")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("track")
    ap.add_argument("shapes")
    ap.add_argument("source")
    ap.add_argument("out")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--sheet", help="also a contact sheet of 8 frames (PNG)")
    a = ap.parse_args(argv)
    tr = json.loads(Path(a.track).read_text())
    sh = json.loads(Path(a.shapes).read_text())
    fps = float(tr["fps"])
    tmp = Path(tempfile.mkdtemp(prefix="mp2mh_prev_"))
    sheet_idx = set(int(len(tr["frames"]) * k / 8) for k in range(8))
    sheet = []
    for i, f in enumerate(tr["frames"]):
        P = {**f["p"], **f.get("tips", {})}
        j = min(len(sh["labels"]["r"]) - 1, int(round(f["t"] * sh["fps"])))
        lab = f"t {f['t']:5.2f}  R {sh['labels']['r'][j]:<9} L {sh['labels']['l'][j]:<9}"
        fig = plt.figure(figsize=(7.2, 7.2), dpi=100)
        ax = fig.add_axes([0, 0.3, 1, 0.7])
        draw(ax, P, ((-60, 60), (55, 140)), label=lab)
        for k, s in enumerate("rl"):  # the hands close up: her right on the left, as the lens sees them
            if f"hand_{s}" not in P:
                continue
            hx, hz = front(P[f"hand_{s}"])
            axh = fig.add_axes([0.02 + 0.5 * k, 0.0, 0.46, 0.3])
            draw(axh, P, ((hx - 14, hx + 14), (hz - 10, hz + 12)), lw=2.5, label=f"{'R' if s == 'r' else 'L'} hand")
        png = tmp / f"f{i:05d}.png"
        fig.savefig(png)
        plt.close(fig)
        if i in sheet_idx:
            sheet.append(png)
    subprocess.run([a.ffmpeg, "-v", "error", "-y", "-i", a.source, "-framerate", str(fps), "-i", str(tmp / "f%05d.png"),
                    "-filter_complex", "[0:v]scale=-2:720,fps=%g[a];[1:v]scale=720:720[b];[a][b]hstack=inputs=2" % fps,
                    "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-shortest", a.out], check=True)
    if a.sheet and sheet:
        args = [a.ffmpeg, "-v", "error", "-y"]
        for p in sorted(sheet):
            args += ["-i", str(p)]
        n = len(sheet)
        args += ["-filter_complex", "".join(f"[{k}:v]scale=360:360[s{k}];" for k in range(n)) +
                 "".join(f"[s{k}]" for k in range(n)) + f"xstack=inputs={n}:layout=" +
                 "|".join(f"{(k % 4) * 360}_{(k // 4) * 360}" for k in range(n)), a.sheet]
        subprocess.run(args, check=True)
    print(a.out)


if __name__ == "__main__":
    main()
