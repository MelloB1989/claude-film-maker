"""Timeless v3 stage: render-time optimisations that do not change the look (task v3-renderopt).

stage.py calls apply(scene, ctx) once after the build (after cull_by_set) and renders through ctx.render_fn when it is
set. Where the per-frame CPU time went (GPU only ~36 % busy):

1. Static visibility. Every card / FX object has keyed hide_render (ctx.show, cull_by_set, the modules). An object whose
   visibility is ANIMATED is always pulled into the render depsgraph, so on every frame Blender evaluated all ~1400 of
   them (animation, image users, Displace modifiers sampling depth sequences) and Cycles synced their shaders and
   images, even though only 2-4 cards can be seen. apply() bakes the keyed visibility into a per-frame table; the
   render then runs in segments of frames whose visible set is constant, with the hide_render keys removed and
   hide_render set statically per segment, so hidden objects are not in the depsgraph at all (persistent data keeps
   the Cycles session between segments). Exception, for an exact match: an object with object motion blur keeps its
   keys on the frames where its visibility changes inside the shutter (see edge_table).
2. Motion steps. Cycles evaluates the whole depsgraph once per motion time; camera motion_steps 4 = 2^4 + 1 = 17 scene
   evaluations per frame. The camera keys are at most a half frame apart (Bezier), and Cycles interpolates between the
   motion samples, so 2 steps (5 times, every <= 0.25 f across the shutter) carries the same blur (pixel-diffed).
3. Emission sampling NONE on the card / void materials (no light tree of ~200 emissive cards per frame; unbiased).
4. Denoise segments computed from the table (the core's render_segments does a frame_set per frame of the range).

Profiling: AMV3_RO = comma list of toggles, default "vis,steps,emis,dngpu"; "off" = the core's path (for before/after timings).
  vis    static visibility segments (1)
  steps  camera motion steps AMV3_RO_STEPS (default 2) (2)
  emis   emission sampling NONE on cards / voids (3)
  dngpu  OIDN on the GPU when rendering on a GPU (Cycles' default runs OIDN on the CPU)
  measurement only: png (compression AMV3_RO_PNG), post (compositor / sequencer off), adapt (adaptive sampling),
  nodepth (depth modifiers off: changes the look)
  stats  log Cycles' phase timeline per frame (render_stats handler) to <out>/ro_stats.txt
Per-frame wall times always go to <out>/ro_times.txt (frame, pass, seconds).
"""
import math
import os
import time

import bpy


def _toggles():
    v = os.environ.get("AMV3_RO", "vis,steps,emis,dngpu")
    return set(x.strip() for x in v.split(",") if x.strip())


def _fcurves(ob):
    ad = ob.animation_data
    if not ad or not ad.action:
        return []
    act = ad.action
    out = []
    if hasattr(act, "layers") and len(act.layers):
        for layer in act.layers:
            for strip in layer.strips:
                for bag in getattr(strip, "channelbags", []):
                    out.extend((bag, fc) for fc in bag.fcurves)
    elif hasattr(act, "fcurves"):
        out.extend((act, fc) for fc in act.fcurves)
    return out


def _vis_fcurve(ob):
    for owner, fc in _fcurves(ob):
        if fc.data_path == "hide_render" and not fc.mute:
            return owner, fc
    return None, None


def visibility_table(sc, f0, f1):
    """{object name: [visible on f for f in f0..f1]} for every object whose hide_render is keyed. A boolean property
    reads an fcurve value as int(value) != 0 (Blender's animsys)."""
    tab = {}
    for ob in sc.objects:
        _, fc = _vis_fcurve(ob)
        if fc is None:
            continue
        tab[ob.name] = [int(fc.evaluate(f)) == 0 for f in range(f0, f1 + 1)]
    return tab


def noisy_flags(ctx, sc, tab, f0, f1):
    """Per frame: render with OIDN (a glass / volume object visible, or a ctx.denoise span); same rule as the core's
    render_segments, read from the table instead of a frame_set per frame."""
    st = _stage()
    flags = [False] * (f1 - f0 + 1)
    for a, b in ctx.denoise_spans:
        for f in range(max(f0, a), min(f1, b - 1) + 1):
            flags[f - f0] = True
    noisy = [ob for ob in sc.objects if ob.type in ("MESH", "CURVE", "FONT")
             and any(st._noisy_material(s.material) for s in ob.material_slots)]
    for ob in noisy:
        # the core's _visible(): the object and every parent visible
        chain, p = [], ob
        while p is not None:
            chain.append(p)
            p = p.parent
        for i in range(f1 - f0 + 1):
            if not flags[i] and all((tab[o.name][i] if o.name in tab else not o.hide_render) for o in chain):
                flags[i] = True
    return flags


def _stage():
    import sys
    m = sys.modules.get("__main__")
    if m is not None and hasattr(m, "render_segments"):
        return m
    import stage
    return stage


def set_motion_steps(ctx, steps):
    cam = ctx.cam
    for owner in (getattr(cam, "cycles", None), cam):
        if owner is not None and hasattr(owner, "motion_steps"):
            try:
                owner.motion_steps = steps
            except Exception as e:  # noqa: BLE001
                ctx.log(f"WARN renderopt motion_steps: {e}")
    ctx.log(f"renderopt: camera motion_steps = {steps} ({(2 << (steps - 1)) + 1} scene evaluations per frame)")


def apply(scene, ctx):
    tg = _toggles()
    ctx.log(f"renderopt: AMV3_RO = {','.join(sorted(tg)) or 'none'}")
    ctx._ro = dict(toggles=tg)
    if "off" in tg:
        ctx.render_fn = _timed_core_render
        return
    if "steps" in tg:
        set_motion_steps(ctx, int(os.environ.get("AMV3_RO_STEPS", "2")))
    if "emis" in tg:
        no_emission_sampling(ctx, scene)
    if "dngpu" in tg and scene.cycles.device == "GPU" and hasattr(scene.cycles, "denoising_use_gpu"):
        # OIDN runs on the CPU by default (denoising_use_gpu False): on the pod that was 3-4 s of every OIDN frame,
        # in each of the three passes. OIDN on the GPU (CUDA build of the same network) ~0.1 s.
        scene.cycles.denoising_use_gpu = True
        ctx.log("renderopt: OIDN on the GPU")
    if "png" in tg:
        scene.render.image_settings.compression = int(os.environ.get("AMV3_RO_PNG", "0"))
        ctx.log(f"renderopt: PNG compression {scene.render.image_settings.compression}")
    if "post" in tg:
        scene.render.use_compositing = False
        scene.render.use_sequencer = False
        ctx.log("renderopt: compositing / sequencer off (the stage has neither)")
    if "adapt" in tg:
        cy = scene.cycles
        cy.use_adaptive_sampling = True
        cy.adaptive_threshold = float(os.environ.get("AMV3_RO_ADAPT", "0.01"))
        cy.adaptive_min_samples = int(os.environ.get("AMV3_RO_ADAPT_MIN", "0"))
        ctx.log(f"renderopt: adaptive sampling threshold {cy.adaptive_threshold} min {cy.adaptive_min_samples}")
    if "nodepth" in tg:  # measurement only: changes the look
        n = 0
        for ob in scene.objects:
            for m in ob.modifiers:
                if m.name in ("depth", "smooth"):
                    m.show_render = False
                    n += 1
        ctx.log(f"renderopt: MEASUREMENT nodepth ({n} modifiers off)")
    for kv in [x for x in os.environ.get("AMV3_RO_SET", "").split(";") if "=" in x]:  # measurement: path=value
        path, _, val = kv.partition("=")
        own, _, attr = path.strip().rpartition(".")
        o = scene
        for part in [x for x in own.split(".") if x]:
            o = getattr(o, part)
        cur = getattr(o, attr)
        setattr(o, attr, type(cur)(val) if not isinstance(cur, bool) else val.strip() in ("1", "True", "true"))
        ctx.log(f"renderopt: MEASUREMENT {path} = {getattr(o, attr)}")
    if "emisall" in tg:  # measurement: every emission out of the light tree
        n = 0
        for m in bpy.data.materials:
            own = getattr(m, "cycles", None)
            own = own if own is not None and hasattr(own, "emission_sampling") else m
            if hasattr(own, "emission_sampling"):
                own.emission_sampling = "NONE"
                n += 1
        ctx.log(f"renderopt: MEASUREMENT emisall ({n} materials)")
    if "nodof" in tg:
        ctx.cam.data.dof.use_dof = False
        ctx.log("renderopt: MEASUREMENT nodof")
    if "vis" in tg:
        ctx.render_fn = render_static


def no_emission_sampling(ctx, scene):
    """Cards and the act voids only display a picture: as lights they fill the light tree with hundreds of emitters
    that next-event estimation picks and wastes shadow rays on (glass blocks them anyway). Emission sampling 'NONE'
    on their materials: rays still see them (BSDF sampling, unbiased; the expected image is unchanged), and the
    real lights of the FX get all the light samples."""
    mats = set()
    for ob in scene.objects:
        if ob.get("amv3_card") or ob.name.startswith("env_") or (ob.instance_collection is not None):
            for sl in ob.material_slots:
                if sl.material is not None:
                    mats.add(sl.material)
    for c in bpy.data.collections:
        if c.name.startswith("ENV_"):
            for ob in c.all_objects:
                for sl in ob.material_slots:
                    if sl.material is not None:
                        mats.add(sl.material)
    n = 0
    for m in mats:
        for owner in (getattr(m, "cycles", None), m):
            if owner is not None and hasattr(owner, "emission_sampling"):
                owner.emission_sampling = "NONE"
                n += 1
                break
    ctx.log(f"renderopt: emission sampling NONE on {n} card / void materials")


# ---- timing ----------------------------------------------------------------------------------------------------------
class _Timer:
    """Per-frame wall time (render_pre -> render_post), plus the Cycles phase timeline when 'stats' is on."""

    def __init__(self, ctx, pass_name):
        self.ctx, self.p = ctx, pass_name
        self.t = None
        self.rows = []
        self.stats = "stats" in ctx._ro["toggles"]
        self.last = None
        self.phases = {}

    def pre(self, sc, *_):
        self.t = time.time()
        self.last = (self.t, "start")
        self.phases = {}

    def write(self, sc, *_):
        now = time.time()
        self._phase(now)
        self.last = (now, "write->post")

    def post(self, sc, *_):
        now = time.time()
        self._phase(now)
        self.rows.append((sc.frame_current, self.p, now - (self.t or now), dict(self.phases)))

    def _phase(self, now):
        if self.last is not None:
            k = self.last[1]
            self.phases[k] = self.phases.get(k, 0.0) + now - self.last[0]

    def on_stats(self, stats, *_):
        s = str(stats)
        k = s.rsplit("|", 1)[-1].strip()
        # coarse phase name: drop numbers and object names ("Synchronizing object | card_S03" -> "Synchronizing object")
        parts = [x.strip() for x in s.split("|")]
        for i, x in enumerate(parts):
            if x.startswith(("Synchroniz", "Updating", "Loading", "Sample", "Rendering", "Denois", "Building",
                             "Initializ", "Waiting", "Finishing", "Reading", "Compiling", "Path Tracing")):
                k = x
                break
        k = "".join(c for c in k if not c.isdigit()).replace("/", "").strip()[:40]
        now = time.time()
        if self.last is None or self.last[1] != k:
            self._phase(now)
            self.last = (now, k)

    def __enter__(self):
        h = bpy.app.handlers
        h.render_pre.append(self.pre)
        h.render_post.append(self.post)
        h.render_write.append(self.write)
        if self.stats:
            h.render_stats.append(self.on_stats)
        return self

    def __exit__(self, *a):
        h = bpy.app.handlers
        for lst, fn in ((h.render_pre, self.pre), (h.render_post, self.post), (h.render_write, self.write), (h.render_stats, self.on_stats)):
            if fn in lst:
                lst.remove(fn)
        with open(os.path.join(self.ctx.out, "ro_times.txt"), "a") as fh:
            for f, p, dt, ph in self.rows:
                fh.write(f"{f} {p} {dt:.3f}\n")
        if self.stats:
            with open(os.path.join(self.ctx.out, "ro_stats.txt"), "a") as fh:
                for f, p, dt, ph in self.rows:
                    top = sorted(ph.items(), key=lambda kv: -kv[1])[:8]
                    fh.write(f"{f} {p} {dt:.3f}  " + "  ".join(f"[{k}] {v:.3f}" for k, v in top) + "\n")


def _timed_core_render(ctx, args):
    """The core's render_passes, with the per-frame timer (AMV3_RO=off: the 'before' numbers)."""
    st = _stage()
    with _Timer(ctx, "all"):
        st.render_passes(ctx, args)


# ---- static visibility render ----------------------------------------------------------------------------------------
def _blurred(ob):
    c = getattr(ob, "cycles", None)
    return bool(getattr(c, "use_motion_blur", True)) if c is not None else True


def edge_table(sc, tab, f0, f1):
    """{name: [keep the keys on f]} for objects with object motion blur whose visibility changes inside the shutter of
    frame f (f +- 0.5). Cycles samples their motion at the subframes, and with keyed visibility a subframe where the
    object is hidden gets the centre transform (no blur from that side, e.g. the first frame of a ring that flies
    in); a static visible object would blur in its pre-appearance motion. Those objects keep their original keys on
    those frames, so the render is the core's exactly."""
    out = {}
    for n, row in tab.items():
        ob = sc.objects[n]
        if not _blurred(ob):
            continue
        _, fc = _vis_fcurve(ob)
        kts = [kp.co[0] for kp in fc.keyframe_points]
        er = []
        for i in range(f1 - f0 + 1):
            f = f0 + i
            ts = [f - 0.5, f + 0.5] + [t + e for t in kts for e in (-1e-3, 1e-3) if f - 0.5 < t + e < f + 0.5]
            er.append(any((int(fc.evaluate(t)) == 0) != row[i] for t in ts))
        if any(er):
            out[n] = er
    return out


def render_static(ctx, args):
    sc = bpy.context.scene
    st = _stage()
    f0, f1 = args.f0, args.f1
    t = time.time()
    tab = visibility_table(sc, f0, f1)
    dn = noisy_flags(ctx, sc, tab, f0, f1)
    if "nodn" in ctx._ro["toggles"]:  # measurement: no OIDN anywhere
        dn = [False] * len(dn)
    edges = edge_table(sc, tab, f0, f1)
    names = sorted(tab)
    # segments: consecutive frames with the same visible set, the same keyed (edge) set and the same denoise flag
    segs = []
    for i in range(f1 - f0 + 1):
        keyed = frozenset(n for n, er in edges.items() if er[i])
        key = (frozenset(n for n in names if tab[n][i] and n not in keyed), keyed, dn[i])
        if segs and segs[-1][2] == key:
            segs[-1][1] = f0 + i
        else:
            segs.append([f0 + i, f0 + i, key])
    nvis = [len(k[0]) for _, _, k in segs]
    nkey = sum(len(k[1]) * (b - a + 1) for a, b, k in segs)
    ctx.log(f"renderopt: {len(names)} objects with keyed visibility -> {len(segs)} static segments "
            f"(visible per segment {min(nvis)}-{max(nvis)}, mean {sum(nvis) / len(nvis):.0f}; {len(edges)} blurred "
            f"objects keep their keys on {nkey} object-frames at a visibility edge); "
            f"{sum(dn)} OIDN frames; table in {time.time() - t:.1f}s")
    # the original keys (restored on edge frames), then drop them: a static hidden object is not in the depsgraph
    saved = {}
    for n in names:
        ob = bpy.data.objects[n]
        owner, fc = _vis_fcurve(ob)
        saved[n] = [(kp.co[0], kp.co[1], kp.interpolation) for kp in fc.keyframe_points]
        while fc is not None:
            owner.fcurves.remove(fc)
            owner, fc = _vis_fcurve(ob)
    obs = {n: bpy.data.objects[n] for n in names}
    state = {n: None for n in names}  # unknown: the first segment sets every object

    def rekey(ob, keys):
        ad = ob.animation_data or ob.animation_data_create()
        if ad.action is None:
            ad.action = bpy.data.actions.new(f"{ob.name}_vis")
        fc = ad.action.fcurve_ensure_for_datablock(ob, "hide_render")
        fc.keyframe_points.add(len(keys))
        co = []
        for x, y, _ in keys:
            co += [x, y]
        fc.keyframe_points.foreach_set("co", co)
        for kp, (_, _, ip) in zip(fc.keyframe_points, keys):
            kp.interpolation = ip
        fc.update()

    hide = tuple(x for x in os.environ.get("AMV3_RO_HIDE", "").split(",") if x)  # measurement: name prefixes off
    if hide:
        for ob in sc.objects:
            if ob.name.startswith(hide) and ob.name not in obs:
                ob.hide_render = True
        ctx.log(f"renderopt: MEASUREMENT hidden {hide}")

    def show(vis, keyed):
        for n, ob in obs.items():
            want = "h" if hide and n.startswith(hide) else ("k" if n in keyed else ("v" if n in vis else "h"))
            if state[n] == want:
                continue
            if state[n] == "k":
                owner, fc = _vis_fcurve(ob)
                while fc is not None:
                    owner.fcurves.remove(fc)
                    owner, fc = _vis_fcurve(ob)
            if want == "k":
                rekey(ob, saved[n])
            else:
                ob.hide_render = want == "h"
            state[n] = want

    for p in [p for p in args.passes.split(",") if p]:
        for n, vl in ctx.layers.items():
            vl.use = n == p
        st.set_filter(ctx, args.filter if p == "plate" else st.TEXT_FILTER)
        d = os.path.join(ctx.out, p)
        os.makedirs(d, exist_ok=True)
        sc.render.filepath = os.path.join(d, "f_#####")
        t = time.time()
        with _Timer(ctx, p):
            for a, b, (vis, keyed, den) in segs:
                show(vis, keyed)
                st.set_denoise(sc, den)
                sc.frame_start, sc.frame_end = a, b
                bpy.ops.render.render(animation=True)
        st.set_denoise(sc, False)
        sc.frame_start, sc.frame_end = f0, f1
        dt = time.time() - t
        n = f1 - f0 + 1
        ctx.log(f"pass {p}: {n} frames in {dt:.1f}s ({dt / n:.2f} s/frame) [static visibility]")
    for vl in ctx.layers.values():
        vl.use = True
