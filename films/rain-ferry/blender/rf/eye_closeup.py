"""The duel's two extreme close-ups (shots/eye-s.py, eye-t.py): one eye filling the letterboxed frame, the brow and
whatever crosses the forehead above it, the rest of the face falling out of focus, the river a blur of mist behind.
The camera breathes in on each thump of the heartbeat (the mix's, at +0.15 s); the eye holds, its glance shifting in
small snaps (saccades) or not at all; rain beads on the skin and runs down past the eye, a wet trail behind it.

`build(ctx, Closeup(...))` makes the shot from the duel's stage (rf/duel.py) with the one character in it. A drop's
path is drawn on the screen (frame fractions of the letterboxed band around the eye) and laid onto the face by casting
rays from the lens at the first frame, then carried by the head, so it stays on the skin as the head breathes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import duel
from . import duel_motion as dm

GATE_H = 20.25     # the engine's gate (mm), fit vertically
BAND = 0.744       # the 2.39 letterbox's share of the frame's height


@dataclass
class Drop:
    """A drop of rain running down the face: its path on the screen [(x, y)] (frame fractions, 0..1 across and up
    the visible band), when it starts to run and how long it takes (s), its size (m)."""
    path: list
    start: float
    length: float
    size: float = 0.0016
    stick: float = 0.35      # how much of its run it spends clinging, creeping, before it slides


@dataclass
class Closeup:
    who: str                 # "shinza" or "tsuru"
    bearing: float           # degrees from straight in front of the face round to the eye's side
    height: float            # m: the visible band's height at the eye
    lens: float = 100.0
    fstop: float = 2.8
    lift: float = 0.0        # m: the eye's place below the band's middle (room for the brow above)
    side: float = 0.0        # m: ... and right of it (room for the look)
    dz: float = 0.0          # m: the camera above (+) or below the eye
    beats: tuple = (0.15,)   # s: the heartbeat's thumps
    pulse: float = 0.045     # how far in each thump moves the camera (a share of its distance)
    creep: float = 0.06      # how far in the camera creeps over the shot (a share)
    face: object = None      # t -> {expression: weight} (with the heartbeat: face(t, beat))
    saccades: list = field(default_factory=list)   # [(s, (x, z) degrees)]: the eyes' glance from then on
    breath: tuple = (0.4, 1.0)                     # (rate, depth)
    drops: list = field(default_factory=list)
    key: tuple = (1.0, -0.3, 0.8)                  # the character's key, from (world)
    look: dict = field(default_factory=dict)       # the compositing setup on the schedule's base
    wind: tuple = (0.0, -1.0, 0.0)                 # the wind in the hair, the character's frame


def basis(front, bearing: float):
    """The direction from the face out to the lens (world), `bearing` degrees from `front` round toward -y (the
    cameras' side of the jetty), level."""
    f = np.asarray(front, float)
    f = f / np.linalg.norm(f)
    side = np.array([0.0, -1.0, 0.0])
    side = side - f * (side @ f)
    side /= np.linalg.norm(side)
    b = math.radians(bearing)
    return f * math.cos(b) + side * math.sin(b)


def build(ctx, c: Closeup) -> None:
    import bpy
    from mathutils import Vector

    from lib import satsuei

    st = duel.stage(ctx, who=(c.who,), ink=None, splashes=False)
    ch = st.ch(c.who)
    body = st.bodies[c.who]
    cam, aim = duel.camera(ctx, lens=c.lens, fstop=c.fstop, clip_start=0.005)
    # rain right up to the lens, the near drops thinning to fine soft streaks
    duel.rain_input(st.rain, "clear").default_value = 0.08
    duel.rain_input(st.rain, "near").default_value = 1.2

    root = st.actors[c.who]["root"]
    turn = root.rotation_euler[2]
    body_front = np.array([math.cos(turn), math.sin(turn), 0.0])
    # the face's own front (the head turns from the body): square to the line between the eyes, level
    eyes_at = {e: np.array(ch.point(e)) for e in ("leftEye", "rightEye")}
    across = eyes_at["leftEye"] - eyes_at["rightEye"]
    front = np.cross(across, (0.0, 0.0, 1.0))
    front[2] = 0.0
    front /= np.linalg.norm(front)
    if front @ body_front < 0:
        front = -front
    out = basis(front, c.bearing)
    # the eye toward the lens, its surface before its pivot
    mid = (eyes_at["leftEye"] + eyes_at["rightEye"]) / 2
    eye0 = max(eyes_at.values(), key=lambda p: float((p - mid) @ out)) + front * 0.012
    d0 = c.height / BAND * c.lens / GATE_H                  # the lens's distance for the band's height at the eye
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(-out, up)
    right /= np.linalg.norm(right)

    def setup(t: float):
        """(camera, aim, distance) at time t: the creep in and the heartbeat's push."""
        hb = dm.heartbeat(t, c.beats)
        d = d0 * (1.0 - c.creep * dm.ease(t / ((ctx.f1 - ctx.f0) / ctx.fps))) * (1.0 - c.pulse * hb)
        # the frame's aim moved off the eye so the eye sits `lift` below and `side` right of the band's middle
        target = eye0 - right * c.side * d / d0 + up * c.lift * d / d0
        at = eye0 + out * d + up * c.dz + duel.shake(t, 0.0008, seed=5)
        return at, target, d

    # the drops, laid on the face from the first frame's lens
    bpy.context.scene.frame_set(ctx.f0)
    at0, target0, _ = setup(0.0)
    fwd = Vector(target0) - Vector(at0)
    fwd.normalize()
    cr = fwd.cross(Vector((0.0, 0.0, 1.0))).normalized()
    cu = cr.cross(fwd)
    half_h = c.height / 2
    half_w = half_h * (ctx.size[0] / ctx.size[1]) / BAND
    head = ch.bone("head")
    head_m = ch.armature.matrix_world @ head.matrix
    drops = []
    rain = [ob for ob in (st.rain, st.rain_cast) if ob is not None]
    for ob in rain:                       # the rays are for the skin, not the drops falling past it
        ob.hide_viewport = True
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    for k, drop in enumerate(c.drops):
        pts = []
        for x, y in drop.path:
            p = Vector(target0) + cr * ((x - 0.5) * 2 * half_w) + cu * ((y - 0.5) * 2 * half_h)
            ray = (p - Vector(at0)).normalized()
            hit, loc, nrm, *_ = bpy.context.scene.ray_cast(dg, Vector(at0), ray, distance=5.0)
            if hit:
                pts.append(loc + nrm * drop.size * 0.4)
        if len(pts) < 2:
            print(f"eye_closeup: drop {k} missed the face; left out")
            continue
        drops.append((drop, _drop(f"drop{k}", drop, pts, head_m, ch, st.cast)))
    for ob in rain:
        ob.hide_viewport = False

    comp = satsuei.setup(ctx.scene, st.cast)
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = (f - ctx.f0) / ctx.fps
        at, target, d = setup(t)
        duel.key_camera(cam, aim, f, at, target, lens=c.lens, fstop=c.fstop, focus=float(np.linalg.norm(at - eye0)))
        hb = dm.heartbeat(t, c.beats)
        glance = (0.0, 0.0)
        for s, g in c.saccades:
            if t >= s:
                glance = g
        eyes = {e: (glance[0], 0.0, glance[1]) for e in ("leftEye", "rightEye")}
        body.key(f, duel.add(duel.breathing(t, *c.breath), eyes),
                 chains=body.sway(t, amount=4.0, cloth=1.0, toward=c.wind, seed=3))
        if c.face is not None:
            from lib import vrm

            vrm.express(ch, c.face(t, hb), frame=f)
        for drop, (ob, trail, n) in drops:
            u = _run(t, drop)
            ob.constraints["path"].offset_factor = u
            ob.constraints["path"].keyframe_insert("offset_factor", frame=f)
            trail.data.bevel_factor_end = max(0.0, u - 0.02)
            trail.data.keyframe_insert("bevel_factor_end", frame=f)
        duel.key_lines(st, f, at, c.lens, 0.0011)
        duel.key_light(st, f, {c.who: c.key})
        comp.key(f, duel.look(st, f, c.look))
    comp.hold()


def _run(t: float, drop: Drop) -> float:
    """How far along its path a drop is at t, 0..1: clinging and creeping for `stick` of its run, then sliding,
    quicker as it goes."""
    x = (t - drop.start) / drop.length
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    if x < drop.stick:
        return 0.08 * (x / drop.stick)
    return 0.08 + 0.92 * dm.ease_in((x - drop.stick) / (1 - drop.stick)) ** 0.6


def _drop(name: str, drop: Drop, pts, head_m, ch, coll):
    """A bead of water running along `pts` (world, on the skin) and the wet trail it leaves, carried by the head:
    (bead, trail curve, points)."""
    import bpy
    from mathutils import Matrix

    inv = head_m.inverted()
    curve = bpy.data.curves.new(f"{name}-path", "CURVE")
    curve.dimensions = "3D"
    sp = curve.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p, q in zip(sp.points, pts):
        lp = inv @ q
        p.co = (lp.x, lp.y, lp.z, 1.0)
    curve.bevel_depth = drop.size * 0.28
    curve.bevel_resolution = 2
    curve.use_fill_caps = True
    curve.bevel_factor_mapping_end = "SPLINE"
    trail = bpy.data.objects.new(f"{name}-trail", curve)
    coll.objects.link(trail)
    _parent(trail, ch, head_m)
    trail.data.materials.append(_water(f"{name}-wet", 0.28, 0.5))

    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=10, radius=drop.size)
    bead = bpy.context.active_object
    bead.name = name
    for c_ in bead.users_collection:
        c_.objects.unlink(bead)
    coll.objects.link(bead)
    bead.scale = (0.8, 0.8, 1.35)                 # pulled long by its fall
    bead.data.materials.append(_water(f"{name}-bead", 0.85, 1.4))
    bpy.ops.object.shade_smooth()
    path_ob = bpy.data.objects.new(f"{name}-follow", curve)   # the bead follows the trail's own curve
    coll.objects.link(path_ob)
    path_ob.hide_render = True
    _parent(path_ob, ch, head_m)
    con = bead.constraints.new("FOLLOW_PATH")
    con.name = "path"
    con.target = path_ob
    con.use_fixed_location = True
    bead.location = (0.0, 0.0, 0.0)
    bead.matrix_parent_inverse = Matrix.Identity(4)
    return bead, trail, len(pts)


def _parent(ob, ch, head_m) -> None:
    ob.parent = ch.armature
    ob.parent_type = "BONE"
    ob.parent_bone = ch.bone("head").name
    # a bone child sits at the bone's tail: undo it so the head's matrix maps local to world
    import bpy

    bpy.context.view_layer.update()
    ob.matrix_world = head_m


def _water(name: str, alpha: float, strength: float):
    """Water on skin, drawn as anime draws it: a pale cold glint at its edge where it turns from the lens, clear in
    the middle, `alpha` at most."""
    import bpy

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.82, 0.87, 0.95, 1)
    em.inputs["Strength"].default_value = strength
    rim = nt.nodes.new("ShaderNodeLayerWeight")
    rim.inputs["Blend"].default_value = 0.4
    mp = nt.nodes.new("ShaderNodeMapRange")
    mp.inputs["To Min"].default_value = 0.12 * alpha
    mp.inputs["To Max"].default_value = alpha
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(rim.outputs["Facing"], mp.inputs["Value"])
    nt.links.new(mp.outputs["Result"], mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"
    return mat
