"""xfx-B harness: a small stand-in for the amv3 stage core, to build and render one xfx module before the core lands.

blender -b --factory-startup -P blender/amv3/xfx/_harness/run.py -- --cut C17 --frames 466-497 --res 0.5 --samples 16 \
    --out out/h/c17 [--passes plate,light] [--save x.blend] [--every 1]

It mimics the stage contract's ctx (cards with the plate sequence, sets 100 m apart, pose, key_cam, teleport, coll, env,
palette), keys simple holds around the window from the module's bounds() (constant rates), runs build()/build_over(),
prints the camera speed at the window edges (velocity continuity), and renders plate/ and light/ PNGs per comp frame.
None of this is used by the modules themselves: they only talk to ctx.
"""
import argparse
import importlib
import json
import math
import os
import sys
import time

import bpy
from mathutils import Matrix, Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
XFX = os.path.dirname(HERE)
AMV3 = os.path.dirname(XFX)
REPO = os.path.dirname(os.path.dirname(AMV3))
for p in (AMV3, XFX):
    if p not in sys.path:
        sys.path.insert(0, p)
try:
    import camlib  # the core's, when it exists
except ImportError:
    sys.path.insert(0, HERE)
    import camlib

import _fx3d as fx  # noqa: E402

PALETTES = {
    "tobey": dict(key=(1.0, 0.72, 0.32), rim=(0.25, 0.62, 0.72), leak=(1.0, 0.62, 0.22), fog=(0.06, 0.045, 0.03)),
    "andrew": dict(key=(0.35, 0.8, 1.0), rim=(1.0, 0.62, 0.22), leak=(0.3, 0.75, 1.0), fog=(0.02, 0.04, 0.075)),
    "tom": dict(key=(1.0, 0.36, 0.12), rim=(0.35, 0.55, 0.95), leak=(1.0, 0.42, 0.1), fog=(0.07, 0.025, 0.02)),
    "outro": dict(key=(1, 1, 1), rim=(0.5, 0.7, 1), leak=(1, 0.5, 0.2), fog=(0.03, 0.03, 0.04)),
}


class HarnessCtx:
    def __init__(self, E, data, res, scene):
        self.E = E
        self.fps = E["fps"]
        self.data = data
        self.res = res
        self.scene = scene
        self._cards = {}
        self._sets = 0
        self.teleports = []
        self.cam = scene.camera
        self._colls = {}
        for n in ("plate", "text", "light", "holdout"):
            c = bpy.data.collections.new(n)
            scene.collection.children.link(c)
            self._colls[n] = c

    def log(self, msg):
        print("[ctx]", msg, flush=True)

    def shot(self, sid):
        return next(s for s in self.E["shots"] if s["id"] == sid)

    def act_at(self, f):
        return next(a for a in self.E["acts"] if a["f0"] <= f < a["f1"]) if f < self.E["dur"] else self.E["acts"][-1]

    def palette(self, act_id):
        return dict(PALETTES[act_id])

    def coll(self, name):
        return self._colls[name]

    def home(self, sid):
        ids = [s["id"] for s in self.E["shots"]] + ["P1", "P2", "P3"]
        return Vector((100.0 * (ids.index(sid) + 1), 0, 0))

    def new_set(self, name):
        self._sets += 1
        return Vector((0, 100.0 * self._sets, 0))

    def _plate_mat(self, sid):
        key = "hplate_" + sid
        if key in bpy.data.materials:
            return bpy.data.materials[key]
        d = os.path.join(self.data, "plates", sid)
        fs = sorted(int(n[2:7]) for n in os.listdir(d) if n.startswith("f_"))
        return fx.plate_image_mat(key, d, fs[0], fs[-1] + 1)

    def make_card(self, sid, name, matrix=None, alpha="none", depth=0.0, hole=None, collection="plate"):
        me = fx.quad_mesh(name, camlib.CARD_W, camlib.CARD_H)
        me.materials.append(self._plate_mat(sid))
        ob = bpy.data.objects.new(name, me)
        ob.matrix_world = matrix if matrix is not None else Matrix.Translation(self.home(sid))
        self._colls[collection].objects.link(ob)
        return ob

    def card(self, sid):
        if sid not in self._cards:
            self._cards[sid] = self.make_card(sid, "card_" + sid)
        return self._cards[sid]

    def matte_card(self, sid, matrix=None):
        return None

    def pose(self, card, st):
        loc, rot, _ = card.matrix_world.decompose()
        M = Matrix.LocRotScale(loc, rot, None)
        p = M @ Vector(((st.cx - 960) * 0.001, -(st.cy - 540) * 0.001, camlib.FILL_DIST / st.s))
        q = rot @ Quaternion((0, 0, 1), math.radians(st.r))
        return p, q

    def key_cam(self, f, loc, rot, lens=None):
        c = self.cam
        c.rotation_mode = "QUATERNION"
        q = Quaternion(rot)
        if getattr(self, "_q", None) is not None and self._q.dot(q) < 0:
            q = -q
        self._q = q.copy()
        c.location = loc
        c.rotation_quaternion = q
        c.keyframe_insert("location", frame=f)
        c.keyframe_insert("rotation_quaternion", frame=f)
        if lens:
            c.data.lens = lens
            c.data.keyframe_insert("lens", frame=f)

    def teleport(self, f_half):
        self.teleports.append(f_half)

    def hold_state(self, sid, f):
        return camlib.State(1.1, 960, 540, 0.0)

    def env(self, origin, act_id):
        """Cheap void: a dim act-tinted fog shell, bokeh discs and a few web strands around origin."""
        import random
        pal = self.palette(act_id)
        rng = random.Random(hash(act_id) & 0xffff)
        sh = bpy.data.meshes.new("env_shell")
        import bmesh
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=40.0)
        bm.to_mesh(sh)
        bm.free()
        m = fx.emission_mat("env_fog_" + act_id, pal["fog"], 1.0)
        sh.materials.append(m)
        ob = bpy.data.objects.new("env_" + act_id, sh)
        ob.location = origin
        self._colls["plate"].objects.link(ob)
        for i in range(70):
            d = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))).normalized() * rng.uniform(5, 30)
            me = bpy.data.meshes.new("bokeh")
            bm = bmesh.new()
            bmesh.ops.create_icosphere(bm, subdivisions=1, radius=rng.uniform(0.05, 0.25))
            bm.to_mesh(me)
            bm.free()
            col = pal[rng.choice(("key", "rim", "leak"))]
            me.materials.append(fx.emission_mat("bokeh_%d" % i, col, rng.uniform(0.3, 1.5)))
            b = bpy.data.objects.new("bokeh_%d" % i, me)
            b.location = origin + d
            self._colls["plate"].objects.link(b)
        return ob


def setup_scene(args):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = args.samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 8
    sc.cycles.glossy_bounces = 4
    sc.cycles.transmission_bounces = 8
    sc.cycles.transparent_max_bounces = 8
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.sample_clamp_indirect = 10.0
    sc.render.fps = 30
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    sc.render.resolution_percentage = int(round(args.res * 100))
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = args.shutter
    sc.view_settings.view_transform = "Standard"
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    cam_d = bpy.data.cameras.new("CAM")
    cam_d.lens = camlib.LENS_MM
    cam_d.sensor_width = camlib.SENSOR_MM
    cam_d.sensor_fit = "HORIZONTAL"
    cam_d.clip_start = 0.005
    cam_d.clip_end = 500
    cam = bpy.data.objects.new("CAM", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.01, 0.01, 0.012, 1)
    return sc


def key_hold(ctx, card, st, f0, f1, ref_f):
    """Constant-rate hold around a window edge (harness only)."""
    f = f0
    while f <= f1 + 1e-9:
        d = f - ref_f
        s = camlib.State(st.s * math.exp(st.ds * d), st.cx + st.dcx * d, st.cy + st.dcy * d, st.r + st.dr * d)
        loc, rot = ctx.pose(card, s)
        ctx.key_cam(f, loc, rot)
        f += 0.5


def stand_in_zt(ctx, T):
    """A plain zoom-through for overlay tests (the core's zt does the real one)."""
    A, B = ctx.card(T["a"]["id"]), ctx.card(T["b"]["id"])
    f, w0, w1 = T["f"], T["w0"], T["w1"]
    p = T["p"]
    roll = p.get("roll", 0.0)
    fh = f - 0.5
    for t in fx.frames_half(w0 - 6, fh - 0.01):
        u = fx.clamp01((t - w0) / (fh - w0))
        s = 1.15 * (p["peak"] / 1.15) ** (camlib.ease_in_expo(u) if t >= w0 else 0) * (1.0 + 0.004 * min(t - w0, 0))
        st = camlib.State(s, 960, 540, roll * 0.5 * camlib.ease_in_expo(u))
        ctx.key_cam(t, *ctx.pose(A, st))
    ctx.key_cam(fh - 0.01, *ctx.pose(A, camlib.State(p["peak"], 960, 540, roll * 0.5)))
    for t in [fh + 0.01] + fx.frames_half(f, w1 + 6):
        u = fx.clamp01((t - fh) / (w1 - fh))
        e = camlib.ease_out_expo(u)
        st = camlib.State(p["land"] * (1.12 / p["land"]) ** e, 960, 540, -roll * 0.5 * (1 - e))
        ctx.key_cam(t, *ctx.pose(B, st))
    ctx.teleport(fh)


def cam_speed(cam, sc, f):
    sc.frame_set(int(math.floor(f)), subframe=f - math.floor(f))
    return cam.matrix_world.copy()


def check_edges(ctx, sc, T, B):
    cam = sc.camera
    out = []
    for edge in (T["w0"], T["w1"]):
        ms = [cam_speed(cam, sc, edge + d) for d in (-1.0, -0.5, 0.0, 0.5, 1.0)]
        v = [(ms[i + 1].translation - ms[i].translation).length * 2 for i in range(4)]
        out.append("edge %s: |v| m/f %s" % (edge, " ".join("%.4f" % x for x in v)))
    for line in out:
        ctx.log(line)


def render(sc, args, frames):
    vl_plate = sc.view_layers[0]
    vl_plate.name = "plate"
    vl_light = sc.view_layers.new("light")
    for vl, hold in ((vl_plate, ()), (vl_light, ("plate", "text", "holdout"))):
        for lc in vl.layer_collection.children:
            if lc.name == "text":
                lc.exclude = True
            if lc.name in hold:
                lc.holdout = True
    bg = sc.world.node_tree.nodes["Background"].inputs[1]
    tf = sc.get("amv3_transparent_from", 10 ** 9)
    passes = args.passes.split(",")
    for p in passes:
        os.makedirs(os.path.join(args.out, p), exist_ok=True)
    tim = []
    for f in frames:
        sc.frame_set(f)
        for p in passes:
            t0 = time.time()
            vl_plate.use = p == "plate"
            vl_light.use = p == "light"
            sc.render.film_transparent = p == "light" or f >= tf
            bg.default_value = 0.0 if p == "light" else 1.0
            bpy.ops.render.render(write_still=False)
            path = os.path.join(args.out, p, "f_%05d.png" % f)
            bpy.data.images["Render Result"].save_render(path)
            tim.append(time.time() - t0)
            print("frame %d %s %.1fs" % (f, p, tim[-1]), flush=True)
    print("render mean %.1fs per pass-frame" % (sum(tim) / max(len(tim), 1)), flush=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--edl", default=os.path.join(REPO, "films/timeless/amv3/edl.json"))
    ap.add_argument("--data", default=os.environ.get("AMV3_DATA", "/home/nikhil/code/film-making/work/timeless_v3"))
    ap.add_argument("--cut", required=True)
    ap.add_argument("--frames", default=None)
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--res", type=float, default=0.5)
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--shutter", type=float, default=0.75)
    ap.add_argument("--passes", default="plate,light")
    ap.add_argument("--out", required=True)
    ap.add_argument("--save", default=None)
    ap.add_argument("--no-render", action="store_true")
    args = ap.parse_args(argv)
    E = json.load(open(args.edl))
    sc = setup_scene(args)
    ctx = HarnessCtx(E, args.data, args.res, sc)
    fx.set_linear_keys()
    C = next(c for c in E["cuts"] if c["id"] == args.cut)
    T = dict(C)
    T["a"] = ctx.shot(C["a"]) if C["a"] else None
    T["b"] = ctx.shot(C["b"]) if C["b"] else None
    t0 = time.time()
    if C["over"]:
        stand_in_zt(ctx, T)
        for o in C["over"]:
            importlib.import_module(o).build_over(T, ctx)
    else:
        mod = importlib.import_module(C["type"])
        bd = mod.bounds(T, ctx)
        ctx.log("bounds A %s" % (bd["A"],))
        ctx.log("bounds B %s" % (bd.get("B"),))
        key_hold(ctx, ctx.card(T["a"]["id"]), bd["A"], C["w0"] - 8, C["w0"] - 0.5, C["w0"])
        if bd.get("B") is not None and T["b"]:
            key_hold(ctx, ctx.card(T["b"]["id"]), bd["B"], C["w1"], C["w1"] + 8, C["w1"])
        mod.build(T, ctx)
        check_edges(ctx, sc, T, bd)
    ctx.log("build %.1fs, teleports %s" % (time.time() - t0, ctx.teleports))
    if args.save:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.save))
    if args.no_render:
        return
    if args.frames:
        frames = []
        for part in args.frames.split(","):
            if "-" in part:
                a, b = part.split("-")
                frames += list(range(int(a), int(b) + 1, args.every))
            else:
                frames.append(int(part))
    else:
        frames = list(range(C["w0"] - 2, C["w1"] + 3, args.every))
    render(sc, args, frames)


if __name__ == "__main__":
    main()
