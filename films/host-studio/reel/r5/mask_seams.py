"""Round 5b loop 4 (agent-02), no editor: does the neck backstop's mask under-shrink at the face's UV seams and island
edges, and does padding fix it? MetaHuman samples the head hidden face map per RENDER vertex (one per UV split): a
face vertex on a seam has a copy on each island, and if one copy samples a dark texel and another a white one, the
neck tears there (one side shrinks, the other stays; a turn brings the unshrunk side through the collar).

Reads the face's UV 0 from garment.export's face.fbx and a mask PNG; per face vertex the bilinear sample of every UV
copy; reports `split` (copies disagreeing by > 0.3) and `dark` (any copy <= 0.4). With --pad N it pads the mask N
texels (each white texel next to a dark one takes the darkest neighbour, N times), recounts, and writes the padded
PNG (--out): that PNG is the loop-4 mask (apply with OUT=<it>).

With --redraw (implies --out) it draws the mask again from the FACE'S OWN per-corner UVs: each face vertex (copies
grouped by POSITION: an FBX export already splits a vertex at its UV seams, so index alone sees no seam) takes the
darkest value any of its copies samples from the given mask, and every triangle is rasterised with its own corners'
UVs. The editor's mask stage rasterised with ONE UV per (welded) vertex, so a triangle on the far side of a seam was
drawn on the near island and the far copies stayed white: the seam tear.

    blender -b --factory-startup -P mask_seams.py -- <face.fbx> <mask.png> [--redraw] [--pad 4 --out <padded.png>]
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

co = np.zeros(len(me.vertices) * 3)
me.vertices.foreach_get("co", co)
_, group = np.unique(np.round(co.reshape(-1, 3) * 1e4).astype(np.int64), axis=0, return_inverse=True)
group = group.ravel()
ng = int(group.max()) + 1
loops_g = group[loops_v]  # each corner's position group: the seam copies of one face vertex share it
redraw = "--redraw" in a
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
    lo = np.full(ng, 9.0)
    hi = np.full(ng, -9.0)
    np.minimum.at(lo, loops_g, s)
    np.maximum.at(hi, loops_g, s)
    dark = lo <= 0.4
    split = dark & (hi - lo > 0.3)
    print(f"{tag}: face verts {len(me.vertices)} ({ng} positions), dark (any copy <= 0.4) {int(dark.sum())}, SPLIT "
          f"(copies disagree > 0.3) {int(split.sum())}, worst copy gap "
          f"{float((hi - lo)[dark].max()) if dark.any() else 0:.2f}")
    return lo


def rasterise(val_g):
    """A white map with every face triangle drawn from its own corners' UVs, each corner's value its position
    group's (never 0: 1/255 at least, nothing culls)."""
    me.calc_loop_triangles()
    P = np.ones((H, W), np.float32)
    for t in me.loop_triangles:
        ls = list(t.loops)
        vals = np.maximum(val_g[loops_g[ls]], 1 / 255)
        if vals.min() >= 0.999:
            continue
        U = uv[ls] * [W, H]
        x0, x1 = int(max(0, np.floor(U[:, 0].min()))), int(min(W - 1, np.ceil(U[:, 0].max())))
        y0, y1 = int(max(0, np.floor(U[:, 1].min()))), int(min(H - 1, np.ceil(U[:, 1].max())))
        (ax, ay), (bx, by), (cx, cy) = U
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-9:
            continue
        X, Y = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        l1 = ((by - cy) * (X - cx) + (cx - bx) * (Y - cy)) / den
        l2 = ((cy - ay) * (X - cx) + (ax - cx) * (Y - cy)) / den
        l3 = 1 - l1 - l2
        inside = (l1 >= -0.02) & (l2 >= -0.02) & (l3 >= -0.02)
        v = l1 * vals[0] + l2 * vals[1] + l3 * vals[2]
        blk = P[y0:y1 + 1, x0:x1 + 1]
        P[y0:y1 + 1, x0:x1 + 1] = np.where(inside, np.minimum(blk, v), blk)
    # every corner's own bilinear footprint (the 2x2 texels its sample reads) takes its value too: a triangle smaller
    # than a texel draws no texel centre, and its corners then sampled white (loop 4 first try: 17 split left)
    val_l = np.maximum(val_g[loops_g], 1 / 255)
    for li in np.where(val_l < 0.999)[0]:
        fx, fy = uv[li, 0] * W - 0.5, uv[li, 1] * H - 0.5
        ix, iy = int(np.floor(fx)), int(np.floor(fy))
        for yy in (iy, iy + 1):
            for xx in (ix, ix + 1):
                if 0 <= xx < W and 0 <= yy < H:
                    P[yy, xx] = min(P[yy, xx], val_l[li])
    return P


lo = judge(pix, "mask as is")
P = pix.copy()
if redraw:
    P = rasterise(np.where(lo <= 0.999, lo, 1.0))
    judge(P, "redrawn from per-corner UVs")
if pad > 0:
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
if out and (pad > 0 or redraw):
    if True:
        full = np.array(img.pixels[:], np.float32).reshape(H, W, img.channels)
        for ch in range(min(3, img.channels)):
            full[:, :, ch] = P
        img.pixels[:] = full.ravel().tolist()
        img.filepath_raw = out
        img.file_format = "PNG"
        img.save()
        print(f"wrote {out}")
