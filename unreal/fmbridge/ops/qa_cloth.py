"""qa.cloth: is a garment's cloth simulation sound, and is it alive? (round 5: "his chest looks like he wore some heavy
armour": the tee never simulated, and no check measured it.)

Two passes over the same frames in the live level, through the FMCloth plugin's simulated positions:
- reference: the max distance scaled to 0, so every particle sits where the body's skinning puts it;
- simulated: scale 1, the cloth reset and pre-rolled (held on the first frame for the preset's settle time, as MRQ's
  warm-up does), then stepped one frame per tick.
fmbridge.qa.cloth.judge compares them per zone (explosion, NaN, velocity spikes, dead/armour, anchor slip, jitter,
cold start). Penetration under simulation is qa.clip's (agent-02): run it on the same frames after cloth.preroll.
"""
from __future__ import annotations

import unreal

from . import op
from .assets import EAL
from ..errors import OpError
from ..clothkit import paint as _paint
from ..clothkit import preroll as _preroll
from ..qa import cloth as _qcloth
from ..qa.issues import issue
from . import cloth as C

PRESET_TAG = "FMClothPreset"   # cloth.setup tags the garment mesh with its preset


def _read(L, comp, idx: list) -> list:
    pts = L.simulated_positions(comp)
    return [(pts[i].x, pts[i].y, pts[i].z) for i in idx] if pts and len(pts) > max(idx) else []


@op("qa.cloth", mutates=False, idempotent=True, tags=["cloth", "qa", "slow", "experimental"])
def cloth(*, label: str, component: str, sequence: str, start: int, end: int, preset: str = "", samples: int = 1500,
          settle: int = 0, fps: float = 24.0, **thresholds):
    """Judge a garment's cloth over frames [start, end) of a sequence: sound (no explosion, NaN, velocity spikes,
    anchor slip, jitter, cold start) and ALIVE (the hem and sleeves move relative to the body while it moves: not
    armour). Multi-tick; ~2 x (end - start + settle) ticks. Needs the FMCloth plugin (simulated positions).

    Args: label/component: the garment (cloth.describe). sequence: the level sequence. start/end: frames (one shot,
    or a gesture inside it: alive needs the body to move >= 2 cm). preset: the garment's cloth preset (default: the
    one cloth.setup tagged on the mesh). samples: vertices read per frame. settle: pre-roll frames (0 = the preset's).
    thresholds: any fmbridge.qa.cloth.DEFAULTS key (alive_min_cm=0.15, spike_cm_s=120, ...).
    Returns: {"pass", "verdict", "issues", "metrics": {"zones": {zone: {"drape_cm", "motion_cm", "slip_cm",
    "body_path_cm", "jitter_cm"}}, "max_disp_cm", "max_speed_cm_s", ...}, "solver"}.
    Example: film-ue op qa.cloth label=Host component=Torso sequence=/Game/Reel/SEQ_Reel start=1000 end=1060
    """
    from ._scrub import set_frame
    from . import call
    bad = [k for k in thresholds if k not in _qcloth.DEFAULTS]
    if bad:
        raise OpError(f"unknown threshold(s) {bad}", code="bad_args", candidates=sorted(_qcloth.DEFAULTS))
    if end - start < 3:
        raise OpError("need at least 3 frames (end - start >= 3)", code="bad_args")
    comp = C.garment(label, component)
    mesh = comp.get_skeletal_mesh_asset()
    if not C.clothing_assets(mesh):
        return {"pass": False, "verdict": "fail", "issues": [issue(
            "cloth.no_clothing", "fail", f"{label}.{component} has no clothing data: it is skinned only (armour)",
            f"film-ue op cloth.setup label={label} component={component} preset=cotton_tee", subject=f"{label}.{component}")],
            "metrics": {}}
    L = C._need_plugin()
    name = preset or EAL.get_metadata_tag(mesh, PRESET_TAG) or "cotton_tee"
    p = C._preset(name)
    cloth_asset = C.clothing_assets(mesh)[0]
    rest = [(v.x, v.y, v.z) for v in L.rest_vertices(cloth_asset, 0)]
    md = list(L.get_weight_map(cloth_asset, 0, "MaxDistance") or [])
    if not rest:
        raise OpError("the clothing asset has no simulation vertices", code="engine")
    heads, parents = C.bones(mesh)
    segs = _paint.bone_segments(heads, parents)
    zones = [z for z, _ in _paint.assign(rest, segs, p)]
    idx = _qcloth.sample(len(rest), int(samples), zones)
    n_settle = int(settle) or _preroll.need_frames(p["settle_s"], fps)
    frames = list(range(int(start), int(end)))
    comp.set_editor_property("wait_for_parallel_cloth_task", True)
    # the editor world ticks cloth only when asked (bUpdateClothInEditor: SkeletalMeshComponentPhysics.cpp:83, 3148);
    # without it the simulation data never changes (round 5: not_simulating, body_path 0)
    C.editor_cloth(comp)
    for _ in range(3):
        yield
    scale0 = comp.get_cloth_max_distance_scale()
    runs = {}
    try:
        for which, scale in (("skin", 0.0), ("sim", 1.0)):
            comp.set_cloth_max_distance_scale(scale)
            call("seq.scrub", path=sequence, frame=frames[0])
            yield
            comp.force_cloth_next_update_teleport_and_reset()
            for f in _preroll.live_steps(frames[0], n_settle, "hold")[:-1]:
                set_frame(f)
                yield
            got = []
            for f in frames:
                set_frame(f)
                yield
                got.append(_read(L, comp, idx))
            runs[which] = got
    finally:
        comp.set_cloth_max_distance_scale(scale0 if scale0 is not None else 1.0)
    subject = f"{label}.{component}"
    stats = C.solver_stats(comp)
    if stats.get("sim_time_ms", 1.0) == 0.0 and stats.get("dynamic_particles", 0) > 0:
        return {"pass": False, "verdict": "fail", "issues": [issue(
            "cloth.no_steps", "fail", f"{subject}: the solver reports no simulation time over {len(frames)} frames: "
            "the editor world did not tick the cloth", "check set_update_cloth_in_editor and that the editor ticks "
            "(t.MaxFPS); report it", subject=subject)], "metrics": {}, "solver": stats}
    if any(not r for r in runs["sim"]) or any(not r for r in runs["skin"]):
        return {"pass": False, "verdict": "fail", "issues": [issue(
            "cloth.not_simulating", "fail", f"{subject}: no simulated positions on some frames (the cloth is "
            "disabled, suspended, or drawn at a LOD without clothing)",
            f"film-ue op cloth.describe label={label} component={component}; cloth.settings", subject=subject)],
            "metrics": {}, "solver": C.solver_stats(comp)}
    hem = _qcloth.hem_mask([rest[i] for i in idx], [zones[i] for i in idx], p["free"], p["hem_band_cm"])
    r = _qcloth.judge(frames, runs["sim"], runs["skin"], [zones[i] for i in idx],
                      [md[i] if i < len(md) else 0.0 for i in idx], fps=fps, free=p["free"], pinned=p["pinned"],
                      hem=hem, subject=subject, **thresholds)
    r["solver"] = C.solver_stats(comp)
    r["preset"] = name
    r["settle_frames"] = n_settle
    return r
