"""B45: every area's selftest (unreal/fmbridge/selftest/<area>.py) dry-run through WP11's real harness on the fake
engine, one parametrized test over all of them, so a selftest that would crash on the GPU box (a renamed op, a wrong
T call, a typo past the first check) fails here first.

The dry run forces every capability on (gpu, display, sign-in), fakes stills (t.still, look.still and seq.still write
a grey PNG; the fake has no renderer) and turns baselines off. An area passes when the harness reports no errors (an
exception in the test or an op), the test ends done (or skipped for content the fake lacks: SKIPS) inside its time
budget, and every failed check is one only a real renderer or engine can judge (FAKE_ONLY). A new selftest module is
picked up with no change here; one that needs more of the fake gets a SETUP entry.
"""
from __future__ import annotations

import io
import os
import time

import pytest

from fakeunreal import core as _core

HERE = os.path.dirname(os.path.abspath(__file__))
SELFTESTS = os.path.join(HERE, "..", "..", "unreal", "fmbridge", "selftest")
AREAS = sorted(f[:-3] for f in os.listdir(SELFTESTS) if f.endswith(".py") and not f.startswith("_"))
BUDGET_S = 90.0  # wall clock per area on the fake (layout.settle waits real seconds)

# checks only a real renderer, physics or engine data can judge: failing here is expected
FAKE_ONLY = {
    "cam": {"marker 0 at (u, v) on 16:9 Digital Film", "marker 0 at (u, v) on Super 35mm",  # pixels (the fake's
            "marker 1 at (u, v) on 16:9 Digital Film", "marker 2 at (u, v) on 16:9 Digital Film",  # capture is a
            "marker 1 at (u, v) on Super 35mm", "marker 2 at (u, v) on Super 35mm",  # stand-in picture)
            "WS: the figure's top on the predicted row", "WS: the feet on the predicted row",
            "MCU: the figure's top on the predicted row", "CU: the figure's top on the predicted row",
            "push-in: Sequencer plays the baked key at 48",  # the fake's Sequencer does not evaluate keys
            "rail: Sequencer plays the rail position at mid-shot",
            "rail: the camera is near the middle of the rail at mid-shot"},
    "env": {"one stop more exposure brightens the image", "env.check fails an underexposed card with a fix",
            "noir_bw has no colour cast", "env.autoexpose lands near the card's EV100"},  # a flat grey card
    "foliage": {"instances follow the ramp's surface", "align_to_normal tilts them ~30 deg",  # traces hit boxes
                "a 20-degree limit drops everything on the 30-degree ramp"},
    "layout": {"rotated table footprint swaps X and Y",  # the fake's bounds do not turn with the actor
               "a dropped crate lands on the floor under physics", "settle reports the crate moved",  # no physics
               "data layers refuse a non-partitioned level"},  # the fake's data layers take any level
    "mh": {"assembled actor has Body and Face"},
    "qa": {"capture and viewport show the same picture (SSIM > 0.6)"},  # the viewport still is the grey stand-in
    "render": {"command-line render (one process, no editor)"},  # its process is a stub here
}
# coverage: the ops under these prefixes the selftest must call, but for the ones named (owners' terms)
COVERAGE = {
    "assets": (("assets.", "mat.", "fab."), {"assets.save_all", "fab.add", "fab.login", "fab.library"}),  # no sign-in
    "env": (("env.", "light."), set()),
    "render": (("render.",), {"render.mrq", "render.progress", "render.concat"}),
}
# checks that must be in the report and pass (owners' lists from their former per-area dry runs)
REQUIRED = {
    "cam": {"focal beyond the lens widens it, not clamped", "cam.add converges", "a missing camera is not_found",
            "a bad size is bad_args", "WS solved", "MCU solved", "cam.frame MCU converges", "cam.project agrees: MCU",
            "cam.frame WS converges", "cam.frame CU converges", "cam.shoot reads its own words back without moving",
            "coverage stays on one side of the line", "cam.coverage converges", "shot.plan cuts",
            "coverage names its cameras by the subjects' labels", "still coverage_master", "still coverage_A_OTS",
            "shot.apply converges", "shot.describe reads the edit back", "a dropped shot's camera is removed",
            "contact sheet: 3 stills per shot"},
    "foliage": {"scatter placed what it planned", "nothing dropped on flat ground", "the instances are in the level",
                "no actor per instance", "cones sit on the floor's top (z 0)", "nothing inside the excluded circle",
                "scatter converges", "still the same count", "slope scatter placed its 20",
                "another seed replaces, never adds", "describe: measured cones", "removed: no instances left",
                "remove again is fine", "PCG generated", "PCG seed set"},
}
# ops the selftest must call (beyond COVERAGE's prefixes)
OPS_REQUIRED = {"anim": {"anim.find", "anim.new", "perf.face", "anim.check"}}
# areas whose test stops early on the fake for want of engine content: the reason must say so
SKIPS = {
    "mh": "MetaHuman presets",
    "pose": "no body Control Rig",
}
# known breakage, owner told; remove the entry when fixed (the test then passes, or fails loudly as xfail(strict))
KNOWN = {  # area: (text still in its selftest while broken, why); the xfail lifts by itself once the text is gone
    "audio": ("paths=paths)", "selftest/audio.py calls t.check(name, ok, **details), not the harness's "
              "t.check(name, got, want): TypeError at the first check (fixed by agent-03 at 964e048, ue-post)"),
}


def _grey_png(path, w=16, h=9):
    from fmbridge.qa import image as im
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    im.write(im.solid(max(1, int(w) // 60 or 16), max(1, int(h) // 60 or 9), (118, 118, 118)), path)


def _fake_stills(fmb, st, monkeypatch):
    def t_still(self, name, camera=None, width=960, height=540):
        """t.still: a grey PNG where the real one would go, recorded like one."""
        path = os.path.join(self.out, "stills", f"{self.area}_{name}.png")
        _grey_png(path, width, height)
        self.stills.append(path)
        self._add(f"still {name}", True, detail="dry run: a grey stand-in")
        yield
        return path
    monkeypatch.setattr(st.T, "still", t_still)

    def look_still(camera_label, path, width=1920, height=1080, timeout=60.0):
        """look.still on the fake: a grey PNG."""
        yield
        _grey_png(path, width, height)
        return {"path": path, "bytes": os.path.getsize(path)}

    def seq_still(path, frame, camera, out, width=1920, height=1080, settle=30):
        """seq.still on the fake: a grey PNG."""
        yield
        _grey_png(out, width, height)
        return {"path": out}
    import fmbridge.ops.look as look
    monkeypatch.setattr(look, "still", look_still)
    monkeypatch.setitem(fmb._OPS, "look.still", look_still)
    if "seq.still" in fmb._OPS:
        monkeypatch.setitem(fmb._OPS, "seq.still", seq_still)


# --- per-area setup: what the fake needs beyond the defaults (moved from each area's own dry-run test) ------------

def _setup_assets(ue, fmb, monkeypatch, tmp_path):
    class FabBrowserApi(ue.Object):  # a Fab plugin with no sign-in
        def call_method(self, name, args=(), kwargs=None):
            return "" if name == "GetAuthToken" else None
    ue.FabBrowserApi = FabBrowserApi


def _setup_anim(ue, fmb, monkeypatch, tmp_path):
    from fmbridge.selftest import anim as st
    from fmbridge.perfkit import rig
    curves = {f"CTRL_expressions_{n}": ([0.0, 1.0, 2.0], [0.0, 0.3, 0.0]) for n in
              ("browRaiseInL", "browRaiseInR", "mouthLipsPressL", "mouthLipsPressR", "jawOpen", "eyeBlinkL")}
    curves.update({rig.PREFIX + n: ([0.0, 2.0], [0.0, 0.0]) for n in rig.RAW[:120] if rig.PREFIX + n not in curves})
    ue.anim(st.FACE_LOOP, length_s=3.0, curves=curves, skeleton="/Game/MH/Face/FaceMesh_Skeleton")
    ue.anim("/MetaHumanCharacter/Optional/Animation/UEFNAnimPreset/Locomotion/AS_MH_Neutral_Walk_Loop_F", length_s=1.1)
    ue.anim(st.BODY_IDLE, length_s=8)


def _setup_mh(ue, fmb, monkeypatch, tmp_path):
    from fakeunreal.ext_mh import add_presets, add_wardrobe
    import fmbridge.ops.mh.cloud as cloud
    add_presets(ue)
    add_wardrobe(ue)
    monkeypatch.setenv("HOME", str(tmp_path))
    cred = tmp_path / ".local/share/.eos_sdk/keychain/abc/persistent_auth/credential"
    cred.parent.mkdir(parents=True)
    cred.write_text("x")
    monkeypatch.setattr(cloud, "POLL_S", 0)


def _setup_cam(ue, fmb, monkeypatch, tmp_path):
    for shape in ("Sphere", "Cylinder"):
        ue.add_asset(f"/Engine/BasicShapes/{shape}", "StaticMesh")


def _setup_foliage(ue, fmb, monkeypatch, tmp_path):
    for shape in ("Cone", "Sphere", "Cube"):
        ue.add_asset(f"/Engine/BasicShapes/{shape}", "StaticMesh")


def _setup_env(ue, fmb, monkeypatch, tmp_path):
    lum = 0.18 * 800 / 3.141592653589793

    class Px:
        def __init__(self, v):
            self.r = self.g = self.b = v
    # an RGBA8 target reads back 0..255 whatever normalize says (day 1), a float one raw
    ue.RenderingLibrary.read_render_target_raw = staticmethod(lambda world, rt, normalize=True:
                                                              [Px(0.46 * 255 if "RGBA8" in str(rt.fmt) else lum)] * 64)

    def still(**kw):
        """view.still on the fake: a flat grey PNG."""
        yield
        path = kw.get("out") or kw.get("path")
        _grey_png(path, 960, 540)
        return {"path": path, "width": 960, "height": 540}
    monkeypatch.setitem(fmb._OPS, "view.still", still)


def _setup_platform(ue, fmb, monkeypatch, tmp_path):
    from fmbridge import jobs, server
    from fmbridge.ops import editor
    reg = jobs.Registry(server._run, server._jsonable, str(tmp_path / "journal"), failure=server._failure_detail)
    monkeypatch.setitem(server._state, "registry", reg)
    monkeypatch.setattr(server, "JOURNAL", str(tmp_path / "journal"))
    monkeypatch.setitem(server._state, "throttle_off", True)
    monkeypatch.setitem(server._state, "engine", ue.engine_version)  # server.start() sets it on a box
    monkeypatch.setattr(editor, "_workers", lambda: 0)

    class Clock:  # wait_compile's settle time passes in a few ticks here
        t = 0.0

        @classmethod
        def time(cls):
            cls.t += 1.0
            return cls.t
    monkeypatch.setattr(editor, "time", Clock)
    monkeypatch.setattr(editor, "_rhi_from_log", lambda: "Vulkan RHI ShaderPlatform for SM6: VULKAN_SM6.")
    return reg.tick  # the bridge's jobs tick with the editor


def _setup_render(ue, fmb, monkeypatch, tmp_path):
    import importlib
    monkeypatch.setattr(fmb.seq, "cuts", lambda path: [["ST_render_CamA", 0, 24], ["ST_render_CamB", 24, 48]])
    monkeypatch.setattr(fmb.seq, "camera_cuts", lambda path, cuts: [[c, s, 48 if i else 24]
                                                                     for i, (c, s) in enumerate(cuts)])
    monkeypatch.setattr(fmb.seq, "new", lambda **k: ue.add_sequence(k["path"], k["start"], k["end"], k["fps"]) and {})
    monkeypatch.setitem(fmb._OPS, "seq.cuts", fmb.seq.cuts)
    for n in ("level.spawn", "look.light", "look.camera", "level.save"):
        monkeypatch.setitem(fmb._OPS, n, lambda **k: "ok")
    monkeypatch.setattr(fmb.render, "gpu_info", lambda max_age_s=2.0: {"name": "L4", "total_gb": 24.0, "used_gb": 4.0,
                                                                       "free_gb": 20.0, "util_pct": 1})
    ue.add_asset("/Game/_Selftest/render/L_Render", "World")
    st = importlib.import_module("fmbridge.selftest.render")
    monkeypatch.setattr(st, "_out_root", lambda: str(tmp_path / "render_out"))
    monkeypatch.setattr(st, "_psnr", lambda a, b: 50.0)

    def fake_compare(**k):  # the fake's frames are not real PNGs
        yield
        return {"pass": True, "metric": 1.0, "method": "qa"}
    monkeypatch.setitem(fmb._OPS, "render.compare", fake_compare)
    monkeypatch.setattr(st, "_build", lambda t, root, prefix: {
        "seq": (ue.add_sequence(root + "/SEQ_Render", 0, 48, 24,
                                cuts=[["ST_render_CamA", 0, 24], ["ST_render_CamB", 24, 48]]) and root + "/SEQ_Render"),
        "level": "/Game/_Selftest/render/L_Render", "cams": ["ST_render_CamA", "ST_render_CamB"]})

    # the cmdline executor's queue goes through the fake's missing MRQ editor library (as on the box): a queue asset
    ue.mrq.frames_per_tick = 4  # an L4 renders the draft frames this fast: the cancel step must not lose the race
    monkeypatch.setattr(fmb.render.subprocess, "Popen", _FakeProc)
    # the box as tested here has no ffmpeg (a dev machine may: the encode steps then skip the same way everywhere)
    which = fmb.render.shutil.which
    monkeypatch.setattr(fmb.render.shutil, "which", lambda name, *a, **k: None if name == "ffmpeg" else which(name, *a, **k))


def _setup_layout(ue, fmb, monkeypatch, tmp_path):
    """The engine's Plane is 100 x 100 x 0 cm; the fake gives every mesh a 50 cm half-size, so a floor would be a
    1 m slab and everything dropped on it would rest 50 cm high."""
    eas = _core.EditorActorSubsystem
    spawn0 = eas.spawn_actor_from_object

    def spawn(self, obj, location=None, rotation=None, transient=False):
        a = spawn0(self, obj, location, rotation, transient)
        if a is not None and obj is not None and obj.get_path_name().split(".")[0] == "/Engine/BasicShapes/Plane":
            object.__setattr__(a, "_extent", ue.Vector(50, 50, 0))
        return a
    monkeypatch.setattr(eas, "spawn_actor_from_object", spawn)


def _setup_seq(ue, fmb, monkeypatch, tmp_path):
    """A light's component is the object "LightComponent0" in the engine (Light.cpp:22, :187); the fake names it after
    its property (point_light_component), and the seq selftest keys it by the engine's name."""
    for cls in (ue.PointLight, ue.SpotLight, ue.RectLight):
        init0 = cls.__init__

        def init(self, *a, _init0=init0, **k):
            _init0(self, *a, **k)
            object.__setattr__(self._components[0], "_name", "LightComponent0")
        monkeypatch.setattr(cls, "__init__", init)


def _setup_wp(ue, fmb, monkeypatch, tmp_path):
    """The fake's new_level ignores is_partitioned_world: remember which levels asked for it, and on reopening one
    turn what was saved in it into fake.partition descriptors, unloaded (as a real partitioned level reopens)."""
    les = _core.LevelEditorSubsystem
    new0, load0 = les.new_level, les.load_level
    wp_levels = set()

    def new_level(self, asset_path, is_partitioned_world=False):
        ok = new0(self, asset_path, is_partitioned_world)
        ue.wp["descs"] = None
        if is_partitioned_world:
            wp_levels.add(asset_path)
        return ok

    def load_level(self, asset_path):
        if asset_path not in wp_levels:
            ue.wp["descs"] = None
            return load0(self, asset_path)
        saved = [a for a in ue.world.actors() if a.get_actor_label().startswith("ST_wp_")]
        descs = []
        for a in saved:
            o, e = a.get_actor_bounds()
            descs.append({"label": a.get_actor_label(), "cls": type(a).__name__, "loaded": False,
                          "bounds": [[o.x - e.x, o.y - e.y, o.z - e.z], [o.x + e.x, o.y + e.y, o.z + e.z]]})
        for a in saved:
            ue.world.remove(a)
        ok = load0(self, asset_path)
        ue.partition(descs)
        return ok
    monkeypatch.setattr(les, "new_level", new_level)
    monkeypatch.setattr(les, "load_level", load_level)


class _FakeProc:
    pid = 4242
    returncode = 0

    def __init__(self, argv, **kw):
        self.argv = argv
        self.stdout = self.stderr = io.BytesIO(b"")

    def poll(self):
        return 0


SETUP = {"assets": _setup_assets, "anim": _setup_anim, "mh": _setup_mh, "cam": _setup_cam, "foliage": _setup_foliage,
         "env": _setup_env, "platform": _setup_platform, "render": _setup_render, "wp": _setup_wp,
         "layout": _setup_layout, "seq": _setup_seq}


def _drive(gen, tick, budget_s):
    """The harness's loop: one fake editor tick per yield (plus the bridge's job tick), until the report comes back
    or the wall-clock budget runs out. Returns (report, ticks)."""
    n, end = 0, time.time() + budget_s
    while True:
        try:
            v = next(gen)
        except StopIteration as e:
            return e.value, n
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            time.sleep(min(float(v), 0.002))
        n += 1
        _core.FAKE.tick(1)
        if tick:
            tick()
        if time.time() > end:
            gen.close()
            raise AssertionError(f"still running after {budget_s:.0f}s ({n} ticks)")


def _broken(area):
    text, _ = KNOWN.get(area, ("\0", ""))
    with open(os.path.join(SELFTESTS, area + ".py")) as f:
        return text in f.read()


@pytest.mark.parametrize("area", [pytest.param(a, marks=pytest.mark.xfail(reason=KNOWN[a][1], strict=True))
                                  if _broken(a) else a for a in AREAS])
def test_selftest_dry_run(area, ue, fmb, tmp_path, monkeypatch):
    import fmbridge.selftest as st
    monkeypatch.setattr(st, "capabilities", lambda: {k: True for k in st.CAPABILITIES})
    _fake_stills(fmb, st, monkeypatch)
    ue.dialogs.clear()
    tick = (SETUP.get(area) or (lambda *a: None))(ue, fmb, monkeypatch, tmp_path)
    rep, ticks = _drive(st.run(area, str(tmp_path / "reports"), baseline="off"), tick, BUDGET_S)
    assert ue.dialogs == [], f"{area} would open a modal dialog on the box: {ue.dialogs}"
    assert not rep["errors"], f"{area}: " + "\n".join(f"[{e['where']}] {e['error'][-1500:]}" for e in rep["errors"])
    if rep["status"] == "skipped":
        assert area in SKIPS and SKIPS[area] in rep.get("skipped", ""), f"{area} skipped: {rep.get('skipped')}"
        return
    assert rep["status"] == "done", rep["status"]
    bad = [c for c in rep["checks"] if not c["ok"] and c["name"] not in FAKE_ONLY.get(area, ())]
    assert not bad, [{k: c.get(k) for k in ("name", "got", "want", "detail")} for c in bad]
    assert rep["passed"] > 0, f"{area}: no check passed"
    got = {c["name"]: c["ok"] for c in rep["checks"]}
    absent = sorted(n for n in REQUIRED.get(area, ()) if got.get(n) is not True)
    assert not absent, f"{area}: required checks missing or failed: {absent}"
    assert len(rep["checks"]) >= {"assets": 55, "platform": 25}.get(area, 1), len(rep["checks"])
    assert OPS_REQUIRED.get(area, set()) <= set(rep["ops_covered"]), OPS_REQUIRED[area] - set(rep["ops_covered"])
    if area in COVERAGE:
        prefixes, allowed = COVERAGE[area]
        allowed = set(allowed) | ({"render.encode"} if "no ffmpeg" in " ".join(rep["notes"]) else set())
        missed = [o for o in rep["ops_missed"] if o.startswith(prefixes) and o not in allowed]
        assert not missed, f"{area} selftest does not call {missed}"
    if area == "env":  # the meter on a grey card of known luminance (the fake's read_render_target_raw)
        assert abs(rep["extra"]["meter_offset_stops"]) < 0.01, rep["metrics"].get("meter_offset_stops")


def test_every_selftest_is_dry_run():
    """Discovery here and the harness's agree: a module the harness lists is a case above."""
    names = sorted(i.name for i in __import__("pkgutil").iter_modules([SELFTESTS]) if not i.name.startswith("_"))
    assert names == AREAS and len(AREAS) >= 15
    assert set(FAKE_ONLY) | set(REQUIRED) | set(OPS_REQUIRED) | set(COVERAGE) | set(SKIPS) | set(KNOWN) | set(SETUP) <= set(AREAS)
