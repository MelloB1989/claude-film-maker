"""Contact strips for the outro: every frame of a PNG folder (NNNN.png), frame numbers burnt in.

    python blender/amv3/outro3_sheet.py <dir> <out.jpg> [cols] [width] [--side <dir2>]

With --side, each tile is the frame of <dir> next to the same frame of <dir2> (e.g. v3 | v2).
"""
import glob
import os
import sys

from PIL import Image, ImageDraw


def main(argv):
    side = None
    if "--side" in argv:
        i = argv.index("--side")
        side = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    d, out = argv[0], argv[1]
    cols = int(argv[2]) if len(argv) > 2 else 6
    tw = int(argv[3]) if len(argv) > 3 else 480
    fs = sorted(f for f in glob.glob(os.path.join(d, "*.png")) if os.path.basename(f)[:4].isdigit())
    tiles = []
    for f in fs:
        n = os.path.basename(f)[:4]
        im = Image.open(f).convert("RGB")
        im = im.resize((tw, round(tw * im.height / im.width)))
        if side:
            g = os.path.join(side, n + ".png")
            if os.path.exists(g):
                im2 = Image.open(g).convert("RGB").resize(im.size)
                pair = Image.new("RGB", (im.width * 2 + 4, im.height))
                pair.paste(im, (0, 0))
                pair.paste(im2, (im.width + 4, 0))
                im = pair
        ImageDraw.Draw(im).text((6, 4), n, fill=(255, 255, 0))
        tiles.append(im)
    w, h = tiles[0].size
    rows = (len(tiles) + cols - 1) // cols
    S = Image.new("RGB", (cols * w, rows * h))
    for i, im in enumerate(tiles):
        S.paste(im, ((i % cols) * w, (i // cols) * h))
    S.save(out, quality=88)
    print("sheet", out, w, h, len(tiles))


if __name__ == "__main__":
    main(sys.argv[1:])
