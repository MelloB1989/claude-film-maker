"""Timeless v3 stage: the whole edit as ONE Blender scene (every shot a card, one continuous camera, real Cycles motion
blur) built from edl.json, rendered as the plate / text / light passes. EDIT.md is the spec.

  blender -b --factory-startup -P blender/amv3/stage.py -- --edl films/timeless/amv3/edl.json --data $AMV3_DATA \
      --frames 0-260 --res 0.25 --samples 8 --out out/stage/t1 [--passes plate,text,light] [--save x.blend] \
      [--only C01,C02] [--device CPU|OPTIX|CUDA] [--gate-only] [--strict] [--identity S03@100]

Build order: shots -> home cards -> hold intents -> every cut's bounds() -> every cut's build() (camera keys into the key
store) -> holds (C1 Hermite between the window bounds) -> hits (punch, shake) -> CAM fcurves + shutter keys ->
build_over() overlays -> text3d.build() -> camera dump + gate -> render passes.
Transition modules: core flow types live in flow.py (open, zt, whip, cube, flip, slam); every other type is
blender/amv3/xfx/<type>.py (bounds(T, ctx), build(T, ctx), optional build_over(T, ctx)); a missing or failing module
falls back to a zt and is logged.
"""
import importlib
import json
import math
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy  # noqa: E402
from mathutils import Matrix, Quaternion, Vector  # noqa: E402

import camlib as cl  # noqa: E402
import cards  # noqa: E402

EPS = 0.02  # teleport keys sit at t_h -/+ EPS; the widest shutter next to a teleport is 2 * (0.5 - 0.025) = 0.95
SET_SPACING = 100.0
SHUTTER_HOLD = 0.75
SHUTTER_PEAK = 1.0

PALETTES = {  # linear RGB: key light, rim, light leak, fog (the void's tint; never black)
    "tobey": dict(key=(1.0, 0.62, 0.22), rim=(0.25, 0.65, 0.62), leak=(1.0, 0.55, 0.12), fog=(0.030, 0.026, 0.018)),
    "andrew": dict(key=(0.25, 0.75, 1.0), rim=(1.0, 0.55, 0.18), leak=(0.20, 0.70, 1.0), fog=(0.012, 0.024, 0.040)),
    "tom": dict(key=(1.0, 0.25, 0.10), rim=(0.35, 0.55, 0.85), leak=(1.0, 0.32, 0.08), fog=(0.036, 0.014, 0.012)),
    "outro": dict(key=(1.0, 1.0, 1.0), rim=(0.5, 0.5, 0.6), leak=(1.0, 0.4, 0.1), fog=(0.02, 0.02, 0.02)),
}
DRIFT_RATE = {"tobey": 0.016, "andrew": 0.022, "tom": 0.028}  # hold push/pull in d ln s per frame (REFS: 1.5-3.5 %/f)
DRIFT_MIN = 0.010  # never slower than ~1 %/f
DRIFT_MAX_ZOOM = math.log(1.9)  # a long hold's drift is capped at x1.9 overall (plate resolution)


def parse_args(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="stage.py")
    ap.add_argument("--edl", default=os.path.join(HERE, "..", "..", "films", "timeless", "amv3", "edl.json"))
    ap.add_argument("--data", default=os.environ.get("AMV3_DATA", "/home/nikhil/code/film-making/work/timeless_v3"))
    ap.add_argument("--frames", default="0-834")
    ap.add_argument("--res", type=float, default=0.5)
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--out", default="out/stage/test")
    ap.add_argument("--passes", default="plate,text,light")
    ap.add_argument("--save", default=None)
    ap.add_argument("--only", default=None, help="comma list of cut ids: build only those windows (and their shots)")
    ap.add_argument("--device", default="CPU")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--gate-only", action="store_true", help="build + gate, no render")
    ap.add_argument("--strict", action="store_true", help="exit non-zero when the gate fails")
    ap.add_argument("--identity", default=None, help="SHOT@F: render that plate frame at s=1, centred, no roll (colour test)")
    ap.add_argument("--no-gate", action="store_true")
    ap.add_argument("--filter", default="GAUSSIAN:0.3", help="plate-pass pixel filter TYPE:width")
    a = ap.parse_args(argv)
    f0, _, f1 = a.frames.partition("-")
    a.f0, a.f1 = int(f0), int(f1 or f0)
    return a


# ======================================================================================================================
class StageContext:
    """Everything a transition / title module gets (the stage contract in the v3 brief)."""

    def __init__(self, E, args):
        self.E = E
        self.args = args
        self.fps = E["fps"]
        self.data = args.data
        self.res = args.res
        self.out = os.path.abspath(args.out)
        self.EPS = EPS
        self._shots = {s["id"]: s for s in E["shots"]}
        for i, p in enumerate(E.get("triptych", {}).get("panels", [])):
            self._shots[p["id"]] = dict(p, a=p["f"], b=E["triptych"]["f1"], focus=None,
                                        move=dict(drift="in", roll=0.0, pan=[0, 0], depth=0.0), fx=[], panel=True)
        self._order = list(self._shots)
        self._homes = {sid: Vector((i * SET_SPACING, 0.0, 0.0)) for i, sid in enumerate(self._order)}
        self._cards = {}  # shot -> home card
        self.all_cards = []  # every card object (home + copies), for the gate
        self._nsets = 0
        self._envs = {}
        self.keys = {}  # t -> (loc Vector, rot Quaternion, lens or None)
        self.dof = {}  # t -> (focus distance m, f-stop): rack pulls; elsewhere the camera is a pinhole (FSTOP_SHARP)
        self.teleports = []
        self.bounds = {}  # cut id -> {"A": State, "B": State}
        self.windows = []  # (w0, w1, cut) of every built window
        self._seq = {}
        self._mats = {}
        self.log_lines = []
        self.colls = {}
        self.cam = None
        self._cam_cache = None

    # ---- info ---------------------------------------------------------------------------------------------------------
    def log(self, msg):
        line = f"[stage] {msg}"
        print(line, flush=True)
        self.log_lines.append(line)

    def shot(self, sid):
        return self._shots[sid]

    def act_at(self, f):
        for a in self.E["acts"]:
            if a["f0"] <= f < a["f1"]:
                return a["id"]
        return self.E["acts"][-1]["id"]

    def act_of(self, sid):
        s = self._shots[sid]
        if s.get("act"):
            return s["act"]
        return self.act_at(s["a"])

    def palette(self, act_id):
        return dict(PALETTES.get(act_id, PALETTES["tom"]))

    def track(self, sid, f):
        """Tracked focus [x, y] (plate pixels) of shot sid at frame f from $AMV3_DATA/tracks/<sid>.json (nearest tracked
        frame, linear between tracked frames), or None when the shot has no track."""
        if not hasattr(self, "_tracks"):
            self._tracks = {}
        if sid not in self._tracks:
            path = os.path.join(self.data, "tracks", f"{sid}.json")
            tr = None
            if os.path.exists(path):
                try:
                    with open(path) as fh:
                        fr = json.load(fh).get("frames", {})
                    tr = sorted((int(k), v) for k, v in fr.items() if v)
                except Exception as e:  # noqa: BLE001
                    self.log(f"WARN track {sid}: {e}")
            self._tracks[sid] = tr
        tr = self._tracks[sid]
        if not tr:
            return None
        if f <= tr[0][0]:
            return list(tr[0][1])
        if f >= tr[-1][0]:
            return list(tr[-1][1])
        import bisect
        i = bisect.bisect_right([k for k, _ in tr], f)
        (fa, va), (fb, vb) = tr[i - 1], tr[i]
        u = (f - fa) / float(fb - fa)
        return [va[0] + (vb[0] - va[0]) * u, va[1] + (vb[1] - va[1]) * u]

    def coll(self, name):
        return self.colls[name]

    def home(self, sid):
        return self._homes[sid].copy()

    def card(self, sid):
        if sid not in self._cards:
            s = self._shots[sid]
            depth = float(s.get("move", {}).get("depth", 0.0) or 0.0)
            self._cards[sid] = self.make_card(sid, f"card_{sid}", Matrix.Translation(self._homes[sid]), depth=depth,
                                              home=True)
        return self._cards[sid]

    def new_set(self, name):
        self._nsets += 1
        o = Vector((self._nsets * SET_SPACING, 2 * SET_SPACING, 0.0))
        self.log(f"set {name} at {tuple(round(x) for x in o)}")
        return o

    # ---- cards --------------------------------------------------------------------------------------------------------
    def _sequence(self, kind, sid, ext):
        key = (kind, sid)
        if key not in self._seq:
            first = cards.link_sequence(os.path.join(self.data, kind, sid), os.path.join(self.out, "_seq", kind, sid), ext)
            if first is None:
                self._seq[key] = None
            else:
                self._seq[key] = cards.load_sequence(first, "sRGB" if kind == "plates" else "Non-Color")
        return self._seq[key]

    def plate_range(self, sid):
        s = self._shots[sid]
        h = self.E.get("handle", 16)
        if s.get("panel"):
            return s["a"], 835
        return max(0, s["a"] - h), min(self.E["dur"], s["b"] + h)

    def make_card(self, sid, name, matrix=None, alpha="none", depth=0.0, hole=None, collection="plate",
                  frames=None, backface=None, sweep=False, home=False):
        """A new card playing shot sid's plate in comp time. matrix: world matrix (default: the shot's home origin).
        alpha 'matte' = subject matte as alpha; depth > 0 = displaced from the depth map (2.5D); hole = dict(center=[x, y],
        radius=[(frame, px), ...], feather=px). frames = (f0, f1) render visibility (default: the plate range)."""
        plate = self._sequence("plates", sid, "jpg")
        if plate is None:
            raise RuntimeError(f"no plates for {sid} in {self.data}/plates")
        matte = self._sequence("mattes", sid, "png") if alpha == "matte" else None
        if alpha == "matte" and matte is None:
            self.log(f"WARN {name}: no mattes for {sid}, card stays opaque")
        dimg = self._sequence("depth", sid, "png") if depth > 0 else None
        if depth > 0 and dimg is None:
            self.log(f"WARN {name}: no depth for {sid}, card stays flat")
        nx, ny = (128, 72) if dimg is not None else (1, 1)
        me = cards.card_mesh(name, nx, ny)
        key = (sid, alpha, bool(hole), tuple(backface) if backface else None, sweep)
        if hole or sweep or key not in self._mats:
            mat = cards.card_material(f"m_{name}", plate, matte, alpha, hole, backface, sweep)
            if not (hole or sweep):
                self._mats[key] = mat
        else:
            mat = self._mats[key]
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        ob.matrix_world = matrix if matrix is not None else Matrix.Translation(self._homes[sid])
        self.colls[collection].objects.link(ob)
        cards.no_shadow(ob)
        if dimg is not None:
            cards.interior_group(ob, nx, ny)
            tex = bpy.data.textures.new(f"d_{name}", type="IMAGE")
            tex.image = dimg
            cards.setup_user(tex.image_user)
            tex.extension = "EXTEND"
            mod = ob.modifiers.new("depth", "DISPLACE")
            mod.texture = tex
            mod.texture_coords = "UV"
            mod.direction = "NORMAL"
            mod.mid_level = 0.5
            mod.strength = depth * 0.6
            mod.vertex_group = "interior"
            sm = ob.modifiers.new("smooth", "SMOOTH")
            sm.factor = 0.6
            sm.iterations = 4
            sm.vertex_group = "interior"
        if hole:
            nt = mat.node_tree
            v = nt.nodes["HoleR"].outputs[0]
            for f, r in hole.get("radius", []):
                v.default_value = r
                v.keyframe_insert("default_value", frame=f)
        f0, f1 = frames if frames else self.plate_range(sid)
        self.show(ob, f0, f1)
        ob["amv3_shot"] = sid
        ob["amv3_card"] = True
        self.all_cards.append(ob)
        return ob

    def matte_card(self, sid, matrix=None, frames=None):
        """Holdout card for the text and light passes: holdout where the subject matte is white. Sits exactly in the card
        plane (never displaced)."""
        matte = self._sequence("mattes", sid, "png")
        name = f"matte_{sid}_{len(self.colls['holdout'].objects)}"
        me = cards.card_mesh(name)
        if matte is None:
            self.log(f"WARN matte_card {sid}: no mattes yet, holdout card is empty")
            me.materials.append(cards.emission_material(name, (0, 0, 0), 0.0, 0.0))
        else:
            me.materials.append(cards.holdout_material(name, matte))
        ob = bpy.data.objects.new(name, me)
        ob.matrix_world = matrix if matrix is not None else Matrix.Translation(self._homes[sid])
        self.colls["holdout"].objects.link(ob)
        cards.no_shadow(ob)
        f0, f1 = frames if frames else self.plate_range(sid)
        self.show(ob, f0, f1)
        return ob

    def show(self, ob, f0, f1):
        """Render visibility: visible on [f0, f1), hidden outside (keyed, constant)."""
        f0, f1 = int(math.floor(f0)), int(math.ceil(f1))
        ob.hide_render = f0 > 0
        ob.keyframe_insert("hide_render", frame=0)
        if f0 > 0:
            ob.hide_render = False
            ob.keyframe_insert("hide_render", frame=f0)
        if f1 < self.E["dur"]:
            ob.hide_render = True
            ob.keyframe_insert("hide_render", frame=f1)
        _constant(ob)

    def env(self, origin, act_id, frames=None):
        """The act's void environment around a set (fog sphere, bokeh, strands, haze). One instance per origin."""
        k = (round(origin.x), round(origin.y), round(origin.z))
        if k in self._envs:
            return self._envs[k]
        act_id = act_id if act_id in PALETTES else "tom"
        src = self.colls.get(f"ENV_{act_id}")
        if src is None:
            src = cards.build_env_collection(act_id, self.palette(act_id), self.colls["_lib"])
            self.colls[f"ENV_{act_id}"] = src
        inst = bpy.data.objects.new(f"env_{act_id}_{len(self._envs)}", None)
        inst.instance_type = "COLLECTION"
        inst.instance_collection = src
        inst.location = origin
        self.colls["env"].objects.link(inst)
        f0, f1 = frames if frames else (0, 819)
        self.show(inst, f0, min(f1, 819))
        self._envs[k] = inst
        return inst

    # ---- camera -------------------------------------------------------------------------------------------------------
    def pose(self, card, state):
        """World (location Vector, rotation Quaternion) of the camera that shows `state` on `card`."""
        (x, y, z), roll = cl.local_pose(state)
        M = card.matrix_world if hasattr(card, "matrix_world") else card
        return pose_from(M, x, y, z, roll)

    def pose_matrix(self, card, state):
        loc, rot = self.pose(card, state)
        return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()

    def intent(self, sid, f):
        return self._intent[sid](f)

    def hold_state(self, sid, f):
        h = self._holds.get(sid)
        if h and h[0] <= f <= h[1] and h[1] > h[0]:
            return cl.hermite_state(h[2], h[3], h[0], h[1], f)
        return self.intent(sid, f)

    def key_cam(self, f, loc, rot, lens=None):
        """Key the camera at (float) frame f. Keys are LINEAR; the core adds hits on top."""
        if not isinstance(rot, Quaternion):
            rot = rot.to_quaternion() if hasattr(rot, "to_quaternion") else Quaternion(rot)
        self.keys[round(float(f), 4)] = (Vector(loc), rot.normalized(), lens)
        self._cam_cache = None

    def key_dof(self, f, focus_m, fstop):
        """Key the camera's depth of field (rack defocus). Outside keyed spans the f-stop is FSTOP_SHARP (no defocus)."""
        self.dof[round(float(f), 4)] = (float(focus_m), float(fstop))

    def key_path(self, fn, t0, t1, step=0.25):
        """Key fn(t) -> (loc, rot[, lens]) on [t0, t1) every `step` frames, plus the sides of every teleport the span owns:
        a teleport at t_h inside the span gets keys at t_h - EPS (pre side) and t_h + EPS (post side); a teleport at
        t0 - 0.5 gives this span its post side, one at t1 - 0.5 its pre side (the neighbour span keys the other side).
        fn must return the right side itself (t < t_h: before the jump)."""
        ts = set()
        n = int(round((t1 - t0) / step))
        for i in range(n):
            ts.add(round(t0 + i * step, 4))
        for th in self.teleports:
            if th < t0 - 0.5 - 1e-6 or th > t1 - 0.5 + 1e-6:
                continue
            for t in list(ts):
                if abs(t - th) < EPS * 1.5 or (abs(th - (t1 - 0.5)) < 1e-6 and t > th):
                    ts.discard(t)
            if th > t0 - 0.5 + 1e-6:
                ts.add(round(th - EPS, 4))
            if th < t1 - 0.5 - 1e-6:
                ts.add(round(th + EPS, 4))
        for t in sorted(ts):
            r = fn(t)
            self.key_cam(t, r[0], r[1], r[2] if len(r) > 2 else None)

    def entry_state(self, T):
        """The State a window should start from at w0: the previous window's exit when the two windows touch (no hold
        between them), else shot A's hold intent at w0."""
        for c in self.E["cuts"]:
            if c["w1"] == T["w0"] and c["id"] != T["id"] and c["id"] in self.bounds and "B" in self.bounds[c["id"]]:
                return self.bounds[c["id"]]["B"]
        return self.intent(T["a"]["id"], T["w0"])

    def settle_entry(self, T, A):
        """Re-place an entry State's scale so the hold before the window is the gentlest curve between the previous
        window's exit rate and this entry's rate (constant acceleration in ln s: the hold covers (ds0 + ds1) / 2 per
        frame). Call it after you have chosen A's rates. Keeps the frame on the card."""
        for c in self.E["cuts"]:
            if c.get("b") == T["a"]["id"] and c["id"] in self.bounds and "B" in self.bounds[c["id"]]:
                P, L = self.bounds[c["id"]]["B"], T["w0"] - c["w1"]
                if L <= 0:
                    return A
                s = P.s * math.exp((P.ds + A.ds) / 2.0 * L)
                return A.with_(s=max(s, cl.min_scale(A.cx, A.cy, A.r, 0.01) * 1.005))
        return A

    def exit_state(self, T):
        """The State a window should end in at w1: shot B's hold intent at w1."""
        return self.intent(T["b"]["id"], T["w1"])

    def teleport(self, f_half):
        f_half = round(float(f_half) * 2) / 2.0
        if f_half not in self.teleports:
            self.teleports.append(f_half)
            self.teleports.sort()

    def cam_matrix(self, f):
        """World matrix of CAM at float frame f from the keys (after hits). At a teleport, f < t_h is the pre side."""
        loc, rot, _ = self._sample(f)
        return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()

    def cam_lens(self, f):
        return self._sample(f)[2]

    def _sample(self, f):
        if self._cam_cache is None:
            self._cam_cache = sorted(self.keys)
        ts = self._cam_cache
        import bisect
        i = bisect.bisect_right(ts, f)
        if i <= 0:
            k = self.keys[ts[0]]
            return k[0], k[1], k[2] or cl.LENS_MM
        if i >= len(ts):
            k = self.keys[ts[-1]]
            return k[0], k[1], k[2] or cl.LENS_MM
        ta, tb = ts[i - 1], ts[i]
        a, b = self.keys[ta], self.keys[tb]
        u = (f - ta) / (tb - ta)
        qb = b[1] if a[1].dot(b[1]) >= 0 else -b[1]
        q = Quaternion([a[1][j] * (1 - u) + qb[j] * u for j in range(4)]).normalized()
        la, lb = a[2] or cl.LENS_MM, b[2] or cl.LENS_MM
        return a[0].lerp(b[0], u), q, la + (lb - la) * u


def pose_from(M, x, y, z, roll):
    """Camera in card space (x, y, z) with roll about the card normal -> world (loc, quat). Uniform card scale is kept."""
    loc = M @ Vector((x, y, z))
    rot = M.to_quaternion() @ Quaternion((0, 0, 1), roll)
    return loc, rot


def _constant(ob):
    ad = ob.animation_data
    if not ad or not ad.action:
        return
    for fc in _fcurves(ad.action):
        if fc.data_path == "hide_render":
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


def _fcurves(action):
    """F-curves of an action (Blender 5 layered actions, or the legacy list)."""
    out = []
    if hasattr(action, "layers") and len(action.layers):
        for layer in action.layers:
            for strip in layer.strips:
                for bag in getattr(strip, "channelbags", []):
                    out.extend(bag.fcurves)
    elif hasattr(action, "fcurves"):
        out.extend(action.fcurves)
    return out


# ======================================================================================================================
# scene setup
def set_filter(ctx, spec):
    """Pixel filter TYPE:width. The plate pass uses a narrow Gaussian (a hold frame reproduces the plate: 99.4 % of
    pixels within +-2 levels at GAUSSIAN:0.3, vs 95.5 % for Blackman-Harris 1.5); text / light use TEXT_FILTER (smooth
    antialiased edges on 3D letters and FX)."""
    cy = bpy.context.scene.cycles
    ftype, _, fw = spec.partition(":")
    for attr, val in (("pixel_filter_type", ftype), ("filter_width", float(fw or 1.0))):
        try:
            setattr(cy, attr, val)
        except (AttributeError, TypeError) as e:
            ctx.log(f"WARN cycles.{attr}: {e}")


TEXT_FILTER = "BLACKMAN_HARRIS:1.5"


def setup_scene(ctx, args):
    sc = bpy.context.scene
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    sc.render.engine = "CYCLES"
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    sc.render.resolution_percentage = max(1, int(round(args.res * 100)))
    sc.render.fps = ctx.fps
    sc.render.film_transparent = True
    sc.render.use_persistent_data = True
    sc.render.dither_intensity = 0.0
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.image_settings.color_depth = "8"
    sc.render.image_settings.compression = 15
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    sc.view_settings.gamma = 1.0
    try:
        sc.display_settings.display_device = "sRGB"
    except TypeError:
        pass
    cy = sc.cycles
    cy.samples = args.samples
    cy.use_adaptive_sampling = False
    cy.use_denoising = False
    try:
        cy.use_preview_denoising = False
    except AttributeError:
        pass
    set_filter(ctx, args.filter)
    cy.max_bounces = 4
    cy.diffuse_bounces = 2
    cy.glossy_bounces = 2
    cy.transmission_bounces = 4
    cy.transparent_max_bounces = 16
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 1.0
    cy.sample_clamp_indirect = 10.0
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = SHUTTER_HOLD
    for owner in (cy, sc.render):
        if hasattr(owner, "motion_blur_position"):
            owner.motion_blur_position = "CENTER"
    dev = args.device.upper()
    if dev in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = dev
        prefs.get_devices()
        n = 0
        for d in prefs.devices:
            d.use = d.type == dev
            n += d.use
        cy.device = "GPU"
        ctx.log(f"device {dev}: {n} device(s)")
    else:
        cy.device = "CPU"
    if args.threads:
        sc.render.threads_mode = "FIXED"
        sc.render.threads = args.threads
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"

    world = bpy.data.worlds.new("void")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0, 0, 0, 1)
        bg.inputs[1].default_value = 0.0
    sc.world = world

    root = sc.collection
    for name in ("plate", "text", "light", "holdout", "_lib"):
        c = bpy.data.collections.new(name)
        root.children.link(c)
        ctx.colls[name] = c
    env = bpy.data.collections.new("env")
    ctx.colls["plate"].children.link(env)
    ctx.colls["env"] = env

    cam_data = bpy.data.cameras.new("CAM")
    cam_data.lens = cl.LENS_MM
    cam_data.sensor_fit = "HORIZONTAL"
    cam_data.sensor_width = cl.SENSOR_MM
    cam_data.clip_start = 0.01
    cam_data.clip_end = 90.0  # sets are 100 m apart: a neighbour set is never visible
    cam = bpy.data.objects.new("CAM", cam_data)
    cam.rotation_mode = "QUATERNION"
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = cl.FSTOP_SHARP
    cam_data.dof.focus_distance = 2.0
    root.objects.link(cam)
    sc.camera = cam
    ctx.cam = cam
    for attr in ("motion_steps",):
        for owner in (getattr(cam, "cycles", None), cam):
            if owner is not None and hasattr(owner, attr):
                try:
                    setattr(owner, attr, 4)
                    ctx.log(f"camera {type(owner).__name__}.{attr} = 4")
                except Exception as e:  # noqa: BLE001
                    ctx.log(f"WARN camera {attr}: {e}")

    # view layers = passes
    vl0 = sc.view_layers[0]
    vl0.name = "plate"
    layers = {"plate": vl0}
    for n in ("text", "light"):
        layers[n] = sc.view_layers.new(n)
    for n, vl in layers.items():
        lc = {c.name: c for c in vl.layer_collection.children}
        lc["_lib"].exclude = True
        if n == "plate":
            lc["text"].exclude = True
            lc["holdout"].exclude = True
        elif n == "text":
            lc["plate"].exclude = True
            lc["light"].exclude = True
        else:
            lc["plate"].exclude = True
            lc["text"].exclude = True
        vl.use_pass_combined = True
    ctx.layers = layers


# ======================================================================================================================
# hold intents: each shot's own slow drift (the shape the holds follow)
def make_intent(ctx, sid):
    s = ctx.shot(sid)
    mv = s.get("move", {})
    act = ctx.act_of(sid)
    a, b = s["a"], s["b"]
    L = max(1.0, float(b - a))
    roll = float(mv.get("roll", 0.0) or 0.0)
    pan = mv.get("pan", [0, 0]) or [0, 0]
    if not roll and not any(pan):
        # never a dead axis: a faint roll and pan drift (alternating per shot) keeps the corners moving while the zoom
        # turns round between a landing and the next entry
        k = ctx._order.index(sid)
        roll = 1.2 * (1 if k % 2 else -1)
        pan = [28.0 * (1 if (k // 2) % 2 else -1), 0.0]
    rate = max(DRIFT_MIN, min(DRIFT_RATE.get(act, 0.02), DRIFT_MAX_ZOOM / L))
    drift = mv.get("drift", "auto")
    ds = rate if drift in ("in", "auto") else -rate
    fx, fy = (s.get("focus") or [960, 540])
    c0x = 960 + 0.25 * (fx - 960)
    c0y = 540 + 0.25 * (fy - 540)
    dr = roll / L
    # base scale: the frame stays on the card over the whole drift (rolled and panned)
    s_need = 1.0
    for u in (0.0, 1.0):
        r = -roll / 2 + roll * u
        cx = c0x - pan[0] * (u - 0.5) / 1.1
        cy = c0y - pan[1] * (u - 0.5) / 1.1
        s_need = max(s_need, cl.min_scale(cx, cy, r, 0.015))
    s_lo = max(1.06, s_need)
    # ln s runs over [ln s_lo, ln s_lo + |ds| L]
    Ls0 = math.log(s_lo) if ds > 0 else math.log(s_lo) + abs(ds) * L
    mid = (a + b) / 2.0

    def fn(f):
        u = (f - a) / L
        st = cl.State(math.exp(Ls0 + ds * (f - a)), c0x - pan[0] * (u - 0.5) / 1.1, c0y - pan[1] * (u - 0.5) / 1.1,
                      roll * (u - 0.5), ds, -pan[0] / 1.1 / L, -pan[1] / 1.1 / L, dr)
        st.cx, st.cy = cl.clamp_center(st.s, st.cx, st.cy, st.r, 0.01)
        return st
    fn.mid = mid
    return fn


# ======================================================================================================================
def load_module(ctx, typ):
    if typ in FLOW_TYPES:
        return flow_mod
    path = os.path.join(HERE, "xfx", f"{typ}.py")
    if not os.path.exists(path):
        return None
    try:
        return importlib.import_module(f"xfx.{typ}")
    except Exception:  # noqa: BLE001
        ctx.log(f"WARN module xfx/{typ}.py failed to import:\n{traceback.format_exc()}")
        return None


def cut_T(ctx, c):
    T = dict(c)
    T["a"] = ctx.shot(c["a"]) if c.get("a") else None
    T["b"] = ctx.shot(c["b"]) if c.get("b") else None
    return T


def resolve_cut(ctx, c):
    """-> (module, T, effective type) with the zt fallback for missing modules."""
    T = cut_T(ctx, c)
    mod = load_module(ctx, c["type"])
    typ = c["type"]
    if mod is None or not hasattr(mod, "bounds") or not hasattr(mod, "build"):
        if T["a"] is not None and T["b"] is not None:
            ctx.log(f"{c['id']} {typ}: no module, falling back to zt")
            T["p"] = dict(peak=3.0, land=2.4, roll=0.0)
            T["fallback_from"] = typ
            T["type"] = typ = "zt"
            mod = flow_mod
        else:
            ctx.log(f"{c['id']} {typ}: no module; the neighbouring hold runs through the window")
            return None, T, typ
    return mod, T, typ


def build(ctx, args):
    E = ctx.E
    cuts = E["cuts"]
    only = set(args.only.split(",")) if args.only else None
    sel = [c for c in cuts if only is None or c["id"] in only]
    shots_needed = set()
    for c in sel:
        for k in ("a", "b"):
            if c.get(k):
                shots_needed.add(c[k])
    if only is None:
        shots_needed |= {s["id"] for s in E["shots"]}
    for sid in ctx._order:
        if sid in shots_needed:
            ctx.card(sid)
    ctx._intent = {sid: make_intent(ctx, sid) for sid in ctx._order}

    # 1. bounds
    resolved = {}
    for c in sel:
        mod, T, typ = resolve_cut(ctx, c)
        if mod is None:
            continue
        try:
            b = mod.bounds(T, ctx)
        except Exception:  # noqa: BLE001
            ctx.log(f"WARN {c['id']} {typ}.bounds failed, zt fallback:\n{traceback.format_exc()}")
            if T["a"] is None or T["b"] is None:
                continue
            T["p"] = dict(peak=3.0, land=2.4, roll=0.0)
            T["fallback_from"] = typ
            T["type"] = typ = "zt"
            mod = flow_mod
            b = mod.bounds(T, ctx)
        ctx.bounds[c["id"]] = b
        resolved[c["id"]] = (mod, T, typ)

    # 2. window builds (camera keys into the key store)
    for c in sel:
        if c["id"] not in resolved:
            continue
        mod, T, typ = resolved[c["id"]]
        t = time.time()
        try:
            mod.build(T, ctx)
        except Exception:  # noqa: BLE001
            ctx.log(f"ERROR {c['id']} {typ}.build failed:\n{traceback.format_exc()}")
            if typ != "zt" and T["a"] is not None and T["b"] is not None:
                for k in [k for k in ctx.keys if c["w0"] - 0.5 <= k < c["w1"]]:
                    del ctx.keys[k]
                T["p"] = dict(peak=3.0, land=2.4, roll=0.0)
                T["type"] = "zt"
                ctx.bounds[c["id"]] = flow_mod.bounds(T, ctx)
                flow_mod.build(T, ctx)
                resolved[c["id"]] = (flow_mod, T, "zt")
                typ = "zt (fallback)"
            else:
                raise
        ctx.windows.append((c["w0"], c["w1"], c))
        ctx.log(f"{c['id']} f{c['f']} {typ:<12} [{c['w0']}, {c['w1']})  {time.time() - t:.2f}s")

    # 3. holds
    ctx._holds = {}
    by_b = {c["b"]: c for c in cuts if c.get("b")}
    by_a = {c["a"]: c for c in cuts if c.get("a")}
    built = {c["id"] for _, _, c in ctx.windows}
    for sid in ctx._order:
        s = ctx.shot(sid)
        if s.get("panel") or sid not in shots_needed:
            continue
        cin, cout = by_b.get(sid), by_a.get(sid)
        h0 = cin["w1"] if cin and cin["id"] in built else s["a"]
        h1 = cout["w0"] if cout and cout["id"] in built else s["b"]
        if cout and cout["id"] not in built and cout.get("b") is None:
            h1 = max(h1, cout["w1"])  # e.g. the triptych without its module: S32's hold runs on
        if only is not None:
            # in --only mode a hold is keyed only next to a selected window (enough to land and to enter)
            h0 = max(h0, (cin["w1"] if cin and cin["id"] in built else h1 - 6))
            h1 = min(h1, (cout["w0"] if cout and cout["id"] in built else h0 + 6))
        if h1 <= h0:
            continue
        A = ctx.bounds[cin["id"]]["B"] if cin and cin["id"] in built else ctx.intent(sid, h0)
        if cout and cout["id"] in built:
            B = ctx.bounds[cout["id"]]["A"]
        elif h1 > s["b"]:
            # the hold runs past the shot (a missing end module): keep the shot's drift, slowing to the minimum
            e = ctx.intent(sid, s["b"])
            ds = math.copysign(DRIFT_MIN, e.ds)
            B = e.at(0).with_(s=e.s * math.exp((e.ds + ds) / 2 * (h1 - s["b"])), ds=ds,
                              r=e.r + e.dr * (h1 - s["b"]))
        else:
            B = ctx.intent(sid, h1)
        ctx._holds[sid] = (h0, h1, A, B)
        card = ctx.card(sid)

        def fn(t, A=A, B=B, h0=h0, h1=h1, card=card):
            st = cl.cover(cl.hermite_state(A, B, h0, h1, t))
            return ctx.pose(card, st)
        ctx.key_path(fn, h0, h1, 0.5)
        ctx.log(f"hold {sid} [{h0}, {h1}) s {A.s:.3f}->{B.s:.3f} ds {A.ds:+.4f}->{B.ds:+.4f} r {A.r:+.1f}->{B.r:+.1f}")
        rev = hold_reversal(A, B, h0, h1)
        if rev and h1 - h0 < 5:
            ctx.log(f"  note: hold {sid} reverses {rev} in {h1 - h0} f (< 5)")
    return resolved


def hold_reversal(A, B, h0, h1):
    out = []
    names = ["zoom", "x", "y", "roll"]
    thr = [0.002, 1.0, 1.0, 0.05]
    for i in range(4):
        vals = [cl.hermite_state(A, B, h0, h1, h0 + (h1 - h0) * k / 16).rates()[i] for k in range(17)]
        if max(vals) > thr[i] and min(vals) < -thr[i]:
            out.append(names[i])
    return ",".join(out)


# ======================================================================================================================
def apply_hits(ctx, only_frames=None):
    """punch@F: +7 % scale in 2 f, settles in 6 f (a lens zoom on top of the path); shake@F: decaying 3D shake ~8 f."""
    punches, shakes = [], []
    for s in ctx.E["shots"]:
        for fx in s.get("fx", []):
            k, _, f = fx.partition("@")
            if k == "punch":
                punches.append(float(f))
            elif k == "shake":
                shakes.append(float(f))
    for t in sorted(ctx.keys):
        loc, rot, lens = ctx.keys[t]
        lens = lens or cl.LENS_MM
        p = sum(cl.punch_curve(t - f) for f in punches)
        if p:
            lens = lens * math.exp(p)
        for i, f in enumerate(shakes):
            (rx, ry, rz), (dx, dy, dz) = cl.shake_offsets(t - f, seed=i + 3)
            if rx or ry or rz or dx or dy or dz:
                q = Quaternion((1, 0, 0), math.radians(rx)) @ Quaternion((0, 1, 0), math.radians(ry)) @ \
                    Quaternion((0, 0, 1), math.radians(rz))
                loc = loc + rot @ Vector((dx, dy, dz))
                rot = rot @ q
        ctx.keys[t] = (loc, rot, lens)
    ctx._cam_cache = None
    ctx.log(f"hits: {len(punches)} punch, {len(shakes)} shake")


def write_camera(ctx):
    cam = ctx.cam
    ts = sorted(ctx.keys)
    if not ts:
        raise RuntimeError("no camera keys")
    cam.animation_data_create()
    act = bpy.data.actions.new("CAM_action")
    cam.animation_data.action = act
    prev = None
    rows = []
    for t in ts:
        loc, rot, lens = ctx.keys[t]
        q = Quaternion(rot)
        if prev is not None and prev.dot(q) < 0:
            q = -q
        prev = q
        rows.append((t, loc, q, lens or cl.LENS_MM))
    fast = hasattr(act, "fcurve_ensure_for_datablock")
    channels = [("location", i, lambda r, i=i: r[1][i]) for i in range(3)] + \
               [("rotation_quaternion", i, lambda r, i=i: r[2][i]) for i in range(4)]
    if fast:
        for path, idx, get in channels:
            fc = act.fcurve_ensure_for_datablock(cam, path, index=idx)
            _fill(fc, [(r[0], get(r)) for r in rows])
        fcl = None
        cam.data.animation_data_create()
        lact = bpy.data.actions.new("CAMlens_action")
        cam.data.animation_data.action = lact
        fcl = lact.fcurve_ensure_for_datablock(cam.data, "lens")
        _fill(fcl, [(r[0], r[3]) for r in rows])
        dts = sorted(set(ts) | set(ctx.dof))
        cur = (2.0, cl.FSTOP_SHARP)
        dk = []
        for t in dts:
            if t in ctx.dof:
                cur = ctx.dof[t]
            elif cur[1] != cl.FSTOP_SHARP:
                cur = (cur[0], cl.FSTOP_SHARP)
            dk.append((t, cur))
        _fill(lact.fcurve_ensure_for_datablock(cam.data, "dof.focus_distance"), [(t, v[0]) for t, v in dk])
        _fill(lact.fcurve_ensure_for_datablock(cam.data, "dof.aperture_fstop"), [(t, v[1]) for t, v in dk])
    else:
        for t, loc, q, lens in rows:
            cam.location = loc
            cam.rotation_quaternion = q
            cam.keyframe_insert("location", frame=t)
            cam.keyframe_insert("rotation_quaternion", frame=t)
            cam.data.lens = lens
            cam.data.keyframe_insert("lens", frame=t)
    ctx.log(f"camera: {len(rows)} keys over [{ts[0]:.2f}, {ts[-1]:.2f}], {len(ctx.teleports)} teleports "
            f"({'fcurve api' if fast else 'keyframe_insert'})")


def _fill(fc, pts):
    fc.keyframe_points.add(len(pts))
    co = []
    for t, v in pts:
        co += [t, v]
    fc.keyframe_points.foreach_set("co", co)
    for kp in fc.keyframe_points:
        kp.interpolation = "LINEAR"
    fc.update()


def key_shutter(ctx):
    """Shutter 0.75 in holds, rising to 1.0 around each cut (never more than 2 * (distance to a teleport - 0.025))."""
    sc = bpy.context.scene
    cuts = [(w0, w1, c["f"]) for w0, w1, c in ctx.windows]
    for f in range(ctx.E["dur"]):
        sh = SHUTTER_HOLD
        for w0, w1, fc in cuts:
            if w0 - 1 <= f < w1 + 1:
                d = abs(f - (fc - 0.5))
                sh = max(sh, SHUTTER_HOLD + (SHUTTER_PEAK - SHUTTER_HOLD) * (1 - cl.smoothstep((d - 0.5) / 3.5)))
        for th in ctx.teleports:
            sh = min(sh, 2 * (abs(f - th) - 0.025))
        sc.render.motion_blur_shutter = sh
        sc.render.keyframe_insert("motion_blur_shutter", frame=f)


# ======================================================================================================================
def camera_dump(ctx, f0, f1):
    """Per-frame camera matrix + lens and every visible card's matrix (with inverse) for the gate."""
    sc = bpy.context.scene
    frames = []
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        ce = ctx.cam.evaluated_get(dg)
        vis = []
        for ob in ctx.all_cards:
            oe = ob.evaluated_get(dg)
            if oe.hide_render:
                continue
            M = oe.matrix_world
            vis.append(dict(name=ob.name, M=[list(r) for r in M], Mi=[list(r) for r in M.inverted_safe()]))
        frames.append(dict(f=f, cam=[list(r) for r in ce.matrix_world], lens=ce.data.lens, cards=vis,
                           shutter=sc.render.motion_blur_shutter))
    windows = [dict(id=c["id"], type=c["type"], f=c["f"], w0=w0, w1=w1) for w0, w1, c in ctx.windows]
    holds = {sid: [h[0], h[1]] for sid, h in ctx._holds.items()}
    return dict(frames=frames, teleports=ctx.teleports, windows=windows, holds=holds, res=[1920, 1080])


def render_identity(ctx, args):
    """Colour test: one plate frame at s = 1, centred, no roll, no motion -> out/identity/<shot>_<f>.png."""
    sid, _, f = args.identity.partition("@")
    f = int(f)
    card = ctx.card(sid)
    loc, rot = ctx.pose(card, cl.State(1.0, 960, 540, 0))
    ctx.cam.location = loc
    ctx.cam.rotation_quaternion = rot
    sc = bpy.context.scene
    sc.render.use_motion_blur = False
    sc.frame_set(f)
    for n, vl in ctx.layers.items():
        vl.use = n == "plate"
    os.makedirs(os.path.join(ctx.out, "identity"), exist_ok=True)
    sc.render.filepath = os.path.join(ctx.out, "identity", f"{sid}_{f:05d}.png")
    bpy.ops.render.render(write_still=True)
    ctx.log(f"identity frame -> {sc.render.filepath}")


def render_passes(ctx, args):
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = args.f0, args.f1
    for p in [p for p in args.passes.split(",") if p]:
        for n, vl in ctx.layers.items():
            vl.use = n == p
        set_filter(ctx, args.filter if p == "plate" else TEXT_FILTER)
        d = os.path.join(ctx.out, p)
        os.makedirs(d, exist_ok=True)
        sc.render.filepath = os.path.join(d, "f_#####")
        t = time.time()
        bpy.ops.render.render(animation=True)
        dt = time.time() - t
        n = args.f1 - args.f0 + 1
        ctx.log(f"pass {p}: {n} frames in {dt:.1f}s ({dt / n:.2f} s/frame)")
    for vl in ctx.layers.values():
        vl.use = True


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = parse_args(argv)
    with open(args.edl) as f:
        E = json.load(f)
    t0 = time.time()
    ctx = StageContext(E, args)
    os.makedirs(ctx.out, exist_ok=True)
    setup_scene(ctx, args)
    if args.identity:
        render_identity(ctx, args)
        return
    resolved = build(ctx, args)
    apply_hits(ctx)
    write_camera(ctx)
    key_shutter(ctx)
    # overlays, then titles (they read the keyed camera via ctx.cam_matrix / the fcurves)
    for c in E["cuts"]:
        if c["id"] not in resolved:
            continue
        for o in c.get("over", []):
            mod = load_module(ctx, o)
            if mod is None or not hasattr(mod, "build_over"):
                ctx.log(f"{c['id']} overlay {o}: no module, skipped")
                continue
            try:
                mod.build_over(cut_T(ctx, c), ctx)
                ctx.log(f"{c['id']} overlay {o} built")
            except Exception:  # noqa: BLE001
                ctx.log(f"ERROR {c['id']} overlay {o}:\n{traceback.format_exc()}")
    if os.path.exists(os.path.join(HERE, "text3d.py")):
        try:
            importlib.import_module("text3d").build(E, ctx)
            ctx.log("text3d built")
        except Exception:  # noqa: BLE001
            ctx.log(f"ERROR text3d:\n{traceback.format_exc()}")
    ctx.log(f"scene built in {time.time() - t0:.1f}s: {len(bpy.data.objects)} objects")
    with open(os.path.join(ctx.out, "keys.json"), "w") as f:
        json.dump(dict(teleports=ctx.teleports, keys=[[t, list(v[0]), list(v[1]), v[2]] for t, v in sorted(ctx.keys.items())],
                       bounds={k: {s: st.as_dict() for s, st in v.items()} for k, v in ctx.bounds.items()}), f)
    rc = 0
    if not args.no_gate:
        import gate
        g0 = max(0, args.f0 - 1) if args.only is None else min(w0 for w0, _, _ in ctx.windows) - 2
        g1 = min(E["dur"] - 1, args.f1 + 1) if args.only is None else max(w1 for _, w1, _ in ctx.windows) + 2
        dump = camera_dump(ctx, max(0, g0), min(E["dur"] - 1, g1))
        with open(os.path.join(ctx.out, "camdump.json"), "w") as f:
            json.dump(dump, f)
        res = gate.analyse(dump, out_csv=os.path.join(ctx.out, "gate.csv"), only=args.only is not None)
        gate.print_report(res)
        if res["fails"] and args.strict:
            rc = 3
    if args.save:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.save))
        ctx.log(f"saved {args.save}")
    if not args.gate_only:
        render_passes(ctx, args)
    with open(os.path.join(ctx.out, "stage.log"), "w") as f:
        f.write("\n".join(ctx.log_lines) + "\n")
    ctx.log(f"done in {time.time() - t0:.1f}s")
    if rc:
        sys.exit(rc)


import flow as flow_mod  # noqa: E402
FLOW_TYPES = set(flow_mod.TYPES)

if __name__ == "__main__":
    main()
