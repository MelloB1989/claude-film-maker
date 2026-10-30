"""The film's thumbnail, in the format of the style reference's: the keeper drawing (blender/draw/thumb.py, rendered to
out/lighthouse-keeper/media/thumb/0000.png) with a handwritten hook and a hand-drawn arrow pointing at him.

    python3 films/lighthouse-keeper/scripts/thumbnail.py      ->  out/lighthouse-keeper/lighthouse-keeper-thumbnail.png (1280x720)
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FILM = Path(__file__).resolve().parents[1]
OUT = FILM.parents[1] / "out" / FILM.name
INK = (27, 26, 29)

img = Image.open(OUT / "media" / "thumb" / "0000.png").convert("RGB")
W, H = img.size
d = ImageDraw.Draw(img)
font = ImageFont.truetype(str(FILM / "fonts" / "PatrickHand-Regular.ttf"), int(H * 0.2))
lines = ["Alone on", "a Rock"]
cx, y = int(W * 0.745), int(H * 0.15)
for ln in lines:
    w = d.textlength(ln, font=font)
    d.text((cx - w / 2, y), ln, font=font, fill=INK)
    y += int(H * 0.22)
# a hand-drawn arrow: a gentle curve from under the words towards the keeper, and its head
pts = []
x0, y0, x1, y1 = W * 0.76, H * 0.66, W * 0.52, H * 0.78
for i in range(41):
    t = i / 40
    x = x0 + (x1 - x0) * t
    yy = y0 + (y1 - y0) * t + math.sin(math.pi * t) * H * 0.09
    pts.append((x, yy))
d.line(pts, fill=INK, width=int(H * 0.011), joint="curve")
ax, ay = pts[-1]
bx, by = pts[-4]
ang = math.atan2(ay - by, ax - bx)
for s in (-1, 1):
    a = ang + math.pi + s * 0.55
    d.line([(ax, ay), (ax + math.cos(a) * H * 0.06, ay + math.sin(a) * H * 0.06)], fill=INK, width=int(H * 0.011))
thumb = img.resize((1280, 720), Image.LANCZOS)
thumb.save(OUT / "lighthouse-keeper-thumbnail.png")
print(OUT / "lighthouse-keeper-thumbnail.png")
