"""Round 5b loop 4 (agent-02), no editor: does the neck backstop's mask under-shrink at the face's UV seams and island
edges, and does padding fix it? MetaHuman samples the head hidden face map per RENDER vertex (one per UV split): a
face vertex on a seam has a copy on each island, and if one copy samples a dark texel and another a white one, the
neck tears there (one side shrinks, the other stays; a turn brings the unshrunk side through the collar).

Reads the face's UV 0 from garment.export's face.fbx and a mask PNG; per face vertex the bilinear sample of every UV
copy; reports `split` (copies disagreeing by > 0.3) and `dark` (any copy <= 0.4). With --pad N it pads the mask N
texels (each white texel next to a dark one takes the darkest neighbour, N times), recounts, and writes the padded
PNG (--out): that PNG is the loop-4 mask (apply with OUT=<it>).

    blender -b --factory-startup -P mask_seams.py -- <face.fbx> <mask.png> [--pad 4 --out <padded.png>]
"""
import sys

import bpy
import numpy as np

a = sys.argv[sys.argv.index("--") + 1:]
face_fbx, png = a[0], a[1]
pad = int(a[a.index("--pad") + 1]) if "--pad" in a else 0
out = a[a.index("--out") + 1] if "--out" in a else ""

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.fbx(filepath=face_fbx)
face = max((o for o in bpy.data.objects if o.type == "MESH"), key=lambda o: len(o.data.vertices))
me = face.data
uvl = me.uv_layers[0].data
loops_v = np.zeros(len(me.loops), int)
me.loops.foreach_get("vertex_index", loops_v)
uv = np.zeros(len(me.loops) * 2)
uvl.foreach_get("uv", uv)
uv = uv.reshape(-1, 2)

img = bpy.data.images.load(png)
W, H = img.size
pix = np.array(img.pixels[:], np.float32).reshape(H, W, img.channels)[:, :, 0]  # Blender: row 0 = bottom = UV v 0


def sample(P, u, v):
    # Blender's UV v and the PNG's rows are both flipped from Unreal's, so they line up as they are
    fx, fy = u * W - 0.5, v * H - 0.5
    ix, iy = np.floor(fx).astype(int), np.floor(fy).astype(int)
    ax, ay = fx - ix, fy - iy
    c = lambda x, y: P[np.clip(y, 0, H - 1), np.clip(x, 0, W - 1)]
    return (1 - ax) * (1 - ay) * c(ix, iy) + ax * (1 - ay) * c(ix + 1, iy) + (1 - ax) * ay * c(ix, iy + 1) + \
        ax * ay * c(ix + 1, iy + 1)


def judge(P, tag):
    s = sample(P, uv[:, 0], uv[:, 1])
    nv = len(me.vertices)
    lo = np.full(nv, 9.0)
    hi = np.full(nv, -9.0)
    np.minimum.at(lo, loops_v, s)
    np.maximum.at(hi, loops_v, s)
    dark = lo <= 0.4
    split = dark & (hi - lo > 0.3)
    print(f"{tag}: face verts {nv}, dark (any copy <= 0.4) {int(dark.sum())}, SPLIT (copies disagree > 0.3) "
          f"{int(split.sum())}, worst copy gap {float((hi - lo)[dark].max()) if dark.any() else 0:.2f}")
    return split


judge(pix, "mask as is")
if pad > 0:
    P = pix.copy()
    for _ in range(pad):
        Q = P.copy()
        white = P >= 0.999
        n = np.full_like(P, 1.0)
        n[1:, :] = np.minimum(n[1:, :], P[:-1, :])
        n[:-1, :] = np.minimum(n[:-1, :], P[1:, :])
        n[:, 1:] = np.minimum(n[:, 1:], P[:, :-1])
        n[:, :-1] = np.minimum(n[:, :-1], P[:, 1:])
        Q[white] = n[white]
        P = Q
    judge(P, f"padded {pad} px")
    if out:
        full = np.array(img.pixels[:], np.float32).reshape(H, W, img.channels)
        for ch in range(min(3, img.channels)):
            full[:, :, ch] = P
        img.pixels[:] = full.ravel().tolist()
        img.filepath_raw = out
        img.file_format = "PNG"
        img.save()
        print(f"wrote {out}")
