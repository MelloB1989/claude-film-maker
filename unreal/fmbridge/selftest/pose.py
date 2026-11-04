"""B31's acceptance test: named poses on a real body rig, measured.

It finds a character to pose: a skeletal mesh with a pelvis whose Control Rig Blueprint the project has (a
MetaHuman body: its rig is found in the asset registry by name: body/MetaHuman/ControlRig), spawns it in the
scratch level, makes a sequence and a Control Rig track, and for hands_on_hips, arms_crossed, wave and sit: poses it
at a frame (pose.apply) and checks every effector within 1.5 cm of its goal (pose.check), that the feet stayed
planted, that a second apply does nothing, and takes a still per pose. It also lists the rig's controls and which
ones the pattern match chose (the first thing to read when a pose misses).

Takes about 1-2 minutes. Needs: a GPU for stills; a body Control Rig and its skeletal mesh in the project (else it
is skipped with a note: e.g. a MetaHuman character asset). Leaves nothing outside /Game/_Selftest/pose.
"""
from __future__ import annotations

import unreal
from ..ops.assets import EAL  # EditorAssetLibrary, or the EditorAssetSubsystem when its plugin is off

REQUIRES: list = []
AREAS = ["pose"]
NEEDS_LEVEL = True
TIMEOUT = 600


def _find_rig_and_mesh():
    """(Control Rig Blueprint path, skeletal mesh path) for a body, or (None, why)."""
    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    rigs = []
    cands = []
    for mod, cls in (("/Script/ControlRigDeveloper", "ControlRigBlueprint"), ("/Script/ControlRig", "ControlRigBlueprint")):
        try:  # ControlRigBlueprintLegacy.h:34 in 5.8; the asset class may move, so also scan by class name below
            cands += list(ar.get_assets_by_class(unreal.TopLevelAssetPath(mod, cls), True) or [])
        except Exception:
            pass
    if not cands:
        cands = [a for a in ar.get_assets_by_path("/Game", True) or []
                 if "ControlRig" in str(a.asset_class_path.asset_name)]
    for a in cands:
        p = str(a.package_name)
        n = p.rsplit("/", 1)[-1].lower()
        if "face" in n:
            continue
        if any(k in n for k in ("body", "metahuman_controlrig", "mannequin", "manny", "quinn")):
            rigs.append(p)
    meshes = []
    for a in ar.get_assets_by_class(unreal.TopLevelAssetPath("/Script/Engine", "SkeletalMesh"), True) or []:
        p = str(a.package_name)
        n = p.rsplit("/", 1)[-1].lower()
        if any(k in n for k in ("body", "manny", "quinn", "mannequin")) and "face" not in n:
            meshes.append(p)
    if not rigs or not meshes:
        return None, f"no body Control Rig ({len(rigs)}) or body skeletal mesh ({len(meshes)}) in the project"
    return (sorted(rigs, key=len)[0], sorted(meshes, key=len)[0]), ""


def run(t):
    found, why = _find_rig_and_mesh()
    if not found:
        t.skip(why)
    rig_class, mesh = found
    t.note(f"rig {rig_class}, mesh {mesh}")
    P = t.prefix
    who = P + "Body"
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    a = eas.spawn_actor_from_object(EAL.load_asset(mesh), unreal.Vector(0, 0, 0),
                                    unreal.Rotator(roll=0.0, pitch=0.0, yaw=0.0))
    a.set_actor_label(who)
    seq = f"{str(t.scratch).rstrip('/')}/{P}Seq"
    t.op("seq.new", path=seq, start=0, end=120, fps=24, replace=True)
    t.op("cam.add", label=P + "Cam", loc=[320, 0, 120], look_at=[0, 0, 100], focal_mm=35)
    first = True
    for k, (pose, params) in enumerate((("hands_on_hips", None), ("arms_crossed", None), ("wave", None),
                                        ("sit", {"drop_cm": 40}))):
        frame = 20 + 25 * k
        r = yield from t.op("pose.apply", label=who, sequence=seq, frame=frame, pose=pose, params=params,
                            rig_class=rig_class if first else "", tolerance_cm=1.0, iterations=10)
        if first:
            ctrls = t.op("anim.rig_controls", sequence=seq, label=who)["controls"]
            t.note(f"rig controls ({len(ctrls)}): {ctrls[:40]}")
            t.note(f"pattern match chose: {r['controls']}")
            first = False
        t.metric(f"{pose}_iterations", r["iterations"])
        t.metric(f"{pose}_max_error_cm", max(r["errors_cm"].values()))
        t.ok(f"{pose}: every effector within tolerance", r["pass"], detail=str(r["errors_cm"]))
        c = yield from t.op("pose.check", label=who, sequence=seq, frame=frame, pose=pose, params=params,
                            tolerance_cm=1.5)
        t.note(f"pose.check {pose}: {c['metrics']['errors_cm']}")
        feet = [r["errors_cm"].get("foot_l"), r["errors_cm"].get("foot_r")]
        t.ok(f"{pose}: feet planted", all(f is None or f < 2.0 for f in feet), detail=str(feet))
        again = yield from t.op("pose.apply", label=who, sequence=seq, frame=frame, pose=pose, params=params)
        t.check(f"{pose}: a second apply changes nothing", again["iterations"], 0)
        try:
            unreal.LevelSequenceEditorBlueprintLibrary.set_current_time(frame)
            yield from t.still(f"pose_{pose}", camera=P + "Cam")
        except Exception as e:
            t.note(f"no still: {e}")
    unreal.LevelSequenceEditorBlueprintLibrary.close_level_sequence()
