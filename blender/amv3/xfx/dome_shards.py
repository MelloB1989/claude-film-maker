"""dome_shards (overlay on C20, window 550-562 around the 554 roll zoom-through S20 -> S21 dome crash): real glass shards
burst toward and past the camera on top of the core's zt (they only ADD objects; the camera is the core's).

Every shard lives in the world, not on the lens: its path is written in the frame of the camera at its birth (in front of
the lens, flying at it faster than the camera moves, spreading out and tumbling), then placed with ctx.cam_matrix, so the
zt's roll and zoom move the shards on screen like objects in the room. A shard alive across the teleport at cut-0.5 is
re-placed in B's set at the same camera-relative pose (no jump). Thin bevelled clear glass (refracts the cards behind),
a quarter carry the S21 picture as a reflection, a few edges glint (light pass), and two area lights ride with the camera
for specular flashes. Births follow a bell around cut+1.5 so the densest frames are 555-557, sparse by 561.
"""
import math
import os
import random
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fx3d as fx  # noqa: E402


def _cam(ctx, t):
    return fx.unit_matrix(ctx.cam_matrix(t))


def build_over(T, ctx):
    fx.set_linear_keys()
    p = T["p"]
    f, w0, w1 = T["f"], T["w0"], T["w1"]
    th = f - 0.5
    eps = getattr(ctx, "EPS", 0.02)
    rng = random.Random(5540 + f)
    plate, light = ctx.coll("plate"), ctx.coll("light")
    pal = ctx.palette(fx.act_id(ctx, f))
    n_big = int(p.get("dome_big", 34))
    n_chip = int(p.get("dome_chips", 70))
    peak_t = f + float(p.get("dome_peak", 1.6))

    glass = fx.glass_mat("ds_glass", tint=(0.93, 0.96, 1.0), emit=pal["rim"], emit_strength=0.08, rough=0.015, ior=1.5)
    frost = fx.glass_mat("ds_frost", tint=(0.9, 0.93, 0.97), emit=(1, 1, 1), emit_strength=0.0, rough=0.12, ior=1.5)
    pic = fx.picture_glass_mat(fx.plate_mat(ctx, T["b"]["id"]), "ds_pic", gloss_rough=0.03, gloss=1.0, dim=0.45)
    edge = fx.emission_mat("ds_edge", (1.0, 0.97, 0.92), 5.0, additive=True)

    def world(t, t_b, L):
        """Camera-at-birth local matrix L -> world at time t (re-placed across the teleport)."""
        W = _cam(ctx, t_b)
        if t_b < th <= t:
            W = _cam(ctx, th + eps) @ _cam(ctx, th - eps).inverted() @ W
        return W @ L

    def times(t0, t1):
        ts = [x for x in fx.frames_half(t0, t1) if abs(x - th) > 1e-6]
        if t0 < th < t1:
            ts += [th - eps, th + eps]
        return sorted(ts)

    shards = []
    for i in range(n_big + n_chip):
        big = i < n_big
        t_b = min(max(rng.gauss(peak_t - 1.8, 1.3), w0 + 0.5), w1 - 3.0)
        t_b = round(t_b * 2) / 2
        if big:
            L = rng.uniform(0.03, 0.11)
            n = rng.choice((3, 4, 4, 5, 6))
            poly = []
            for k in range(n):
                a = 2 * math.pi * (k + rng.uniform(-0.35, 0.35)) / n
                poly.append((L * math.cos(a) * rng.uniform(0.45, 1.5), L * math.sin(a) * rng.uniform(0.45, 1.0)))
            poly = sorted(poly, key=lambda q: math.atan2(q[1], q[0]))
            thick = rng.uniform(0.0025, 0.0045)
        else:
            L = rng.uniform(0.006, 0.02)
            poly = [(L * math.cos(2 * math.pi * k / 3 + rng.uniform(-0.5, 0.5)),
                     L * math.sin(2 * math.pi * k / 3 + rng.uniform(-0.5, 0.5))) for k in range(3)]
            thick = 0.0015
        u0, v0 = rng.uniform(0.2, 0.8), rng.uniform(0.2, 0.8)
        me, _ = fx.shard_mesh("ds_%03d" % i, poly, thick, lambda x, y, u0=u0, v0=v0: (u0 + x * 0.8, v0 + y * 0.8))
        r = rng.random()
        face = pic if (big and r < 0.25) else (frost if r > 0.85 else glass)
        me.materials.append(face)
        me.materials.append(glass)
        ob = bpy.data.objects.new(me.name, me)
        if big:
            fx.bevel(ob, min(0.0012, thick * 0.4))
        fx.link(ob, plate)
        # camera-local path: born in front of the lens, flying at it and outward, tumbling
        z0 = -rng.uniform(0.5, 1.5)
        ang = rng.uniform(0, 2 * math.pi)
        rad = abs(z0) * rng.uniform(0.02, 0.32)
        p0 = Vector((math.cos(ang) * rad * 1.15, math.sin(ang) * rad * 0.7, z0))
        vz = rng.uniform(0.22, 0.45) * (1.25 if not big else 1.0)
        out = Vector((math.cos(ang), math.sin(ang) * 0.7, 0)) * rng.uniform(0.02, 0.07)
        ax = fx.rand_axis(rng)
        spin = rng.uniform(14, 45) * (1.6 if not big else 1.0)
        q0 = Quaternion(fx.rand_axis(rng), rng.uniform(0, math.pi))
        t_end = t_b + min(6.0, (abs(z0) + 0.1) / vz + 0.5)
        prev = {}
        for t in times(t_b - 0.5, t_end):
            u = max(0.0, t - t_b)
            pos = p0 + Vector((0, 0, vz * u * (1 + 0.08 * u))) + out * u * (1 + 0.25 * u)
            Lm = Matrix.LocRotScale(pos, Quaternion(ax, math.radians(spin * u)) @ q0, None)
            fx.key_matrix(ob, t, world(t, t_b, Lm), prev)
        fx.key_visible(ob, t_b, t_end)
        if big and rng.random() < 0.35:
            pts = [(Vector((x, y, thick / 2 + 0.0002)), 1.0) for x, y in poly] + \
                  [(Vector((poly[0][0], poly[0][1], thick / 2 + 0.0002)), 1.0)]
            eo = fx.poly_curve(ob.name + "_edge", [pts], 0.00045, edge, caps=False)
            eo.parent = ob
            fx.link(eo, light)
            fx.key_visible(eo, t_b, t_end)
        shards.append(ob)
    for t, g in ((w0, 0.0), (f, 5.0), (peak_t + 1, 6.0), (w1, 1.5)):
        fx.key_glow(edge, t, g)

    # two area lights riding with the camera: the glass flashes as it turns through them
    for name, off, col, watts in (("ds_key", Vector((-0.6, 0.45, -0.2)), pal["key"], 60.0),
                                  ("ds_rim", Vector((0.7, -0.3, -0.5)), pal["rim"], 45.0)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.color = col[:3]
        ld.energy = watts
        ld.size = 0.5
        lo = bpy.data.objects.new(name, ld)
        lo.visible_camera = False
        bpy.context.scene.collection.objects.link(lo)
        rot = (Vector((0, 0, -0.8)) - off).to_track_quat("-Z", "Y")
        prev = {}
        for t in times(w0, w1):
            fx.key_matrix(lo, t, _cam(ctx, t) @ Matrix.LocRotScale(off, rot, None), prev)
        fx.key_visible(lo, w0, w1)
    ctx.log("dome_shards: %d glass shards + %d chips, births around f%.1f" % (n_big, n_chip, peak_t - 1.8))
