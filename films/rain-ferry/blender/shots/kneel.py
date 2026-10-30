"""Shot 23, the kneel: Shinza on his knees in the rain, staring at his broken sword. "...Then what is it?" (L13)

From in front of him and a little above, the rain falling past the lens onto him, the jetty running
away behind him to the hut and its red lantern, soft. He starts as the lesson leaves him (shot 21's kneel, rf/clash.py's
FALL: the stub's broken end on the planks); then he lifts it in both hands and stares at where it broke. His grip
tightens before he speaks; he asks it of the blade, low; after it his eyes lift a little, toward where she went. The
camera creeps in from a medium shot toward his face.

RF_S7_CAST=none builds the shot without its cast.
"""
from __future__ import annotations

import math
import os

SHOT = {"scene": "kneel"}

LINE = (92.0, 93.73)        # L13 (film s)
BEARING = -24.0             # degrees from his front toward his right: where the camera looks at him from
DIST = (2.45, 1.85)         # m from his face, from and to
HEIGHT = (0.32, 0.2)        # m over his eyes
LENS, FSTOP = 50.0, 2.0
LIFT = (90.95, 91.85)       # film s: the stub lifted from the planks into both hands
STUB = ((-0.06, -0.24, 0.7), (0.38, -0.5, 0.78))   # (pommel, hilt direction) held up before him (his frame)
GRIP = (91.55, 91.95)       # film s: his grip tightening
EYES_UP = (93.95, 94.55, 7.0)   # after the line: his head lifts this many degrees (and his eyes with it)
# the stub: the cast's broken nodachi (rf/vroid_shinza.py's BROKEN) still reads whole at a glance, so this shot cuts
# it shorter, its end a ragged break across the whole width, the fracture catching the light, a glint on it as he
# grips. Metres from the guard to the break along the back and the edge; the teeth across it (fraction across the
# blade from the back, metres beyond the break's line)
SNAP = (0.2, 0.17)
TEETH = [(0.0, 0.0), (0.14, 0.045), (0.27, 0.006), (0.4, 0.062), (0.55, 0.012), (0.68, 0.04), (0.82, -0.006),
         (1.0, 0.0)]
GLINT = (91.75, 92.05, 0.045)  # film s: the glint on the break flaring and fading; its size (m)


def build(ctx):
    import sys
    from pathlib import Path

    import numpy as np

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import cinema, toon3d
    from rf import ending as E

    st = E.stage(ctx)
    actors = None
    eyes = np.array([E.SHINZA_AT[0], E.SHINZA_AT[1], 0.95])

    if os.environ.get("RF_S7_CAST", "vroid") != "none":
        from rf import clash

        actors = E.cast(st, {"shinza": dict(kasa="back", sword="broken", headband=True)})
        sh = actors["shinza"]
        ch = sh["vrm"]
        E.stick_half(sh)
        snapped = _snap(sh)
        E.cut_headband(sh)
        fall = E.shot_module("fall")
        for f in range(ctx.f0 - 1, ctx.f1 + 2, 2):
            t = ctx.time(f)
            breath = math.sin(2 * math.pi * 0.5 * t)
            lift = E.ease((t - LIFT[0]) / (LIFT[1] - LIFT[0]))
            grip = E.ease((t - GRIP[0]) / (GRIP[1] - GRIP[0]))
            up = E.ease((t - EYES_UP[0]) / (EYES_UP[1] - EYES_UP[0])) * EYES_UP[2]
            shake = 0.004 * grip * math.sin(2 * math.pi * 7.0 * t)        # the blade trembling in his hands
            turns = {k: v for k, v in fall.KNEEL.items()}
            sx, sy, sz = turns["spine"]
            turns["spine"] = (sx + 2.0 * breath - 4.0 * lift, sy, sz)
            cx, cy, cz = turns["chest"]
            turns["chest"] = (cx - 2.0 * grip, cy, cz)                   # his shoulders set as he grips
            hx, hy, hz = turns["head"]
            turns["head"] = (hx - 12.0 * lift - up, hy, hz * (1 - lift) + 6.0 * lift)
            turns["leftEye"] = turns["rightEye"] = (12.0 * lift - 1.5 * up, 0.0, 6.0 * lift)
            if LIFT[0] < t < LIFT[1]:
                continue                     # the lift: tweened between the fall's pose and the held stub
            pommel, hilt = STUB
            stub = (tuple(np.add(pommel, (0.0, 0.0, shake))), hilt) if lift >= 1.0 else None
            p, fingers = E.fallen(sh, turns=turns, stub=stub)
            p.hips = (p.hips[0], p.hips[1], p.hips[2] + 0.004 * breath)
            clash.apply(sh, p, fingers=fingers)
            clash.key(sh, f)
        _face(ctx, ch, LINE)
        eyes = np.array(ch.face())
        # his key from beyond him on his left, high: the camera sees his face in the 1st shade, his hair and shoulders
        # edged, the blade's flat lit
        toon3d.aim(sh["key"], (-0.5, 0.9, 1.0))

    b = math.radians(math.degrees(E.SHINZA_FACING) + BEARING)
    toward = np.array([math.cos(b), math.sin(b), 0.0])

    def at(k):
        d = DIST[0] + (DIST[1] - DIST[0]) * k
        return (eyes + toward * d + np.array([0.0, 0.0, HEIGHT[0] + (HEIGHT[1] - HEIGHT[0]) * k]),
                eyes + np.array([0.0, 0.0, -0.22 + 0.1 * k]))

    (c0, a0), (c1, a1) = at(0.0), at(1.0)
    focus = E.head_of(actors["shinza"]) if actors else tuple(eyes)
    rig = cinema.film(ctx, [cinema.Setup("kneel", 0.0, cinema.drift(cinema.line(c0, c1, a0, a1), 0.015), lens=LENS,
                                         fstop=FSTOP, focus=focus, shake=cinema.Shake(breath=0.06, seed=23))])
    E.weather(ctx, st, rig)
    if actors:
        _glint(ctx, st, snapped)

    def look(f, s):
        L = s.light
        return dict(rims=[((-0.7, 1.0), L.rim, 0.35, 0.003, 0.9), ((-1.0, 0.2), L.accent, 0.12, 0.003, 0.9)],
                    para_from=(0.5, 0.9), para_to=(0.5, 0.0))

    E.finish(ctx, st, look, actors, lambda f: LENS)


def _face(ctx, ch, line) -> None:
    """His face keyed every frame: a grieving set, the mouth flapping through the line."""
    from lib import vrm
    from rf import ending as E

    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = ctx.time(f)
        vrm.express(ch, {"sad": 0.45, "aa": 0.7 * E.mouth(t, [line])}, frame=f)


def _snap(sh):
    """His stub cut down to SNAP and its end made a ragged break: the cast's blade mesh rebuilt in its own space (the
    guard, the blade's line, its width and thickness read off the cast's rings), the break's faces a bright fractured
    steel. Returns (the blade object, the break's middle in its space)."""
    import bmesh
    import bpy
    import numpy as np

    blade = next(ob for ob in sh["parts"]["sword"] if ob.name.endswith("-blade"))
    me = blade.data
    co = np.array([v.co[:] for v in me.vertices])
    rings = co[: len(co) // 4 * 4].reshape(-1, 4, 3)
    centers = rings.mean(axis=1)
    guard = centers[0]
    d = centers[-1] - centers[0]
    d /= np.linalg.norm(d)
    offs = rings[0] - guard
    across = offs[np.argmax(np.linalg.norm(offs, axis=1))]
    half_w = float(np.linalg.norm(across)) * 0.95
    w = across / np.linalg.norm(across)
    t = np.cross(d, w)
    t /= np.linalg.norm(t)
    half_t = float(max(abs(np.dot(o, t)) for o in offs)) or 0.0016

    # the outline in the blade's plane: up the back, across the break's teeth, down the edge
    outline = [(0.0, half_w)]
    for k, beyond in TEETH:
        along = SNAP[0] + (SNAP[1] - SNAP[0]) * k + beyond
        outline.append((along, half_w - 2.0 * half_w * k))
    outline.append((0.0, -half_w))
    bm = bmesh.new()
    top = [bm.verts.new(tuple(guard + d * a + w * c + t * half_t)) for a, c in outline]
    bot = [bm.verts.new(tuple(guard + d * a + w * c - t * half_t)) for a, c in outline]
    n = len(outline)
    bm.faces.new(top)
    bm.faces.new(list(reversed(bot)))
    breaks = []
    for i in range(n):
        j = (i + 1) % n
        f = bm.faces.new((top[j], top[i], bot[i], bot[j]))
        if 1 <= i < n - 2:
            breaks.append(f)
    steel = me.materials[0] if len(me.materials) else None
    for f in breaks:
        f.material_index = 1
    new = bpy.data.meshes.new(f"{me.name}-snapped")
    bm.to_mesh(new)
    bm.free()
    new.materials.append(steel)
    new.materials.append(_fracture())
    blade.data = new
    for md in list(blade.modifiers):
        if md.type == "SUBSURF":
            blade.modifiers.remove(md)
    mid = guard + d * (0.5 * (SNAP[0] + SNAP[1]) + 0.012)
    return blade, tuple(mid)


def _fracture():
    """Freshly broken steel: pale, grainy-bright, lit by nothing but itself (it must catch the eye in the rain)."""
    import bpy

    mat = bpy.data.materials.new("nodachi-fracture")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.92, 0.95, 1.0, 1.0)
    em.inputs["Strength"].default_value = 2.2
    nt.links.new(em.outputs[0], out.inputs[0])
    return mat


def _glint(ctx, st, snapped):
    """A four-pointed glint on the break, facing the lens, flaring as his grip tightens and fading: the eye sent to
    where the blade ends."""
    import bpy

    blade, mid = snapped
    r = GLINT[2]
    verts, faces = [(0.0, 0.0, 0.0)], []
    for i in range(8):
        a = math.pi / 4 * i
        rr = r if i % 2 == 0 else r * 0.12
        verts.append((rr * math.cos(a), rr * math.sin(a), 0.0))
    for i in range(8):
        faces.append((0, 1 + i, 1 + (i + 1) % 8))
    me = bpy.data.meshes.new("break-glint")
    me.from_pydata(verts, [], faces)
    me.update()
    mat = bpy.data.materials.new("break-glint")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (1.0, 0.98, 0.92, 1.0)
    nt.links.new(em.outputs[0], out.inputs[0])
    me.materials.append(mat)
    ob = bpy.data.objects.new("break-glint", me)
    st.cast.objects.link(ob)
    ob.parent = blade
    ob.location = mid
    c = ob.constraints.new("TRACK_TO")
    c.target = ctx.scene.camera
    c.track_axis = "TRACK_Z"
    c.up_axis = "UP_Y"
    strength = em.inputs["Strength"]
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = ctx.time(f)
        if t < GLINT[0]:
            k = 0.0
        elif t < GLINT[1]:
            k = (t - GLINT[0]) / (GLINT[1] - GLINT[0])
        else:
            k = max(0.0, 1.0 - (t - GLINT[1]) / 0.5)
        ob.scale = (0.2 + 0.8 * k,) * 3
        ob.keyframe_insert("scale", frame=f)
        strength.default_value = 6.0 * k
        strength.keyframe_insert("default_value", frame=f)
        ob.hide_render = k <= 0.0
        ob.keyframe_insert("hide_render", frame=f)
