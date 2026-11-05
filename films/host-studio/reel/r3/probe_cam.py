"""Read-only: what each reel camera really is on given frames of SEQ_Reel (agent-11's camera probe, round 3). It
compares the engine's camera with shots.py/motion.py's plan for the shot: location, rotation, focal, filmback, fields
of view, and which camera the cut track picks. It changes nothing (no keys, no save; it only moves the playhead).

    cd tools && uv run python ../films/host-studio/reel/r3/probe_cam.py V05 [--frames 600,660,719]
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
            b = s.get_camera_binding_id()
            cuts.append([s.get_start_frame(), s.get_end_frame(), str(seq.get_binding_display_name(b) if hasattr(seq, "get_binding_display_name") else b)])
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
            "hfov": round(c.get_horizontal_field_of_view(), 2), "vfov": round(c.get_vertical_field_of_view(), 2),
            "constrain": c.get_editor_property("constrain_aspect_ratio"),
            "focus": round(c.get_editor_property("current_focus_distance"), 1)}
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("shot")
    ap.add_argument("--frames", default="")
    a = ap.parse_args()
    shot = next(s for s in SHOTS if s.id == a.shot)
    frames = [int(x) for x in a.frames.split(",")] if a.frames else [shot.start, shot.start + shot.frames // 2,
                                                                      shot.end - 1]
    res = client.exec_code(f"SEQ = {SEQ!r}\nLABEL = {'Reel_' + shot.id!r}\nFRAMES = {frames!r}\n" + CODE)
    if not res.get("ok"):
        raise SystemExit(res.get("stdout", "") + res.get("error", ""))
    print(json.dumps({"plan": plan(shot, set(frames)), "engine": res["result"]}, indent=1, default=str))


if __name__ == "__main__":
    main()
