"""Timeless v3 stage module `layer`: subject-layer transitions (REFS.md "Refs a and c" item 9, "Real layering").

  cut(f, "layer", pre, post, dict(mode="keep" | "sweep", ...))

mode "keep" (ref c 278-305, c 210-232): A's matted subject stays in front and keeps moving while A's background is
  carried away behind it and B arrives in 3D behind the subject; then the subject flies past the lens and B continues.
  Private set: A's background copy (card plane z = 0, the matte cut out of it as the subject separates) and A's subject
  copy (alpha = matte) start exactly where A's home card is, so the teleport at w0 - 0.5 is invisible. B's card sits
  `depth` m behind, scaled so it covers the frame for the whole window, and dollies in (`b_travel` m, expo-out) as it is
  revealed. A's background slides away (`carry` m, expo-in) with a soft wipe edge (light-leak glow on the light pass)
  running the `dir` way; the subject card flies toward the lens along its own sight line (it grows over the hole it left,
  so no double image), turns (`tilt`) and leaves the frame on the `dir` side `exit` frames after the cut, motion-blurred
  and defocused (real DOF focused on B). The camera blends from A's pose to B's pose with one ease that is zero-rate at
  w0 and w1 (exact C1 with the holds) and peaks on the cut; B's card is offset `shift` m against `dir`, so the camera
  travels sideways and the subject / B parallax reads as depth.
mode "sweep" (ref c 492-503, c 101-122): B's matted subject sweeps in over A from the `from` frame edge, big and close to
  the lens (defocused, motion-blurred), and decelerates onto its exact place on B's card; A wipes away behind the
  subject's trailing edge, so B's background resolves behind it. The camera tracks the sweep sideways (`shift`).

Parameters (all optional): keep: dir L|R|U|D (default: the side the subject is nearer to), depth 1.0, b_travel 0.5,
shift 0.3, carry 0.45, feather 380, exit 2, approach 0.86, tilt 18, dof 4.0, glow 1.0, ease 1.5 (camera blend ease), settle (B exit scale).
sweep: from L|R|U|D (default: the side away from B's subject), depth 0.3, enter 3, land 5, approach 0.78, tilt 22,
shift 0.25, feather 320, dof 4.0, ease 3.0, settle.
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
    "keep": dict(dir=None, depth=1.0, b_travel=0.5, shift=0.3, carry=0.45, feather=380.0, exit=2, approach=0.86,
                 tilt=18.0, dof=4.0, glow=1.0, settle=None, ease=1.5),
    "sweep": dict(dir=None, depth=0.3, enter=3, land=5, approach=0.78, tilt=22.0, shift=0.25, feather=320.0, dof=4.0,
                  settle=None, b_travel=0.0, ease=3.0),
}
SIDES = {"L": (-1, 0), "R": (1, 0), "U": (0, 1), "D": (0, -1)}  # screen direction (x right, y up)
STEP = 0.25
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
def bounds(T, ctx):
    """Entry: A's hold, entered already pushing in (the layer move is a push). Exit: B's hold at w1, still pushing in
    (B's card dollies toward the camera and decelerates), at `settle` x when given."""
    p = params(T)
    A = ctx.entry_state(T)
    if flow.prev_hold(T, ctx) >= flow.REVERSAL_MIN:
        A = A.with_(ds=max(A.ds, flow.ENTRY))
    A = ctx.settle_entry(T, A)
    B = ctx.exit_state(T)
    if p.get("settle"):
        B = B.with_(s=max(float(p["settle"]), cl.min_scale(B.cx, B.cy, B.r, 0.01)))
    if flow.next_hold(T, ctx) >= flow.REVERSAL_MIN:
        B = B.with_(ds=max(B.ds, flow.EXIT))
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
    A, B = ctx.bounds[T["id"]]["A"], ctx.bounds[T["id"]]["B"]
    w0, w1, f = T["w0"], T["w1"], T["f"]
    sa, sb = T["a"]["id"], T["b"]["id"]
    act = ctx.act_at(f)
    pal = ctx.palette(act)
    o = ctx.new_set(f"layer_{T['id']}")
    vis = (w0 - 1, w1 + 1)
    MA = Matrix.Translation(o)

    # subject: centroid at the cut from the matte (else the shot focus / frame centre)
    mc = matte_centroid(ctx, sa, f - 1)
    sc_px = mc["c"] if mc else list(T["a"].get("focus") or [A.cx, A.cy])
    d = p["dir"] or (("L" if sc_px[0] < A.cx else "R"))
    sx, sy = SIDES[d]
    coord = "x" if sx else "y"
    sgn = -sx if sx else sy  # wipe coordinate q = sgn * px (or sgn * py, y down); A's bg is kept where q < edge
    ctx.log(f"  layer keep {T['id']}: subject {sa} at {[round(v) for v in sc_px]}"
            f"{' (matte area %.0f %%)' % (100 * mc['area']) if mc else ' (no matte: seed)'}, carried {d}")

    # B card: depth m behind, offset against dir (the camera travels that way: parallax), scaled to cover the frame
    D, btr, shift = float(p["depth"]), float(p["b_travel"]), float(p["shift"])
    # phases: A's background goes over [w0 + 1, t_wipe1] while the subject is nearly still (the layered moment: the
    # subject over B), the subject then flies past the lens over [f - 1, t_exit]
    pre = f - w0
    t_exit = f + int(p["exit"])
    t_wipe1 = f - max(1, int(round(0.3 * pre)))
    ek = float(p["ease"])

    def b_off(t):
        u = cl.clamp01((t - w0) / float(w1 - w0))
        return btr * (1 - u) ** 3  # extra distance behind, expo-out-like arrival, zero rate at w1

    def MB_at(kb, t=None):
        z = -D - (b_off(t) if t is not None else 0.0)
        return Matrix.Translation(o + Vector((-sx * shift, -sy * shift, z))) @ Matrix.Scale(kb, 4)

    kb = 1.0
    for _ in range(30):
        cam = Blend(ctx, MA, A, MB_at(kb), B, w0, f, w1, ek, ek)
        if all(covers(*cam(t), MB_at(kb, t)) for t in frange(w0 + 1, w1, 0.5)):
            break
        kb *= 1.05
    else:
        ctx.log(f"  WARN layer {T['id']}: B card does not cover the frame at kb {kb:.2f}")
    MB = MB_at(kb)
    cam = Blend(ctx, MA, A, MB, B, w0, f, w1, ek, ek)

    # A's background (tiled like the home card so the teleport at w0 is exact), wipe + carry + matte hole
    dA = shot_depth(ctx, sa)
    bgA = ctx.make_card(sa, f"layer_{T['id']}_Abg", MA, depth=dA, frames=(w0 - 1, t_wipe1 + 1), tile=3)
    mat = own_material(bgA, f"m_layer_{T['id']}_Abg")
    fe = float(p["feather"])
    mimg = ctx._sequence("mattes", sa, "png")
    if mimg is None:
        ctx.log(f"  WARN layer {T['id']}: no mattes for {sa}: no subject hole, opaque subject card")
    nt = patch_alpha(mat, ctx, mat.name, coord, sgn, fe, matte_img=mimg)
    # visible card px range along the wipe axis at the cut (from the camera at f)
    lo_v, hi_v = visible_range(cam, MA, f, coord, sgn)
    carry = float(p["carry"])
    kc = 3.5

    def edge(t):
        u = cl.clamp01((t - (w0 + 1)) / float(t_wipe1 - (w0 + 1)))
        return hi_v + fe + 40 - (hi_v + fe + 40 - (lo_v - 40)) * cl.smootherstep(u)

    def carry_at(t):
        return carry * cl.expo_in(cl.clamp01((t - w0) / float(t_wipe1 - w0)), kc)
    wkeys = [(t, edge(t)) for t in frange(w0 - 1, t_wipe1 + 1, 0.5)]
    key_value(nt, "WipeE", wkeys)
    if "HoleH" in nt.nodes:
        key_value(nt, "HoleH", [(w0 - 1, 0.0), (w0, 0.0), (w0 + 2, 1.0)])
    for t in frange(w0 - 1, t_wipe1 + 1, 0.5):
        key_matrix(bgA, MA @ Matrix.Translation((sx * carry_at(t), sy * carry_at(t), 0.0)), t)
    if p["glow"]:
        g = glow_bar(ctx, f"layer_{T['id']}_glow", bgA, tuple(min(1.0, 0.35 + c) for c in pal["leak"]),
                     (w0, t_wipe1 + 1), vertical=coord == "x")
        gm = g.data.materials[0].node_tree.nodes["Emission"].inputs["Strength"]
        for t in frange(w0, t_wipe1 + 1, 0.5):
            e = (edge(t) - fe * 0.35) * sgn  # back to plate px
            x, y = cl.px_to_local(e, 540) if coord == "x" else cl.px_to_local(960, e)
            g.location = (x, 0.0, 0.004) if coord == "x" else (0.0, y, 0.004)
            g.keyframe_insert("location", frame=t)
            sp = abs(edge(t + 0.25) - edge(t - 0.25)) * 2  # px/f of the edge
            gm.default_value = float(p["glow"]) * 2.4 * min(1.0, sp / 300.0)
            gm.keyframe_insert("default_value", frame=t)

    # B (full plate, tiled like its home card so the teleport at w1 is exact), dollying in behind
    dB = shot_depth(ctx, sb)
    bgB = ctx.make_card(sb, f"layer_{T['id']}_B", MB, depth=dB, frames=vis, tile=3)
    for t in frange(w0 - 1, w1, 0.5):
        key_matrix(bgB, MB_at(kb, t), t)
    key_matrix(bgB, MB, w1)
    key_matrix(bgB, MB, w1 + 1)

    # A's subject: flies toward the lens along its sight line, turns, leaves on the dir side at t_exit
    subj = ctx.make_card(sa, f"layer_{T['id']}_Asub", MA, alpha="matte", depth=dA, frames=(w0 - 1, t_exit + 1),
                         tile=3)
    own_material(subj, f"m_layer_{T['id']}_Asub")
    clip_matte(subj)
    c0 = MA @ px_local(*sc_px)
    half = (mc["half"] if mc else [420.0, 420.0])
    ext = max(half[0], half[1]) / 1000.0  # subject half-size (m)
    ap = float(p["approach"])
    tilt = math.radians(float(p["tilt"])) * (-sx if sx else sy)
    t_lat0 = f - 1

    def subj_M(t):
        loc, rot = cam(t)
        a = ap * cl.expo_in(cl.clamp01((t - w0) / float(t_exit - w0)), 3.5)
        P = c0 + (loc - c0) * a
        dist = (loc - P).length
        lat_need = 1.3 * ext + dist * 0.75 + 0.08  # out of frame with its blur and defocus
        ul = cl.clamp01((t - t_lat0) / float(t_exit - t_lat0))
        L = lat_need * cl.expo_in(ul, 2.0) * 1.05
        right, up = rot @ Vector((1, 0, 0)), rot @ Vector((0, 1, 0))
        P = P + (right * sx + up * sy) * L
        ang = tilt * cl.smootherstep(ul)
        axis = "Y" if sx else "X"
        return Matrix.Translation(P) @ Matrix.Rotation(ang, 4, axis) @ Matrix.Translation(-c0) @ MA0
    MA0 = MA @ Matrix.Translation((0, 0, ZSEP))
    for t in frange(w0 - 1, t_exit + 1, 0.5):
        key_matrix(subj, subj_M(max(t, w0)), t)

    ctx.env(o, act, frames=vis)
    ctx.teleport(w0 - 0.5)
    ctx.teleport(w1 - 0.5)
    ctx.key_path(cam, w0, w1, STEP)
    # DOF: focus on B once A's background has gone; the subject card near the lens defocuses
    fst = float(p["dof"])
    for t in frange(w0, w1 - 0.5, STEP):
        loc, rot = cam(t)
        u = cl.smoothstep((t - (t_wipe1 - 1)) / 3.0) * (1 - cl.smoothstep((t - (w1 - 3)) / 2.5))
        if u <= 0:
            continue
        N = cl.FSTOP_SHARP * (fst / cl.FSTOP_SHARP) ** u
        ctx.key_dof(t, focus_dist(loc, rot, MB_at(kb, t)), N)
    ctx.log(f"  layer keep {T['id']}: B {D:.2f} m behind x{kb:.2f}, travel {btr} m, shift {shift} m; A bg carried "
            f"{carry} m, wipe px {hi_v:.0f}->{lo_v:.0f} by f{t_wipe1}; subject exits f{t_exit}")


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
    mc = matte_centroid(ctx, sb, t_land)
    sc_px = mc["c"] if mc else list(T["b"].get("focus") or [B.cx, B.cy])
    # enter from the far side by default: the subject crosses (and covers) more of A
    d = p["dir"] or ("R" if sc_px[0] < B.cx else "L")
    ex, ey = SIDES[d]  # the side it comes from
    coord = "x" if ex else "y"
    # A is kept on the side the subject has not reached yet (q = sgn * px or sgn * py < edge)
    sgn = ex if ex else -ey
    ctx.log(f"  layer sweep {T['id']}: B subject {sb} at {[round(v) for v in sc_px]}"
            f"{' (matte area %.0f %%)' % (100 * mc['area']) if mc else ' (no matte: seed)'}, from {d}")

    D, shift = float(p["depth"]), float(p["shift"])

    def MB_at(kb):
        # offset toward `from`: the camera travels with the subject (tracks it), the background pans the other way
        return Matrix.Translation(o + Vector((-ex * shift, -ey * shift, -D))) @ Matrix.Scale(kb, 4)

    kb = 1.0
    for _ in range(30):
        cam = Blend(ctx, MA, A, MB_at(kb), B, w0, f, w1, float(p["ease"]), float(p["ease"]))
        if all(covers(*cam(t), MB_at(kb)) for t in frange(w0 + 1, w1, 0.5)):
            break
        kb *= 1.05
    MB = MB_at(kb)
    cam = Blend(ctx, MA, A, MB, B, w0, f, w1, float(p["ease"]), float(p["ease"]))

    dA, dB = shot_depth(ctx, sa), shot_depth(ctx, sb)
    cardA = ctx.make_card(sa, f"layer_{T['id']}_A", MA, depth=dA, frames=(w0 - 1, t_land + 1), tile=3)
    mat = own_material(cardA, f"m_layer_{T['id']}_A")
    fe = float(p["feather"])
    nt = patch_alpha(mat, ctx, mat.name, coord, sgn, fe, hole=False)
    bgB = ctx.make_card(sb, f"layer_{T['id']}_B", MB, depth=dB, frames=vis, tile=3)
    subj = ctx.make_card(sb, f"layer_{T['id']}_Bsub", MB @ Matrix.Translation((0, 0, ZSEP / kb)), alpha="matte",
                         depth=dB, frames=(t_in - 1, t_land + 2), tile=3)
    own_material(subj, f"m_layer_{T['id']}_Bsub")
    clip_matte(subj)

    cf = MB @ px_local(*sc_px)  # the subject's final centroid (world)
    half = (mc["half"] if mc else [420.0, 420.0])
    ext = max(half[0], half[1]) / 1000.0 * kb
    ap = float(p["approach"])
    tilt = math.radians(float(p["tilt"]))
    Mfin = MB @ Matrix.Translation((0, 0, ZSEP / kb))

    def subj_M(t):
        loc, rot = cam(t)
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
        key_matrix(subj, subj_M(max(t, t_in)) if t < t_land else Mfin, t)

    # A wipes away behind the subject's trailing edge: the edge follows the subject's projection on A's plane and is
    # off A's visible range by the landing
    lo_v, hi_v = visible_range(cam, MA, f, coord, sgn)

    def proj(t):
        loc, rot = cam(t)
        M = subj_M(max(t, t_in))
        cw = M @ (Mfin.inverted_safe() @ cf)
        dvec = (cw - loc)
        Mi = MA.inverted_safe()
        p0, dl = Mi @ loc, Mi.to_3x3() @ dvec
        if abs(dl.z) < 1e-9:
            return None
        h = p0 + dl * (-p0.z / dl.z)
        px, py = cl.local_to_px(h.x, h.y)
        return sgn * (px if coord == "x" else py)

    keys = []
    t_gone = max(t_in + 2, t_land - 2)
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
