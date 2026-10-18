"""xfx-A test harness: a small scene that mimics the stage contract's ctx, builds ONE transition module and renders it.

    blender -b --factory-startup -P blender/amv3/xfx/_harness_a/harness.py -- --edl films/timeless/amv3/edl.json \
        --data <dir with plates/ tracks/> --cut C09 [--frames A-B] [--res 0.5] [--samples 16] [--out out/xa/C09] \
        [--passes plate,light] [--save x.blend] [--threads N] [--no-render]

Holds outside the window are the module's own bounds carried along their rates (the core solves real holds); that is
enough to see the window edges and to run the same entry/exit continuity check as the core's gate. Only harness code
lives here; the modules in blender/amv3/xfx/ must not import it.
"""
import argparse
import importlib.util
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
for p in (AMV3, XFX, HERE):  # real camlib (AMV3) wins over the stand-in (HERE)
    if p not in sys.path:
        sys.path.append(p)
import camlib  # noqa: E402
import _xfxa as X  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--edl", required=True)
ap.add_argument("--data", required=True)
ap.add_argument("--cut", required=True)
ap.add_argument("--frames", default=None)
ap.add_argument("--res", type=float, default=0.5)
ap.add_argument("--samples", type=int, default=16)
ap.add_argument("--out", default=None)
ap.add_argument("--passes", default="plate")
ap.add_argument("--save", default=None)
ap.add_argument("--threads", type=int, default=0)
ap.add_argument("--no-render", action="store_true")
ap.add_argument("--device", default="CPU")
ap.add_argument("--shutter", type=float, default=0.9)
args = ap.parse_args(argv)

E = json.load(open(args.edl))
PAL = {
    "tobey": dict(key=(1.0, 0.70, 0.32), rim=(1.0, 0.86, 0.62), leak=(1.0, 0.58, 0.18), fog=(0.10, 0.065, 0.035)),
    "andrew": dict(key=(0.30, 0.82, 1.0), rim=(1.0, 0.62, 0.26), leak=(0.25, 0.75, 1.0), fog=(0.02, 0.055, 0.085)),
    "tom": dict(key=(1.0, 0.32, 0.10), rim=(0.45, 0.62, 0.95), leak=(1.0, 0.36, 0.08), fog=(0.085, 0.03, 0.02)),
    "outro": dict(key=(1, 1, 1), rim=(1, 1, 1), leak=(1, 1, 1), fog=(0.03, 0.03, 0.03)),
}


class Ctx:
    def __init__(self, E, data, res):
        self.E, self.fps, self.data, self.res = E, E["fps"], data, res
        self.keys = {}
        self.lens_keys = {}
        self.dof_keys = {}
        self.teleports = []
        self._cards = {}
        self._sets = 0
        self._colls = {}
        sc = bpy.context.scene
        for name in ("plate", "text", "light", "holdout", "env"):
            c = bpy.data.collections.new(name)
            sc.collection.children.link(c)
            self._colls[name] = c

    def log(self, msg):
        print("[ctx]", msg, flush=True)

    def shot(self, sid):
        return next(s for s in self.E["shots"] if s["id"] == sid)

    def act_at(self, f):
        for a in self.E["acts"]:
            if a["f0"] <= f < a["f1"]:
                return a["id"]
        return self.E["acts"][-1]["id"]

    def palette(self, act_id):
        return dict(PAL[act_id])

    def home(self, sid):
        i = [s["id"] for s in self.E["shots"]].index(sid)
        return Vector((100.0 * (i + 1), 0.0, 0.0))

    def new_set(self, name):
        self._sets += 1
        o = Vector((100.0 * self._sets, 1000.0, 0.0))
        self.log(f"set {name} at {tuple(o)}")
        return o

    def card(self, sid):
        if sid not in self._cards:
            self._cards[sid] = self.make_card(sid, f"CARD_{sid}", Matrix.Translation(self.home(sid)))
        return self._cards[sid]

    def make_card(self, sid, name, matrix=None, alpha="none", depth=0.0, hole=None, collection="plate"):
        ob = X.plane_obj(name, camlib.CARD_W, camlib.CARD_H, self._colls[collection])
        if matrix is not None:
            ob.matrix_world = matrix
        m, nt, out = X._nodes(f"M_{name}")
        img = X.plate_node(nt, self, sid)
        em = X.node(nt, "ShaderNodeEmission", Strength=1.0)
        nt.links.new(img.outputs["Color"], em.inputs["Color"])
        surf = em.outputs[0]
        if hole:
            uv = nt.nodes.new("ShaderNodeTexCoord")
            sep = nt.nodes.new("ShaderNodeSeparateXYZ")
            nt.links.new(uv.outputs["UV"], sep.inputs[0])
            px = X.math_node(nt, "MULTIPLY", sep.outputs[0], camlib.CARD_W * 1000)
            py = X.math_node(nt, "MULTIPLY", X.math_node(nt, "SUBTRACT", 1.0, sep.outputs[1]), camlib.CARD_H * 1000)
            dx = X.math_node(nt, "SUBTRACT", px, float(hole["center"][0]))
            dy = X.math_node(nt, "SUBTRACT", py, float(hole["center"][1]))
            d = X.math_node(nt, "SQRT", X.math_node(nt, "ADD", X.math_node(nt, "MULTIPLY", dx, dx),
                                                    X.math_node(nt, "MULTIPLY", dy, dy)))
            rad = X.key_value(nt, "hole_radius", hole["radius"])
            fe = float(hole.get("feather", 4.0))
            a = X.math_node(nt, "DIVIDE", X.math_node(nt, "SUBTRACT", d, rad), fe)
            a = X.math_node(nt, "ADD", a, 1.0, clamp=True)  # 0 inside r - feather, 1 outside r
            tr = nt.nodes.new("ShaderNodeBsdfTransparent")
            mx = nt.nodes.new("ShaderNodeMixShader")
            nt.links.new(a, mx.inputs[0])
            nt.links.new(tr.outputs[0], mx.inputs[1])
            nt.links.new(surf, mx.inputs[2])
            surf = mx.outputs[0]
        nt.links.new(surf, out.inputs["Surface"])
        ob.data.materials.append(m)
        return ob

    def matte_card(self, sid, matrix=None):
        return self.make_card(sid, f"MATTE_{sid}", matrix, alpha="matte", collection="holdout")

    def pose(self, card, st):
        m = X.cam_world(card.matrix_world.copy(), st)
        loc, rot, _ = m.decompose()
        return loc, rot

    def hold_state(self, sid, f):
        return HOLD(sid, f)

    def key_cam(self, f, loc, rot, lens=None):
        self.keys[round(float(f), 4)] = (Vector(loc), Quaternion(rot))
        if lens is not None:
            self.lens_keys[round(float(f), 4)] = lens

    def key_dof(self, f, focus_m, fstop):
        self.dof_keys[round(float(f), 4)] = (focus_m, fstop)

    def teleport(self, f_half):
        self.teleports.append(float(f_half))

    def coll(self, name):
        return self._colls[name]

    def env(self, origin, act_id):
        """Harness stand-in for the core's act void: a dim nebula shell, bokeh discs, a few web strands."""
        p = self.palette(act_id)
        r = X.rng(hash((round(origin.x), round(origin.y), act_id)) & 0xFFFF)
        coll = self._colls["env"]
        n = 48
        vs, fs = [], []
        R = 60.0
        for j in range(n // 2 + 1):
            th = math.pi * j / (n // 2)
            for i in range(n + 1):
                ph = 2 * math.pi * i / n
                vs.append(origin + Vector((R * math.sin(th) * math.cos(ph), R * math.sin(th) * math.sin(ph), R * math.cos(th))))
        for j in range(n // 2):
            for i in range(n):
                a = j * (n + 1) + i
                fs.append((a, a + n + 1, a + n + 2, a + 1))
        sh = X.mesh_obj(f"ENV_shell_{act_id}", vs, fs, coll)
        m, nt, out = X._nodes(f"M_env_{act_id}")
        tc = nt.nodes.new("ShaderNodeTexCoord")
        no = X.node(nt, "ShaderNodeTexNoise", Scale=0.08, Detail=4.0)
        nt.links.new(tc.outputs["Object"], no.inputs["Vector"])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*[c * 0.25 for c in p["fog"]], 1)
        ramp.color_ramp.elements[1].color = (*[c * 1.6 for c in p["fog"]], 1)
        nt.links.new(no.outputs["Fac"], ramp.inputs[0])
        em = X.node(nt, "ShaderNodeEmission", Strength=1.0)
        nt.links.new(ramp.outputs[0], em.inputs["Color"])
        nt.links.new(em.outputs[0], out.inputs["Surface"])
        sh.data.materials.append(m)
        bm = X.mat_emit(f"M_bokeh_{act_id}", p["key"], 1.5)
        for k in range(40):
            d = Vector((r.uniform(-1, 1), r.uniform(-1, 1), r.uniform(-1, 1))).normalized() * r.uniform(8, 25)
            b = X.annulus_obj(f"ENV_bokeh_{act_id}_{k}", 0.0, r.uniform(0.15, 0.5), coll, n=24)
            b.location = origin + d
            b.rotation_mode = "QUATERNION"
            b.rotation_quaternion = (-d).to_track_quat("Z", "Y")
            b.data.materials.append(bm)
        return sh


HOLDS = {}


def HOLD(sid, f):
    w = HOLDS.get(sid)
    if not w:
        return None
    t0, st = w
    return X.extrap(st, f - t0)


# ------------------------------------------------------------------------------------------------- scene
sc = bpy.context.scene
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)
bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
sc.render.fps = E["fps"]
sc.render.resolution_x, sc.render.resolution_y = E["w"], E["h"]
sc.render.resolution_percentage = int(round(args.res * 100))
sc.render.engine = "CYCLES"
sc.cycles.samples = args.samples
sc.cycles.use_denoising = True
sc.cycles.max_bounces = 6
sc.cycles.glossy_bounces = 3
sc.cycles.transparent_max_bounces = 16
sc.cycles.device = "GPU" if args.device != "CPU" else "CPU"
if args.device != "CPU":
    pr = bpy.context.preferences.addons["cycles"].preferences
    pr.compute_device_type = args.device
    pr.get_devices()
    for d in pr.devices:
        d.use = d.type == args.device
if args.threads:
    sc.render.threads_mode = "FIXED"
    sc.render.threads = args.threads
sc.render.use_motion_blur = True
sc.render.motion_blur_shutter = args.shutter
sc.render.motion_blur_position = "CENTER"
sc.view_settings.view_transform = "Standard"
sc.world = bpy.data.worlds.new("W")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0, 0, 0, 1)

cam_data = bpy.data.cameras.new("CAM")
cam_data.lens = camlib.LENS_MM
cam_data.sensor_width = camlib.SENSOR_MM
cam_data.sensor_fit = "HORIZONTAL"
cam_data.clip_start = 0.005
cam_data.clip_end = 500
CAM = bpy.data.objects.new("CAM", cam_data)
sc.collection.objects.link(CAM)
CAM.rotation_mode = "QUATERNION"
sc.camera = CAM

ctx = Ctx(E, args.data, args.res)
T0 = next(c for c in E["cuts"] if c["id"] == args.cut)
T = dict(T0)
T["a"] = ctx.shot(T0["a"]) if T0["a"] else None
T["b"] = ctx.shot(T0["b"]) if T0["b"] else None
w0, w1 = T["w0"], T["w1"]

spec = importlib.util.spec_from_file_location(f"xfx_{T['type']}", os.path.join(XFX, f"{T['type']}.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

t_build = time.time()
B = mod.bounds(T, ctx)
print("bounds A", B["A"])
print("bounds B", B["B"])
HOLDS[T0["a"]] = (w0, B["A"])
HOLDS[T0["b"]] = (w1, B["B"])
cardA, cardB = ctx.card(T0["a"]), ctx.card(T0["b"])
mod.build(T, ctx)
print(f"build {time.time() - t_build:.1f} s")

if args.frames:
    fa, fb = (int(x) for x in args.frames.split("-"))
else:
    fa, fb = w0 - 3, w1 + 3
# holds: the bounds carried along their rates, keyed on the home cards like the core does
for i in range(int((w0 - (fa - 2)) * 2)):
    t = fa - 2 + i * 0.5
    ctx.key_cam(t, *ctx.pose(cardA, X.extrap(B["A"], t - w0)))
for i in range(int(((fb + 3) - w1) * 2)):
    t = w1 + i * 0.5
    ctx.key_cam(t, *ctx.pose(cardB, X.extrap(B["B"], t - w1)))

# ------------------------------------------------------------------------------------------------- gate (core's check)
def ang(q1, q2):
    a = math.degrees(q1.rotation_difference(q2).angle)
    return min(a, 360.0 - a)


bad = []
for i in range(int((w1 - w0) * 2)):
    t = round(w0 + i * 0.5, 4)
    if t not in ctx.keys and not any(abs(t - th) < 1e-6 for th in ctx.teleports):
        bad.append(t)
if bad:
    print("GATE missing keys", bad[:10])
la, ra = ctx.pose(cardA, B["A"])
lk, rk = ctx.keys[float(w0)]
print(f"GATE entry pose: {1000 * (lk - la).length:.3f} mm, {ang(rk, ra):.4f} deg")
t1 = min(t for t in ctx.keys if t > w0)
l1, r1 = ctx.pose(cardA, X.extrap(B["A"], t1 - w0))
lk1, rk1 = ctx.keys[t1]
dv = (lk1 - lk) - (l1 - la)
print(f"GATE entry rate (f{t1}): {1000 * dv.length:.3f} mm vs step {1000 * (l1 - la).length:.3f} mm, "
      f"rot {ang(rk1, r1):.4f} deg")
tb = max(t for t in ctx.keys if t < w1)
lb, rb = ctx.pose(cardB, X.extrap(B["B"], tb - w1))
lkb, rkb = ctx.keys[tb]
print(f"GATE exit (f{tb}): {1000 * (lkb - lb).length:.3f} mm, {ang(rkb, rb):.4f} deg")
# per-frame motion: camera-space translation (m/f) and rotation (deg/f), set changes skipped
ks = sorted(ctx.keys)
prev = None
print("GATE  f      v(m/f)   w(deg/f)")
for t in ks:
    if t != int(t) or t < fa - 1 or t > fb + 1:
        continue
    if prev is not None and not any(prev < th < t for th in ctx.teleports):
        (l0, q0), (l1_, q1) = ctx.keys[prev], ctx.keys[t]
        print(f"GATE {t:6.1f} {(l1_ - l0).length / (t - prev):8.4f} {ang(q0, q1) / (t - prev):8.3f}")
    prev = t

# write the keys
last_q = None
for t in sorted(ctx.keys):
    loc, q = ctx.keys[t]
    if last_q is not None and last_q.dot(q) < 0:
        q = -q
    last_q = q
    CAM.location = loc
    CAM.rotation_quaternion = q
    CAM.keyframe_insert("location", frame=t)
    CAM.keyframe_insert("rotation_quaternion", frame=t)
for t, lens in sorted(ctx.lens_keys.items()):
    cam_data.lens = lens
    cam_data.keyframe_insert("lens", frame=t)
if ctx.dof_keys:
    cam_data.dof.use_dof = True
    for t, (fd, fs) in sorted(ctx.dof_keys.items()):
        cam_data.dof.focus_distance = fd
        cam_data.dof.aperture_fstop = fs
        cam_data.dof.keyframe_insert("focus_distance", frame=t)
        cam_data.dof.keyframe_insert("aperture_fstop", frame=t)
X.set_linear(CAM)
X.set_linear(cam_data)

if args.save:
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.save))
if args.no_render or not args.out:
    sys.exit(0)

# ------------------------------------------------------------------------------------------------- render passes
vl = sc.view_layers[0]


def setup_pass(name):
    light_only = name == "light"
    sc.render.film_transparent = light_only
    for lc in vl.layer_collection.children:
        lc.exclude = False
        lc.holdout = light_only and lc.name in ("plate", "holdout")
        if light_only and lc.name in ("env", "text"):
            lc.exclude = True
        if not light_only and lc.name == "holdout":
            lc.exclude = True


sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGBA"
for ps in args.passes.split(","):
    os.makedirs(os.path.join(args.out, ps), exist_ok=True)
times = []
for f in range(fa, fb + 1):
    for ps in args.passes.split(","):
        setup_pass(ps)
        sc.frame_set(f)
        sc.render.filepath = os.path.abspath(os.path.join(args.out, ps, f"f_{f:05d}.png"))
        t = time.time()
        bpy.ops.render.render(write_still=True)
        times.append(time.time() - t)
        print(f"RENDER {ps} f{f} {times[-1]:.1f} s", flush=True)
print(f"RENDER mean {sum(times) / len(times):.1f} s/frame-pass over {len(times)}")
