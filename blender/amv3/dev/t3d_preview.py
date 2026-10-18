"""Preview comp of stage passes: plate + text (over, straight alpha) + light (glow, add), and strips.
python dev/t3d_preview.py <stage out dir> [--strip A-B[:step]] ...  -> <out>/comp/f_NNNNN.png, <out>/strip_A_B.jpg"""
import glob
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def load(p, mode):
    return np.asarray(Image.open(p).convert(mode)).astype(np.float32) / 255.0 if os.path.exists(p) else None


def comp(out, name):
    pl = load(os.path.join(out, "plate", name), "RGB")
    tx = load(os.path.join(out, "text", name), "RGBA")
    li = load(os.path.join(out, "light", name), "RGB")
    img = pl if pl is not None else np.zeros((tx.shape[0], tx.shape[1], 3), np.float32)
    if tx is not None:
        a = tx[..., 3:4]
        img = img * (1 - a) + tx[..., :3] * a
    if li is not None:
        L = Image.fromarray((np.clip(li, 0, 1) * 255).astype(np.uint8))
        r = max(2, img.shape[1] // 120)
        g1 = np.asarray(L.filter(ImageFilter.GaussianBlur(r))).astype(np.float32) / 255
        g2 = np.asarray(L.filter(ImageFilter.GaussianBlur(r * 4))).astype(np.float32) / 255
        img = 1 - (1 - img) * (1 - np.clip(g1 * 0.6 + g2 * 0.5, 0, 1))
    return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))


def main():
    out = sys.argv[1]
    names = sorted(os.path.basename(p) for p in glob.glob(os.path.join(out, "plate", "f_*.png")) +
                   glob.glob(os.path.join(out, "text", "f_*.png")))
    names = sorted(set(names))
    os.makedirs(os.path.join(out, "comp"), exist_ok=True)
    frames = {}
    for n in names:
        im = comp(out, n)
        im.save(os.path.join(out, "comp", n))
        frames[int(n[2:7])] = im
    args = sys.argv[2:]
    for i, a in enumerate(args):
        if a == "--strip":
            rng, _, step = args[i + 1].partition(":")
            f0, f1 = map(int, rng.split("-"))
            fs = [f for f in range(f0, f1 + 1, int(step or 1)) if f in frames]
            if not fs:
                continue
            tw = 480
            th = int(frames[fs[0]].height * tw / frames[fs[0]].width)
            cols = 6
            rows = (len(fs) + cols - 1) // cols
            sheet = Image.new("RGB", (cols * tw, rows * th), (20, 20, 20))
            for k, f in enumerate(fs):
                t = frames[f].resize((tw, th))
                ImageDraw.Draw(t).text((6, 4), str(f), fill=(255, 255, 0))
                sheet.paste(t, ((k % cols) * tw, (k // cols) * th))
            sheet.save(os.path.join(out, f"strip_{f0}_{f1}.jpg"), quality=88)
    print("comp", len(frames), "frames")


if __name__ == "__main__":
    main()
