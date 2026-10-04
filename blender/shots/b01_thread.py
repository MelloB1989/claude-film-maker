"""B01, the film's cold open (scene `thread`, spec §4 01): a macro of one bone thread, and the snap.

One bone 3-ply thread (THREAD_LOOK's rope, built fibre by fibre: lib/thread.py FibreRope) spans the frame on a shallow
diagonal, near and soft at the left, far and soft at the right, sharp where it will break. 85 mm at f/1.8 on a 1 cm
cord 29 cm away (the macro's depth of field), a dark world, a warm-neutral key raking in from the left that sculpts
every ply turn, a soft top light, and a hard rim from behind that lights the fuzz.

  - Black, then the light: on the beat at 0.6 s the rim and key come up while the focus racks in. Taut by 1.0 s.
  - The pulse: every beat plucks it like a string, a lub-dub heartbeat that rings out and lifts the fuzz.
  - "forgets": the fray. At the middle the fuzz lifts and the plies loosen, untwist and part; each beat after it
    tugs the fray further open, and just before the break the plies neck down.
  - "zero": the snap, in a speed ramp. Time eases from 1x at "to" to 0.25x at "zero" and holds to the scene's end
    (the cut, on the beat). Each ply parts at its own place and each fibre near it, so a broken end is a brush of the
    thread's own fibres. The halves recoil, curl and unravel, a ripple runs out along each, and a few hundred freed
    fibres tumble out of the break through the key light.

The camera pushes in slowly all shot (a small push on the downbeat after "forgets"); the thread's time runs through
the ramp, the camera and the light with it. Everything is a pure function of the film frame (+ subframe) and the
seeded rope: a frame_change_pre handler poses it, so Cycles motion-blurs every fibre at every step. The break ends are
tracked (`end_l`, `end_r`) for the engine's cracked "zero.". So are twelve freed fibres (`fibre_0` ... `fibre_11`, empties
on their midpoints), the brightest the cut can catch: scene `ex` seeds its first float numerals on them (the match cut).

  Blender -b -P blender/render.py -- --shot b01_thread --mode look            (the key moments, 960x540)
  Blender -b -P blender/render.py -- --shot b01_thread --mode preview         (the whole window, proxies + track)
"""
from __future__ import annotations

import math

import numpy as np

FIBRES = 12  # freed fibres tracked for the match cut into `ex` (fibre_0 ... fibre_11)
SHOT = {"scene": "thread", "frames": "scene", "track": ["end_l", "end_r"] + [f"fibre_{k}" for k in range(FIBRES)],
        "look": "30,60,168"}
# where the tracked fibres must be on the shot's last frame: inside title-safe (the inner 90% of the frame), a little
# apart, and as near the focal plane as can be (sharp, so bright)
SAFE = (0.05, 0.95)
FIBRE_GAP = 0.035  # of the frame's width, between any two tracked fibres

R = 0.012  # thread radius (m): at 85 mm f/1.8 and 63 R the fibres on the focal plane stay sharp (+-1 R in 4.6 px)
LENGTH = 80 * R  # material length; the anchors are far outside the frame
LENS, SENSOR, FSTOP = 85.0, 36.0, 1.8
DIST = 63 * R  # camera to the break point, at rest
BETA, GAMMA = math.radians(22), math.radians(-9)  # recession (right end away) and tilt on screen (descending)
AT = (0.58, 0.52)  # where the break point sits in frame (fractions from the top left)
SEED = 7
LAY_DEG = 24.0  # longer than THREAD_LOOK's 32: a finer, more elegant cord at macro

# the pulse
PLUCK = 0.2 * R  # lub amplitude at the middle; the dub is DUB of it
DUB, DUB_AFTER = 0.55, 0.16
PLUCK_HZ, PLUCK_DECAY = 5.5, 0.14
PLUCK_WIDTH = 9 * R
# the fray
FRAY_SPAN = 4.5  # R
# the snap (thread time after it, s)
RECOIL, RECOIL_T = 4.0 * R, 0.03
CURL, CURL_T = math.radians(36), 0.05
UNRAVEL, SPLAY, BRUSH = 0.25, 0.45, 0.18
DEBRIS = 170


# ------------------------------------------------------------------------------------------------------ time

def ramp_area(u: float) -> float:
    """The area under ease.inOutCubic from 0 to u (motion.ts rampArea)."""
    return u**4 if u <= 0.5 else u - 0.5 + (1 - u) ** 4


def speed_ramp(t: float, keys: list[tuple[float, float]]) -> float:
    """motion.ts speedRamp: the time played at local time t, the integral of the speed curve (keys [t, speed], eased
    inOutCubic between them; two keys at one time change speed instantly)."""
    if not keys:
        return t
    pts = sorted(keys)

    def area(x: float) -> float:
        t0, s0 = pts[0]
        if x <= t0:
            return s0 * (x - t0)
        a = 0.0
        for i in range(1, len(pts)):
            p, sp = pts[i - 1]
            k, sk = pts[i]
            if x >= k:
                a += (k - p) * (sp + sk) / 2
                continue
            u = (x - p) / (k - p)
            return a + (k - p) * (sp * u + (sk - sp) * ramp_area(u))
        tn, sn = pts[-1]
        return a + sn * (x - tn)

    return area(t) - area(0.0)


def smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def out_cubic(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


class Clock:
    """The shot's times, all from the data: words (vo.json), beats (audio.json) and the scene's end. `tau(t)` is the
    thread's own time (the speed ramp); every event below is in it."""

    def __init__(self, timing):
        self.forgets = timing.word("L01", 2).start
        self.forgets_end = timing.word("L01", 2).end
        self.to = timing.word("L02", 3).start
        self.zero = timing.word("L02", 4).start
        scene = next(s for s in timing.vo["scenes"] if s["id"] == "thread")
        self.end = scene["end"]
        # 1x until "to", easing to 0.25x at the snap ("zero"), held to the scene's end: the cut, on the beat, where it
        # goes back to 1x (motion language: the snap at 0.25x, back to real time on a beat)
        self.ramp = [(self.to, 1.0), (self.zero, 0.25), (self.end, 0.25), (self.end, 1.0)]
        self.snap = self.tau(self.zero)
        self.beats = [self.tau(b) for b in timing.audio["beats"] if b < self.zero]
        self.downbeats = [self.tau(b) for b in timing.audio["downbeats"] if b < self.zero]
        # the light comes up on the first beat after the opening's half second of black
        self.light_on = next(b for b in timing.audio["beats"] if b > 0.4)
        self.fray_beats = [b for b in self.beats if b > self.forgets_end]
        self.push = next((b for b in self.downbeats if b > self.forgets), None)

    def tau(self, t: float) -> float:
        return speed_ramp(t, self.ramp)


# ------------------------------------------------------------------------------------------------------ the story

def pluck(clock: Clock, tau: float) -> tuple[float, float]:
    """The heartbeat: the displacement at the middle (m) and a 0..1 flutter, the sum of every lub and dub so far."""
    y, fl = 0.0, 0.0
    for b in clock.beats:
        for at, amp in ((b, 1.0), (b + DUB_AFTER, DUB)):
            x = tau - at
            if x < 0 or x > 1.2:
                continue
            env = (1 - math.exp(-x / 0.012)) * math.exp(-x / PLUCK_DECAY)
            y += amp * PLUCK * env * math.sin(2 * math.pi * PLUCK_HZ * x)
            fl += amp * env
    if tau > clock.snap:
        y *= math.exp(-(tau - clock.snap) / 0.02)
    return y, min(1.0, fl)


def fray_amount(clock: Clock, tau: float) -> float:
    """0 before "forgets"; up to 0.5 as she says it; a step on every beat after it; 1 at the snap."""
    if tau <= clock.forgets:
        return 0.0
    f = 0.5 * out_cubic((tau - clock.forgets) / (clock.forgets_end - clock.forgets))
    n = len(clock.fray_beats)
    step = (0.92 - 0.5) / max(1, n)
    for b in clock.fray_beats:
        f += step * out_cubic((tau - b) / 0.22)
    f += 0.08 * smooth((tau - (clock.snap - 0.5)) / 0.5)
    return min(1.0, f)


def neck_amount(clock: Clock, tau: float) -> float:
    """The plies thin at the break in the last moments before it (accelerating)."""
    x = (tau - (clock.snap - 0.4)) / 0.4
    return 0.0 if x <= 0 else min(1.0, x) ** 2


# ------------------------------------------------------------------------------------------------------ build

def build(ctx):
    import bpy
    from mathutils import Matrix, Vector

    from lib import lights, thread

    scene = ctx.scene
    coll = scene.collection
    clock = Clock(ctx.timing)

    # the thread's line: through the break point (the origin) at material s = LENGTH / 2
    u = np.array([math.cos(BETA) * math.cos(GAMMA), math.sin(BETA), math.cos(BETA) * math.sin(GAMMA)])
    up = np.array([0.0, 0.0, 1.0])
    n0 = up - u * (up @ u)
    n0 /= np.linalg.norm(n0)
    pluck_dir = np.array([0.0, 0.35, 1.0]) - u * (np.array([0.0, 0.35, 1.0]) @ u)
    pluck_dir /= np.linalg.norm(pluck_dir)
    # both broken ends drop away below the break (the space above it is the word's), in the focal plane so they stay
    # sharp: the thread falls, lifeless
    curl_l = -n0.copy()
    curl_l -= u * (curl_l @ u)
    curl_l /= np.linalg.norm(curl_l)
    curl_r = -n0
    curl_r -= u * (curl_r @ u)
    curl_r /= np.linalg.norm(curl_r)

    rope = thread.fibre_rope(R, LENGTH, seed=SEED, fibres=72, fibre_radius=0.022, fuzz_per_R=48, samples_per_R=10,
                             fray_span=FRAY_SPAN, fray_per_R=34, lay_deg=LAY_DEG)
    # under tension a fray opens the lay a little and bristles; it does not balloon into a cage (the engine's 1.4, 0.12
    # and 1.35 are for an untensioned fray seen wide)
    rope.fray_separation, rope.fray_swell, rope.fray_untwist, rope.fray_loose = 1.0, 0.04, 0.7, 0.03
    sc_ = rope.break_at
    halves = {side: thread.half_samples(rope, side) for side in ("left", "right")}
    debris = Debris(rope, u, np.random.default_rng(SEED + 101))

    fibre = thread.fibre_material("b01_fibre")
    core = thread.fibre_material("b01_core", core=True)
    mr = thread.MacroRope(rope, name="thread", fibre_mat=fibre, core_mat=core, collection=coll)
    deb_ob = debris.build(coll, fibre)

    # camera: 85 mm, the break point at AT in frame
    cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    cam.data.lens = LENS
    cam.data.sensor_fit = "HORIZONTAL"
    cam.data.sensor_width = SENSOR
    cam.data.clip_start = 0.01
    cam.data.dof.use_dof = True
    cam.data.dof.aperture_fstop = FSTOP
    cam.data.dof.aperture_blades = 0
    coll.objects.link(cam)
    scene.camera = cam

    fwd = np.array([0.0, 1.0, -0.12])
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, up)
    right /= np.linalg.norm(right)
    qup = np.cross(right, fwd)
    rot = Matrix(((right[0], qup[0], -fwd[0]), (right[1], qup[1], -fwd[1]), (right[2], qup[2], -fwd[2])))

    def place_camera(tau: float) -> float:
        """The slow push (and a small one on the downbeat after "forgets"), a slight truck along the thread. Returns
        the focus distance."""
        k = smooth((tau - clock.light_on) / (clock.tau(clock.end) - clock.light_on))
        d = DIST * (1.08 - 0.10 * k)
        if clock.push is not None:
            d *= 1 - 0.025 * out_cubic((tau - clock.push) / 0.35)
        truck = (0.3 - 0.8 * k) * R
        wf = SENSOR / LENS * d
        hf = wf * 9 / 16
        C = -d * fwd - (AT[0] - 0.5) * wf * right - (0.5 - AT[1]) * hf * qup + truck * right
        cam.matrix_world = Matrix.Translation(Vector(C)) @ rot.to_4x4()
        return d

    # light: a warm-neutral key raking in from the left, a soft top light, a hard rim from behind
    P = Vector((0.0, 0.0, 0.0))
    ls = R / 0.005  # the rig was set up round a 5 mm thread: distances scale with R, power with its square
    # the key: a soft spot 30 degrees off the thread's axis, from the upper left and in front (warm-neutral 5600 K,
    # below the 4000 K that would open the bloom's chroma gate on bone); a pool that falls off towards the frame's ends
    kd = -0.75 * u + 0.5 * up + 0.35 * np.array([0.0, -1.0, 0.0])
    kd /= np.linalg.norm(kd)
    key = _light("key", "SPOT", 45.0 * ls * ls / 5.76, P + Vector(kd * 0.5 * ls), P, spot=math.radians(50),
                 soft=0.08 * ls, temperature=5600)
    key.data.spot_blend = 0.85
    top = _light("top", "AREA", 0.6 * ls * ls, P + Vector((0.0, 0.15, 0.5)) * ls, P, size=0.3 * ls, temperature=6200)
    rim = _light("rim", "SPOT", 200.0 * ls * ls, P + Vector((0.10, 0.55, 0.25)) * ls, P, spot=math.radians(24),
                 soft=0.003 * ls, temperature=6500)
    power = {ob.name: ob.data.energy for ob in (key, top, rim)}
    for ob in (key, top, rim):
        coll.objects.link(ob)
    lights.world_color("ink")

    ends = {}
    for name in ("end_l", "end_r"):
        e = bpy.data.objects.new(name, None)
        e.empty_display_size = R
        coll.objects.link(e)
        ends[name] = e
    picked = pick_fibres(scene, cam, clock, debris, place_camera, f1=ctx.f1)
    fibres = []
    for k in range(FIBRES):
        e = bpy.data.objects.new(f"fibre_{k}", None)
        e.empty_display_size = 0.2 * R
        coll.objects.link(e)
        fibres.append(e)

    def pose(sc, *_):
        t = (sc.frame_current + sc.frame_subframe) / 30.0
        tau = clock.tau(t)
        after = tau - clock.snap
        y_pl, flutter = pluck(clock, tau)
        F = fray_amount(clock, tau)
        neck = neck_amount(clock, tau)

        poses = {}
        for side, s in halves.items():
            m = len(s)
            X = (s - sc_)[:, None] * u[None, :]
            X = X + (y_pl * np.exp(-((s - sc_) / PLUCK_WIDTH) ** 2))[:, None] * pluck_dir[None, :]
            y = (s - sc_) / (FRAY_SPAN * R)
            fray = F * thread.bump(y)
            unravel = np.zeros(m)
            splay = np.zeros((3, m))
            brush = np.zeros((3, m))
            taper = np.ones((3, m))
            neck_f = np.array([neck * thread.bump((s - c) / (2.5 * R)) for c in rope.ply_break])
            if after > 0:
                sign = -1.0 if side == "left" else 1.0
                q = sign * (s - sc_)  # distance from the break, into this half
                curl_dir = curl_l if side == "left" else curl_r
                th = CURL * (1 - math.exp(-after / CURL_T)) * (1 + 0.08 * math.sin(after * 60))
                lc = (2.0 + 3.0 * (1 - math.exp(-after / 0.06))) * R
                alpha = np.minimum(th * np.exp(-np.maximum(q, -3 * R) / lc), 1.6 * th)
                tang = np.cos(alpha)[:, None] * u[None, :] + np.sin(alpha)[:, None] * curl_dir[None, :] * -sign
                steps = (tang[1:] + tang[:-1]) / 2 * np.diff(s)[:, None]
                if side == "left":
                    X = X[0] + np.concatenate([[np.zeros(3)], np.cumsum(steps, axis=0)])
                else:
                    back = np.cumsum(steps[::-1], axis=0)[::-1]
                    X = X[-1] - np.concatenate([back, [np.zeros(3)]])
                # the recoil: the end springs back towards its anchor, the release reaching far along the thread
                rec = RECOIL * (1 - math.exp(-after / RECOIL_T)) * np.exp(-np.maximum(q, 0) / (25 * R))
                X = X + sign * rec[:, None] * u[None, :]
                # a ripple runs out along the thread from the break
                front = 180 * R * after
                wave = 0.3 * R * math.exp(-after / 0.12) * np.exp(-((q - front) / (4 * R)) ** 2)
                X = X + wave[:, None] * curl_dir[None, :]
                grow = 1 - math.exp(-after / 0.04)
                unravel = sign * UNRAVEL * grow * np.exp(-np.maximum(q, 0) / (5 * R))  # the free end untwists
                for k, c in enumerate(rope.ply_break):
                    qk = sign * (s - c)  # into the half from this ply's own parting
                    splay[k] = SPLAY * grow * (1 + 0.25 * (k - 1)) * np.exp(-np.maximum(qk, 0) / (3 * R))
                    brush[k] = BRUSH * R * grow * np.clip(-qk / R + 0.6, 0, 4) ** 1.3
                    # the core (the ply's inner fibres) parts a little inside the sheath: the brush is all fibre
                    tip = np.clip((qk - 1.1 * R * grow) / (1.2 * R), 0, 1)
                    taper[k] = 1 - min(1.0, after / 0.012) * (1 - np.sqrt(tip))
                    neck_f[k] *= math.exp(-after / 0.02)
                fray = fray * (1 + 0.3 * grow)
            _, N, _ = thread.rmf(X, n0, reverse=side == "right")
            poses[side] = thread.RopePose(s, X, N, fray, unravel, splay, neck_f, brush, taper,
                                          lift=0.35 * flutter * (0.3 + F), broken=min(1.0, max(0.0, after) / 0.01))
        mr.update(poses, fray_centre=sc_, fray_amount=F)
        debris.update(deb_ob, after, poses)
        mids = debris.centres(after)
        for e, i in zip(fibres, picked):
            e.location = Vector(mids[i])

        for name, side in (("end_l", "left"), ("end_r", "right")):
            p = poses[side]
            ends[name].location = Vector(thread.interp_rows([sc_], p.s, p.X)[0])

        dist = place_camera(tau)
        # the reveal: the rim comes on on the beat, the key follows, the focus racks in
        on = tau - clock.light_on
        # at the snap the key dips and the rim flares: the freed fibres glitter against the dark
        hit = smooth(after / 0.03) if after > 0 else 0.0
        # first the rim alone draws the thread as a contour of backlit fuzz, then the key brings up its form
        rim.data.energy = power["rim"] * smooth(on / 0.08) * (1 + 0.7 * hit)
        key.data.energy = power["key"] * smooth((on - 0.1) / 0.3) * (1 - 0.62 * hit)
        top.data.energy = power["top"] * smooth((on - 0.1) / 0.3)
        cam.data.dof.focus_distance = dist - 7 * R * (1 - out_cubic(on / 0.42))

    bpy.app.handlers.frame_change_pre.append(pose)
    pose(scene)


def pick_fibres(scene, cam, clock, debris, place_camera, f1: int) -> list[int]:
    """The freed fibres to track (debris indices): on the shot's last frame (film frame f1 - 1, held over the cut), each
    in front of the camera and inside title-safe, at least FIBRE_GAP apart, the ones nearest the focal plane first (the
    sharpest, so the brightest points). Deterministic: a function of the seeded debris and the clock."""
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector

    tau = clock.tau((f1 - 1) / 30.0)
    focus = place_camera(tau)
    cam_inv = cam.matrix_world.inverted()
    mids = debris.centres(tau - clock.snap)
    cands = []
    for i, c in enumerate(mids):
        v = world_to_camera_view(scene, cam, Vector(c))
        if not (v.z > 0 and SAFE[0] <= v.x <= SAFE[1] and SAFE[0] <= v.y <= SAFE[1]):
            continue
        depth = -(cam_inv @ Vector(c)).z
        cands.append((abs(depth - focus), i, v.x, v.y * 9 / 16))
    cands.sort()
    out: list[tuple[int, float, float]] = []
    for _, i, x, y in cands:
        if all(math.hypot(x - a, y - b) >= FIBRE_GAP for _, a, b in out):
            out.append((i, x, y))
        if len(out) == FIBRES:
            break
    if len(out) < FIBRES:
        raise RuntimeError(f"b01_thread: only {len(out)} freed fibres are in title-safe on the last frame (want {FIBRES})")
    return [i for i, _, _ in out]


class Debris:
    """The thread's own fibres, freed at the break: short kinked fibres that fly out of the parting plies, slow in the
    air and tumble. Hidden (zero radius) until the snap."""

    PTS = 7

    def __init__(self, rope, u, rng):
        n = DEBRIS
        self.rope, self.u, self.n = rope, u, n
        self.s = rope.break_at + rng.normal(0, 1.1, n) * R
        self.ang = rng.uniform(0, 2 * np.pi, n)
        self.r = rope.R * np.sqrt(rng.uniform(0.05, 0.95, n))
        L = np.clip(rng.lognormal(math.log(1.1 * R), 0.45, n), 0.5 * R, 2.8 * R)
        k = np.linspace(-0.5, 0.5, self.PTS)
        kink = rng.uniform(0.01, 0.05, n)[:, None] * L[:, None]
        shape = np.zeros((n, self.PTS, 3))
        shape[..., 0] = k[None] * L[:, None]
        shape[..., 1] = kink * np.sin(2 * np.pi * rng.uniform(0.5, 1.6, n)[:, None] * k[None] + rng.uniform(0, 6.3, n)[:, None])
        shape[..., 2] = kink * np.sin(2 * np.pi * rng.uniform(0.5, 1.6, n)[:, None] * k[None] + rng.uniform(0, 6.3, n)[:, None])
        self.shape = shape
        ax = rng.normal(size=(n, 3))
        self.axis = ax / np.linalg.norm(ax, axis=1, keepdims=True)
        self.spin = rng.uniform(3, 16, n) * np.where(rng.random(n) < 0.5, -1, 1)
        o = rng.normal(size=(n, 3))
        self.orient = o / np.linalg.norm(o, axis=1, keepdims=True)
        speed = rng.lognormal(math.log(40 * R), 0.7, n)
        radial = rng.normal(size=(n, 3))
        radial -= u[None, :] * (radial @ u)[:, None]
        radial /= np.linalg.norm(radial, axis=1, keepdims=True)
        along = rng.normal(0, 1.1, n)  # flung along the recoil as much as out of the thread
        side = np.sign(self.s - rope.break_at + 1e-12)
        v = 0.7 * radial + (along + 0.9 * side)[:, None] * u[None, :]
        self.v0 = v / np.linalg.norm(v, axis=1, keepdims=True) * speed[:, None]
        self.drift = rng.normal(0, 2.5 * R, (n, 3)) + np.array([0, 0, 1.5 * R])
        self.drag = rng.uniform(0.03, 0.08, n)
        self.radius = rope.R * 0.006 * rng.uniform(0.7, 1.3, n)
        self.tone = rng.uniform(0.9, 1.06, n)
        e1 = np.cross(u, [0.0, 0.0, 1.0])
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(u, e1)
        # where each sat in the thread
        self.p0 = (self.s - rope.break_at)[:, None] * u[None, :] + self.r[:, None] * (
            np.cos(self.ang)[:, None] * e1[None, :] + np.sin(self.ang)[:, None] * e2[None, :])

    def build(self, coll, material):
        from lib import thread

        return thread._new_curves("debris", np.full(self.n, self.PTS), self.tone, material, coll, None)

    def centres(self, after: float) -> np.ndarray:
        """Each fibre's midpoint (n, 3): where it sat in the thread until the snap, then where it has flown."""
        if after <= 0:
            return self.p0.copy()
        return self.p0 + self.v0 * (self.drag * (1 - np.exp(-after / self.drag)))[:, None] + self.drift * after

    def update(self, ob, after: float, poses) -> None:
        from lib import thread

        n = self.n
        if after <= 0:
            pts = np.zeros((n, self.PTS, 3))
            rad = np.zeros((n, self.PTS))
        else:
            c = self.centres(after)
            pts = _rotate(_orient(self.shape, self.orient), self.axis, self.spin * after) + c[:, None, :]
            grow = min(1.0, after / 0.006)
            rad = np.repeat(self.radius[:, None] * grow, self.PTS, axis=1) * np.linspace(1, 0.5, self.PTS)[None]
        thread._set_curves(ob, pts.reshape(-1, 3), rad.reshape(-1))


def _orient(shape, d):
    """Turn each shape (n, p, 3), laid along x, to lie along d (n, 3)."""
    x = np.array([1.0, 0.0, 0.0])
    ax = np.cross(x, d)
    s = np.linalg.norm(ax, axis=1)
    c = d @ x
    ang = np.arctan2(s, c)
    ax = ax / np.maximum(s, 1e-12)[:, None]
    return _rotate(shape, ax, ang)


def _rotate(pts, axis, ang):
    """Rodrigues: rotate points (n, p, 3) about axis (n, 3) by ang (n,)."""
    c, s = np.cos(ang)[:, None, None], np.sin(ang)[:, None, None]
    k = axis[:, None, :]
    return pts * c + np.cross(k, pts) * s + k * np.sum(k * pts, axis=2, keepdims=True) * (1 - c)


def _light(name, kind, power, pos, target, *, size=None, spot=None, soft=None, temperature=None):
    import bpy

    data = bpy.data.lights.new(name, kind)
    data.energy = power
    if temperature:
        data.use_temperature = True
        data.temperature = temperature
    if size is not None:
        data.shape = "DISK"
        data.size = size
    if spot is not None:
        data.spot_size = spot
        data.spot_blend = 0.6
    if soft is not None:
        data.shadow_soft_size = soft
    ob = bpy.data.objects.new(name, data)
    ob.location = pos
    ob.rotation_euler = (target - pos).to_track_quat("-Z", "Y").to_euler()
    return ob
