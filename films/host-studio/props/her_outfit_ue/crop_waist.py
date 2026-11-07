"""Round 7 (agent-05): 1:1 waist crops from presenter stills, ON THE BOX (they never leave it but for s3 private).

    python3 crop_waist.py --dir /srv/ue/explainer/review/r7waist2 --frame 1074 [--size 512]

Reads waist_px.json (waist_px.py), projects her waistband (13 cm above the pelvis along the spine: just past spine_03,
as the band's centre sits in her bind pose, edge 109.6 / pelvis 94.5) through
each camera (fmbridge.qa.clip.project_px's maths), and cuts a size x size crop at 1:1 pixels centred there from
her_<CAM>_f<frame>.png with ffmpeg -> waist_<CAM>_f<frame>.png. Pure python + ffmpeg.
"""
import argparse
import json
import math
import os
import subprocess


def project_px(info, p, w, h):
    pr, yw, rl = (math.radians(float(info["rot"][k])) for k in ("pitch", "yaw", "roll"))
    sp, cp, sy, cy, sr, cr = math.sin(pr), math.cos(pr), math.sin(yw), math.cos(yw), math.sin(rl), math.cos(rl)
    fwd = (cp * cy, cp * sy, sp)
    right = (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp)
    up = (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp)
    d = [float(p[i]) - float(info["loc"][i]) for i in range(3)]
    z = sum(a * b for a, b in zip(d, fwd))
    if z <= 1e-6:
        return float("nan"), float("nan"), z
    half = math.tan(math.radians(float(info["fov"])) / 2)
    x = sum(a * b for a, b in zip(d, right)) / (z * half)
    y = sum(a * b for a, b in zip(d, up)) / (z * half) * (w / h)
    return (x + 1) / 2 * w, (1 - y) / 2 * h, z


def dims(path):
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", path], capture_output=True, text=True, check=True).stdout.strip()
    w, h = (int(v) for v in o.split(",")[:2])
    return w, h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--frame", type=int, required=True)
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--ffmpeg", default="ffmpeg")
    a = ap.parse_args()
    meta = json.load(open(os.path.join(a.dir, "waist_px.json")))
    b = meta["bones"]
    waist = [b["spine_03"][i] + 0.15 * (b["spine_03"][i] - b["pelvis"][i]) for i in range(3)]
    rep = {"waist_world": waist, "seated": meta.get("seated"), "crops": {}}
    for cam, info in meta["cameras"].items():
        src = os.path.join(a.dir, f"her_{cam}_f{a.frame}.png")
        if "error" in info or not os.path.exists(src):
            rep["crops"][cam] = {"skipped": info.get("error") or "no still"}
            continue
        w, h = dims(src)
        x, y, z = project_px(info, waist, w, h)
        if not (0 <= x < w) or not math.isfinite(y) or y < 0:
            rep["crops"][cam] = {"skipped": f"waist off frame at ({x:.0f}, {y:.0f})"}
            continue
        below = y >= h   # under the frame's bottom edge (the MCUs): the crop sits on that edge, as close as it gets
        s = min(a.size, w, h)
        x0 = int(min(max(x - s / 2, 0), w - s))
        y0 = int(min(max(y - s / 2, 0), h - s))
        dst = os.path.join(a.dir, f"waist_{cam}_f{a.frame}.png")
        subprocess.run([a.ffmpeg, "-v", "error", "-y", "-i", src, "-vf", f"crop={s}:{s}:{x0}:{y0}", dst], check=True)
        rep["crops"][cam] = {"still": [w, h], "waist_px": [round(x), round(y)], "depth_cm": round(z, 1),
                             "crop": [x0, y0, s, s], "out": dst,
                             **({"note": "the band is below the frame: crop on the bottom edge"} if below else {})}
    json.dump(rep, open(os.path.join(a.dir, f"waist_crops_f{a.frame}.json"), "w"), indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
