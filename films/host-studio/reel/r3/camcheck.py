# Framing check (agent-05): for each frame, the current camera's render (camcheck dir) against final_c's frame: the
# zoom factor and shift that best align them (normalised correlation of edge maps, scales 0.75-1.35). A framing
# match is scale 1.00 +- 0.02 and shift under 1% of the width. Prints one JSON line. Read-only.
import json, os, sys
import numpy as np
from PIL import Image, ImageFilter
CAM, FIN = sys.argv[1], sys.argv[2]
FRAMES = [int(x) for x in sys.argv[3].split(",")]
W, H = 480, 270

def load(p):
    g = Image.open(p).convert("L").resize((W, H), Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.5))
    a = np.asarray(g, dtype=np.float32)
    gx, gy = np.zeros_like(a), np.zeros_like(a)
    gx[:, 1:-1], gy[1:-1, :] = a[:, 2:] - a[:, :-2], a[2:, :] - a[:-2, :]
    e = np.hypot(gx, gy)
    return (e - e.mean()) / (e.std() + 1e-6)

def zoom(a, s):  # scale about the centre, cropped back to W x H
    im = Image.fromarray(a)
    w, h = int(round(W * s)), int(round(H * s))
    z = np.asarray(im.resize((w, h), Image.BILINEAR))
    if s >= 1:
        x0, y0 = (w - W) // 2, (h - H) // 2
        return z[y0:y0 + H, x0:x0 + W]
    out = np.zeros((H, W), np.float32)
    x0, y0 = (W - w) // 2, (H - h) // 2
    out[y0:y0 + h, x0:x0 + w] = z
    return out

def best_shift(a, b):  # phase correlation: integer shift of b onto a
    F = np.fft.fft2(a) * np.conj(np.fft.fft2(b))
    r = np.fft.ifft2(F / (np.abs(F) + 1e-6)).real
    y, x = np.unravel_index(np.argmax(r), r.shape)
    return (y if y < H // 2 else y - H), (x if x < W // 2 else x - W)

def ncc(a, b):
    m = 30  # ignore borders
    a, b = a[m:-m, m:-m], b[m:-m, m:-m]
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-6))

def name(f):
    return ("-" if f < 0 else "") + f"{abs(f):04d}.png"

res = {}
for f in FRAMES:
    pc, pf = os.path.join(CAM, name(f)), os.path.join(FIN, name(f))
    if not (os.path.exists(pc) and os.path.exists(pf)):
        res[f] = {"error": "missing", "cam": os.path.exists(pc), "final": os.path.exists(pf)}
        continue
    a, b = load(pf), load(pc)
    best = (-2, 1.0, (0, 0))
    for s in np.arange(0.75, 1.351, 0.01):
        bz = zoom(b, float(s))
        dy, dx = best_shift(a, bz)
        c = ncc(a, np.roll(bz, (dy, dx), (0, 1)))
        if c > best[0]:
            best = (c, float(s), (int(dy), int(dx)))
    same = ncc(a, b)
    ok = abs(best[1] - 1.0) <= 0.02 and abs(best[2][1]) <= W * 0.01 and abs(best[2][0]) <= H * 0.01
    res[f] = {"scale_cam_to_final": round(best[1], 3), "shift_px_480": best[2], "ncc_best": round(best[0], 3),
              "ncc_as_is": round(same, 3), "framing_match": bool(ok)}
print(json.dumps(res))
