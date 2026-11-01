"""Stills of the karma studio for posting: one Movie Render Queue frame per camera from unreal/studio.py, at its own
aspect, brought back to out/host-studio/stills/karma/. The empty-room angles hide the host and show the stool.

    cd tools && uv run python ../films/host-studio/stills.py [--only KarmaWide,KarmaShelf] [--path-tracer] [--fetch]
"""
from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

from filmtools.unreal import client, workstation as ws

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "host-studio" / "stills" / "karma"
PROJECT = r"C:\UEProjects\HostStudio"
LEVEL = "/Game/Studio/Studio"
IDLE = "/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle"
# hair strands take the sky light unoccluded: in a closed, daylit room it turns the host's hair white
CVARS = {"r.HairStrands.SkyLighting": 0}
SHOTS = {  # camera: (width, height, host in frame)
    "KarmaHost": (3840, 2160, True),
    "KarmaVertical": (2160, 3840, True),
    "KarmaWide": (3840, 2160, False),
    "KarmaShelf": (2400, 3000, False),
    "KarmaCredenza": (2400, 3000, False),
    "KarmaSign": (2880, 2880, False),
}
SHOW = '''
import unreal
from fmbridge.ops import level as L
for label, hide in {hidden!r}.items():
    try:
        a = L.actor(label)
    except ValueError:
        continue
    a.set_actor_hidden_in_game(hide)
    a.set_is_temporarily_hidden_in_editor(hide)
result = True
'''


def ok(res: dict):
    if not res.get("ok"):
        raise SystemExit(res.get("stdout", "") + res.get("error", ""))
    return res.get("result")


def render(cam: str, path_tracer: bool) -> Path:
    w, h, host = SHOTS[cam]
    ok(client.exec_code(SHOW.format(hidden={"Host": not host, "Stool": host})))
    seq = f"/Game/Studio/Stills/SEQ_{cam}"
    ok(client.op("seq.close"))
    ok(client.op("seq.shot", path=seq, actor_label="Host", anims={"Body": IDLE}, camera=cam, seconds=2.0))
    ok(client.op("assets.save_all"))
    remote = rf"{PROJECT}\Saved\MovieRenders\karma_{cam}"
    ok(client.exec_code(f"import shutil\nshutil.rmtree({remote!r}, ignore_errors=True)\nresult = True"))  # no stale frame
    ok(client.op("render.mrq", sequence=seq, level=LEVEL, out_dir=remote, width=w, height=h, start=24, end=25,
                 temporal=1 if path_tracer else 16, spatial=64 if path_tracer else 2, path_tracer=path_tracer,
                 name=f"karma_{cam}", warmup=64, cvars=CVARS))
    t0 = time.time()
    while not ok(client.op("render.progress", out_dir=remote))["done"]:
        time.sleep(10)
    print(f"{cam}: {time.time() - t0:.0f}s")
    return fetch(cam)


def fetch(cam: str) -> Path:
    remote = rf"{PROJECT}\Saved\MovieRenders\karma_{cam}"
    tmp = OUT / f"_{cam}"
    ws.pull_dir(remote, str(tmp))
    png = sorted(tmp.glob("*.png"))[-1]
    dst = OUT / f"{cam}.png"
    shutil.move(str(png), dst)
    shutil.rmtree(tmp, ignore_errors=True)
    return dst


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--path-tracer", action="store_true")
    ap.add_argument("--fetch", action="store_true", help="only bring back finished renders")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    cams = a.only.split(",") if a.only else list(SHOTS)
    for cam in cams:
        print(fetch(cam) if a.fetch else render(cam, a.path_tracer))
    ok(client.exec_code(SHOW.format(hidden={"Host": False, "Stool": True})))


if __name__ == "__main__":
    main()
