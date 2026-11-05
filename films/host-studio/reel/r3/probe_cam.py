"""Read-only: what each reel camera really is on given frames of SEQ_Reel (agent-11's camera probe, round 3). It
compares the engine's camera with shots.py/motion.py's plan for the shot: location, rotation, focal, filmback, fields
of view, and which camera the cut track picks. It changes nothing (no keys, no save; it only moves the playhead).

    cd tools && uv run python ../films/host-studio/reel/r3/probe_cam.py V05 [--frames 600,660,719]
    cd tools && uv run python ../films/host-studio/reel/r3/probe_cam.py V01,V02,V03,V05 --check   # a pre-render gate

--check prints one line per shot and exits 1 when a camera is off its plan (more than 1 cm, 0.1 deg, 0.05 mm of focal
or of filmback) or when a shot has more or fewer than one camera actor.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from filmtools.unreal import client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import motion as M  # noqa: E402
from shots import FULL_FRAME, SHOTS  # noqa: E402

SEQ = "/Game/Reel/SEQ_Reel"

CODE = r"""
import unreal
LSE = unreal.LevelSequenceEditorBlueprintLibrary
seq = unreal.load_asset(SEQ)
LSE.open_level_sequence(seq)
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
same = [a for a in EAS.get_all_level_actors() if a.get_actor_label().startswith(LABEL)]
out = {"actors": [[a.get_actor_label(), a.get_class().get_name(), a.get_path_name()] for a in same], "frames": {}}
cuts = []
for t in seq.get_tracks():
    if t.get_class().get_name() == "MovieSceneCameraCutTrack":
        for s in t.get_sections():
            try:
                b = s.get_camera_binding_id()
                g = b.get_editor_property("guid").export_text()  # the cut's binding, matched to the sequence's by guid
                who = [str(x.get_display_name()) for x in seq.get_bindings() if x.get_id().export_text() == g]
                cuts.append([s.get_start_frame(), s.get_end_frame(), who or g])
            except Exception as e:
                cuts.append([s.get_start_frame(), s.get_end_frame(), "?: " + str(e)[:120]])
out["cuts"] = cuts
for f in FRAMES:
    LSE.set_current_time(f)
    LSE.refresh_current_level_sequence()
    row = {}
    for a in same:
        c = a.get_cine_camera_component()
        p, r = c.get_world_location(), c.get_world_rotation()
        fb = c.get_editor_property("filmback")
        la = c.get_editor_property("lens_settings")
        row[a.get_actor_label()] = {"loc": [round(p.x, 1), round(p.y, 1), round(p.z, 1)],
            "rot": [round(r.pitch, 2), round(r.yaw, 2), round(r.roll, 2)],
            "focal": round(c.get_editor_property("current_focal_length"), 2),
            "filmback": [fb.sensor_width, fb.sensor_height],
            "hfov": round(c.get_horizontal_field_of_view(), 2) if hasattr(c, "get_horizontal_field_of_view") else None,
            "vfov": round(c.get_vertical_field_of_view(), 2) if hasattr(c, "get_vertical_field_of_view") else None,
            "constrain": c.get_editor_property("constrain_aspect_ratio"),
            "focus": round(c.get_editor_property("focus_settings").get_editor_property("manual_focus_distance"), 1)}  # the keyed value (current_focus_distance only updates on tick)
    out["frames"][f] = row
result = out
"""


def plan(shot, frames):
    out = {}
    for f, loc, pitch, yaw, focus in M.samples(shot, M.HANDLE):
        if shot.start + f in frames:
            out[shot.start + f] = {"loc": [round(v, 1) for v in loc], "rot": [round(pitch, 2), round(yaw % 360, 2)],
                                   "focal": shot.lens, "filmback": list(FULL_FRAME),
                                   "hfov": round(math.degrees(2 * math.atan(FULL_FRAME[0] / 2 / shot.lens)), 2),
                                   "focus": round(focus, 1)}
    return out


def off(plan_row: dict, eng: dict) -> list:
    """What differs between the plan and the engine's camera at one frame (empty when it is on plan)."""
    bad = []
    if max(abs(p - q) for p, q in zip(plan_row["loc"], eng["loc"])) > 1.0:
        bad.append(f"loc {eng['loc']} (plan {plan_row['loc']})")
    dy = (eng["rot"][1] - plan_row["rot"][1] + 180) % 360 - 180
    if abs(eng["rot"][0] - plan_row["rot"][0]) > 0.1 or abs(dy) > 0.1:
        bad.append(f"rot {eng['rot'][:2]} (plan {plan_row['rot']})")
    if abs(eng["focal"] - plan_row["focal"]) > 0.05:
        bad.append(f"focal {eng['focal']} (plan {plan_row['focal']})")
    if max(abs(p - q) for p, q in zip(eng["filmback"], plan_row["filmback"])) > 0.05:
        bad.append(f"filmback {eng['filmback']} (plan {plan_row['filmback']})")
    return bad


def probe(shot, frames: list) -> dict:
    res = client.exec_code(f"SEQ = {SEQ!r}\nLABEL = {'Reel_' + shot.id!r}\nFRAMES = {frames!r}\n" + CODE)
    if not res.get("ok"):
        raise SystemExit(res.get("stdout", "") + res.get("error", ""))
    return {"plan": plan(shot, set(frames)), "engine": res["result"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("shots", help="shot ids, comma-separated")
    ap.add_argument("--frames", default="")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    bad_any = False
    for sid in a.shots.split(","):
        shot = next(s for s in SHOTS if s.id == sid)
        frames = [int(x) for x in a.frames.split(",")] if a.frames else [shot.start, shot.start + shot.frames // 2,
                                                                          shot.end - 2]  # keyed (even) frames
        got = probe(shot, frames)
        if not a.check:
            print(json.dumps(got, indent=1, default=str))
            continue
        lab, eng = f"Reel_{sid}", got["engine"]
        bad = [] if [x[0] for x in eng["actors"]] == [lab] else [f"actors {[x[0] for x in eng['actors']]}"]
        for f, row in got["plan"].items():
            e = eng["frames"].get(f) or eng["frames"].get(str(f), {})
            bad += [f"f{f} " + b for b in (off(row, e[lab]) if lab in e else ["no camera"])]
        print(sid, "OK" if not bad else "OFF: " + "; ".join(bad), flush=True)
        bad_any = bad_any or bool(bad)
    raise SystemExit(1 if bad_any else 0)


if __name__ == "__main__":
    main()
