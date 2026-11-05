# Round-3 finals check (agent-05): every report under final/_render, then each shot's frames on disk: count, missing,
# unreadable/black frames and luminance jumps between consecutive frames (pops). Prints one JSON line. Read-only.
import glob, json, os, sys
import numpy as np
from PIL import Image
R = os.environ.get("R3", "/srv/ue/reel/r3") + "/" + os.environ.get("FINAL", "final_c")
sys.path.insert(0, os.environ.get("REEL", "/srv/ue/r3tree/films/host-studio/reel"))
from shots import SHOTS
H = 12
out = {"reports": [], "shots": {}}
for p in sorted(glob.glob(R + "/_render/*.report.json")):
    r = json.load(open(p))
    out["reports"].append({"name": r.get("name"), "status": r.get("status"), "frames": r.get("frames"),
                           "seconds": r.get("seconds"), "vram_peak_gb": r.get("vram_peak_gb"),
                           "measured": r.get("measured"), "errors": (r.get("errors") or [])[:5],
                           "chunks": [[c.get("camera"), c.get("status"), c.get("frames"), c.get("missing"),
                                       c.get("median_s")] for c in r.get("chunks") or []]})
def name(f):
    return ("-" if f < 0 else "") + f"{abs(f):04d}.png"
for k, s in enumerate(SHOTS):
    a = s.start - (H if k == 0 else 0)
    b = s.end + (H if k == len(SHOTS) - 1 else 0)
    have = [f for f in range(a, b) if os.path.exists(f"{R}/{name(f)}")]
    if not have:
        continue
    bad, black, lum = [], [], []
    for f in have:
        try:
            g = np.asarray(Image.open(f"{R}/{name(f)}").convert("L").reduce(4), dtype=np.float32) / 255.0
        except Exception:
            bad.append(f)
            lum.append(None)
            continue
        m = float(g.mean())
        lum.append(m)
        if m < 0.01:
            black.append(f)
    jumps = []
    for i in range(1, len(have)):
        x, y = lum[i - 1], lum[i]
        if x is not None and y is not None and abs(y - x) > max(0.03, 0.15 * x):
            jumps.append([have[i], round(x, 3), round(y, 3)])
    out["shots"][s.id] = {"range": [a, b], "on_disk": len(have), "missing": [f for f in range(a, b) if f not in set(have)][:20],
                          "unreadable": bad[:10], "black": black[:10], "lum_jumps": jumps[:10],
                          "lum_min_max": [round(min(v for v in lum if v is not None), 3), round(max(v for v in lum if v is not None), 3)]}
print(json.dumps(out))
