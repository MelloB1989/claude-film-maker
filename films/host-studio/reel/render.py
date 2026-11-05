"""The reel's renders (task R7): each shot of /Game/Reel/SEQ_Reel through Movie Render Queue, one shot per call so
the bridge is free between them, into Saved\\MovieRenders\\reel_<res>\\<shot>\\<master frame:04d>.png on the
workstation (agent-07's cut pulls them from there through S3). Frames are numbered by the master sequence's frame
(S03 = 0240..0299), the shot's own range [start, end), plus PREROLL frames before it: the first frame of a shot
rendered cold carries the previous shot's temporal history (a double exposure); the cut ignores the pre-roll.

    cd tools && uv run python ../films/host-studio/reel/render.py --shots S01,S02 [--res 1080|2160] [--samples 8]
    cd tools && uv run python ../films/host-studio/reel/render.py --shots S14 --frames 24   # a calibration chunk
    cd tools && uv run python ../films/host-studio/reel/render.py --shots N01 --at 946 --frames 8   # a mid-shot test

Run studio.py, rig.py, build.py and light.py --seq first (PLAN.md section 5). Quality as the plan's: Lumen deferred,
render.QUALITY_CVARS, the hair strands' sky light off, motion blur from the cameras, `--samples` temporal samples.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from filmtools.unreal import client

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from shots import SHOTS  # noqa: E402

SEQ = "/Game/Reel/SEQ_Reel"
LEVEL = "/Game/Studio/Studio"
PROJECT = r"C:\UEProjects\HostStudio"
CVARS = {"r.HairStrands.SkyLighting": 0}
PREROLL = 4
CAST = ("Host", "Presenter")
# Note 3 (round 3): her hair shortened at the shoulders at the end of S17's crane out (v2 45 s cut 0:39-0:40, master
# f1416-1440): the groom dropped to a coarser LOD as she got smaller in frame. MRQ's lod_zero pins meshes, not grooms,
# so every presenter's LODSync, grooms and skeletal meshes are pinned to LOD 0 before each job (on the placed actors:
# PIE duplicates the editor world, so the render world has them). Each step is tried; the result says what took.
PIN_LOD0 = """
import unreal
done = {}
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    lab = a.get_actor_label()
    if lab not in LABELS:
        continue
    r = done.setdefault(lab, [])
    for c in a.get_components_by_class(unreal.LODSyncComponent) if hasattr(unreal, "LODSyncComponent") else []:
        try:
            c.set_editor_property("forced_lod", 0)
            r.append(f"lodsync {c.get_name()}")
        except Exception as e:
            r.append(f"lodsync {c.get_name()} ERR {e}")
    for c in a.get_components_by_class(unreal.GroomComponent):
        try:
            c.set_forced_lod(0)
            r.append(f"groom {c.get_name()}")
        except Exception as e:
            r.append(f"groom {c.get_name()} ERR {e}")
    for c in a.get_components_by_class(unreal.SkeletalMeshComponent):
        try:
            c.set_forced_lod(1)  # SkinnedMeshComponent: 0 = auto, N = LOD N-1
            r.append(f"skel {c.get_name()}")
        except Exception as e:
            r.append(f"skel {c.get_name()} ERR {e}")
result = done
"""


def ok(res: dict):
    if not res.get("ok"):
        raise SystemExit(res.get("stdout", "") + res.get("error", ""))
    return res.get("result")


def remote(sid: str, res: int) -> str:
    return rf"{PROJECT}\Saved\MovieRenders\reel_{res}p\{sid}"


def render(sid: str, res: int, samples: int, frames: int = 0, at: int = 0) -> dict:
    s = next(x for x in SHOTS if x.id == sid)
    first = at or s.start
    end = first + frames if frames else s.end
    out = remote(sid, res) + (f"_t{at}" if at else "")  # a mid-shot test keeps the shot's own dir
    ok(client.exec_code(f"import shutil\nshutil.rmtree({out!r}, ignore_errors=True)\nresult = True"))  # no stale frames
    ok(client.op("seq.close"))
    pinned = ok(client.exec_code(f"LABELS = {CAST!r}\n" + PIN_LOD0))
    t0 = time.time()
    ok(client.op("render.mrq", sequence=SEQ, level=LEVEL, out_dir=out, width=res * 16 // 9, height=res,
                 start=first - PREROLL,
                 end=end, temporal=samples, spatial=1, name=f"reel_{sid}", warmup=32, cvars=CVARS))
    while True:
        p = ok(client.op("render.progress", out_dir=out, expected=end - first + PREROLL))
        if p["done"]:
            break
        time.sleep(10)
    dt = time.time() - t0
    return {"shot": sid, "dir": out, "frames": p["frames"], "expected": end - first + PREROLL, "first": first,
            "last": end - 1, "s": round(dt), "s_per_frame": round(dt / max(1, p["frames"]), 1), "lod0": pinned}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", required=True, help="S01,S02,... (one MRQ job each, in order)")
    ap.add_argument("--res", type=int, default=1080, help="frame height: 1080 (the first cut) or 2160")
    ap.add_argument("--samples", type=int, default=8, help="temporal samples per frame")
    ap.add_argument("--frames", type=int, default=0, help="only the first N frames of each shot (calibration)")
    ap.add_argument("--at", type=int, default=0, help="a test from this master frame (into <shot>_t<at>)")
    a = ap.parse_args()
    for sid in a.shots.split(","):
        print(render(sid, a.res, a.samples, a.frames, a.at), flush=True)


if __name__ == "__main__":
    main()
