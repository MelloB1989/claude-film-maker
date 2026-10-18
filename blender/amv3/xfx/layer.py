"""Timeless v3 stage module `layer`: subject-layer transitions (REFS.md "Refs a and c" item 9, "Real layering").

  cut(f, "layer", pre, post, dict(mode="keep" | "sweep", ...))

mode "keep" (EDIT.md "v3.1: nested null-camera zooms", background variant; ref c 280-300): nothing moves but the camera.
  Private set: one copy of A's card, identical to its home card (same tiled mesh and depth), so the teleport at w0 - 0.5
  is invisible. Its alpha is 1 - Fade * (1 - m'), m' = the subject matte feathered and choked in the shader, so A's
  subject stays while A's background opacity fades away over `fade` frames (ending one frame before the cut). Behind it,
  B's card is static and already playing, `depth` m back, scaled so it fills the frame for the whole window. The camera
  then flies forward past A's static subject: it crosses A's plane `margin` m beside the subject (the subject passes the
  lens on the `dir` side, defocusing: DOF focused on B) and lands on B's hold framing. The camera is one blend from A's
  pose to B's pose, with zero rate at w0 and w1 (exact C1 with the holds), fastest on the cut. bounds() raises B's exit
  scale until the camera's distance to B shrinks the whole way and the camera ends `past` m beyond A's plane.
mode "sweep" (ref c 492-503, c 101-122): B's matted subject sweeps in over A from the `from` frame edge, big and close to
  the lens (defocused, motion-blurred), and decelerates onto its exact place on B's card; A wipes away behind the
  subject's trailing edge, so B's background resolves behind it. The camera tracks the sweep sideways (`shift`).

Parameters (all optional): keep: dir L|R|U|D (the side the subject leaves by; default: the camera passes on the
roomier side), depth 16.0, fade 10, margin 0.35 (m beside the subject's matte box), past 0.12, dof 2.8, ease 1.5 /
ease_out 1.8 (camera blend attack / decay), choke 3 (px: the matte is feathered inward by this much, so the plate's own
background never shows around the subject), settle 1.35 (B's minimum exit scale).
sweep: from L|R|U|D (default: the side away from B's subject), depth 0.3, enter 4, land 5, approach 0.78, tilt 22,
shift 0.25, feather 320, dof 4.0, ease 1.8, ease_out 1.6, settle 1.35, b_travel 0.35, choke 3, zoom push|pull (default:
push, or A's own zoom sign when the hold before is too short to turn round; a pull lands B receding).
Mattes: $AMV3_DATA/mattes/<shot>/f_NNNNN.png (white subject). Without mattes the module still runs (opaque subject
cards; the log says so) so camera tests work before the prep lands.
"""
import math
import os

import bpy
from mathutils import Matrix, Quaternion, Vector

import camlib as cl
import cards
import flow

DEFAULTS = {
    "keep": dict(dir=None, depth=16.0, fade=10, margin=0.35, dof=2.8, settle=1.35, ease=1.5, ease_out=1.8, choke=3.0,
                 past=0.12),
    "sweep": dict(dir=None, depth=0.3, enter=4, land=5, approach=0.78, tilt=22.0, shift=0.25, feather=320.0, dof=4.0,
                  settle=1.35, b_travel=0.35, ease=1.8, ease_out=1.6, choke=3.0, zoom=None),
}
SIDES = {"L": (-1, 0), "R": (1, 0), "U": (0, 1), "D": (0, -1)}  # screen direction (x right, y up)
STEP = 0.25
ENTRY = 0.02  # d ln s / f a layer window is entered with (the hold before turns to it: REFS holds 1.5-3.5 %/f)
ZSEP = 0.004  # m a subject card sits in front of the plate it came from: coplanar cards z-fight in Cycles (a ray that
#               passes the transparent part of one card skips the other at random -> ~50 % see-through)


def params(T):
    p = dict(T.get("p") or {})
    mode = p.get("mode", "keep")
    if mode not in DEFAULTS:
        mode = "keep"
    q = dict(DEFAULTS[mode])
    q.update({k: v for k, v in p.items() if v is not None})
    if mode == "sweep" and p.get("from"):
        q["dir"] = p["from"]
    q["mode"] = mode
    return q


# ======================================================================================================================
def zoom_sign(T, ctx, p, A):
    """+1 push / -1 pull through the window. keep always pushes (the subject flies at the lens); sweep pushes unless
    p.zoom says otherwise or the hold before is too short to turn A's pull round (then it keeps A's sign)."""
    if p["mode"] == "keep":
        return 1
    if p.get("zoom") in ("push", "pull"):
        return 1 if p["zoom"] == "push" else -1
    if A.ds < 0 and flow.prev_hold(T, ctx) < flow.REVERSAL_MIN:
        return -1
    return 1


def layout(T, ctx, p, A, B, adjust=False):
    """The window's geometry in set-local space (A's card at the origin, facing +Z): which side things move to, B's
    card depth / offset / dolly, its cover scale kb, and (adjust=True, from bounds) B's exit scale raised until the
    camera's distance to B's card changes monotonically the window's zoom way. Without that, the cover scale puts B's
    exit pose farther from B than the camera already is and B lands pulling out of a push (a hidden zoom reversal)."""
    w0, w1, f = T["w0"], T["w1"], T["f"]
    keep = p["mode"] == "keep"
    L = dict(keep=keep)
    if keep:
        mc = matte_centroid(ctx, T["a"]["id"], f - 1)
        sc_px = mc["c"] if mc else list(T["a"].get("focus") or [A.cx, A.cy])
        # dir = the screen side A's subject leaves by; default: the camera passes on the roomier side of the subject
        d = p["dir"] or ("L" if sc_px[0] < 960 else "R")
        sx, sy = SIDES[d]
        half = (mc["half"] if mc else [420.0, 420.0])
        ext = (half[0] if sx else half[1]) / 1000.0
        c0 = px_local(*sc_px)
        # where the camera crosses A's plane: beside the subject, on the side opposite to where it leaves the frame
        Xc = c0 + Vector((-sx, -sy, 0.0)) * (ext + float(p["margin"]))
        A0 = Vector(cl.local_pose(A)[0])  # the camera at w0 (A's card space = set-local space)
        ox = oy = 0.0
        sg = 1
    else:
        t_land = min(w1 - 1, f + int(p["land"]))
        mc = matte_centroid(ctx, T["b"]["id"], t_land)
        sc_px = mc["c"] if mc else list(T["b"].get("focus") or [B.cx, B.cy])
        d = p["dir"] or ("R" if sc_px[0] < B.cx else "L")  # enter from the far side: it crosses more of A
        sx, sy = SIDES[d]
        ox, oy = -sx, -sy  # toward `from`: the camera tracks the subject
        sg = zoom_sign(T, ctx, p, A)
    D = float(p["depth"])
    shift = 0.0 if keep else float(p["shift"])
    btr = 0.0 if keep else float(p["b_travel"]) * sg  # sweep push: B arrives from further back; pull: recedes
    ek, eko = float(p["ease"]), float(p["ease_out"])

    def b_off(t):
        u = cl.clamp01((t - w0) / float(w1 - w0))
        return btr * (1 - u) ** 3  # zero rate at w1

    def MBl(kb, t=None, Bx=None):
        if keep:
            # static B, D behind A, placed so the camera's line from A's pose (at w0) to B's exit pose crosses A's
            # plane at Xc, beside the subject (the camera travels much further in depth than sideways, so B's exit
            # pose carries the sideways offset scaled by how far past A's plane it ends)
            Bx = Bx or B
            (bxl, byl, bzl), _ = cl.local_pose(Bx)
            zB = -D + kb * bzl
            k = (A0.z - zB) / A0.z
            Px, Py = A0.x + (Xc.x - A0.x) * k, A0.y + (Xc.y - A0.y) * k
            return Matrix.Translation((Px - kb * bxl, Py - kb * byl, -D)) @ Matrix.Scale(kb, 4)
        # a pull starts B at D behind A and recedes to D + |btr| (never in front of A's plane)
        z = -D - max(0.0, -btr) - (b_off(t) if t is not None else 0.0)
        return Matrix.Translation((ox * shift, oy * shift, z)) @ Matrix.Scale(kb, 4)

    def solve(Bx):
        # start at the scale that just fills the frame from A's framing (camera FILL / A.s in front of A's plane)
        kb = max(1.0, 0.95 * (cl.FILL_DIST / A.s + D + max(0.0, btr)) / cl.FILL_DIST)
        for _ in range(120):
            cam = Blend(ctx, Matrix(), A, MBl(kb, None, Bx), Bx, w0, f, w1, ek, eko)
            if all(covers(*cam(t), MBl(kb, t, Bx)) for t in frange(w0 + 1, w1, 0.5)):
                return kb, cam, True
            kb *= 1.04
        return kb, cam, False

    def past_ok(cam):
        """keep: the camera ends `past` m beyond A's plane (A is behind it at w1)."""
        return not keep or cam(w1 - 0.01)[0].z <= -float(p["past"])

    def monotone(cam, kb, Bx):
        ds = []
        prev = None
        for t in frange(w0, w1, 0.5):
            d_ = cam(t)[0].z - MBl(kb, t, Bx).translation.z
            if prev is not None:
                ds.append(sg * (prev - d_))
            prev = d_
        return min(ds) >= -1e-4, ds

    kb, cam, ok = solve(B)
    if adjust and keep:
        for _ in range(24):
            mono, _ds = monotone(cam, kb, B)
            if (mono and past_ok(cam)) or B.s > 2.2:
                break
            B = B.with_(s=B.s * 1.04)
            kb, cam, ok = solve(B)
    mono, _ds = monotone(cam, kb, B)
    if keep and not past_ok(cam):
        ctx.log(f"  WARN layer {T['id']}: the camera does not get past A's plane (raise depth)")
    L.update(mc=mc, sc_px=sc_px, dir=d, sx=sx, sy=sy, sg=sg, D=D, shift=shift, btr=btr, ek=ek, eko=eko, b_off=b_off,
             MBl=lambda kb_, t=None: MBl(kb_, t, B), kb=kb, B=B, covered=ok, monotone=mono)
    return L


def bounds(T, ctx):
    """Entry: A's hold, entered moving the window's zoom way. Exit: B's hold at w1, still moving that way (push: at
    >= `settle` x, B's card dollies toward the camera; pull: B's card recedes)."""
    p = params(T)
    A = ctx.entry_state(T)
    sg = zoom_sign(T, ctx, p, A)
    if flow.prev_hold(T, ctx) >= flow.REVERSAL_MIN:
        A = A.with_(ds=max(A.ds, ENTRY) if sg > 0 else min(A.ds, -ENTRY))
    A = ctx.settle_entry(T, A)
    B = ctx.exit_state(T)
    if sg > 0 and p.get("settle"):
        B = B.with_(s=max(B.s, float(p["settle"]), cl.min_scale(B.cx, B.cy, B.r, 0.01)))
    if flow.next_hold(T, ctx) >= flow.REVERSAL_MIN:
        B = B.with_(ds=max(B.ds, flow.EXIT) if sg > 0 else min(B.ds, -flow.EXIT))
    B = layout(T, ctx, p, A, B, adjust=True)["B"]
    return {"A": A, "B": B}


def build(T, ctx):
    p = params(T)
    if p["mode"] == "sweep":
        build_sweep(T, ctx, p)
    else:
        build_keep(T, ctx, p)


# ---- helpers ---------------------------------------------------------------------------------------------------------
def shot_depth(ctx, sid):
    return float(ctx.shot(sid).get("move", {}).get("depth", 0.0) or 0.0)


def matte_centroid(ctx, sid, f):
    """Subject centroid (plate px, y down) and bbox half-size (px) from the matte at frame f, or None."""
    d = os.path.join(ctx.data, "mattes", sid)
    if not os.path.isdir(d):
        return None
    have = sorted(int(n[2:7]) for n in os.listdir(d) if n.startswith("f_") and n.endswith(".png") and n[2:7].isdigit())
    if not have:
        return None
    fr = min(have, key=lambda k: abs(k - f))
    try:
        import numpy as np
        img = bpy.data.images.load(os.path.join(d, f"f_{fr:05d}.png"), check_existing=False)
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        bpy.data.images.remove(img)
        a = px.reshape(h, w, 4)[::-1, :, 0]  # Blender rows are bottom-up; row 0 = top
        a = a[::4, ::4]
        tot = float(a.sum())
        if tot < 50:
            return None
        ys, xs = np.mgrid[0:a.shape[0], 0:a.shape[1]]
        cx, cy = float((a * xs).sum() / tot) * 4 * 1920 / w, float((a * ys).sum() / tot) * 4 * 1080 / h
        m = a > 0.5
        if not m.any():
            return None
        xx, yy = xs[m] * 4 * 1920 / w, ys[m] * 4 * 1080 / h
        return dict(c=[cx, cy], half=[float(xx.max() - xx.min()) / 2, float(yy.max() - yy.min()) / 2],
                    area=float(m.mean()), frame=fr)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"WARN layer: matte centroid {sid}@{f}: {e}")
        return None


def px_local(px, py):
    x, y = cl.px_to_local(px, py)
    return Vector((x, y, 0.0))


def key_matrix(ob, M, t):
    loc, rot, sc = M.decompose()
    ob.rotation_mode = "QUATERNION"
    ob.location, ob.rotation_quaternion, ob.scale = loc, rot, sc
    ob.keyframe_insert("location", frame=t)
    ob.keyframe_insert("rotation_quaternion", frame=t)
    ob.keyframe_insert("scale", frame=t)


def frange(t0, t1, step=STEP):
    n = int(round((t1 - t0) / step))
    return [round(t0 + i * step, 4) for i in range(n + 1)]


def plane_hit(loc, rot, M, u, v):
    """Card-local hit (x, y) of screen pixel (u, v) of a camera (loc, rot) on the plane of card matrix M, or None."""
    Mi = M.inverted_safe()
    d = rot @ Vector(cl.pixel_ray(u, v))
    p0 = Mi @ loc
    dl = Mi.to_3x3() @ d
    if abs(dl.z) < 1e-9:
        return None
    k = -p0.z / dl.z
    if k <= 0:
        return None
    h = p0 + dl * k
    return h.x, h.y


def covers(loc, rot, M, margin=0.015):
    for u, v in ((0, 0), (1920, 0), (1920, 1080), (0, 1080), (960, 0), (960, 1080), (0, 540), (1920, 540)):
        h = plane_hit(loc, rot, M, u, v)
        if h is None or abs(h[0]) > cl.CARD_W / 2 * (1 - margin) or abs(h[1]) > cl.CARD_H / 2 * (1 - margin):
            return False
    return True


def patch_alpha(mat, ctx, name, coord, sign, feather, hole=True, fade=False, matte_img=None):
    """Turn a card material into A's background layer: opacity = wipe * (1 - matte * HoleH) [* (1 - Fade)].
    wipe = 1 - smoothstep(WipeE - feather, WipeE, sign * coord_px): the layer is kept on the low side of the moving edge
    WipeE (px, keyed by the caller). Value nodes 'WipeE', 'HoleH', 'Fade' are keyed by the caller. The matte texture is
    set to CLIP (no mirrored holes on a tiled card)."""
    nt = mat.node_tree
    N = nt.nodes
    tc = next(n for n in N if n.bl_idname == "ShaderNodeTexCoord")
    texs = [n for n in N if n.bl_idname == "ShaderNodeTexImage"]
    matte = texs[1] if len(texs) > 1 else None
    if matte is None and hole and matte_img is not None:
        matte = N.new("ShaderNodeTexImage")
        matte.image, matte.interpolation = matte_img, "Linear"
        cards.setup_user(matte.image_user)
        nt.links.new(tc.outputs["UV"], matte.inputs["Vector"])
    out = next(n for n in N if n.bl_idname == "ShaderNodeOutputMaterial")
    mix = next((n for n in N if n.bl_idname == "ShaderNodeMixShader" and n.location.x >= 590), None)
    if matte is not None:
        matte.extension = "CLIP"

    def node(kind, **kw):
        n = N.new(kind)
        for k, v in kw.items():
            setattr(n, k, v)
        return n
    sep = node("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["UV"], sep.inputs[0])
    q = node("ShaderNodeMath", operation="MULTIPLY_ADD")  # px = u * 1920 (x) or (1 - v) * 1080 (y, down)
    if coord == "x":
        nt.links.new(sep.outputs[0], q.inputs[0])
        q.inputs[1].default_value = 1920.0 * sign
        q.inputs[2].default_value = 0.0
    else:
        nt.links.new(sep.outputs[1], q.inputs[0])
        q.inputs[1].default_value = -1080.0 * sign
        q.inputs[2].default_value = 1080.0 * sign
    e = node("ShaderNodeValue", name="WipeE", label="WipeE")
    e.outputs[0].default_value = 1e5
    lo = node("ShaderNodeMath", operation="SUBTRACT")
    nt.links.new(e.outputs[0], lo.inputs[0])
    lo.inputs[1].default_value = feather
    mr = node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
    nt.links.new(q.outputs[0], mr.inputs["Value"])
    nt.links.new(lo.outputs[0], mr.inputs["From Min"])
    nt.links.new(e.outputs[0], mr.inputs["From Max"])
    mr.inputs["To Min"].default_value = 1.0
    mr.inputs["To Max"].default_value = 0.0
    fac = mr.outputs["Result"]
    if hole and matte is not None:
        h = node("ShaderNodeValue", name="HoleH", label="HoleH")
        h.outputs[0].default_value = 0.0
        mh = node("ShaderNodeMath", operation="MULTIPLY")
        nt.links.new(matte.outputs["Color"], mh.inputs[0])
        nt.links.new(h.outputs[0], mh.inputs[1])
        inv = node("ShaderNodeMath", operation="SUBTRACT")
        inv.inputs[0].default_value = 1.0
        nt.links.new(mh.outputs[0], inv.inputs[1])
        m2 = node("ShaderNodeMath", operation="MULTIPLY")
        nt.links.new(fac, m2.inputs[0])
        nt.links.new(inv.outputs[0], m2.inputs[1])
        fac = m2.outputs[0]
    if fade:
        fd = node("ShaderNodeValue", name="Fade", label="Fade")
        fd.outputs[0].default_value = 0.0
        inv = node("ShaderNodeMath", operation="SUBTRACT")
        inv.inputs[0].default_value = 1.0
        nt.links.new(fd.outputs[0], inv.inputs[1])
        m3 = node("ShaderNodeMath", operation="MULTIPLY")
        nt.links.new(fac, m3.inputs[0])
        nt.links.new(inv.outputs[0], m3.inputs[1])
        fac = m3.outputs[0]
    if mix is None:
        surf = out.inputs["Surface"].links[0].from_socket
        tr = node("ShaderNodeBsdfTransparent")
        mix = node("ShaderNodeMixShader")
        nt.links.new(tr.outputs[0], mix.inputs[1])
        nt.links.new(surf, mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
    nt.links.new(fac, mix.inputs[0])
    mat.name = name
    return nt


def key_value(nt, node_name, pairs):
    v = nt.nodes[node_name].outputs[0]
    for t, x in pairs:
        v.default_value = x
        v.keyframe_insert("default_value", frame=t)


def own_material(ob, name):
    m = ob.data.materials[0].copy()
    m.name = name
    ob.data.materials[0] = m
    return m


def clip_matte(ob):
    """Subject card on a tiled mesh: the matte reads CLIP so only the central card shows the subject."""
    for n in ob.data.materials[0].node_tree.nodes:
        if n.bl_idname == "ShaderNodeTexImage" and n.image is not None and "mattes" in (n.image.filepath or ""):
            n.extension = "CLIP"


def choke_matte(ob, r_px):
    """Feather + choke the subject matte in the card shader: alpha = smoothstep(0.5, 1, blur_r(matte)) (9 taps, a ring
    of radius r px + centre). Alpha is 0 on the matte's own edge and reaches 1 r px inside, so the plate's background
    never shows around the subject and the cut edge is soft."""
    if r_px <= 0:
        return
    nt = ob.data.materials[0].node_tree
    N, L = nt.nodes, nt.links
    mt = next((n for n in N if n.bl_idname == "ShaderNodeTexImage" and n.image is not None
               and "mattes" in (n.image.filepath or "")), None)
    if mt is None:
        return
    outs = [(l.to_socket) for l in mt.outputs["Color"].links]
    uv = mt.inputs["Vector"].links[0].from_socket
    acc = mt.outputs["Color"]
    taps = [(1, 0), (-1, 0), (0, 1), (0, -1), (0.707, 0.707), (-0.707, 0.707), (0.707, -0.707), (-0.707, -0.707)]
    for dx, dy in taps:
        off = N.new("ShaderNodeVectorMath")
        off.operation = "ADD"
        off.inputs[1].default_value = (dx * r_px / 1920.0, dy * r_px / 1080.0, 0.0)
        L.new(uv, off.inputs[0])
        t = N.new("ShaderNodeTexImage")
        t.image, t.interpolation, t.extension = mt.image, "Linear", mt.extension
        cards.setup_user(t.image_user)
        L.new(off.outputs[0], t.inputs["Vector"])
        add = N.new("ShaderNodeMath")
        add.operation = "ADD"
        L.new(acc, add.inputs[0])
        L.new(t.outputs["Color"], add.inputs[1])
        acc = add.outputs[0]
    mr = N.new("ShaderNodeMapRange")
    mr.interpolation_type = "SMOOTHSTEP"
    L.new(acc, mr.inputs["Value"])
    mr.inputs["From Min"].default_value = 0.5 * 9
    mr.inputs["From Max"].default_value = 1.0 * 9
    for sock in outs:
        L.new(mr.outputs["Result"], sock)


def glow_bar(ctx, name, parent, rgb, vis, vertical=True):
    """A soft emissive bar riding the wipe edge (light collection -> glow pass). Parented to the layer it lights."""
    me = cards.card_mesh(name, 1, 1, 0.07 if vertical else 2.4, 1.6 if vertical else 0.07)
    me.materials.append(cards.emission_material(name, rgb, 0.0, 1.0, radial=True))
    ob = bpy.data.objects.new(name, me)
    ctx.coll("light").objects.link(ob)
    cards.no_shadow(ob)
    ob.parent = parent
    ctx.show(ob, *vis)
    return ob


class Blend:
    """Camera = blend of A's pose (A's state extrapolated on card MA) and B's pose (B's state extrapolated on card MB)
    with weight w(t) = flow.Turn(1, w0, f, w1): zero rate at both ends (C1 with the holds), fastest on the cut.
    extra(t, loc, rot) -> (loc, rot) adds a move on top (must vanish with its rate at w0 and w1)."""

    def __init__(self, ctx, MA, A, MB, B, w0, f, w1, kA=3.0, kB=3.0, extra=None):
        self.ctx, self.MA, self.A, self.MB, self.B, self.w0, self.w1 = ctx, MA, A, MB, B, w0, w1
        self.turn = flow.Turn(1.0, w0, f, w1, kA, kB, 0.0)
        self.extra = extra

    def __call__(self, t):
        la, ra = self.ctx.pose(self.MA, self.A.at(t - self.w0))
        lb, rb = self.ctx.pose(self.MB, self.B.at(t - self.w1))
        w = self.turn(t)
        loc = la.lerp(lb, w)
        if ra.dot(rb) < 0:
            rb = -rb
        rot = ra.slerp(rb, w)
        if self.extra:
            loc, rot = self.extra(t, loc, rot)
        return loc, rot


def bump(t, w0, w1):
    """sin^2 bump on [w0, w1]: 0 with zero rate at both ends, 1 in the middle."""
    u = cl.clamp01((t - w0) / float(w1 - w0))
    return math.sin(math.pi * u) ** 2


def focus_dist(loc, rot, M):
    h = plane_hit(loc, rot, M, 960, 540)
    if h is None:
        return 3.0
    p = M @ Vector((h[0], h[1], 0.0))
    return max(0.05, (p - loc).length)


# ======================================================================================================================
def build_keep(T, ctx, p):
    """v3.1 background variant (EDIT.md "nested null-camera zooms", ref c 280-300): nothing moves but the camera. A's card
    (identical to its home card) keeps its subject while its background opacity fades away (feathered, choked inverse
    matte) over `fade` frames, revealing B already playing behind it (static, `depth` m back, scaled to fill the frame);
    the camera then flies forward past A's static subject (it crosses A's plane beside the subject, so the subject passes
    the lens on the `dir` side, defocusing: DOF on B) and lands on B's hold framing."""
    A, B = ctx.bounds[T["id"]]["A"], ctx.bounds[T["id"]]["B"]
    w0, w1, f = T["w0"], T["w1"], T["f"]
    sa, sb = T["a"]["id"], T["b"]["id"]
    act = ctx.act_at(f)
    o = ctx.new_set(f"layer_{T['id']}")
    vis = (w0 - 1, w1 + 1)
    MA = Matrix.Translation(o)
    Lg = layout(T, ctx, p, A, B)
    mc, sc_px, d, kb = Lg["mc"], Lg["sc_px"], Lg["dir"], Lg["kb"]
    ctx.log(f"  layer keep {T['id']}: subject {sa} at {[round(v) for v in sc_px]}"
            f"{' (matte area %.0f %%)' % (100 * mc['area']) if mc else ' (no matte: seed)'}, leaves the frame {d}")
    MB = Matrix.Translation(o) @ Lg["MBl"](kb)
    cam = Blend(ctx, MA, A, MB, B, w0, f, w1, Lg["ek"], Lg["eko"])
    layout_log(ctx, T, Lg)

    # A: one static card, the subject matte (feathered + choked) keeps it, its background fades: alpha = 1 - F (1 - m')
    dA = shot_depth(ctx, sa)
    cardA = ctx.make_card(sa, f"layer_{T['id']}_A", MA, alpha="matte", depth=dA, frames=vis, tile=3)
    mat = own_material(cardA, f"m_layer_{T['id']}_A")
    clip_matte(cardA)
    choke_matte(cardA, float(p["choke"]))
    nt = fade_background(mat)
    fl = max(4, int(p["fade"]))
    t_f0 = max(w0, f - fl - 1)
    if nt is not None:
        key_value(nt, "Fade", [(t, cl.smoothstep((t - t_f0) / float(fl))) for t in frange(w0 - 1, t_f0 + fl + 1, 0.5)])
    else:
        ctx.log(f"  WARN layer {T['id']}: no mattes for {sa}: A stays opaque")
    # B: static, already playing
    dB = shot_depth(ctx, sb)
    ctx.make_card(sb, f"layer_{T['id']}_B", MB, depth=dB, frames=vis, tile=3)
    # no act void here: B covers the frame for the whole window (layout checks it), and the void's web strands would
    # hang between the camera and B, D m deep
    if not Lg["covered"]:
        ctx.env(o, act, frames=vis)
    ctx.teleport(w0 - 0.5)
    ctx.teleport(w1 - 0.5)
    ctx.key_path(cam, w0, w1, STEP)
    # DOF on B from the fade on: A's subject defocuses as the camera nears it; sharp again before w1
    fst = float(p["dof"])
    for t in frange(w0, w1 - 0.5, STEP):
        loc, rot = cam(t)
        u = cl.smoothstep((t - t_f0) / float(fl)) * (1 - cl.smoothstep((t - (w1 - 3)) / 2.5))
        if u <= 0:
            continue
        N = cl.FSTOP_SHARP * (fst / cl.FSTOP_SHARP) ** u
        ctx.key_dof(t, focus_dist(loc, rot, MB), N)
    zc = [round(cam(t)[0].z - o.z, 2) for t in (w0, f, w1 - 0.01)]
    ctx.log(f"  layer keep {T['id']}: A bg fades f{t_f0}-f{t_f0 + fl}; camera z over A's plane {zc[0]} -> {zc[1]} "
            f"-> {zc[2]} m (w0, cut, w1)")


def fade_background(mat):
    """alpha = 1 - Fade * (1 - m') on a matte card material whose Mix-shader factor is the (choked) matte m'.
    Returns the node tree (with a 'Fade' value node to key) or None when the card has no matte."""
    nt = mat.node_tree
    N, Lk = nt.nodes, nt.links
    mix = next((n for n in N if n.bl_idname == "ShaderNodeMixShader" and n.inputs[0].links), None)
    if mix is None:
        return None
    m = mix.inputs[0].links[0].from_socket
    fd = N.new("ShaderNodeValue")
    fd.name = fd.label = "Fade"
    fd.outputs[0].default_value = 0.0
    inv = N.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    Lk.new(m, inv.inputs[1])
    mul = N.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    Lk.new(fd.outputs[0], mul.inputs[0])
    Lk.new(inv.outputs[0], mul.inputs[1])
    al = N.new("ShaderNodeMath")
    al.operation = "SUBTRACT"
    al.inputs[0].default_value = 1.0
    Lk.new(mul.outputs[0], al.inputs[1])
    Lk.new(al.outputs[0], mix.inputs[0])
    return nt


def layout_log(ctx, T, Lg):
    ctx.log(f"  layer {T['id']}: B card x{Lg['kb']:.2f} at {Lg['D']:.2f} m (+{Lg['btr']:+.2f} dolly), exit s "
            f"{Lg['B'].s:.2f}, zoom {'push' if Lg['sg'] > 0 else 'pull'}"
            f"{'' if Lg['covered'] else '  WARN: B does not cover the frame'}"
            f"{'' if Lg['monotone'] else '  WARN: the distance to B is not monotone (zoom reversal behind the subject)'}")


def visible_range(cam, M, t, coord, sgn):
    """Range (lo, hi) of the signed wipe coordinate q = sgn * px (or sgn * py) visible on card M from the camera at t."""
    loc, rot = cam(t)
    vals = []
    for u, v in ((0, 0), (1920, 0), (1920, 1080), (0, 1080)):
        h = plane_hit(loc, rot, M, u, v)
        if h is None:
            continue
        px, py = cl.local_to_px(h[0], h[1])
        vals.append(sgn * (px if coord == "x" else py))
    if not vals:
        return (0.0, 1920.0)
    return min(vals), max(vals)


# ======================================================================================================================
def build_sweep(T, ctx, p):
    A, B = ctx.bounds[T["id"]]["A"], ctx.bounds[T["id"]]["B"]
    w0, w1, f = T["w0"], T["w1"], T["f"]
    sa, sb = T["a"]["id"], T["b"]["id"]
    act = ctx.act_at(f)
    pal = ctx.palette(act)
    o = ctx.new_set(f"layer_{T['id']}")
    vis = (w0 - 1, w1 + 1)
    MA = Matrix.Translation(o)

    t_land = min(w1 - 1, f + int(p["land"]))
    t_in = max(w0, f - int(p["enter"]))
    Lg = layout(T, ctx, p, A, B)
    mc, sc_px, d, ex, ey = Lg["mc"], Lg["sc_px"], Lg["dir"], Lg["sx"], Lg["sy"]
    coord = "x" if ex else "y"
    # A is kept on the side the subject has not reached yet (q = sgn * px or sgn * py < edge)
    sgn = ex if ex else -ey
    ctx.log(f"  layer sweep {T['id']}: B subject {sb} at {[round(v) for v in sc_px]}"
            f"{' (matte area %.0f %%)' % (100 * mc['area']) if mc else ' (no matte: seed)'}, from {d}")
    D, shift, btr, kb = Lg["D"], Lg["shift"], Lg["btr"], Lg["kb"]

    def MB_at(kb, t=None):
        return Matrix.Translation(o) @ Lg["MBl"](kb, t)
    MB = MB_at(kb)
    cam = Blend(ctx, MA, A, MB, B, w0, f, w1, Lg["ek"], Lg["eko"])
    layout_log(ctx, T, Lg)

    dA, dB = shot_depth(ctx, sa), shot_depth(ctx, sb)
    cardA = ctx.make_card(sa, f"layer_{T['id']}_A", MA, depth=dA, frames=(w0 - 1, t_land + 1), tile=3)
    mat = own_material(cardA, f"m_layer_{T['id']}_A")
    fe = float(p["feather"])
    nt = patch_alpha(mat, ctx, mat.name, coord, sgn, fe, hole=False)
    bgB = ctx.make_card(sb, f"layer_{T['id']}_B", MB, depth=dB, frames=vis, tile=3)
    if btr:
        for t in frange(w0 - 1, w1, 0.5):
            key_matrix(bgB, MB_at(kb, t), t)
        key_matrix(bgB, MB, w1)
        key_matrix(bgB, MB, w1 + 1)
    subj = ctx.make_card(sb, f"layer_{T['id']}_Bsub", MB @ Matrix.Translation((0, 0, ZSEP / kb)), alpha="matte",
                         depth=dB, frames=(t_in - 1, t_land + 2), tile=3)
    own_material(subj, f"m_layer_{T['id']}_Bsub")
    clip_matte(subj)
    choke_matte(subj, float(p["choke"]))

    cl_loc = px_local(*sc_px)  # the subject centroid on B's card (card-local)
    half = (mc["half"] if mc else [420.0, 420.0])
    ext = max(half[0], half[1]) / 1000.0 * kb
    ap = float(p["approach"])
    tilt = math.radians(float(p["tilt"]))

    def Mfin_at(t):  # where the subject card lands: on B's (moving) card, ZSEP in front
        return MB_at(kb, t) @ Matrix.Translation((0, 0, ZSEP / kb))

    def subj_M(t):
        loc, rot = cam(t)
        Mfin = Mfin_at(t)
        cf = Mfin @ cl_loc
        b = 1.0 - (1.0 - cl.clamp01((t - t_in) / float(t_land - t_in))) ** 3  # decelerating arrival, zero rate at land
        a = ap * (1 - b)
        P = cf + (loc - cf) * a
        dist = (loc - P).length
        L = (ext + dist * 0.6 + 0.05) * (1 - b) ** 1.3
        right, up = rot @ Vector((1, 0, 0)), rot @ Vector((0, 1, 0))
        P = P + (right * ex + up * ey) * L
        ang = tilt * (1 - b) * (ex if ex else ey)
        axis = "Y" if ex else "X"
        return Matrix.Translation(P) @ Matrix.Rotation(ang, 4, axis) @ Matrix.Translation(-cf) @ Mfin
    for t in frange(t_in - 1, t_land + 2, 0.5):
        key_matrix(subj, subj_M(max(t, t_in)) if t < t_land else Mfin_at(t), t)

    # A wipes away behind the subject's trailing edge: the edge follows the subject's projection on A's plane and is
    # off A's visible range by the landing
    lo_v, hi_v = visible_range(cam, MA, f, coord, sgn)

    def proj(t):
        loc, rot = cam(t)
        M = subj_M(max(t, t_in))
        cw = M @ cl_loc
        dvec = (cw - loc)
        Mi = MA.inverted_safe()
        p0, dl = Mi @ loc, Mi.to_3x3() @ dvec
        if abs(dl.z) < 1e-9:
            return None
        h = p0 + dl * (-p0.z / dl.z)
        px, py = cl.local_to_px(h.x, h.y)
        return sgn * (px if coord == "x" else py)

    keys = []
    t_gone = max(t_in + 2, min(t_land - 2, f + 1))
    for t in frange(w0 - 1, t_land + 1, 0.5):
        u = cl.clamp01((t - t_in) / float(t_gone - t_in))
        lin = hi_v + fe + 40 - (hi_v + fe + 40 - (lo_v - 40)) * cl.smootherstep(u)
        pr = proj(t) if t >= t_in else None
        e = lin if pr is None else min(lin, pr + fe * 0.5)
        keys.append((t, e if t >= t_in else hi_v + fe + 400))
    key_value(nt, "WipeE", keys)

    ctx.env(o, act, frames=vis)
    ctx.teleport(w0 - 0.5)
    ctx.teleport(w1 - 0.5)
    ctx.key_path(cam, w0, w1, STEP)
    fst = float(p["dof"])
    for t in frange(w0, w1 - 0.5, STEP):
        loc, rot = cam(t)
        u = cl.smoothstep((t - (t_in - 1)) / 2.0) * (1 - cl.smoothstep((t - (t_land - 1)) / 2.5))
        if u <= 0:
            continue
        N = cl.FSTOP_SHARP * (fst / cl.FSTOP_SHARP) ** u
        ctx.key_dof(t, focus_dist(loc, rot, MB), N)
    ctx.log(f"  layer sweep {T['id']}: B {D:.2f} m behind x{kb:.2f}, shift {shift}; subject in f{t_in} lands f{t_land}")
