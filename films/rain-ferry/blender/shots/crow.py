"""2 crow: the crow on the ferry's signpost. Close on the weathered post, 「渡し」 painted down its face in the near
foreground, the crow on its cap against the misted river, the hut's red lantern and the jetty soft beyond; rain beads
on its feathers and drips off its beak. It watches the river, snaps its head round to us, cocks it, cries out (the caw,
at 2.15 s in the mix), crouches, and at the wingbeat (3.1 s) springs off the post, spraying the water off its wings,
and flies away over the jetty, the camera lifting after it and the focus going out to the crossing it flies toward.

The set is the film's world (rf/set_world.py: the crow perches on its signpost's `sign_top`); the crow is the core's
(blender/lib/bird.py); the rain and the light are the look schedule's.
"""
from __future__ import annotations

import math

SHOT = {"scene": "crow", "look": "150,175,196,214,226,236"}

LENS = 42.0
DIST = 2.35          # m from the crow's head to the lens
BEARING = 38.0       # degrees: where the camera stands round the post, from the face's normal toward the left
DROP = -0.12         # m: the lens below the crow's head (it looks a little up at it)
THIRD = 0.36         # m: the aim right of the crow, so it sits on the left third with room to look into
FSTOP = 2.8
# the crow's heading: across the frame, toward the river at the right (degrees from the camera's right toward away)
HEADING = 18.0
# its acting, in s into the shot (the mix: the caw at 8.15 s, its wings at 9.1 s; the shot starts at 6.0)
HEAD = [(0.0, (-0.5, -0.05, 0.0)), (1.0, (1.05, 0.05, 0.0)), (1.45, (0.95, 0.0, 0.32)), (1.8, (0.25, 0.08, 0.0))]
CAW = (1.98, 2.15, 2.5)          # it draws up, the beak opens wide (the caw), it closes
CROUCH = (2.62, 3.04)            # it sinks to spring
LAUNCH = 3.1                     # the wings open and it leaps
FLAP = 4.6                       # wingbeats a second
DRIP = (0.35, 1.25)              # a drop gathers at the beak's tip, then falls
FOCUS_PULL = (3.35, 3.95)        # the focus goes out from the crow to the crossing


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def build(ctx):
    import sys
    from pathlib import Path

    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import bird, rig, shapes, toon
    from rf import set_world

    scene = ctx.scene
    scene.render.use_motion_blur = False
    world = set_world.build(ctx)
    look = world["look"]
    toon.ink("ink-near", world["near"], radius=0.0028, crease=150)
    fps = ctx.fps

    def T(f):
        return ctx.time(f) - ctx.time(ctx.f0)

    # ---- the perch and the framing ----
    top = set_world.anchor(world, "sign_top")
    face = set_world.anchor(world, "sign_face")
    root = world["sign"]["root"]
    normal = root.matrix_world.to_3x3() @ Vector((1.0, 0.0, 0.0))
    normal.z = 0.0
    normal.normalize()
    b = math.radians(BEARING)
    toward_cam = Matrix.Rotation(b, 3, "Z") @ normal
    head0 = top + Vector((0.0, 0.0, 0.42))
    cam_at = head0 + toward_cam * DIST + Vector((0.0, 0.0, DROP))
    view = (head0 - cam_at).normalized()
    right = view.cross(Vector((0.0, 0.0, 1.0))).normalized()
    aim0 = head0 + right * THIRD + Vector((0.0, 0.0, -0.06))
    far_focus = set_world.anchor(world, "jetty_end") if "jetty_end" in world["anchors"] else head0 + view * 12.0

    cam = rig.engine_camera("camera", fstop=FSTOP, size=ctx.size)
    cam.data.lens = LENS
    cam.data.clip_end = 4000.0
    scene.camera = cam
    target = bpy.data.objects.new("aim", None)
    scene.collection.objects.link(target)
    tc = cam.constraints.new("TRACK_TO")
    tc.target, tc.track_axis, tc.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
    focus = bpy.data.objects.new("focus", None)
    scene.collection.objects.link(focus)
    cam.data.dof.focus_object = focus

    # ---- the crow ----
    crow = bird.build("crow", look=look, scale=1.0, beads=46, seed=4)
    ink_crow = toon.ink("ink-crow", crow.coll, radius=0.0011, crease=130)
    heading = math.atan2(-right.x, right.y) + math.radians(HEADING)
    fwd = Vector((-math.sin(heading), math.cos(heading), 0.0))

    # its flight: off the cap, up and out over the jetty toward the river
    n_fly = max(2, ctx.f1 - ctx.frame(ctx.time(ctx.f0) + LAUNCH) + 2)
    away = (far_focus - top)
    away.z = 0.0
    away.normalize()
    pts = [top, top + fwd * 0.35 + Vector((0, 0, 0.38)), top + fwd * 1.1 + away * 0.6 + Vector((0, 0, 0.9)),
           top + fwd * 1.6 + away * 3.2 + Vector((0, 0, 1.5)), top + fwd * 1.4 + away * 8.0 + Vector((0, 0, 2.3))]
    speeds = np.clip(np.linspace(0.25, 1.6, n_fly), 0, None)
    flight = bird.path([tuple(p) for p in pts], n_fly, speeds=speeds, bank=0.8)

    f_launch = ctx.frame(ctx.time(ctx.f0) + LAUNCH)
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = T(f)
        yaw, pitch, tilt = (bird.holds([(k, v[i]) for k, v in HEAD], t, snap=0.1) for i in range(3))
        pose = bird.replace(bird.PERCH, head_yaw=yaw, neck_yaw=yaw, head_pitch=bird.PERCH.head_pitch + pitch, head_tilt=tilt)
        # breathing and the rain: the body rising and falling, a shake of the tail now and then
        pose = bird.replace(pose, lift=pose.lift + 0.002 * math.sin(2 * math.pi * 0.9 * t),
                            tail_pitch=pose.tail_pitch + math.radians(4) * math.exp(-((t - 0.8) / 0.08) ** 2))
        # the caw: it draws itself up, then thrusts its head out with the beak wide, then closes
        a, c, e = CAW
        if a <= t < e + 0.25:
            up = ease((t - a) / (c - a))
            cry = ease((t - c + 0.05) / 0.08) * (1 - ease((t - e) / 0.18))
            pose = bird.lerp(pose, bird.replace(pose, body_pitch=pose.body_pitch + math.radians(8), neck_pitch=math.radians(-6),
                                                head_pitch=math.radians(10)), up * (1 - cry))
            pose = bird.lerp(pose, bird.replace(bird.CAW, head_yaw=pose.head_yaw * 0.4, neck_yaw=pose.neck_yaw * 0.4), cry)
        # the crouch, the spring
        if t >= CROUCH[0]:
            k = ease((t - CROUCH[0]) / (CROUCH[1] - CROUCH[0]))
            pose = bird.lerp(pose, bird.CROUCH, k)
        if f >= f_launch:
            i = min(f - f_launch, n_fly - 1)
            u = (f - f_launch) / fps
            opened = min(1.0, u / 0.1)
            flying = bird.flap(bird.beat(u, FLAP, phase=0.6), amp=min(1.0, 0.6 + u * 2.0))
            pose = bird.lerp(bird.replace(bird.CROUCH, open=opened), flying, min(1.0, u / 0.12))
            pose = bird.replace(pose, open=opened)
            p = flight[i]
            crow.place(f, p.location, p.heading, p.pitch * 0.6, p.bank)
        else:
            crow.place(f, tuple(top), heading)
        crow.key(f, pose)
    crow.hold()

    # ---- water: the drop on its beak, the spray off its wings ----
    bead_mat = toon.flat("crow-drip", (0.55, 0.6, 0.7), look=look, strength=1.1)
    drop = shapes.ellipsoid("drip", (0.0, 0.0, 0.0), (0.0035, 0.0035, 0.005), material=bead_mat, coll=crow.coll, n=8)
    drop.visible_shadow = False
    drop.lineart.usage = "EXCLUDE"
    head = crow.joints["head"]
    tip_local = Vector((0.0, 0.097, -0.02))
    bpy.context.view_layer.update()
    g0, g1 = DRIP
    fall_from = None
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = T(f)
        scene.frame_set(f)
        tip = head.matrix_world @ tip_local
        if t < g1:
            s = 0.3 + 0.7 * ease((t - g0) / (g1 - g0)) if t >= g0 else 0.3
            drop.location = tip + Vector((0, 0, -0.004 * s))
            drop.scale = (s, s, s * (1 + 0.4 * s))
            fall_from = (tip.copy(), t)
        else:
            p0, t0 = fall_from
            dt = t - t0
            drop.location = p0 + Vector((0.0, 0.0, -4.9 * dt * dt - 0.004))
            drop.scale = (0.8, 0.8, 1.8)
        drop.keyframe_insert("location", frame=f)
        drop.keyframe_insert("scale", frame=f)
    # the spray: drops flung off the wings and back as they open, falling away
    rng = np.random.default_rng(12)
    spray = []
    scene.frame_set(f_launch)
    origin = crow.joints["body"].matrix_world.translation.copy()
    for i in range(36):
        d = Vector((rng.normal(0, 1), rng.normal(0, 1), rng.uniform(-0.2, 1.0))).normalized()
        v = d * rng.uniform(0.8, 2.4) + fwd * -0.4
        p0 = origin + d * 0.12
        ob = shapes.ellipsoid(f"spray{i}", (0, 0, 0), (0.003, 0.003, 0.006), material=bead_mat, coll=crow.coll, n=6)
        ob.visible_shadow = False
        ob.lineart.usage = "EXCLUDE"
        for f in range(ctx.f0 - 1, ctx.f1 + 1):
            dt = (f - f_launch) / fps
            on = dt >= 0
            ob.hide_render = ob.hide_viewport = not on
            ob.keyframe_insert("hide_render", frame=f)
            ob.location = p0 + v * max(dt, 0) + Vector((0, 0, -4.9 * max(dt, 0) ** 2))
            ob.keyframe_insert("location", frame=f)
        spray.append(ob)
    # the post shivers as it springs off
    post_root = world["sign"]["root"]
    base_rot = post_root.rotation_euler.copy()
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        dt = (f - f_launch) / fps
        wob = math.radians(0.6) * math.exp(-dt * 6) * math.sin(dt * 2 * math.pi * 7) if dt >= 0 else 0.0
        post_root.rotation_euler = (base_rot.x + wob, base_rot.y, base_rot.z)
        post_root.keyframe_insert("rotation_euler", frame=f)

    # ---- the rain, and the camera ----
    s = ctx.look_at(ctx.f0)
    r = s.rain
    box_c = cam_at + view * 9.0
    toon.rain("rain", (box_c.x - 9, box_c.y - 9, top.z - 4), (box_c.x + 9, box_c.y + 9, top.z + 4), count=max(1, r.drops),
              speed=r.speed, wind=r.wind, length=r.length, width=r.width, color=r.color, alpha=r.alpha, seed=6,
              near=1.8, clear=0.6)
    lift_to = Vector(flight[-1].location)
    for f in range(ctx.f0 - 1, ctx.f1 + 1):
        t = T(f)
        # a held breath of a frame, alive: a slow drift in, then it lifts after the crow
        drift = Vector((0.0, 0.0, 0.006 * math.sin(2 * math.pi * 0.23 * t))) + view * 0.06 * ease(t / 3.0)
        follow = ease((t - LAUNCH - 0.05) / 0.9)
        cam.location = cam_at + drift + Vector((0, 0, 0.12 * follow))
        aim = aim0.lerp(aim0 + (lift_to - aim0) * 0.18 + Vector((0, 0, 0.35)), follow)
        target.location = aim
        k = ease((t - FOCUS_PULL[0]) / (FOCUS_PULL[1] - FOCUS_PULL[0]))
        focus.location = head0.lerp(far_focus, k)
        for ob, path in ((cam, "location"), (target, "location"), (focus, "location")):
            ob.keyframe_insert(path, frame=f)
