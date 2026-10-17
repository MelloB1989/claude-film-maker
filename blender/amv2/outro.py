"""Timeless v2 outro: the 3D SAU_EDITZ piece (comp frames 819-899, 1920x1080, 30 fps), Blender 5.2 Cycles.

    blender -b -t 12 --factory-startup -P blender/amv2/outro.py -- [--res-scale 1] [--frames 819-899 | 828,844-850]
        [--every 1] [--samples 96] [--device CPU|OPTIX|CUDA|HIP] [--out DIR] [--save out/timeless/amv2/blender/outro_v2.blend]
        [--no-render]

Frames land as `<out>/NNNN.png` (NNNN = comp frame); the default out is `$AMV2_DATA/blender/outro` (or out/amv2/outro).
The whole timeline is procedural: every object is keyed once per frame from the functions below, so the motion blur is exact
and the script is the single source of truth. Hits (EDL `outro.hits`): 828 837 844* 854 860 880 892* 897 (* = big).

Look: a dark navy multiverse void with a halftone comic backdrop, a spiral portal ringed by three coloured rings (gold / cyan /
red = the three Spider-Men's acts), a metallic web net that draws on over 819-827 (it catches the triptych shards the
EffectCraft layer throws in), candy-red letters with navy sides, blue rim light and emissive blue halftone dots, web strands
that snap on the hits, and fake volumetrics (emissive shaft cards, no volume fog).
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

F0, F1 = 819, 899                     # first / last comp frame of the outro
FPS = 30
WORD = "SAU_EDITZ"
HITS = [(828, 0.55), (837, 0.6), (844, 1.0), (854, 0.65), (860, 0.75), (880, 0.5), (892, 1.0), (897, 0.7)]
HIT_FRAMES = [h for h, _ in HITS]

# palette (linear-ish; the act colours of the edit: Tobey gold, Andrew cyan, Tom red)
RED = (0.62, 0.006, 0.02)
RED_BEVEL = (0.95, 0.05, 0.05)
NAVY = (0.006, 0.014, 0.12)
BLUE = (0.07, 0.30, 1.0)
GOLD = (1.0, 0.62, 0.10)
CYAN = (0.08, 0.75, 1.0)
HOT = (1.0, 0.07, 0.10)
WHITE = (1.0, 0.97, 0.95)

# letter flights: ch index -> (start frame, landing frame, start offset from rest (BU), start rotation (deg), start scale)
# every letter has its own direction, spin and start time; the landings sit on / between the hits
FLIGHTS = {
    4: (819, 837, (0.0, 9.0, 0.5), (35, 220, -25), 0.08),       # E  born in the portal, spins out of it; first landing
    7: (820, 841, (-15.0, 5.0, -11.0), (-70, -170, 40), 1.0),   # T  from deep lower-left
    2: (819, 844, (17.0, -7.0, -10.0), (80, 150, -95), 1.0),    # U  sweeps in from the lower right; the big hit
    1: (822, 848, (4.0, 8.0, 11.0), (-165, 40, -125), 0.12),    # A  from the portal, top
    5: (825, 854, (19.0, 1.0, 9.5), (-120, 60, 160), 1.0),      # D  far right, high
    0: (827, 857, (-19.0, -13.0, -6.0), (140, -80, 205), 1.0),  # S  skims the lens from the lower left
    8: (829, 859, (10.0, -8.0, 16.0), (170, 105, 70), 1.0),     # Z  from the top right
    6: (831, 860, (3.0, -27.0, -4.0), (200, -35, 60), 1.0),     # I  from behind the camera: it flies past the lens
    3: (833, 860, (-7.0, -4.0, 17.0), (0, 115, 75), 1.0),       # _  swings down like a pendulum onto the baseline
}
EXIT_F = 892                         # the letters are yanked away on the big hit


# --- small maths ------------------------------------------------------------------------------------------------------
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def out_pow(u, p):
    return 1.0 - (1.0 - clamp(u)) ** p


def env(f, h, decay):
    """Impulse envelope: 0 before h, 1 at h, exponential decay after."""
    return math.exp(-(f - h) / decay) if f >= h else 0.0


def ring_osc(f, h, decay, w=1.2):
    return env(f, h, decay) * math.cos((f - h) * w) if f >= h else 0.0


def lerp(a, b, t):
    return a + (b - a) * t


def v3(a, b, t):
    return tuple(lerp(x, y, t) for x, y in zip(a, b))


# --- animation helpers ------------------------------------------------------------------------------------------------
def all_fcurves(action):
    if hasattr(action, "fcurves"):
        return list(action.fcurves)
    out = []
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                out.extend(bag.fcurves)
    return out


def linearize(id_block):
    ad = id_block.animation_data
    if ad and ad.action:
        for fc in all_fcurves(ad.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"


def key(target, path, frame, value=None, index=-1):
    if value is not None:
        setattr(target, path, value)
    target.keyframe_insert(path, index=index, frame=frame)


def frames():
    return range(F0, F1 + 1)


def node(nt, kind, x=0, y=0, **kw):
    n = nt.nodes.new(kind)
    n.location = (x, y)
    for k, v in kw.items():
        setattr(n, k, v)
    return n


def link(nt, a, b):
    nt.links.new(a, b)


def new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    return m, nt


def rgba(c, a=1.0):
    return (c[0], c[1], c[2], a)


# --- materials --------------------------------------------------------------------------------------------------------
def halftone(nt, coord, axes, scale, radius_socket, soft=0.07):
    """Comic halftone dots on a 45-degree lattice: returns a 0..1 mask socket. `axes` picks the two object coordinates."""
    sep = node(nt, "ShaderNodeSeparateXYZ", -900, 0)
    link(nt, coord, sep.inputs[0])
    p, q = sep.outputs[axes[0]], sep.outputs[axes[1]]

    def m(op, a=None, b=None, x=0, y=0, clampit=False):
        n = node(nt, "ShaderNodeMath", x, y, operation=op, use_clamp=clampit)
        if a is not None:
            if isinstance(a, float):
                n.inputs[0].default_value = a
            else:
                link(nt, a, n.inputs[0])
        if b is not None:
            if isinstance(b, float):
                n.inputs[1].default_value = b
            else:
                link(nt, b, n.inputs[1])
        return n.outputs[0]

    s_add = m("ADD", p, q, -700, 100)
    s_sub = m("SUBTRACT", p, q, -700, -100)
    a = m("SUBTRACT", m("FRACT", m("MULTIPLY", s_add, scale, -500, 100), None, -400, 100), 0.5, -300, 100)
    b = m("SUBTRACT", m("FRACT", m("MULTIPLY", s_sub, scale, -500, -100), None, -400, -100), 0.5, -300, -100)
    d = m("SQRT", m("ADD", m("MULTIPLY", a, a, -200, 100), m("MULTIPLY", b, b, -200, -100), -100, 0), None, 0, 0)
    diff = m("SUBTRACT", radius_socket, d, 100, 0)
    return m("MULTIPLY", diff, 1.0 / soft, 200, 0, clampit=True)


def letter_material(name, kind):
    """kind: front | bevel | side. Emission strengths live on nodes named PULSE (a Value) so each letter can be keyed."""
    m, nt = new_mat(name)
    out = node(nt, "ShaderNodeOutputMaterial", 900, 0)
    bs = node(nt, "ShaderNodeBsdfPrincipled", 600, 0, name="BSDF")
    link(nt, bs.outputs[0], out.inputs[0])
    pulse = node(nt, "ShaderNodeValue", 100, -300, name="PULSE")
    pulse.outputs[0].default_value = 1.0
    if kind == "front":
        bs.inputs["Base Color"].default_value = rgba(RED)
        bs.inputs["Roughness"].default_value = 0.16
        bs.inputs["Specular IOR Level"].default_value = 0.7
        bs.inputs["Coat Weight"].default_value = 1.0
        bs.inputs["Coat Roughness"].default_value = 0.03
        bs.inputs["Emission Color"].default_value = rgba((0.03, 0.12, 1.0))
        tc = node(nt, "ShaderNodeTexCoord", -1100, 0)
        # dots grow towards the bottom of the letter and vanish at the top
        sep = node(nt, "ShaderNodeSeparateXYZ", -1100, -250)
        link(nt, tc.outputs["Object"], sep.inputs[0])
        rad = node(nt, "ShaderNodeMath", -950, -250, operation="MULTIPLY_ADD", use_clamp=True)
        link(nt, sep.outputs["Z"], rad.inputs[0])
        rad.inputs[1].default_value = -0.21
        rad.inputs[2].default_value = 0.30
        mask = halftone(nt, tc.outputs["Object"], ("X", "Z"), 2.6, rad.outputs[0])
        st = node(nt, "ShaderNodeMath", 300, -150, operation="MULTIPLY")
        link(nt, mask, st.inputs[0])
        link(nt, pulse.outputs[0], st.inputs[1])
        link(nt, st.outputs[0], bs.inputs["Emission Strength"])
        ink = node(nt, "ShaderNodeMix", 350, 200, data_type="RGBA")      # the dots are printed ink: deep blue over the red
        link(nt, mask, ink.inputs["Factor"])
        ink.inputs["A"].default_value = rgba(RED)
        ink.inputs["B"].default_value = (0.01, 0.05, 0.55, 1.0)
        link(nt, ink.outputs["Result"], bs.inputs["Base Color"])
        # the dots also darken the red a little so they read as printed ink, not as light
        pulse.outputs[0].default_value = 0.45
    elif kind == "bevel":
        bs.inputs["Base Color"].default_value = rgba(RED_BEVEL)
        bs.inputs["Roughness"].default_value = 0.12
        bs.inputs["Specular IOR Level"].default_value = 0.8
        bs.inputs["Coat Weight"].default_value = 1.0
        bs.inputs["Coat Roughness"].default_value = 0.02
        bs.inputs["Emission Color"].default_value = rgba(BLUE)
        lw = node(nt, "ShaderNodeLayerWeight", 100, -100)
        lw.inputs["Blend"].default_value = 0.35
        mul = node(nt, "ShaderNodeMath", 300, -150, operation="MULTIPLY")
        link(nt, lw.outputs["Fresnel"], mul.inputs[0])
        link(nt, pulse.outputs[0], mul.inputs[1])
        link(nt, mul.outputs[0], bs.inputs["Emission Strength"])
        pulse.outputs[0].default_value = 1.4
    else:
        bs.inputs["Base Color"].default_value = rgba(NAVY)
        bs.inputs["Metallic"].default_value = 0.85
        bs.inputs["Roughness"].default_value = 0.22
        bs.inputs["Emission Color"].default_value = rgba(BLUE)
        lw = node(nt, "ShaderNodeLayerWeight", 100, -100)
        lw.inputs["Blend"].default_value = 0.5
        mul = node(nt, "ShaderNodeMath", 300, -150, operation="MULTIPLY")
        link(nt, lw.outputs["Fresnel"], mul.inputs[0])
        link(nt, pulse.outputs[0], mul.inputs[1])
        link(nt, mul.outputs[0], bs.inputs["Emission Strength"])
        pulse.outputs[0].default_value = 1.0
    m["rest_pulse"] = pulse.outputs[0].default_value
    return m


def metal_material(name, tint, emit):
    m, nt = new_mat(name)
    out = node(nt, "ShaderNodeOutputMaterial", 400, 0)
    bs = node(nt, "ShaderNodeBsdfPrincipled", 100, 0, name="BSDF")
    link(nt, bs.outputs[0], out.inputs[0])
    bs.inputs["Base Color"].default_value = rgba(tint)
    bs.inputs["Metallic"].default_value = 1.0
    bs.inputs["Roughness"].default_value = 0.22
    bs.inputs["Emission Color"].default_value = rgba(tint)
    bs.inputs["Emission Strength"].default_value = emit
    return m


def emit_material(name, colour, strength, alpha=None):
    """Emission (optionally behind a transparency mix): returns (material, strength socket, mix-factor socket or None)."""
    m, nt = new_mat(name)
    out = node(nt, "ShaderNodeOutputMaterial", 600, 0)
    em = node(nt, "ShaderNodeEmission", 200, 0, name="EMIT")
    em.inputs["Color"].default_value = rgba(colour)
    em.inputs["Strength"].default_value = strength
    if alpha is None:
        link(nt, em.outputs[0], out.inputs[0])
        return m, em.inputs["Strength"], None
    tr = node(nt, "ShaderNodeBsdfTransparent", 200, -150)
    mix = node(nt, "ShaderNodeMixShader", 420, 0, name="MIX")
    mix.inputs[0].default_value = alpha
    link(nt, tr.outputs[0], mix.inputs[1])
    link(nt, em.outputs[0], mix.inputs[2])
    link(nt, mix.outputs[0], out.inputs[0])
    return m, em.inputs["Strength"], mix.inputs[0]


def backdrop_material():
    """Halftone comic backdrop: red left, blue right, dots biggest at the corners, clear in the middle (the word)."""
    m, nt = new_mat("halftone_bg")
    out = node(nt, "ShaderNodeOutputMaterial", 1500, 0)
    em = node(nt, "ShaderNodeEmission", 1200, 0, name="EMIT")
    link(nt, em.outputs[0], out.inputs[0])
    tc = node(nt, "ShaderNodeTexCoord", -1300, 0)
    sep = node(nt, "ShaderNodeSeparateXYZ", -1300, -300)
    link(nt, tc.outputs["Object"], sep.inputs[0])
    # radius from the distance to the centre: 0 at the middle, up to ~0.62 at the edges
    xs = node(nt, "ShaderNodeMath", -1100, -300, operation="MULTIPLY")
    link(nt, sep.outputs["X"], xs.inputs[0])
    xs.inputs[1].default_value = 0.55
    dist = node(nt, "ShaderNodeVectorMath", -950, -300, operation="LENGTH")
    comb = node(nt, "ShaderNodeCombineXYZ", -1100, -450)
    link(nt, xs.outputs[0], comb.inputs["X"])
    link(nt, sep.outputs["Y"], comb.inputs["Y"])
    link(nt, comb.outputs[0], dist.inputs[0])
    rad = node(nt, "ShaderNodeMapRange", -800, -300, clamp=True)
    link(nt, dist.outputs["Value"], rad.inputs["Value"])
    rad.inputs["From Min"].default_value = 3.0
    rad.inputs["From Max"].default_value = 14.0
    rad.inputs["To Min"].default_value = 0.0
    rad.inputs["To Max"].default_value = 0.4
    mask = halftone(nt, tc.outputs["Object"], ("X", "Y"), 1.2, rad.outputs["Result"], soft=0.09)
    ramp = node(nt, "ShaderNodeMapRange", -600, 200, clamp=True)       # red -> blue by x
    link(nt, sep.outputs["X"], ramp.inputs["Value"])
    ramp.inputs["From Min"].default_value = -14.0
    ramp.inputs["From Max"].default_value = 14.0
    mixc = node(nt, "ShaderNodeMix", 600, 100, data_type="RGBA")
    link(nt, ramp.outputs["Result"], mixc.inputs["Factor"])
    mixc.inputs["A"].default_value = rgba(HOT)
    mixc.inputs["B"].default_value = rgba(BLUE)
    cm = node(nt, "ShaderNodeMix", 850, 0, data_type="RGBA")           # dot colour over a near-black base
    link(nt, mask, cm.inputs["Factor"])
    cm.inputs["A"].default_value = (0.004, 0.006, 0.02, 1.0)
    link(nt, mixc.outputs["Result"], cm.inputs["B"])
    link(nt, cm.outputs["Result"], em.inputs["Color"])
    em.inputs["Strength"].default_value = 1.0
    return m


def portal_material():
    """Swirling spiral disc: a rotating angular+radial band pattern, red/blue by angle, transparent outside the disc."""
    m, nt = new_mat("portal")
    out = node(nt, "ShaderNodeOutputMaterial", 1500, 0)
    tc = node(nt, "ShaderNodeTexCoord", -1400, 0)
    sep = node(nt, "ShaderNodeSeparateXYZ", -1200, 0)
    link(nt, tc.outputs["Object"], sep.inputs[0])
    comb = node(nt, "ShaderNodeCombineXYZ", -1050, 0)
    link(nt, sep.outputs["X"], comb.inputs["X"])
    link(nt, sep.outputs["Y"], comb.inputs["Y"])
    r = node(nt, "ShaderNodeVectorMath", -900, 0, operation="LENGTH")
    link(nt, comb.outputs[0], r.inputs[0])
    ang = node(nt, "ShaderNodeMath", -900, -200, operation="ARCTAN2")
    link(nt, sep.outputs["Y"], ang.inputs[0])
    link(nt, sep.outputs["X"], ang.inputs[1])
    phase = node(nt, "ShaderNodeValue", -900, -400, name="PHASE")
    # band = fract(angle/2pi * 4 + r * 0.55 - phase)
    a1 = node(nt, "ShaderNodeMath", -700, -200, operation="MULTIPLY")
    link(nt, ang.outputs[0], a1.inputs[0])
    a1.inputs[1].default_value = 4.0 / (2 * math.pi)
    r1 = node(nt, "ShaderNodeMath", -700, 0, operation="MULTIPLY")
    link(nt, r.outputs["Value"], r1.inputs[0])
    r1.inputs[1].default_value = 0.55
    s1 = node(nt, "ShaderNodeMath", -520, -100, operation="ADD")
    link(nt, a1.outputs[0], s1.inputs[0])
    link(nt, r1.outputs[0], s1.inputs[1])
    s2 = node(nt, "ShaderNodeMath", -350, -100, operation="SUBTRACT")
    link(nt, s1.outputs[0], s2.inputs[0])
    link(nt, phase.outputs[0], s2.inputs[1])
    fr = node(nt, "ShaderNodeMath", -200, -100, operation="FRACT")
    link(nt, s2.outputs[0], fr.inputs[0])
    # a soft bright band (triangle wave)
    tri = node(nt, "ShaderNodeMath", -50, -100, operation="SUBTRACT")
    link(nt, fr.outputs[0], tri.inputs[0])
    tri.inputs[1].default_value = 0.5
    ab = node(nt, "ShaderNodeMath", 100, -100, operation="ABSOLUTE")
    link(nt, tri.outputs[0], ab.inputs[0])
    band = node(nt, "ShaderNodeMapRange", 250, -100, clamp=True)
    link(nt, ab.outputs[0], band.inputs["Value"])
    band.inputs["From Min"].default_value = 0.08
    band.inputs["From Max"].default_value = 0.42
    band.inputs["To Min"].default_value = 1.0
    band.inputs["To Max"].default_value = 0.0
    # radial envelope: dark hole in the middle, falls off at the rim
    rad_in = node(nt, "ShaderNodeMapRange", 100, 150, clamp=True)
    link(nt, r.outputs["Value"], rad_in.inputs["Value"])
    rad_in.inputs["From Min"].default_value = 0.6
    rad_in.inputs["From Max"].default_value = 3.0
    rad_in.inputs["To Min"].default_value = 0.0
    rad_in.inputs["To Max"].default_value = 1.0
    rad_out = node(nt, "ShaderNodeMapRange", 100, 350, clamp=True)
    link(nt, r.outputs["Value"], rad_out.inputs["Value"])
    rad_out.inputs["From Min"].default_value = 5.2
    rad_out.inputs["From Max"].default_value = 8.4
    rad_out.inputs["To Min"].default_value = 1.0
    rad_out.inputs["To Max"].default_value = 0.0
    env_ = node(nt, "ShaderNodeMath", 450, 250, operation="MULTIPLY")
    link(nt, rad_in.outputs["Result"], env_.inputs[0])
    link(nt, rad_out.outputs["Result"], env_.inputs[1])
    amp = node(nt, "ShaderNodeMath", 650, 0, operation="MULTIPLY")
    link(nt, band.outputs["Result"], amp.inputs[0])
    link(nt, env_.outputs[0], amp.inputs[1])
    # colour by angle: red <-> blue, with a glow floor so the hole reads mid-dark
    t = node(nt, "ShaderNodeMath", 100, -350, operation="SINE")
    link(nt, ang.outputs[0], t.inputs[0])
    t01 = node(nt, "ShaderNodeMath", 250, -350, operation="MULTIPLY_ADD")
    link(nt, t.outputs[0], t01.inputs[0])
    t01.inputs[1].default_value = 0.5
    t01.inputs[2].default_value = 0.5
    col = node(nt, "ShaderNodeMix", 800, -300, data_type="RGBA")
    link(nt, t01.outputs[0], col.inputs["Factor"])
    col.inputs["A"].default_value = rgba(HOT)
    col.inputs["B"].default_value = rgba(BLUE)
    em = node(nt, "ShaderNodeEmission", 1050, 0, name="EMIT")
    link(nt, col.outputs["Result"], em.inputs["Color"])
    stv = node(nt, "ShaderNodeValue", 800, 150, name="STRENGTH")
    st = node(nt, "ShaderNodeMath", 1000, 150, operation="MULTIPLY")
    link(nt, amp.outputs[0], st.inputs[0])
    link(nt, stv.outputs[0], st.inputs[1])
    link(nt, st.outputs[0], em.inputs["Strength"])
    tr = node(nt, "ShaderNodeBsdfTransparent", 1050, -200)
    mx = node(nt, "ShaderNodeMixShader", 1300, 0)
    link(nt, env_.outputs[0], mx.inputs[0])          # outside the disc / in the hole: transparent
    link(nt, tr.outputs[0], mx.inputs[1])
    link(nt, em.outputs[0], mx.inputs[2])
    link(nt, mx.outputs[0], out.inputs[0])
    return m


def shaft_material(colour):
    """A soft-edged light shaft: gradient across the width, fade along the length, emission mixed over transparency."""
    m, nt = new_mat(f"shaft_{colour[0]:.1f}_{colour[2]:.1f}")
    out = node(nt, "ShaderNodeOutputMaterial", 1000, 0)
    tc = node(nt, "ShaderNodeTexCoord", -600, 0)
    sep = node(nt, "ShaderNodeSeparateXYZ", -400, 0)
    link(nt, tc.outputs["UV"], sep.inputs[0])
    across = node(nt, "ShaderNodeMath", -200, 100, operation="SUBTRACT")
    link(nt, sep.outputs["X"], across.inputs[0])
    across.inputs[1].default_value = 0.5
    aab = node(nt, "ShaderNodeMath", -50, 100, operation="ABSOLUTE")
    link(nt, across.outputs[0], aab.inputs[0])
    soft = node(nt, "ShaderNodeMapRange", 100, 100, clamp=True)
    link(nt, aab.outputs[0], soft.inputs["Value"])
    soft.inputs["From Min"].default_value = 0.0
    soft.inputs["From Max"].default_value = 0.5
    soft.inputs["To Min"].default_value = 1.0
    soft.inputs["To Max"].default_value = 0.0
    sq = node(nt, "ShaderNodeMath", 250, 100, operation="POWER")
    link(nt, soft.outputs["Result"], sq.inputs[0])
    sq.inputs[1].default_value = 2.5
    along = node(nt, "ShaderNodeMath", -200, -100, operation="SUBTRACT")
    link(nt, sep.outputs["Y"], along.inputs[0])
    along.inputs[1].default_value = 0.5
    aab2 = node(nt, "ShaderNodeMath", -50, -100, operation="ABSOLUTE")
    link(nt, along.outputs[0], aab2.inputs[0])
    fade = node(nt, "ShaderNodeMapRange", 100, -100, clamp=True)
    link(nt, aab2.outputs[0], fade.inputs["Value"])
    fade.inputs["From Min"].default_value = 0.1
    fade.inputs["From Max"].default_value = 0.5
    fade.inputs["To Min"].default_value = 1.0
    fade.inputs["To Max"].default_value = 0.0
    prod = node(nt, "ShaderNodeMath", 450, 0, operation="MULTIPLY")
    link(nt, sq.outputs[0], prod.inputs[0])
    link(nt, fade.outputs["Result"], prod.inputs[1])
    em = node(nt, "ShaderNodeEmission", 600, 100, name="EMIT")
    em.inputs["Color"].default_value = rgba(colour)
    sv = node(nt, "ShaderNodeValue", 450, 200, name="STRENGTH")
    st = node(nt, "ShaderNodeMath", 600, 250, operation="MULTIPLY")
    link(nt, sv.outputs[0], st.inputs[0])
    link(nt, prod.outputs[0], st.inputs[1])
    link(nt, st.outputs[0], em.inputs["Strength"])
    tr = node(nt, "ShaderNodeBsdfTransparent", 600, -200)
    mx = node(nt, "ShaderNodeMixShader", 800, 0)
    link(nt, prod.outputs[0], mx.inputs[0])
    link(nt, tr.outputs[0], mx.inputs[1])
    link(nt, em.outputs[0], mx.inputs[2])
    link(nt, mx.outputs[0], out.inputs[0])
    return m


# --- geometry ---------------------------------------------------------------------------------------------------------
def glyph_mesh(font, ch, size, extrude, bevel):
    cu = bpy.data.curves.new(f"g_{ch}", "FONT")
    cu.body = ch
    cu.font = font
    cu.size = size
    cu.extrude = extrude
    cu.bevel_depth = bevel
    cu.bevel_resolution = 4
    cu.resolution_u = 12
    cu.align_x = "LEFT"
    cu.align_y = "BOTTOM_BASELINE"
    ob = bpy.data.objects.new(f"g_{ch}", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    return me


def stand_up(me):
    me.transform(Matrix.Rotation(math.pi / 2, 4, "X"))      # text plane XY -> XZ, extrusion +Z -> -Y: front faces -Y (camera)


def bounds(me):
    xs = [v.co.x for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    return min(xs), max(xs), min(zs), max(zs)


def bar_mesh(w, h, depth, bevel):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= w
        v.co.y *= depth * 2
        v.co.z *= h
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=4, profile=0.6, affect="EDGES")
    me = bpy.data.meshes.new("g__")
    bm.to_mesh(me)
    bm.free()
    return me


def split_materials(me, mats):
    me.materials.clear()
    for m in mats:
        me.materials.append(m)
    for p in me.polygons:
        ny = -p.normal.y
        p.material_index = 0 if ny > 0.93 else (2 if abs(p.normal.y) < 0.2 else 1)
        p.use_smooth = p.material_index == 1
    me.update()


WORD_W, CAP = 14.6, 3.7
GAP = 0.15
KERN = {("S", "A"): 0.0, ("A", "U"): 0.05, ("U", "_"): 0.03, ("_", "E"): 0.03, ("E", "D"): 0.02, ("D", "I"): 0.04,
        ("I", "T"): 0.08, ("T", "Z"): 0.03}


def find_font():
    here = Path(__file__).resolve()
    repo = here.parents[2]
    cands = [os.environ.get("AMV2_FONT", ""), repo / "films/timeless/fonts/Spider-Man.otf.ttf",
             "/home/nikhil/code/film-making/handover/amv_handover/fonts/Spider-Man.otf.ttf"]
    for c in cands:
        if c and Path(c).exists():
            return str(c)
    raise SystemExit("outro: Spider-Man.otf.ttf not found (set AMV2_FONT)")


def build_letters(mats_for):
    """9 letter objects at their rest positions, word centred on the origin. `mats_for(i)` -> [front, bevel, side]."""
    font = bpy.data.fonts.load(find_font())
    trial = glyph_mesh(font, "SAUEDITZ", 1.0, 0.0, 0.0)
    stand_up(trial)
    _, _, z0, z1 = bounds(trial)
    bpy.data.meshes.remove(trial)
    cap1 = z1 - z0
    unit, stem = {}, 0.0
    for ch in set(WORD) - {"_"}:
        m = glyph_mesh(font, ch, 1.0, 0.0, 0.0)
        stand_up(m)
        a, b, c, d = bounds(m)
        unit[ch] = b - a
        if ch == "T":
            zs = [v.co.z for v in m.vertices]
            lo, hi = min(zs), max(zs)
            xs = [v.co.x for v in m.vertices if v.co.z < lo + 0.15 * (hi - lo)]
            stem, tz0, tz1 = max(xs) - min(xs), c, d
        bpy.data.meshes.remove(m)
    bar_w1 = 0.46 * cap1
    w1 = [bar_w1 if ch == "_" else stem if ch == "I" else unit[ch] for ch in WORD]
    g1 = [GAP + KERN.get(p, 0.0) for p in zip(WORD, WORD[1:])]
    size = CAP / cap1
    for _ in range(4):
        k = size * cap1 / CAP
        size = min(CAP / cap1, (WORD_W - 0.2 * k * len(w1)) / (sum(w1) + sum(g1)))
    k = size * cap1 / CAP
    extrude, bevel = 0.55 * k, 0.10 * k
    gaps = [size * g for g in g1]
    parts = []
    for ch in WORD:
        if ch == "_":
            w = bar_w1 * size
            me = bar_mesh(w, 0.13 * cap1 * size, extrude, bevel)
            cz = -cap1 * size * 0.56
        elif ch == "I":
            w = stem * size + 2 * bevel
            me = bar_mesh(w, (tz1 - tz0) * size + 2 * bevel, extrude, bevel)
            cz = (tz0 + tz1) / 2 * size
        else:
            me = glyph_mesh(font, ch, size, extrude, bevel)
            stand_up(me)
            a, b, c, d = bounds(me)
            cx, cz = (a + b) / 2, (c + d) / 2
            w = b - a
            me.transform(Matrix.Translation((-cx, 0, -cz)))
        parts.append([ch, me, w, cz])
    total = sum(p[2] for p in parts) + sum(gaps)
    cap_c = (z0 + z1) / 2 * size
    objs, x = [], -total / 2
    for i, (ch, me, w, cz) in enumerate(parts):
        split_materials(me, mats_for(i))
        ob = bpy.data.objects.new(f"L{i}_{ch}", me)
        bpy.context.scene.collection.objects.link(ob)
        rest = (x + w / 2, 0.0, (cz - cap_c) if ch != "_" else cz)
        ob.location = rest
        ob["rest"] = rest
        ob.rotation_mode = "XYZ"
        objs.append(ob)
        x += w + (gaps[i] if i < len(gaps) else 0.0)
    return objs, {"width": total, "height": cap1 * size}


def make_curve(name, mat, bevel, collection=None):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = bevel
    cu.bevel_resolution = 1
    cu.use_fill_caps = True
    cu.bevel_factor_mapping_start = "SPLINE"
    cu.bevel_factor_mapping_end = "SPLINE"
    cu.materials.append(mat)
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    return ob, cu


def poly(cu, pts, cyclic=False):
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p, c in zip(sp.points, pts):
        p.co = (c[0], c[1], c[2], 1.0)
    sp.use_cyclic_u = cyclic
    return sp


# --- scene pieces -----------------------------------------------------------------------------------------------------
def build_world():
    w = bpy.data.worlds.new("void")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = node(nt, "ShaderNodeOutputWorld", 600, 0)
    bg = node(nt, "ShaderNodeBackground", 300, 0, name="BG")
    link(nt, bg.outputs[0], out.inputs[0])
    tc = node(nt, "ShaderNodeTexCoord", -600, 0)
    sep = node(nt, "ShaderNodeSeparateXYZ", -400, 0)
    link(nt, tc.outputs["Generated"], sep.inputs[0])
    ramp = node(nt, "ShaderNodeMapRange", -200, 0, clamp=True)
    link(nt, sep.outputs["Z"], ramp.inputs["Value"])
    mix = node(nt, "ShaderNodeMix", 50, 0, data_type="RGBA")
    link(nt, ramp.outputs["Result"], mix.inputs["Factor"])
    mix.inputs["A"].default_value = (0.004, 0.006, 0.03, 1)
    mix.inputs["B"].default_value = (0.045, 0.02, 0.09, 1)
    link(nt, mix.outputs["Result"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    return bg


def area(name, loc, size, power, colour, target=(0, 0, 0), shape="RECTANGLE", size_y=None):
    ld = bpy.data.lights.new(name, "AREA")
    ld.shape = shape
    ld.size = size
    if shape == "RECTANGLE":
        ld.size_y = size_y or size
    ld.energy = power
    ld.color = colour
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    d = Vector(target) - Vector(loc)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    ob.visible_camera = False
    return ob, ld


def pulse_env(f, scale=1.0, decay=3.0):
    return sum(s * env(f, h, decay) for h, s in HITS) * scale


def build_lights():
    L = {}
    L["key"] = area("key_red", (-13, -15, 10), 9, 4500, (1.0, 0.18, 0.12), size_y=5)
    L["top"] = area("top_soft", (0, -12, 17), 14, 2200, (0.95, 0.97, 1.0), size_y=4)
    L["rimR"] = area("rim_blue_R", (13, 7, 5), 8, 9000, (0.18, 0.40, 1.0), target=(0, 0, 0), size_y=4)
    L["rimL"] = area("rim_cyan_L", (-13, 7, 6), 8, 5000, (0.10, 0.65, 1.0), target=(0, 0, 0), size_y=4)
    L["fill"] = area("fill_mag", (4, -18, -8), 10, 900, (0.85, 0.2, 0.55))
    base = {k: v[1].energy for k, v in L.items()}
    for f in frames():
        p = pulse_env(f)
        sweep = env(f, 880, 4.0)
        for k, (ob, ld) in L.items():
            m = 1.0 + 0.25 * p
            if k in ("rimR", "rimL"):
                m *= 1.0 + 0.8 * sweep
            if f < 822:
                m *= 0.35 + 0.65 * smooth((f - 819) / 3.0)       # opens dark, the rim lights ignite with the portal
            if f >= 897:
                m *= max(0.0, 1.0 - (f - 896) / 2.0)             # light dies with the portal collapse
            key(ld, "energy", f, base[k] * m)
    for ob, ld in L.values():
        linearize(ld)


def build_backdrop(bgnode):
    me = bpy.data.meshes.new("bd")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("backdrop", me)
    bpy.context.scene.collection.objects.link(ob)
    mat = backdrop_material()
    me.materials.append(mat)
    ob.scale = (34, 20, 1)
    ob.rotation_euler = (math.pi / 2, 0, 0)
    ob.location = (0, 17, 0)
    em = mat.node_tree.nodes["EMIT"].inputs["Strength"]
    for f in frames():
        base = 0.55 + 0.35 * smooth((f - 819) / 12.0)
        key(em, "default_value", f, base * (1 + 0.25 * pulse_env(f, 1.0, 2.5)) * (1.0 if f < 897 else max(0.0, 1 - (f - 896) / 2)))
    linearize(mat.node_tree)
    # slow drift so the halftone parallaxes with the camera
    for f in frames():
        key(ob, "location", f, (math.sin((f - F0) * 0.02) * 0.8, 17, 0.0))
    linearize(ob)


def build_portal():
    root = bpy.data.objects.new("portal_root", None)
    bpy.context.scene.collection.objects.link(root)
    root.location = (0, 6.0, 0)
    # the swirl disc
    me = bpy.data.meshes.new("pd")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)
    bm.to_mesh(me)
    bm.free()
    disc = bpy.data.objects.new("portal_disc", me)
    bpy.context.scene.collection.objects.link(disc)
    mat = portal_material()
    me.materials.append(mat)
    disc.scale = (9.0, 9.0, 1.0)
    disc.rotation_euler = (math.pi / 2, 0, 0)
    disc.parent = root
    nt = mat.node_tree
    phase, strength = nt.nodes["PHASE"].outputs[0], nt.nodes["STRENGTH"].outputs[0]
    for f in frames():
        t = f - F0
        key(phase, "default_value", f, -t * 0.045)
        st = 1.2 + 1.5 * env(f, 819, 3.0) + 0.4 * pulse_env(f, 1.0, 3.0)
        st *= smooth((f - 818) / 2.0)
        if f >= 892:
            st *= 1.0 + 1.5 * smooth((f - 892) / 3.0)
        if f >= 897:
            st *= max(0.0, 1.0 - (f - 896) / 2.0)
        key(strength, "default_value", f, st)
    linearize(nt)
    # coloured rings: gold (Tobey) / cyan (Andrew) / red (Tom) + a white inner line
    specs = [("ring_white", 6.6, 0.05, WHITE, 14.0, (0, 0, 0.0)), ("ring_gold", 7.15, 0.075, GOLD, 9.0, (0.30, 0.18, 0.5)),
             ("ring_cyan", 7.7, 0.075, CYAN, 9.0, (-0.25, 0.30, 2.0)), ("ring_red", 8.25, 0.075, HOT, 9.0, (0.12, -0.34, 4.0))]
    rings = []
    for name, R, r, col, st, (tx, ty, ph) in specs:
        bm = bmesh.new()
        n_major, n_minor = 96, 8
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
        rm = bpy.data.meshes.new(name)
        bm.to_mesh(rm)
        bm.free()
        for p in rm.polygons:
            p.use_smooth = True
        mt, st_in, _ = emit_material(name, col, st)
        rm.materials.append(mt)
        ob = bpy.data.objects.new(name, rm)
        bpy.context.scene.collection.objects.link(ob)
        ob.parent = root
        ob.rotation_mode = "ZYX"                        # spin about the ring's own axis first, then stand it up / tilt
        ob.rotation_euler = (math.pi / 2, 0, 0)
        rings.append((ob, st_in, st, tx, ty, ph))
    for f in frames():
        t = f - F0
        grow = out_pow((f - 819) / 8.0, 3)
        for k, (ob, st_in, st, tx, ty, ph) in enumerate(rings):
            s = (0.2 + 0.8 * grow) * (1 + 0.05 * pulse_env(f, 1.0, 3.0))
            if f >= 892:
                s *= 1.0 + 0.5 * smooth((f - 892) / 4.0)
            if f >= 896:
                s *= max(0.02, 1.0 - (f - 896) / 2.5)
            ob.scale = (s, s, s)
            ob.keyframe_insert("scale", frame=f)
            # tilt wobble: each ring precesses at its own rate, so the three act rings interlock like gyroscopes
            wob = 0.4 if k else 0.0
            ob.rotation_euler = (math.pi / 2 + wob * ty * math.sin(t * 0.09 + ph), wob * tx * math.cos(t * 0.07 + ph),
                                 t * (0.02 + 0.008 * k) * (1 if k % 2 else -1))
            ob.keyframe_insert("rotation_euler", frame=f)
            val = st * (0.25 + 0.75 * smooth((f - 818) / 2.0)) * (1 + 0.5 * env(f, 819, 3) + 0.25 * pulse_env(f, 1.0, 3.0))
            if f >= 897:
                val *= max(0.0, 1.0 - (f - 896) / 2.0)
            key(st_in, "default_value", f, val)
    for ob, *_ in rings:
        linearize(ob)
        linearize(ob.data.materials[0].node_tree)
    return root


def web_geometry(mat_hi):
    """Metallic web net behind the word: spokes draw out from the centre (819-823), rings spiral on after (821-827)."""
    rnd = random.Random(7)
    R = 17.0
    spokes_n, rings_n = 18, 11
    ob_s, cu_s = make_curve("web_spokes", mat_hi, 0.032)
    ob_r, cu_r = make_curve("web_rings", mat_hi, 0.024)
    ang = [2 * math.pi * i / spokes_n + rnd.uniform(-0.05, 0.05) for i in range(spokes_n)]
    for a in ang:
        poly(cu_s, [(0.4 * math.cos(a), 0, 0.4 * math.sin(a)), (R * math.cos(a), 0, R * math.sin(a))])
    for k in range(rings_n):
        r = 1.2 + (R - 1.2) * (k / (rings_n - 1)) ** 1.25
        pts = []
        for i in range(spokes_n):
            a0, a1 = ang[i], ang[(i + 1) % spokes_n] + (2 * math.pi if i == spokes_n - 1 else 0)
            rj = r * (1 + rnd.uniform(-0.02, 0.02))
            for s in range(4):                        # the sag between two spokes: the thread bows towards the hub
                u = s / 4
                a = lerp(a0, a1, u)
                rr = rj * (1 - 0.055 * math.sin(math.pi * u) * (0.6 + 0.4 * k / rings_n))
                pts.append((rr * math.cos(a), 0, rr * math.sin(a)))
        poly(cu_r, pts, cyclic=True)
    for ob in (ob_s, ob_r):
        ob.location = (0, 3.2, 0)      # curves are built in the XZ plane: they already face the camera
    return ob_s, cu_s, ob_r, cu_r


def build_web():
    mat = metal_material("web_metal", (0.55, 0.64, 0.9), 0.35)
    ob_s, cu_s, ob_r, cu_r = web_geometry(mat)
    for f in frames():
        t = f - F0
        key(cu_s, "bevel_factor_end", f, out_pow((f - 819) / 4.5, 2.2))
        key(cu_r, "bevel_factor_end", f, out_pow((f - 821.5) / 6.0, 2.0))
        # the net is a trampoline: it rings on every hit (a damped scale pulse about its centre)
        wob = 1.0 + 0.03 * sum(s * ring_osc(f, h, 3.2, 1.35) for h, s in HITS) + 0.0
        sc = wob * (1.0 + 0.0012 * t)
        if f >= 892:
            sc *= 1.0 + 0.35 * smooth((f - 892) / 5.0)
        for ob in (ob_s, ob_r):
            ob.scale = (sc, sc, sc)
            ob.keyframe_insert("scale", frame=f)
            ob.rotation_euler = (0, 0, 0.002 * t + 0.03 * sum(s * ring_osc(f, h, 4.0, 1.0) for h, s in HITS))
            ob.keyframe_insert("rotation_euler", frame=f)
        if f >= 895:
            k = max(0.0, 1.0 - (f - 894) / 3.0)
            key(cu_s, "bevel_factor_start", f, 1.0 - k)
            key(cu_r, "bevel_factor_start", f, 1.0 - k)
    for o in (ob_s, ob_r):
        linearize(o)
    linearize(cu_s)
    linearize(cu_r)
    return ob_s, ob_r


def build_strands(objs):
    """Web strands that shoot and snap on the hits; they stay attached to the landed letters until the exit snap."""
    mat = metal_material("strand_metal", (0.9, 0.94, 1.0), 0.7)
    rest = {i: Vector(ob["rest"]) for i, ob in enumerate(objs)}
    FRONT = -0.7

    def strand(name, a, b, f0, life_end, sag=0.7, snap_amp=0.8, speed=2.0, thick=0.028):
        """a = anchor (far end), b = the target; shot at f0 (draw over `speed` frames), wobbles, retracts at life_end."""
        ob, cu = make_curve(name, mat, thick)
        a, b = Vector(a), Vector(b)
        mid = (a + b) / 2
        perp = (b - a).cross(Vector((0, 1, 0)))
        perp = perp.normalized() if perp.length > 1e-4 else Vector((0, 0, 1))
        sp = poly(cu, [a, mid, b])
        for f in frames():
            if f < f0 - 1:
                key(cu, "bevel_factor_end", f, 0.0)
                continue
            u = out_pow((f - f0 + 1) / speed, 2)
            key(cu, "bevel_factor_end", f, u)
            d = f - f0
            wob = snap_amp * env(f, f0 + speed, 3.0) * math.cos(d * 1.9) if f >= f0 + speed else 0.0
            m = mid + perp * wob
            sp.points[1].co = (m.x, m.y, m.z, 1.0)
            sp.points[1].keyframe_insert("co", frame=f)
            if life_end and f >= life_end:
                k = clamp((f - life_end) / 1.6)
                key(cu, "bevel_factor_start", f, k)
        linearize(cu)
        return ob

    far = lambda sx, sz: (sx * 17.0, 4.0, sz * 10.5)
    top = lambda x, sz: (x * 1.3, 1.0, sz * 11.0)
    # 828: the net snaps taut: three strands lash across it from the frame edges
    strand("s828a", far(-1, 1), (-1.5, 3.2, 2.5), 828, 892)
    strand("s828b", far(1, -1), (2.0, 3.2, -1.5), 828, 892)
    strand("s828c", far(1, 1), (3.0, 3.2, 3.0), 829, 892, snap_amp=0.5)
    # letters: a strand from the edge to the face of each landing letter, shot on the landing
    cfg = {4: (837, 1), 7: (841, -1), 2: (844, 1), 1: (848, -1), 5: (854, 1), 0: (857, -1), 8: (859, 1), 6: (860, -1), 3: (861, -1)}
    for i, (f, sgn) in cfg.items():
        an = top(rest[i].x, sgn)
        tgt = rest[i] + Vector((0, FRONT * 0.4, sgn * 1.55 if i != 3 else -0.2))     # attach to the letter's top / bottom edge
        strand(f"s_letter{i}", an, tgt, f, 892, snap_amp=0.9 if f in HIT_FRAMES else 0.55)
    # 888-892: the web wrap: six strands cross in front of the word and bite tight; they snap on the big hit
    wrap = [((-17, -2.6, -6.0), (17, -2.6, 4.0)), ((17, -2.6, -4.5), (-17, -2.6, 6.0)), ((-17, -2.8, 4.0), (17, -2.8, -5.5)),
            ((17, -2.6, 5.5), (-17, -2.6, -4.0))]
    for k, (a, b) in enumerate(wrap):
        strand(f"wrap{k}", a, b, 889 + (k % 2), 892, snap_amp=0.1, speed=2.5, thick=0.032)


def star_mesh(arm=1.0, waist=0.09):
    bm = bmesh.new()
    pts = []
    for i in range(8):
        r = arm if i % 2 == 0 else waist
        a = i * math.pi / 4
        pts.append(bm.verts.new((r * math.cos(a), 0, r * math.sin(a))))
    bm.faces.new(pts)
    me = bpy.data.meshes.new("star")
    bm.to_mesh(me)
    bm.free()
    return me


def annulus_mesh(r0=0.95, r1=1.0, n=64):
    bm = bmesh.new()
    a = [bm.verts.new((r0 * math.cos(2 * math.pi * i / n), 0, r0 * math.sin(2 * math.pi * i / n))) for i in range(n)]
    b = [bm.verts.new((r1 * math.cos(2 * math.pi * i / n), 0, r1 * math.sin(2 * math.pi * i / n))) for i in range(n)]
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))
    me = bpy.data.meshes.new("annulus")
    bm.to_mesh(me)
    bm.free()
    return me


def landing_events(objs):
    rest = {i: Vector(ob["rest"]) for i, ob in enumerate(objs)}
    ev = []
    for i, (fs, fl, *_r) in FLIGHTS.items():
        big = fl in HIT_FRAMES
        ev.append((fl, rest[i] + Vector((0, -0.9, 0.2)), 1.0 if big else 0.55, i))
    return ev


def build_fx(objs):
    """Glints, shockwave rings, debris shards and the light sweep on the landings and hits."""
    rnd = random.Random(11)
    star = star_mesh()
    ann = annulus_mesh()
    shard_me = bpy.data.meshes.new("shard")
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in ((0, 0, 0.5), (0.18, 0, -0.35), (-0.18, 0, -0.35))]
    bm.faces.new(vs)
    bm.to_mesh(shard_me)
    bm.free()
    n_made = {"glint": 0, "ring": 0, "shard": 0}

    def card(kind, mesh, mat, loc, f0, life, size0, size1, strength, decay_pow=1.0, spin=0.0):
        ob = bpy.data.objects.new(f"{kind}{n_made[kind]}", mesh)
        n_made[kind] += 1
        bpy.context.scene.collection.objects.link(ob)
        m, st, _ = emit_material(f"{kind}_m{n_made[kind]}", mat, strength)
        ob.data = mesh.copy()
        ob.data.materials.append(m)
        for f in frames():
            t = (f - f0) / life
            if 0.0 <= t <= 1.0:
                sz = lerp(size0, size1, out_pow(t, 3))
                ob.location = loc
                ob.scale = (sz, sz, sz)
                ob.rotation_euler = (0, spin * (f - f0), 0)
                key(st, "default_value", f, strength * (1 - t) ** decay_pow)
            else:
                ob.location = (0, 1000, 0)
                ob.scale = (0.001, 0.001, 0.001)
                key(st, "default_value", f, 0.0)
            ob.keyframe_insert("location", frame=f)
            ob.keyframe_insert("scale", frame=f)
            ob.keyframe_insert("rotation_euler", frame=f)
        linearize(ob)
        linearize(m.node_tree)

    for (f, loc, s, i) in landing_events(objs):
        big = s >= 1.0
        card("glint", star, WHITE, loc + Vector((rnd.uniform(-0.8, 0.8), -0.5, rnd.uniform(0.6, 1.6))), f, 8, 0.2, 1.3 * s + 0.4,
             10.0)
        card("ring", ann, CYAN if i % 2 else HOT, loc + Vector((0, 0.6, 0)), f, 8 if not big else 11, 0.5, 3.0 * s + 1.2, 6.0,
             decay_pow=1.8)
        for k in range(14 if big else 7):                      # debris: shards fly out and fall, tumbling
            ang = rnd.uniform(0, 2 * math.pi)
            sp = rnd.uniform(0.35, 0.9) * (1.4 if big else 1.0)
            vel = Vector((math.cos(ang) * sp, rnd.uniform(-0.6, -0.1), math.sin(ang) * sp + 0.15))
            mat = rnd.choice([HOT, BLUE, WHITE, GOLD])
            me = shard_me.copy()
            ob = bpy.data.objects.new(f"shard{n_made['shard']}", me)
            n_made["shard"] += 1
            bpy.context.scene.collection.objects.link(ob)
            m, st, _ = emit_material(f"shard_m{n_made['shard']}", mat, 6.0)
            me.materials.append(m)
            life = rnd.randint(9, 14)
            spin = rnd.uniform(-0.8, 0.8)
            base_sz = rnd.uniform(0.35, 0.9)
            for fr in frames():
                t = fr - f
                if 0 <= t <= life:
                    p = loc + vel * t + Vector((0, 0, -0.02 * t * t))
                    ob.location = p
                    ob.rotation_euler = (0.4 * t * spin, 1.1 * t * spin, ang + 0.5 * t * spin)
                    sz = base_sz * (1 - 0.6 * t / life)
                    ob.scale = (sz, sz, sz)
                    key(st, "default_value", fr, 6.0 * (1 - t / life))
                else:
                    ob.location = (0, 1000, 0)
                    ob.scale = (0.001,) * 3
                    key(st, "default_value", fr, 0.0)
                ob.keyframe_insert("location", frame=fr)
                ob.keyframe_insert("scale", frame=fr)
                ob.keyframe_insert("rotation_euler", frame=fr)
            linearize(ob)
            linearize(m.node_tree)
    # 880: a bright glint ladder runs across the word with the light sweep
    xs = sorted(ob["rest"][0] for ob in objs)
    for k, x in enumerate(xs):
        card("glint", star, WHITE, Vector((x, -1.4, 1.9)), 880 + k // 3, 5, 0.2, 1.1, 9.0)
    # 897: the last snap: a big blue-white star at the portal centre
    card("glint", star, WHITE, Vector((0, 4.0, 0.0)), 896, 3, 0.5, 9.0, 12.0, spin=0.2)


def build_shafts():
    """Fake volumetrics: soft emissive shaft cards through the portal centre (no volume fog)."""
    specs = [(-0.55, CYAN, 1.0), (0.35, HOT, 1.0), (1.15, BLUE, 0.8), (2.2, GOLD, 0.6), (-1.6, HOT, 0.7)]
    for i, (rot, col, w) in enumerate(specs):
        me = bpy.data.meshes.new(f"shaft{i}")
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
        bm.to_mesh(me)
        bm.free()
        uv = me.uv_layers.new(name="UVMap")
        for l in me.loops:
            vi = me.vertices[l.vertex_index].co
            uv.data[l.index].uv = (vi.x + 0.5, vi.y + 0.5)
        mat = shaft_material(col)
        me.materials.append(mat)
        ob = bpy.data.objects.new(f"shaft{i}", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.scale = (4.0 * w, 46.0, 1.0)
        ob.location = (0, 4.6 - i * 0.3, 0)
        ob.rotation_mode = "ZYX"      # spin within the XZ plane (about the card's own normal)
        st = mat.node_tree.nodes["STRENGTH"].outputs[0]
        for f in frames():
            t = f - F0
            ob.rotation_euler = (math.pi / 2, 0, rot + 0.01 * t * (1 if i % 2 else -1))
            ob.keyframe_insert("rotation_euler", frame=f)
            v = (0.14 + 0.7 * env(f, 819, 4.0)) * smooth((f - 818) / 3.0) + 0.55 * pulse_env(f, 1.0, 2.5) * (0.5 + 0.5 * math.sin(i))
            if f >= 892:
                v *= 1.0 + 2.0 * smooth((f - 892) / 3.0)
            if f >= 897:
                v *= max(0.0, 1.0 - (f - 896) / 2.0)
            key(st, "default_value", f, v)
        linearize(ob)
        linearize(mat.node_tree)


def build_sweep(objs):
    """880: a light blade crosses the word left to right (a tilted bright card behind the camera plane) + a rim pulse."""
    me = bpy.data.meshes.new("blade")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
    bm.to_mesh(me)
    bm.free()
    uv = me.uv_layers.new(name="UVMap")
    for l in me.loops:
        vi = me.vertices[l.vertex_index].co
        uv.data[l.index].uv = (vi.x + 0.5, vi.y + 0.5)
    mat = shaft_material(WHITE)
    me.materials.append(mat)
    ob = bpy.data.objects.new("blade", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.scale = (2.4, 14.0, 1.0)
    ob.rotation_mode = "ZYX"
    ob.rotation_euler = (math.pi / 2, 0, 0.35)
    st = mat.node_tree.nodes["STRENGTH"].outputs[0]
    for f in frames():
        u = (f - 878) / 8.0
        ob.location = (lerp(-12, 12, clamp(u)), -1.6, 0)
        ob.keyframe_insert("location", frame=f)
        key(st, "default_value", f, 9.0 * math.sin(math.pi * clamp(u)) if 0 < u < 1 else 0.0)
    linearize(ob)
    linearize(mat.node_tree)


# --- letter animation -------------------------------------------------------------------------------------------------
def letter_pose(i, f, rest):
    """Position (BU), euler (rad), uniform scale of letter i at comp frame f."""
    fs, fl, off, rot, s0 = FLIGHTS[i]
    rest = Vector(rest)
    u = (f - fs) / (fl - fs)
    uc = clamp(u)
    e_pos = out_pow(uc, 3.0)                # decelerating: fast out of the dark, long readable settle
    e_rot = out_pow(uc, 2.4)
    off = Vector(off)
    d = off * (1 - e_pos)
    # curved flight path: swing sideways in an arc that closes at the landing
    side = off.cross(Vector((0, 0, 1)))
    side = side.normalized() if side.length > 1e-4 else Vector((1, 0, 0))
    arc = side * (0.22 * off.length * math.sin(math.pi * e_pos) * (1 - e_pos))
    pos = rest + d + arc
    rot_v = [math.radians(a) * (1 - e_rot) for a in rot]
    sc = lerp(s0, 1.0, out_pow(uc, 2.2))
    # landing: a damped spring in depth, squash and a little tilt, so each letter "hits" its spot
    t = f - fl
    if t >= 0:
        sp = math.exp(-t / 2.6) * math.cos(t * 1.25)
        pos = pos + Vector((0, 0.7 * sp, 0))
        sc *= 1 + 0.07 * sp
        rot_v[2] += 0.05 * sp * (1 if i % 2 else -1)
    # lockup: a slow, tiny float so nothing is dead still
    if f >= fl:
        ph = i * 0.9
        pos += Vector((0.03 * math.sin(f * 0.11 + ph), 0.05 * math.sin(f * 0.07 + ph), 0.04 * math.cos(f * 0.09 + ph)))
        rot_v[2] += 0.006 * math.sin(f * 0.09 + ph)
    # the 880 sweep: a ripple lifts each letter slightly as the blade passes
    sw = env(f, 880 + i * 0.55, 2.2)
    pos += Vector((0, -0.25 * sw, 0))
    # 888-891: tension, the letters shudder in the web wrap
    if 887 <= f < EXIT_F:
        k = (f - 887) / 5.0
        r = random.Random(i * 100 + f)
        pos += Vector((r.uniform(-1, 1), r.uniform(-1, 1) * 0.5, r.uniform(-1, 1))) * 0.1 * k
    # the exit: yanked off on the big hit, each its own way, through and past the lens
    if f >= EXIT_F:
        r = random.Random(i + 40)
        dt = f - EXIT_F - (i % 4) * 0.35
        if dt > 0:
            if dt < 1.5:   # a two-frame glitch slice before the throw
                pos += Vector((r.choice([-1, 1]) * 0.6, 0, r.uniform(-0.2, 0.2)))
            dirv = Vector((r.uniform(-0.8, 0.8), -1.0, r.uniform(-0.6, 0.9))).normalized()
            pos += dirv * (0.9 * dt * dt + 1.2 * dt)
            rot_v = [a + (r.uniform(-0.5, 0.5) * dt) for a in rot_v]
            sc *= 1 + 0.09 * dt
    return pos, rot_v, sc


def animate_letters(objs, face_mats):
    for i, ob in enumerate(objs):
        rest = ob["rest"]
        pulses = [(m.node_tree.nodes["PULSE"].outputs[0], m["rest_pulse"]) for m in face_mats[i]]
        for f in frames():
            pos, rot, sc = letter_pose(i, f, rest)
            ob.location = pos
            ob.rotation_euler = rot
            ob.scale = (sc, sc, sc)
            ob.keyframe_insert("location", frame=f)
            ob.keyframe_insert("rotation_euler", frame=f)
            ob.keyframe_insert("scale", frame=f)
            land = FLIGHTS[i][1]
            glow = env(f, land, 4.0) * (1.0 if land in HIT_FRAMES else 0.6)
            glow += env(f, 880 + i * 0.55, 3.0) * 0.7 + pulse_env(f, 0.35, 2.5)
            if f >= 892:
                glow += 1.2 * env(f, 892, 3.0)
            ramp = smooth((f - FLIGHTS[i][0]) / 6.0)
            for sock, rest_v in pulses:
                key(sock, "default_value", f, rest_v * (0.35 + 0.65 * ramp) * (1.0 + 3.2 * glow))
        linearize(ob)
        for m in face_mats[i]:
            linearize(m.node_tree)


# --- camera, flash and black -------------------------------------------------------------------------------------------
def build_camera():
    sc = bpy.context.scene
    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = 40.0
    cam_d.sensor_width = 36.0
    cam_d.clip_start, cam_d.clip_end = 0.05, 200.0
    cam_d.dof.use_dof = False
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    rig = bpy.data.objects.new("camrig", None)
    sc.collection.objects.link(rig)
    cam.parent = rig
    cam.rotation_mode = "QUATERNION"
    q90 = Quaternion((1, 0, 0), math.pi / 2)
    rnd = random.Random(3)
    jit = [(rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1)) for _ in range(400)]
    for f in frames():
        t = (f - F0) / (F1 - F0)
        punch = sum(s * ring_osc(f, h, 2.6, 1.0) for h, s in HITS)       # dolly impulse (negative = towards the word)
        hit_env = sum(s * env(f, h, 3.0) for h, s in HITS)
        d = 27.0 - 6.5 * out_pow((f - 819) / 22.0, 2.0) - 1.8 * smooth((f - 840) / 50.0)      # pulls back from close, then pushes in
        d -= 1.9 * punch
        if f >= 892:
            d -= 7.0 * smooth((f - 892) / 5.0)                    # the yank: the camera drives into the exit
        az = math.radians(-11 + 17 * smooth(t * 1.05))              # a slow orbit that never stops
        el = math.radians(5.0 - 4.0 * smooth(t) + 1.2 * punch)
        roll = math.radians(1.2 * math.sin(t * 5.0) + 2.2 * punch + (7.0 * smooth((f - 892) / 6.0) if f >= 892 else 0.0))
        shake = hit_env * 0.12
        j = jit[(f - F0) % 400]
        rig.rotation_euler = (el + 0.004 * j[0] * hit_env * 3, 0, az + 0.004 * j[1] * hit_env * 3)
        rig.location = (shake * j[2] * 0.6, 0, shake * j[0] * 0.5)
        cam.location = (0, -d, 0)
        cam.rotation_quaternion = q90 @ Quaternion((0, 0, 1), roll)
        rig.keyframe_insert("rotation_euler", frame=f)
        rig.keyframe_insert("location", frame=f)
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_quaternion", frame=f)
    linearize(rig)
    linearize(cam)
    # screen-space cards parented to the camera: colour flash + final black
    def screen_card(name, dist):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        sc.collection.objects.link(ob)
        ob.parent = cam
        ob.location = (0, 0, -dist)
        ob.scale = (dist * 0.55, dist * 0.32, 1.0)
        for a in ("visible_diffuse", "visible_glossy", "visible_transmission", "visible_shadow", "visible_volume_scatter"):
            if hasattr(ob, a):
                setattr(ob, a, False)
        return ob, me
    fl, fme = screen_card("flash", 0.5)
    mat, nt_ = new_mat("flash")
    o_ = node(nt_, "ShaderNodeOutputMaterial", 600, 0)
    em_ = node(nt_, "ShaderNodeEmission", 200, 0, name="EMIT")
    tr_ = node(nt_, "ShaderNodeBsdfTransparent", 200, -150)
    ad_ = node(nt_, "ShaderNodeAddShader", 420, 0)
    link(nt_, tr_.outputs[0], ad_.inputs[0])
    link(nt_, em_.outputs[0], ad_.inputs[1])
    link(nt_, ad_.outputs[0], o_.inputs[0])
    fme.materials.append(mat)
    fac = em_.inputs["Strength"]
    emnode = em_.inputs["Color"]
    flash_ev = [(819, (0.3, 0.5, 1.0), 0.05, 1.3), (828, HOT, 0.03, 1.1), (837, BLUE, 0.025, 1.1), (844, WHITE, 0.035, 1.3),
                (854, HOT, 0.03, 1.1), (860, (0.5, 0.7, 1.0), 0.06, 1.2), (880, WHITE, 0.03, 1.2), (892, WHITE, 0.07, 1.4),
                (897, WHITE, 1.0, 1.0)]
    for f in frames():
        best, col = 0.0, WHITE
        for h, c, a, dcy in flash_ev:
            v = a * env(f, h, dcy)
            if v > best:
                best, col = v, c
        key(fac, "default_value", f, best)
        key(emnode, "default_value", f, rgba(col))
    linearize(mat.node_tree)
    bk, bme = screen_card("black", 0.4)
    bmat, bst, bfac = emit_material("black", (0, 0, 0), 1.0, alpha=0.0)
    bme.materials.append(bmat)
    for f in frames():
        a = 1.0 if f >= 899 else 0.0 if f < 897 else (0.55 if f == 897 else 0.97)
        key(bfac, "default_value", f, a)
    for kp_owner in (bmat.node_tree,):
        for fc in all_fcurves(kp_owner.animation_data.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"
    return cam


# --- compositor -------------------------------------------------------------------------------------------------------
def build_compositor(res_scale):
    sc = bpy.context.scene
    nt = bpy.data.node_groups.new("outro_comp", "CompositorNodeTree")
    sc.compositing_node_group = nt
    nt.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = node(nt, "CompositorNodeRLayers", 0, 0)
    gl = node(nt, "CompositorNodeGlare", 250, 0)
    gl.inputs["Type"].default_value = "Bloom"
    gl.inputs["Threshold"].default_value = 4.0
    gl.inputs["Size"].default_value = 0.6
    gl.inputs["Quality"].default_value = "Low"
    gl.inputs["Strength"].default_value = 0.2
    link(nt, rl.outputs["Image"], gl.inputs["Image"])
    last = gl.outputs["Image"]
    split = None
    try:       # chromatic misregistration on the hits: R and B channels slide apart (the Spider-Verse print offset)
        sepc = node(nt, "CompositorNodeSeparateColor", 480, 0)
        link(nt, last, sepc.inputs[0])
        tr_r = node(nt, "CompositorNodeTranslate", 700, 120)
        tr_b = node(nt, "CompositorNodeTranslate", 700, -120)
        for t_, ch in ((tr_r, "Red"), (tr_b, "Blue")):
            t_.inputs["Interpolation"].default_value = "Bilinear" if "Interpolation" in t_.inputs else None
        link(nt, sepc.outputs["Red"], tr_r.inputs["Image"])
        link(nt, sepc.outputs["Blue"], tr_b.inputs["Image"])
        comb = node(nt, "CompositorNodeCombineColor", 950, 0)
        link(nt, tr_r.outputs["Image"], comb.inputs["Red"])
        link(nt, sepc.outputs["Green"], comb.inputs["Green"])
        link(nt, tr_b.outputs["Image"], comb.inputs["Blue"])
        last = comb.outputs["Image"]
        split = (tr_r, tr_b)
    except Exception as e:      # the node API moved between 5.x builds: skip the split, the picture is still complete
        print("outro: chromatic split skipped:", e)
    go = node(nt, "NodeGroupOutput", 1200, 0)
    link(nt, last, go.inputs[0])
    if split:
        for f in frames():
            amt = sum(s * env(f, h, 2.2) for h, s in HITS) * 9.0 * res_scale
            if f >= 892:
                amt += 10.0 * res_scale * smooth((f - 892) / 4.0)
            for t_, sign in ((split[0], 1), (split[1], -1)):
                t_.inputs["X"].default_value = sign * amt
                t_.inputs["X"].keyframe_insert("default_value", frame=f)
        linearize(nt)


# --- render setup -----------------------------------------------------------------------------------------------------
def setup_render(args):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = args.samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.02
    cy.use_denoising = True
    cy.denoiser = "OPENIMAGEDENOISE"
    cy.max_bounces = 6
    cy.diffuse_bounces = 2
    cy.glossy_bounces = 4
    cy.transmission_bounces = 2
    cy.transparent_max_bounces = 10
    cy.sample_clamp_indirect = 6.0
    cy.sample_clamp_direct = 60.0
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    sc.render.resolution_percentage = max(1, round(args.res_scale * 100))
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end = F0, F1
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.75          # 270 degrees, the edit's shutter
    sc.render.motion_blur_position = "CENTER"
    sc.render.film_transparent = False
    im = sc.render.image_settings
    im.file_format, im.color_mode, im.color_depth, im.compression = "PNG", "RGB", "8", 15
    sc.render.dither_intensity = 0.0               # the last frame has to be exactly black
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Punchy"
    sc.view_settings.exposure = 0.0
    sc.render.use_compositing = True
    sc.render.use_sequencer = False
    try:
        sc.render.compositor_device = "CPU"
    except Exception:
        pass
    prefs = bpy.context.preferences.addons["cycles"].preferences
    gpu = False
    dev = args.device.upper()
    if dev != "CPU":
        kinds = [dev] if dev not in ("AUTO", "GPU") else ["OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"]
        for kind in kinds:
            try:
                prefs.compute_device_type = kind
                prefs.refresh_devices() if hasattr(prefs, "refresh_devices") else prefs.get_devices()
                ds = [d for d in prefs.devices if d.type == kind]
                if ds:
                    for d in prefs.devices:
                        d.use = d.type == kind
                    gpu = True
                    break
            except Exception as e:
                print(f"outro: {kind} unavailable: {e}")
        if not gpu:
            raise SystemExit(f"outro: --device {args.device}: no such device found (use --device CPU to render on the CPU)")
    cy.device = "GPU" if gpu else "CPU"
    if gpu:
        cy.denoising_use_gpu = True
    print("outro: cycles device", cy.device)


def frame_list(arg, every):
    if not arg:
        return list(range(F0, F1 + 1, every))
    out = []
    for tok in arg.split(","):
        a, _, b = tok.partition("-")
        out += list(range(max(F0, int(a)), min(F1, int(b or a)) + 1, every if b else 1))
    return out


def parse(argv):
    ap = argparse.ArgumentParser(prog="outro.py")
    ap.add_argument("--res-scale", type=float, default=1.0)
    ap.add_argument("--frames", help="comp frames, e.g. 819-899 or 828,844-850 (default all)")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--samples", type=int, default=96)
    ap.add_argument("--device", default="CPU", help="CPU | OPTIX | CUDA | HIP | AUTO")
    ap.add_argument("--out", help="default $AMV2_DATA/blender/outro, else out/amv2/outro")
    ap.add_argument("--save", help="save the .blend here (default none)")
    ap.add_argument("--no-render", action="store_true")
    return ap.parse_args(argv)


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
    print(f"outro: word {layout['width']:.2f} x {layout['height']:.2f} BU")
    bg = build_world()
    build_lights()
    build_backdrop(bg)
    build_portal()
    build_web()
    build_strands(objs)
    build_shafts()
    build_sweep(objs)
    build_fx(objs)
    animate_letters(objs, per_letter)
    build_camera()
    build_compositor(args.res_scale)


def main(argv):
    args = parse(argv)
    build_scene(args)
    sc = bpy.context.scene
    default = Path(os.environ["AMV2_DATA"]) / "blender/outro" if os.environ.get("AMV2_DATA") else Path("out/amv2/outro")
    out = Path(args.out) if args.out else default
    if args.save:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save).resolve()), compress=True)
        print("outro: saved", args.save)
    if args.no_render:
        return
    out.mkdir(parents=True, exist_ok=True)
    for f in frame_list(args.frames, args.every):
        t0 = time.time()
        sc.frame_set(f)
        sc.render.filepath = str(out / f"{f:04d}")
        bpy.ops.render.render(write_still=True)
        print(f"outro: frame {f} rendered in {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
