"""WP4's acceptance test: animation and performance, measured in the editor.

It proves, in a scratch level:
- the library: anim.find ranks the MetaHuman template animations (a walk loop for "walk forward loop", a face
  expression loop for "happy face"), anim.describe reads their length, rate, skeleton and face curves;
- curves round-trip exactly: anim.new makes an empty animation on the face skeleton (converges on a re-run),
  anim.write_curves writes 30 curves in one batch and anim.read_curves reads the same keys back; "add" adds;
- perf.face turns a face loop into a living copy without touching its mouth curves, and the naturalness numbers
  (anim.check) pass on the result while a robotic head (keyed straight lines) fails them;
- additive: anim.additive makes a local-space additive copy based on its first frame;
- on a face mesh in the level (spawned from the template face loop's skeleton), Sequencer really plays the curves:
  perf.calibrate measures which way HeadYaw/Pitch/Roll and eyeLook* turn the head and eyes (it fails loudly if the
  head curves do not move the head), and a PERFORMANCE spec applied with perf.apply makes the head bone turn toward
  a gaze target (sampled with seq.sample), converges (a second apply runs nothing), and perf.describe reads it back;
- errors are actionable (a misspelt animation, an unknown expression preset, a bad spec);
- stills of the face at rest and turned (artifacts).

Takes about 1-2 minutes. Needs: the MetaHuman plugin's optional content (/MetaHumanCharacter/Optional/Animation)
and a GPU for the stills; no Epic login. Leaves nothing outside /Game/_Selftest/anim (and
Saved/fmbridge/perf/signs_<face skeleton>.json, the calibration, which is meant to stay).
"""
from __future__ import annotations

import math
import os
import struct
import wave

import unreal

REQUIRES = ["gpu"]
AREAS = ["anim", "perf"]
NEEDS_LEVEL = True
TIMEOUT = 900

MH = "/MetaHumanCharacter/Optional/Animation"
FACE_LOOP = MH + "/TemplateAnimations/Expression_Loops/HappyA/mhc_mh002_fmn_f_facialloop_happy_f_s001"
BODY_IDLE = MH + "/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle"
from ..ops.assets import EAL  # EditorAssetLibrary, or the EditorAssetSubsystem when its plugin is off


def _wav(path: str, seconds: float = 3.0, sr: int = 16000) -> str:
    """A voice-like test tone: syllables at 0.3 loudness with a loud one each second and pauses between phrases."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        out = bytearray()
        for i in range(int(seconds * sr)):
            ph = (i / sr) % 1.0
            amp = 0.0 if ph > 0.7 else (1.0 if 0.3 < ph < 0.4 else 0.3)
            out += struct.pack("<h", int(amp * 15000 * math.sin(2 * math.pi * 180 * i / sr)))
        w.writeframes(bytes(out))
    return path


def _face_mesh(skeleton: str) -> str:
    """A SkeletalMesh on `skeleton` under /MetaHumanCharacter (the asset registry's Skeleton tag), or ""."""
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    flt = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "SkeletalMesh")],
                          package_paths=["/MetaHumanCharacter"], recursive_paths=True)
    for ad in reg.get_assets(flt) or []:
        v = ad.get_tag_value("Skeleton")
        v = v[-1] if isinstance(v, tuple) else v
        if v and skeleton in str(v):
            return str(ad.package_name)
    return ""


def run(t):
    P = t.prefix
    s = getattr(t, "scratch", None)
    root = str((s() if callable(s) else s) or "/Game/_Selftest/anim").rstrip("/")
    if not EAL.does_asset_exist(FACE_LOOP):
        t.skip(f"no MetaHuman optional content ({FACE_LOOP}): enable the MetaHuman plugin's content")

    # --- 1. the library ------------------------------------------------------------------------------------------
    r = t.op("anim.find", query="walk forward loop", path="/MetaHumanCharacter", limit=5)
    t.ok("find.walk", r["found"] and r["found"][0]["path"].endswith("Walk_Loop_F"), detail=r["found"][:3])
    r = t.op("anim.find", query="happy face loop", path="/MetaHumanCharacter", kind="face", limit=5)
    t.ok("find.happy_face", r["found"] and r["found"][0]["emotion"] == "happy" and r["found"][0]["kind"] == "face",
         detail=r["found"][:3])
    d = t.op("anim.describe", anim=FACE_LOOP)
    t.ok("describe.face_curves", d["face_curves"] > 100, detail=d)
    t.ok("describe.length", d["length_s"] > 0.5 and d["frames"] > 10, detail=d)
    skel = d["skeleton"]
    t.metric("face_loop_s", d["length_s"], "s")

    # --- 2. curves round-trip, in batches ----------------------------------------------------------------------
    blank = f"{root}/AS_{P}blank"
    r = t.op("anim.new", path=blank, skeleton=skel, length_s=2.0, fps=30)
    t.check("new.frames", r["frames"], 61, tol=1)
    t.idempotent("new.converges", "anim.new", path=blank, skeleton=skel, length_s=2.0, fps=30)
    names = sorted(d.get("curves") or t.op("anim.describe", anim=FACE_LOOP, curves=True)["curves"])[:30]
    want = {n: [[0.0, 0.5, 1.0, 2.0], [0.0, 0.1 * (i % 7), 0.05, 0.0]] for i, n in enumerate(names)}
    w = t.op("anim.write_curves", anim=blank, curves=want)
    t.check("write.curves", w["curves"], 30)
    got = t.op("anim.read_curves", anim=blank, names=names)
    t.check("read.round_trip", {n: got[n] for n in names}, want, tol=1e-4)
    t.op("anim.write_curves", anim=blank, curves={names[0]: [[0.0, 2.0], [0.2, 0.2]]}, mode="add")
    got = t.op("anim.read_curves", anim=blank, names=[names[0]])
    t.check("write.add", got[names[0]][1][:2], [0.2, 0.2], tol=1e-4)

    # --- 3. a living face: perf.face, and the numbers that judge it --------------------------------------------
    wav = _wav(os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()),
                            "Selftest", "anim", "line.wav"), seconds=min(4.0, d["length_s"]))
    a = t.op("perf.analyze_audio", wav=wav)
    t.ok("audio.emphasis", len(a["emphasis"]) >= 2 and len(a["pauses"]) >= 2, detail=a["emphasis"])
    src = f"{root}/AS_{P}face_src"
    EAL.duplicate_asset(FACE_LOOP, src)
    out = f"{root}/AS_{P}face_perf"
    f = t.op("perf.face", anim=src, out=out, wav=wav, mood="warm",
             gaze=[{"t": 0.0, "yaw": 0.0, "scan": "lens"}, {"t": 1.0, "yaw": 25.0, "pitch": -5.0}], seed=4)
    before = t.op("anim.read_curves", anim=src, contains="mouthLips")
    after = t.op("anim.read_curves", anim=out, contains="mouthLips")
    t.ok("face.mouth_untouched", before and all(after.get(k) == v for k, v in before.items()),
         detail=sorted(before)[:5])
    chk = t.op("anim.check", anim=out)
    t.ok("face.alive", not (set(chk["failed"]) - {"expression_range"}), detail=chk["failed"])
    robot = f"{root}/AS_{P}robot"
    t.op("anim.new", path=robot, skeleton=skel, length_s=8.0)
    t.op("anim.write_curves", anim=robot, curves={"HeadYaw": [[0, 1, 2, 3, 4, 5, 6, 7, 8], [0, 10, 10, -10, -10, 0, 0, 12, 0]],
                                                    "HeadPitch": [[0, 8], [0, 0]], "HeadRoll": [[0, 8], [0, 0]]})
    chk = t.op("anim.check", anim=robot)
    t.ok("check.catches_robot", "head_linear" in chk["failed"] and "frozen_head" in chk["failed"], detail=chk["failed"])
    t.metric("blinks_per_min", f["report"]["blinks"].get("per_min"), "1/min")

    # --- 4. additive ----------------------------------------------------------------------------------------------
    if EAL.does_asset_exist(BODY_IDLE):
        r = t.op("anim.additive", anim=BODY_IDLE, out=f"{root}/AS_{P}idle_add")
        t.ok("additive.type", "LOCAL_SPACE" in r["type"].upper(), detail=r)

    # --- 5. errors an agent can act on -------------------------------------------------------------------------
    t.raises("error.missing_anim", "anim.describe", code="not_found", anim=FACE_LOOP + "x")
    t.raises("error.bad_preset", "perf.face", code="bad_args", anim=src, out=out,
             expressions=[{"preset": "smiel", "t": 0, "until": 1}])
    t.raises("error.bad_spec", "perf.plan", code="bad_args",
             spec={"kind": "performance", "version": 1, "name": "x", "sequence": "/Game/X", "actor": "A",
                   "lines": [{"id": "a", "mood": "grumpy"}]})

    # --- 6. on a face in the level: calibration and a whole performance ---------------------------------------
    mesh = _face_mesh(skel)
    if not mesh:
        t.note(f"no face SkeletalMesh on {skel} under /MetaHumanCharacter: level part skipped")
        return {"face_loop": FACE_LOOP}
    face = P + "Face"
    t.op("level.spawn", label=face, asset=mesh, loc=[0, 0, 0])
    comp = _actor(face).get_components_by_class(unreal.SkeletalMeshComponent)[0].get_name()
    cam = P + "Cam"
    head = _actor(face).get_components_by_class(unreal.SkeletalMeshComponent)[0].get_socket_location("head")
    t.op("level.spawn", label=cam, cls="CineCameraActor", loc=[head.x + 80, head.y, head.z])
    t.op("level.move", label=cam, look_at=[head.x, head.y, head.z])
    try:
        cal = yield from t.op("perf.calibrate", label=face, face_component=comp, scratch=root + "/Calibrate")
        sg = cal["signs"]
        t.ok("calibrate.measured", sg["measured"] and all(abs(sg[k]) == 1 for k in ("yaw", "pitch", "roll")), detail=cal)
        t.ok("calibrate.eye_gains", all(5 < v < 60 for v in sg["eye_deg"].values()), detail=sg["eye_deg"])
    except Exception as e:  # recorded; the spec part below still runs on the default signs
        t.ok("calibrate.measured", False, detail=str(e)[:500])
    seqp = f"{root}/LS_{P}perf"
    spec = {"kind": "performance", "version": 1, "name": f"{P}perf", "sequence": seqp, "actor": face,
            "face_component": comp, "camera": cam, "fps": 24, "seed": 2,
            "face": {"out": f"{root}/AS_{P}perf_face", "solve_folder": root + "/Speech"},
            "lines": [{"id": "l1", "face_anim": src, "mood": "warm",
                       "gaze": [{"at_s": 0, "target": "camera"}, {"at_s": 1.0, "target": {"yaw": 35, "pitch": 0}}]},
                      {"id": "l2", "duration_s": 1.5, "listen": True, "gaze": [{"at_s": 0, "target": "camera"}]}]}
    r = yield from t.op("perf.apply", spec=spec)
    t.ok("apply.converged", r.get("converged"), detail={k: r.get(k) for k in ("rounds", "ran")})
    r2 = yield from t.op("perf.apply", spec=spec)
    t.ok("apply.idempotent", r2.get("converged") and not r2.get("ran"), detail=r2.get("ran"))
    desc = t.op("perf.describe", sequence=seqp, label=face, face_component=comp)
    t.ok("describe.face_section", desc["face"] and desc["face"][0]["anim"] == f"{root}/AS_{P}perf_face", detail=desc)
    smp = yield from t.op("seq.sample", path=seqp, actor_label=face, component=comp, bones=["head"],
                          frames=[6, 60], ticks=3)
    h0, h1 = smp["bones"]["head"]
    fwd0, fwd1 = h0[3:6], h1[3:6]
    ang = math.degrees(math.acos(max(-1.0, min(1.0, sum(a * b for a, b in zip(fwd0, fwd1))))))
    t.ok("head.turns_to_target", ang > 8.0, detail=f"head axis turned {ang:.1f} deg between frames 6 and 60")
    t.metric("head_turn_deg", round(ang, 2), "deg")
    t.op("seq.scrub", path=seqp, frame=6)
    yield from t.still("rest", camera=cam, width=480, height=270)
    t.op("seq.scrub", path=seqp, frame=60)
    yield from t.still("turned", camera=cam, width=480, height=270)
    t.op("seq.close")
    return {"face_loop": FACE_LOOP, "face_mesh": mesh, "component": comp}


def _actor(label: str):
    from fmbridge.ops._util import actor
    return actor(label)
