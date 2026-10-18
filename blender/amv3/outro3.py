"""Timeless v3 outro: the 3D SAU_EDITZ piece (comp frames 819-899, 1920x1080, 30 fps), Blender 5.2 Cycles.

    blender -b -t 12 --factory-startup -P blender/amv3/outro3.py -- [--res-scale 1] [--frames 819-899 | 828,844-850]
        [--every 1] [--samples 64] [--device CPU|OPTIX|CUDA] [--out DIR] [--save out/outro3.blend] [--no-render]

Frames land as `<out>/NNNN.png` (NNNN = comp frame, opaque RGBA); the default out is `$AMV3_DATA/blender/outro3`.
Built on v2's outro (blender/amv2/outro.py, imported read-only for its materials, portal, web, shafts and lights).

What v3 changes (EDIT.md motion rules, REFS.md): the camera never stops.
- 819: the triptych shatters (stage, xfx-B) with the camera pushing +10 %/f, rolling +1 deg/f clockwise. The outro opens on
  that same push (decaying x0.85/f), flying into a funnel web / multiverse ring tunnel, while act-coloured embers burst
  out of the frame centre with the stage's shards (the stage comps its shards over these frames until ~834).
- 819-862: the nine letters fly in, each on its own path, spin and time (some from the portal deep behind the word, some
  from behind the camera, overtaking the lens with motion blur), landing on the outro hits.
- 834-886: a slow push, a smooth reversal into a pull, a constant orbit and a small roll drift: hold drift ~1 %/f with
  parallax on everything; hits punch the camera (dolly + roll impulses that decay in 5-8 f) and pulse the light.
- 880: a light blade (a strip light seen only in reflections) sweeps across the bevels: real specular glints, starred
  by the compositor glare. 892: the big hit: the letters flip one after another (a 360 deg wave) under a second sweep.
- 888-899: the resolve: the camera pulls out and rolls faster and faster (ref a's logo outro), the word sinks into the
  portal, the rings collapse to a point on 897, black on 899. No white flash.
"""
from __future__ import annotations

import argparse
import math
import os
import random
import sys
import time
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "amv2"))
import outro as v2  # noqa: E402  (v2's outro, read-only: materials, portal, web, shafts, lights)

F0, F1 = 819, 899
FPS = 30
WORD = "SAU_EDITZ"
HITS = [(828, 0.55), (837, 0.6), (844, 1.0), (854, 0.65), (860, 0.75), (880, 0.5), (892, 1.0), (897, 0.7)]
HIT_FRAMES = [h for h, _ in HITS]
LENS = 35.0                       # the stage camera's lens (camlib.LENS_MM), so the 819 handoff speed matches

# palette: Spider-Man red face, gold-cream bevel, the act colours (EDIT.md / triptych shard rims)
RED = (0.55, 0.004, 0.012)
HOT = (1.0, 0.07, 0.10)
GOLD = (1.0, 0.62, 0.22)
CREAM = (1.0, 0.86, 0.62)
TOBEY = (1.0, 0.72, 0.32)
ANDREW = (0.35, 0.80, 1.0)
TOM = (1.0, 0.36, 0.12)
WHITE = (1.0, 0.97, 0.95)
NAVY = (0.010, 0.012, 0.05)

# letter flights: index -> (start, landing, offset from rest (m), start rotation (deg), start scale)
FLIGHTS = {
    4: (819, 828, (0.0, 30.0, 2.0), (40, 260, -30), 0.3),        # E  born in the burst, spins out of the portal
    7: (820, 837, (-18.0, 6.0, -10.0), (-70, -170, 40), 1.0),    # T  from deep lower left
    2: (821, 844, (16.0, -20.0, -9.0), (80, 150, -95), 1.0),     # U  sweeps across the lens from the lower right (big hit)
    1: (823, 848, (3.0, 34.0, 9.0), (-165, 40, -125), 0.4),      # A  out of the portal, high
    5: (825, 854, (20.0, 4.0, 11.0), (-120, 60, 160), 1.0),      # D  far right, high
    0: (827, 857, (-20.0, -16.0, -7.0), (140, -80, 205), 1.0),   # S  skims past the lens from the lower left
    8: (829, 860, (11.0, 10.0, 16.0), (170, 105, 70), 1.0),      # Z  drops from the top right
    6: (831, 860, (2.5, -40.0, -2.0), (200, -35, 60), 1.0),      # I  from behind the camera: overtakes the lens
    3: (833, 862, (-6.0, -4.0, 18.0), (0, 115, 75), 1.0),        # _  swings down like a pendulum onto the baseline
}
FLIP_F = 892                      # the big hit: a flip wave runs through the word
SINK_F = 893                      # the word sinks back into the portal


clamp, smooth, out_pow, env, ring_osc, lerp = v2.clamp, v2.smooth, v2.out_pow, v2.env, v2.ring_osc, v2.lerp
node, link, new_mat, rgba, key, linearize = v2.node, v2.link, v2.new_mat, v2.rgba, v2.key, v2.linearize


def frames():
    return range(F0, F1 + 1)


def subframes():
    """Every frame and half frame: the camera and the fast letters are keyed here so the centred shutter samples exact
    motion (LINEAR between keys)."""
    for f in range(F0 - 1, F1 + 2):
        yield float(f)
        yield f + 0.5


def pulse_env(f, scale=1.0, decay=3.0):
    return sum(s * env(f, h, decay) for h, s in HITS) * scale


# --- camera ------------------------------------------------------------------------------------------------------------
def zoom_rate(f):
    """Camera push rate in d ln(distance) per frame (+ = push in). EDIT.md motion rules: continuous, never zero."""
    k = f - 819.5
    push = 0.10 * 0.85 ** max(0.0, k) if k >= 0 else 0.10 * 1.25 ** k     # the triptych's push, decaying x0.85/f
    hold = 0.012 * smooth((f - 822) / 10.0)                                 # settles into a 1.2 %/f push
    hold = lerp(hold, -0.008, smooth((f - 856) / 10.0))                     # smooth reversal (10 f) into a slow pull
    pull = -0.008 * (1.33 ** (f - 888) - 1.0) if f > 888 else 0.0           # the resolve: accelerating pull-out
    pull = max(pull, -0.13)
    return push + hold + pull


def build_dist_table(d_end_hold=17.5):
    """d(f) on every half frame from the rate curve; anchored so the camera is d_end_hold from the word at 860."""
    ts = [F0 - 2 + 0.5 * i for i in range(int((F1 + 3 - (F0 - 2)) * 2) + 1)]
    ln = [0.0]
    for a, b in zip(ts, ts[1:]):
        ln.append(ln[-1] - 0.5 * (zoom_rate(a) + zoom_rate(b)) * (b - a))
    anchor = min(range(len(ts)), key=lambda i: abs(ts[i] - 860))
    off = math.log(d_end_hold) - ln[anchor]
    return {t: math.exp(v + off) for t, v in zip(ts, ln)}


def roll_deg(f):
    """Camera roll in degrees (+ = the picture turns clockwise). Integrated from a rate so it never steps."""
    total, t = 0.0, F0 - 1.0
    while t < f:
        dt = min(0.25, f - t)
        tm = t + dt / 2
        r = 1.0 * 0.85 ** max(0.0, tm - 819.5)                              # the triptych's +1 deg/f, decaying
        r += 0.18 * math.sin((tm - 819) * 0.07)                             # slow roll drift through the hold
        r += sum(s * 1.6 * (1 if i % 2 else -1) * env(tm, h, 2.5) for i, (h, s) in enumerate(HITS[:-2]))
        if tm > 886:
            r += 0.5 * (1.36 ** (tm - 886) - 1.0) if tm < 899 else 0.5 * (1.36 ** 13 - 1.0)   # the resolve spin
        total += r * dt
        t += dt
    return total


def build_camera():
    sc = bpy.context.scene
    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = LENS
    cam_d.sensor_width = 36.0
    cam_d.clip_start, cam_d.clip_end = 0.05, 400.0
    cam_d.dof.use_dof = True
    cam_d.dof.aperture_fstop = 0.9
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    rig = bpy.data.objects.new("camrig", None)
    sc.collection.objects.link(rig)
    cam.parent = rig
    cam.rotation_mode = "QUATERNION"
    rig.rotation_mode = "XYZ"
    q90 = Quaternion((1, 0, 0), math.pi / 2)
    D = build_dist_table()
    rnd = random.Random(3)
    jit = [(rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1)) for _ in range(800)]
    for i, t in enumerate(subframes()):
        d = D[min(D, key=lambda x: abs(x - t))]
        punch = sum(s * ring_osc(t, h, 2.6, 1.0) for h, s in HITS[:-2])
        d *= 1.0 - 0.025 * punch                                            # dolly kick on the hits
        u = (t - F0) / (F1 - F0)
        az = math.radians(-16 + 30 * smooth(u * 1.1) + 1.0 * math.sin(u * 7.0))    # a slow orbit that never stops
        el = math.radians(6.0 - 7.0 * smooth(u) + 0.6 * punch)
        shake = sum(s * env(t, h, 2.2) for h, s in HITS[:-2]) * 0.004
        j = jit[i % 800]
        rig.location = (0.0, 0.0, 0.35)
        rig.rotation_euler = (el + shake * j[0], 0.0, az + shake * j[1])
        cam.location = (0.0, -d, 0.0)
        cam.rotation_quaternion = q90 @ Quaternion((0, 0, 1), math.radians(-roll_deg(t)))
        rig.keyframe_insert("location", frame=t)
        rig.keyframe_insert("rotation_euler", frame=t)
        cam.keyframe_insert("location", frame=t)
        cam.keyframe_insert("rotation_quaternion", frame=t)
        # focus on the word (rack in from the burst over 819-826), aperture opens on the resolve
        key(cam_d.dof, "focus_distance", t, max(1.0, d - 0.4))
        key(cam_d.dof, "aperture_fstop", t, 2.8 if t < 886 else lerp(2.8, 1.2, smooth((t - 886) / 10)))
    linearize(rig)
    linearize(cam)
    linearize(cam_d)
    print(f"outro3: camera d 819={D[819.0]:.1f} 834={D[834.0]:.1f} 860={D[860.0]:.1f} 886={D[886.0]:.1f} 899={D[899.0]:.1f}")
    return cam


# --- letters -------------------------------------------------------------------------------------------------------------
def letter_material(name, kind):
    """kind: front (candy red) | bevel (gold-cream metal, glossy) | side (deep red-black metal)."""
    m, nt = new_mat(name)
    out = node(nt, "ShaderNodeOutputMaterial", 900, 0)
    bs = node(nt, "ShaderNodeBsdfPrincipled", 600, 0, name="BSDF")
    link(nt, bs.outputs[0], out.inputs[0])
    pulse = node(nt, "ShaderNodeValue", 100, -300, name="PULSE")
    lw = node(nt, "ShaderNodeLayerWeight", 100, -100)
    mul = node(nt, "ShaderNodeMath", 300, -150, operation="MULTIPLY")
    link(nt, pulse.outputs[0], mul.inputs[1])
    link(nt, mul.outputs[0], bs.inputs["Emission Strength"])
    if kind == "front":
        bs.inputs["Base Color"].default_value = rgba(RED)
        bs.inputs["Metallic"].default_value = 0.45
        bs.inputs["Roughness"].default_value = 0.16
        bs.inputs["Coat Weight"].default_value = 1.0
        bs.inputs["Coat Roughness"].default_value = 0.03
        bs.inputs["Emission Color"].default_value = rgba(HOT)
        lw.inputs["Blend"].default_value = 0.6
        link(nt, lw.outputs["Facing"], mul.inputs[0])
        pulse.outputs[0].default_value = 0.12
    elif kind == "bevel":
        bs.inputs["Base Color"].default_value = rgba(CREAM)
        bs.inputs["Metallic"].default_value = 1.0
        bs.inputs["Roughness"].default_value = 0.12
        bs.inputs["Coat Weight"].default_value = 0.5
        bs.inputs["Coat Roughness"].default_value = 0.02
        bs.inputs["Emission Color"].default_value = rgba(GOLD)
        lw.inputs["Blend"].default_value = 0.3
        link(nt, lw.outputs["Fresnel"], mul.inputs[0])
        pulse.outputs[0].default_value = 0.35
    else:
        bs.inputs["Base Color"].default_value = rgba((0.10, 0.006, 0.01))
        bs.inputs["Metallic"].default_value = 0.85
        bs.inputs["Roughness"].default_value = 0.25
        bs.inputs["Emission Color"].default_value = rgba(TOM)
        lw.inputs["Blend"].default_value = 0.5
        link(nt, lw.outputs["Fresnel"], mul.inputs[0])
        pulse.outputs[0].default_value = 0.25
    m["rest_pulse"] = pulse.outputs[0].default_value
    return m


WORD_W, CAP, GAP = 14.6, 3.7, 0.15


def build_letters(mats_for):
    """v2's layout (Spider-Man font, the same kerning) with a chunkier extrusion and a deeper bevel (the v3 title look)."""
    font = bpy.data.fonts.load(v2.find_font())
    trial = v2.glyph_mesh(font, "SAUEDITZ", 1.0, 0.0, 0.0)
    v2.stand_up(trial)
    _, _, z0, z1 = v2.bounds(trial)
    bpy.data.meshes.remove(trial)
    cap1 = z1 - z0
    unit, stem, tz0, tz1 = {}, 0.0, 0.0, 0.0
    for ch in set(WORD) - {"_"}:
        m = v2.glyph_mesh(font, ch, 1.0, 0.0, 0.0)
        v2.stand_up(m)
        a, b, c, d = v2.bounds(m)
        unit[ch] = b - a
        if ch == "T":
            zs = [v.co.z for v in m.vertices]
            lo, hi = min(zs), max(zs)
            xs = [v.co.x for v in m.vertices if v.co.z < lo + 0.15 * (hi - lo)]
            stem, tz0, tz1 = max(xs) - min(xs), c, d
        bpy.data.meshes.remove(m)
    bar_w1 = 0.46 * cap1
    w1 = [bar_w1 if ch == "_" else stem if ch == "I" else unit[ch] for ch in WORD]
    g1 = [GAP + v2.KERN.get(p, 0.0) for p in zip(WORD, WORD[1:])]
    size = CAP / cap1
    for _ in range(4):
        k = size * cap1 / CAP
        size = min(CAP / cap1, (WORD_W - 0.28 * k * len(w1)) / (sum(w1) + sum(g1)))
    k = size * cap1 / CAP
    extrude, bevel = 0.85 * k, 0.14 * k
    gaps = [size * g for g in g1]
    parts = []
    for ch in WORD:
        if ch == "_":
            w = bar_w1 * size
            me = v2.bar_mesh(w, 0.13 * cap1 * size, extrude, bevel)
            cz = -cap1 * size * 0.56
        elif ch == "I":
            w = stem * size + 2 * bevel
            me = v2.bar_mesh(w, (tz1 - tz0) * size + 2 * bevel, extrude, bevel)
            cz = (tz0 + tz1) / 2 * size
        else:
            me = v2.glyph_mesh(font, ch, size, extrude, bevel)
            v2.stand_up(me)
            a, b, c, d = v2.bounds(me)
            cx, cz = (a + b) / 2, (c + d) / 2
            w = b - a
            me.transform(Matrix.Translation((-cx, 0, -cz)))
        parts.append([ch, me, w, cz])
    total = sum(p[2] for p in parts) + sum(gaps)
    cap_c = (z0 + z1) / 2 * size
    objs, x = [], -total / 2
    for i, (ch, me, w, cz) in enumerate(parts):
        v2.split_materials(me, mats_for(i))
        ob = bpy.data.objects.new(f"L{i}_{ch}", me)
        bpy.context.scene.collection.objects.link(ob)
        rest = (x + w / 2, 0.0, (cz - cap_c) if ch != "_" else cz)
        ob.location = rest
        ob["rest"] = rest
        ob.rotation_mode = "XYZ"
        objs.append(ob)
        x += w + (gaps[i] if i < len(gaps) else 0.0)
    return objs, {"width": total, "height": cap1 * size}


def letter_pose(i, f, rest, order):
    """Position (m), euler (rad), uniform scale of letter i at comp frame f (float)."""
    fs, fl, off, rot, s0 = FLIGHTS[i]
    rest = Vector(rest)
    uc = clamp((f - fs) / (fl - fs))
    e_pos = out_pow(uc, 3.0)                 # fast out of the dark, a long readable settle
    e_rot = out_pow(uc, 2.4)
    off = Vector(off)
    side = off.cross(Vector((0, 0, 1)))
    side = side.normalized() if side.length > 1e-4 else Vector((1, 0, 0))
    arc = side * (0.22 * off.length * math.sin(math.pi * e_pos) * (1 - e_pos))
    pos = rest + off * (1 - e_pos) + arc
    rot_v = [math.radians(a) * (1 - e_rot) for a in rot]
    sc = lerp(s0, 1.0, out_pow(uc, 2.2))
    sc *= max(0.0005, out_pow(clamp((f - fs) / 3.0), 2.0))     # materialises over its first 3 frames, no pop
    t = f - fl
    if t >= 0:                               # landing: a damped spring in depth with a little squash and tilt
        sp = math.exp(-t / 2.6) * math.cos(t * 1.25)
        pos += Vector((0, 0.7 * sp, 0))
        sc *= 1 + 0.07 * sp
        rot_v[2] += 0.05 * sp * (1 if i % 2 else -1)
        ph = i * 0.9                          # lockup: a slow float so nothing is ever still
        pos += Vector((0.03 * math.sin(f * 0.11 + ph), 0.06 * math.sin(f * 0.07 + ph), 0.04 * math.cos(f * 0.09 + ph)))
        rot_v[2] += 0.008 * math.sin(f * 0.09 + ph)
        # every later hit knocks the landed word back a little (a wave from the centre outwards)
        for h, s in HITS[:-2]:
            if h > fl:
                pos += Vector((0, 0.35 * s * ring_osc(f, h + abs(rest.x) * 0.06, 2.4, 1.3), 0))
    sw = env(f, 880 + order * 0.55, 2.2)      # the 880 sweep lifts each letter as the blade passes
    pos += Vector((0, -0.25 * sw, 0))
    # 892: the flip wave, one letter after another left to right, a full turn about the vertical axis
    u = clamp((f - FLIP_F - order * 0.45) / 5.0)
    rot_v[2] += 2 * math.pi * (u * u * (3 - 2 * u))
    # 893-899: the word sinks into the portal and shrinks to its centre
    k = clamp((f - SINK_F - abs(order - 4) * 0.25) / 6.0)
    if k > 0:
        e = k * k
        pos = pos.lerp(Vector((0.0, 9.0, 0.3)), e)
        sc *= 1.0 - 0.9 * e
    return pos, rot_v, sc


def animate_letters(objs, face_mats):
    order = {i: r for r, i in enumerate(sorted(range(len(objs)), key=lambda j: objs[j]["rest"][0]))}
    for i, ob in enumerate(objs):
        rest = ob["rest"]
        pulses = [(m.node_tree.nodes["PULSE"].outputs[0], m["rest_pulse"]) for m in face_mats[i]]
        for t in subframes():
            pos, rot, sc = letter_pose(i, t, rest, order[i])
            ob.location = pos
            ob.rotation_euler = rot
            ob.scale = (sc, sc, sc)
            ob.keyframe_insert("location", frame=t)
            ob.keyframe_insert("rotation_euler", frame=t)
            ob.keyframe_insert("scale", frame=t)
        for f in frames():
            land = FLIGHTS[i][1]
            glow = env(f, land, 4.0) * (1.0 if land in HIT_FRAMES else 0.6)
            glow += env(f, 880 + order[i] * 0.55, 3.0) * 0.7 + pulse_env(f, 0.35, 2.5)
            glow += 1.2 * env(f, FLIP_F + order[i] * 0.45, 3.0)
            ramp = smooth((f - FLIGHTS[i][0]) / 6.0)
            for sock, rest_v in pulses:
                key(sock, "default_value", f, rest_v * (0.35 + 0.65 * ramp) * (1.0 + 1.8 * glow))
        linearize(ob)
        for m in face_mats[i]:
            linearize(m.node_tree)


# --- the living background ---------------------------------------------------------------------------------------------
def make_curve(name, mat, bevel):
    return v2.make_curve(name, mat, bevel)


def build_funnel_web():
    """A funnel web the camera flies into: spokes from a hub deep behind the portal out to a wide mouth behind the
    camera's start, crossed by sagging spiral threads. Parallax on every frame; it breathes on the hits."""
    mat = v2.metal_material("funnel_metal", (0.35, 0.42, 0.70), 0.08)
    rnd = random.Random(21)
    hub_y, mouth_y, R_hub, R_mouth = 70.0, -70.0, 2.0, 30.0
    n_sp, n_ring = 18, 26
    ob_s, cu_s = make_curve("funnel_spokes", mat, 0.014)
    ob_r, cu_r = make_curve("funnel_rings", mat, 0.008)
    ang = [2 * math.pi * i / n_sp + rnd.uniform(-0.08, 0.08) for i in range(n_sp)]

    def rad(y):
        u = (hub_y - y) / (hub_y - mouth_y)
        return R_hub + (R_mouth - R_hub) * u ** 1.6

    for a in ang:
        pts = []
        for s in range(12):
            y = lerp(hub_y, mouth_y, s / 11)
            r = rad(y)
            pts.append((r * math.cos(a), y, r * math.sin(a)))
        v2.poly(cu_s, pts)
    for k in range(n_ring):
        y0 = lerp(hub_y - 4, mouth_y + 2, (k / (n_ring - 1)) ** 0.9)
        pts = []
        for i in range(n_sp):
            a0 = ang[i]
            a1 = ang[(i + 1) % n_sp] + (2 * math.pi if i == n_sp - 1 else 0)
            for s in range(5):
                u = s / 5
                a = lerp(a0, a1, u)
                y = y0 + 1.2 * math.sin(math.pi * u)            # threads sag toward the hub between spokes
                r = rad(y) * (1 - 0.04 * math.sin(math.pi * u))
                pts.append((r * math.cos(a), y, r * math.sin(a)))
        v2.poly(cu_r, pts, cyclic=True)
    for ob in (ob_s, ob_r):
        ob.rotation_mode = "XYZ"
    for f in frames():
        t = f - F0
        wob = 1.0 + 0.012 * sum(s * ring_osc(f, h, 3.2, 1.35) for h, s in HITS)
        for ob in (ob_s, ob_r):
            ob.scale = (wob, 1.0, wob)
            ob.rotation_euler = (0, -0.004 * t, 0)              # the tunnel turns slowly about its axis
            ob.keyframe_insert("scale", frame=f)
            ob.keyframe_insert("rotation_euler", frame=f)
        draw = out_pow((f - 818) / 7.0, 2.0)                     # the web spins on as the burst opens it
        key(cu_s, "bevel_factor_end", f, draw)
        key(cu_r, "bevel_factor_end", f, out_pow((f - 820) / 9.0, 2.0))
        if f >= 894:
            key(cu_s, "bevel_factor_start", f, 1.0 - clamp(1.0 - (f - 894) / 5.0))
            key(cu_r, "bevel_factor_start", f, 1.0 - clamp(1.0 - (f - 894) / 5.0))
    bs = mat.node_tree.nodes["BSDF"].inputs["Emission Strength"]
    for f in frames():
        key(bs, "default_value", f, 0.08 * (1 + 1.5 * pulse_env(f, 1.0, 3.0)) * (1.0 if f < 896 else max(0.0, 1 - (f - 896) / 3)))
    for o in (ob_s, ob_r, cu_s, cu_r, mat.node_tree):
        linearize(o)


def torus_mesh(name, R, r, n_major=128, n_minor=8):
    bm = bmesh.new()
    for i in range(n_major):
        a = 2 * math.pi * i / n_major
        for j in range(n_minor):
            b = 2 * math.pi * j / n_minor
            bm.verts.new(((R + r * math.cos(b)) * math.cos(a), (R + r * math.cos(b)) * math.sin(a), r * math.sin(b)))
    bm.verts.ensure_lookup_table()
    for i in range(n_major):
        for j in range(n_minor):
            a0, a1 = i, (i + 1) % n_major
            b0, b1 = j, (j + 1) % n_minor
            bm.faces.new((bm.verts[a0 * n_minor + b0], bm.verts[a1 * n_minor + b0], bm.verts[a1 * n_minor + b1],
                          bm.verts[a0 * n_minor + b1]))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    return me


def build_ring_tunnel():
    """Multiverse rings receding behind the portal (Tobey gold, Andrew cyan, Tom red, white), each precessing on its own;
    they light up in sequence on the hits (a pulse travelling down the tunnel)."""
    specs = [(20.0, 11.0, TOBEY), (34.0, 13.0, ANDREW), (50.0, 15.0, TOM), (68.0, 17.0, WHITE)]
    rings = []
    for k, (y, R, col) in enumerate(specs):
        me = torus_mesh(f"tun{k}", R, 0.05 + 0.012 * k)
        mt, st, _ = v2.emit_material(f"tun{k}", col, 2.0)
        me.materials.append(mt)
        ob = bpy.data.objects.new(f"tun{k}", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.location = (0, y, 0)
        ob.rotation_mode = "ZYX"
        rings.append((ob, st, k, mt))
    for f in frames():
        t = f - F0
        for ob, st, k, mt in rings:
            ob.rotation_euler = (math.pi / 2 + 0.25 * math.sin(t * 0.05 + k), 0.2 * math.cos(t * 0.04 + 2 * k),
                                 t * 0.015 * (1 if k % 2 else -1))
            ob.keyframe_insert("rotation_euler", frame=f)
            born = out_pow((f - 819 - 1.0 * k) / 6.0, 3)
            s = 0.15 + 0.85 * born
            if f >= 894:
                s *= max(0.02, 1.0 - smooth((f - 894 - 0.4 * (3 - k)) / 4.0))     # the tunnel closes from the far end
            ob.scale = (s, s, s)
            ob.keyframe_insert("scale", frame=f)
            travel = sum(sc * env(f, h + 0.8 * k, 2.5) for h, sc in HITS)
            key(st, "default_value", f, (0.5 + 2.5 * travel) * born * (1.0 if f < 896 else max(0.0, 1 - (f - 896) / 3)))
    for ob, st, k, mt in rings:
        linearize(ob)
        linearize(mt.node_tree)


def mote_mesh(name, n, box, size, rnd, avoid_r=0.0):
    """Many tiny octahedra scattered in a box (one mesh: cheap). avoid_r keeps a clear radius around the Y axis."""
    bm = bmesh.new()
    (x0, x1), (y0, y1), (z0, z1) = box
    made = 0
    while made < n:
        p = Vector((rnd.uniform(x0, x1), rnd.uniform(y0, y1), rnd.uniform(z0, z1)))
        if math.hypot(p.x, p.z) < avoid_r:
            continue
        s = size * rnd.uniform(0.5, 1.4)
        vs = [bm.verts.new(p + Vector(d) * s) for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))]
        for a, b, c in ((0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4), (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)):
            bm.faces.new((vs[a], vs[b], vs[c]))
        made += 1
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def build_motes():
    """Drifting dust/energy motes in three layers that swirl about the tunnel axis (a slow vortex): parallax, motion blur
    streaks near the lens, never still. Plus the 819 burst: embers in the act colours fly out of the frame centre toward
    the camera with the stage's shards (one object scaled up from the centre = radial motion, exact motion blur)."""
    rnd = random.Random(5)
    layers = []
    for k, (col, n, st) in enumerate(((TOBEY, 260, 3.0), (ANDREW, 260, 3.0), (WHITE, 180, 4.0))):
        me = mote_mesh(f"motes{k}", n, ((-26, 26), (-60, 50), (-15, 15)), 0.045, rnd, avoid_r=1.5)
        mt, s_in, _ = v2.emit_material(f"motes{k}", col, st)
        me.materials.append(mt)
        ob = bpy.data.objects.new(f"motes{k}", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.rotation_mode = "XYZ"
        layers.append((ob, s_in, st, k, mt))
    for f in frames():
        t = f - F0
        for ob, s_in, st, k, mt in layers:
            ob.rotation_euler = (0, (0.006 + 0.003 * k) * t * (1 if k != 1 else -1), 0)
            ob.location = (0, -0.05 * t * (k + 1), 0)                   # drifting toward the camera
            ob.keyframe_insert("rotation_euler", frame=f)
            ob.keyframe_insert("location", frame=f)
            v = st * (0.6 + 0.6 * pulse_env(f, 1.0, 3.0)) * (1.0 if f < 895 else max(0.0, 1 - (f - 895) / 4))
            key(s_in, "default_value", f, v)
    for ob, s_in, st, k, mt in layers:
        linearize(ob)
        linearize(mt.node_tree)
    # the burst
    for k, col in enumerate((TOBEY, ANDREW, TOM)):
        me = mote_mesh(f"embers{k}", 70, ((-1.2, 1.2), (-0.6, 0.6), (-0.7, 0.7)), 0.010, rnd)
        mt, s_in, _ = v2.emit_material(f"embers{k}", col, 30.0)
        me.materials.append(mt)
        ob = bpy.data.objects.new(f"embers{k}", me)
        bpy.context.scene.collection.objects.link(ob)
        for f in frames():
            u = max(0.0, f - 819.5 + 0.3 * k)
            s = 1.0 + 9.0 * (1 - math.exp(-u / 4.0)) + 1.5 * u              # fast out, then a steady spread
            ob.scale = (s, s * 0.5, s)
            ob.location = (0, 6.0 - 1.6 * u, 0.35)                          # from the portal toward (and past) the lens
            ob.keyframe_insert("scale", frame=f)
            ob.keyframe_insert("location", frame=f)
            key(s_in, "default_value", f, 30.0 * math.exp(-u / 3.5) if f >= 819 else 0.0)
        linearize(ob)
        linearize(mt.node_tree)


def build_sweep_light():
    """The light blade: a bright strip seen only in reflections (not by the camera) that crosses in front of the word on
    880 and again on 892, so the glossy bevels and the coat catch a real moving specular highlight."""
    me = bpy.data.meshes.new("blade")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
    bm.to_mesh(me)
    bm.free()
    mat, st, _ = v2.emit_material("blade", WHITE, 0.0)
    me.materials.append(mat)
    ob = bpy.data.objects.new("blade", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.visible_camera = False
    ob.visible_shadow = False
    ob.scale = (1.2, 26.0, 1.0)
    ob.rotation_mode = "XYZ"
    passes = [(878.0, 8.0, -1, 60.0), (890.5, 5.0, 1, 90.0), (843.0, 6.0, 1, 30.0)]
    for t in subframes():
        x, s_val, tilt = 40.0, 0.0, 0.3
        for f0, dur, sgn, power in passes:
            u = (t - f0) / dur
            if 0.0 <= u <= 1.0:
                x = sgn * lerp(-16.0, 16.0, u)
                s_val = power * math.sin(math.pi * u) ** 0.7
                tilt = 0.3 * sgn
        ob.location = (x, -9.0, 2.0)
        ob.rotation_euler = (math.radians(80), tilt, 0.0)               # faces the word, leaning, above the lens line
        ob.keyframe_insert("location", frame=t)
        ob.keyframe_insert("rotation_euler", frame=t)
        key(st, "default_value", t, s_val)
    linearize(ob)
    linearize(mat.node_tree)


def build_finale_glint():
    """897: the rings collapse into a point; a last bright core flares and dies (the compositor stars it), then black."""
    me = bpy.data.meshes.new("core")
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=1.0)
    bm.to_mesh(me)
    bm.free()
    mat, st, _ = v2.emit_material("core", (1.0, 0.85, 0.7), 0.0)
    me.materials.append(mat)
    ob = bpy.data.objects.new("core", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = (0, 9.0, 0.3)
    for t in subframes():
        a = env(t, 896.5, 1.2) if t >= 896.5 else smooth((t - 893) / 3.5) * 0.25
        r = 0.08 + 0.5 * a
        ob.scale = (r, r, r)
        ob.keyframe_insert("scale", frame=t)
        key(st, "default_value", t, 300.0 * a)
    linearize(ob)
    linearize(mat.node_tree)


def build_black():
    """898-899: the last light dies; 899 is exactly black (a holdout card at the lens)."""
    cam = bpy.context.scene.camera
    me = bpy.data.meshes.new("black")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("black", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = cam
    ob.location = (0, 0, -0.3)
    ob.scale = (0.3, 0.2, 1.0)
    for a in ("visible_diffuse", "visible_glossy", "visible_transmission", "visible_shadow", "visible_volume_scatter"):
        setattr(ob, a, False)
    mat, _st, fac = v2.emit_material("black", (0, 0, 0), 1.0, alpha=0.0)
    me.materials.append(mat)
    for f in frames():
        key(fac, "default_value", f, {898: 0.55, 899: 1.0}.get(f, 0.0))
    linearize(mat.node_tree)


# --- compositor ----------------------------------------------------------------------------------------------------------
def build_compositor(res_scale):
    """Bloom on the light, star streaks on the brightest speculars (real glints), and a chromatic split on the hits."""
    sc = bpy.context.scene
    nt = bpy.data.node_groups.new("outro3_comp", "CompositorNodeTree")
    sc.compositing_node_group = nt
    nt.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = node(nt, "CompositorNodeRLayers", 0, 0)
    last = rl.outputs["Image"]
    gl = node(nt, "CompositorNodeGlare", 250, 0)
    gl.inputs["Type"].default_value = "Streaks"
    gl.inputs["Threshold"].default_value = 6.0
    gl.inputs["Quality"].default_value = "Medium"
    gl.inputs["Strength"].default_value = 0.5
    for k, v in (("Streaks", 4), ("Streaks Angle", math.radians(45)), ("Fade", 0.88)):
        try:
            gl.inputs[k].default_value = v
        except (KeyError, TypeError) as e:
            print("outro3: glare streaks input", k, "skipped:", e)
    link(nt, last, gl.inputs["Image"])
    bl = node(nt, "CompositorNodeGlare", 500, 0)
    bl.inputs["Type"].default_value = "Bloom"
    bl.inputs["Threshold"].default_value = 2.0
    bl.inputs["Size"].default_value = 0.7
    bl.inputs["Quality"].default_value = "Medium"
    bl.inputs["Strength"].default_value = 0.35
    link(nt, gl.outputs["Image"], bl.inputs["Image"])
    last = bl.outputs["Image"]
    split = None
    try:
        sepc = node(nt, "CompositorNodeSeparateColor", 750, 0)
        link(nt, last, sepc.inputs[0])
        tr_r = node(nt, "CompositorNodeTranslate", 950, 120)
        tr_b = node(nt, "CompositorNodeTranslate", 950, -120)
        link(nt, sepc.outputs["Red"], tr_r.inputs["Image"])
        link(nt, sepc.outputs["Blue"], tr_b.inputs["Image"])
        comb = node(nt, "CompositorNodeCombineColor", 1150, 0)
        link(nt, tr_r.outputs["Image"], comb.inputs["Red"])
        link(nt, sepc.outputs["Green"], comb.inputs["Green"])
        link(nt, tr_b.outputs["Image"], comb.inputs["Blue"])
        link(nt, sepc.outputs["Alpha"], comb.inputs["Alpha"])
        last = comb.outputs["Image"]
        split = (tr_r, tr_b)
    except Exception as e:
        print("outro3: chromatic split skipped:", e)
    go = node(nt, "NodeGroupOutput", 1400, 0)
    link(nt, last, go.inputs[0])
    if split:
        for f in frames():
            # 819-822: the burst carries the stage's lens split; then hits only, decaying over 2-3 f
            amt = 10.0 * math.exp(-max(0.0, f - 819) / 2.0) + sum(s * 7.0 * env(f, h, 1.3) for h, s in HITS[:-1])
            amt *= res_scale
            for t_, sign in ((split[0], 1), (split[1], -1)):
                t_.inputs["X"].default_value = sign * amt
                t_.inputs["X"].keyframe_insert("default_value", frame=f)
        linearize(nt)


# --- render setup ---------------------------------------------------------------------------------------------------------
def setup_render(args):
    v2.setup_render(args)            # Cycles, AgX Punchy, PNG RGBA 8-bit, the device selection
    sc = bpy.context.scene
    sc.cycles.samples = args.samples
    sc.cycles.adaptive_threshold = 0.03
    sc.cycles.glossy_bounces = 3
    sc.cycles.transparent_max_bounces = 12
    sc.render.motion_blur_shutter = 0.75
    sc.frame_start, sc.frame_end = F0, F1


def build_scene(args):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    setup_render(args)
    templates = {k: letter_material(f"tpl_{k}", k) for k in ("front", "bevel", "side")}
    per_letter = []

    def mats_for(i):
        ms = []
        for k in ("front", "bevel", "side"):
            m = templates[k].copy()
            m.name = f"L{i}_{k}"
            ms.append(m)
        per_letter.append(ms)
        return ms

    objs, layout = build_letters(mats_for)
    print(f"outro3: word {layout['width']:.2f} x {layout['height']:.2f} m")
    v2.build_world()
    v2.build_lights()
    v2.build_portal()
    v2.build_shafts()
    build_funnel_web()
    build_ring_tunnel()
    build_motes()
    build_sweep_light()
    build_finale_glint()
    animate_letters(objs, per_letter)
    build_camera()
    build_black()
    build_compositor(args.res_scale)


def parse(argv):
    ap = argparse.ArgumentParser(prog="outro3.py")
    ap.add_argument("--res-scale", type=float, default=1.0)
    ap.add_argument("--frames", help="comp frames, e.g. 819-899 or 828,844-850 (default all)")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--device", default="CPU", help="CPU | OPTIX | CUDA | HIP | AUTO")
    ap.add_argument("--out", help="default $AMV3_DATA/blender/outro3, else out/amv3/outro3")
    ap.add_argument("--save", help="save the .blend here")
    ap.add_argument("--no-render", action="store_true")
    return ap.parse_args(argv)


def main(argv):
    args = parse(argv)
    t0 = time.time()
    build_scene(args)
    print(f"outro3: scene built in {time.time() - t0:.1f}s")
    sc = bpy.context.scene
    default = Path(os.environ["AMV3_DATA"]) / "blender/outro3" if os.environ.get("AMV3_DATA") else Path("out/amv3/outro3")
    out = Path(args.out) if args.out else default
    if args.save:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save).resolve()), compress=True)
        print("outro3: saved", args.save)
    if args.no_render:
        return
    out.mkdir(parents=True, exist_ok=True)
    for f in v2.frame_list(args.frames, args.every):
        t1 = time.time()
        sc.frame_set(f)
        sc.render.filepath = str(out / f"{f:04d}")
        bpy.ops.render.render(write_still=True)
        print(f"outro3: frame {f} rendered in {time.time() - t1:.1f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
