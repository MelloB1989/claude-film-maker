"""Casting stills of the presenters' bodies: each one alone on the mark in the idle loop (not the A-pose), seen full
length from the front, three-quarter and profile, and waist-up, at viewport quality (quick: for judging a body
between MetaHuman rebuilds, not for posting). They land in out/host-studio/bodycheck/<who>_<view>.png.

    cd tools && uv run python ../films/host-studio/bodycheck.py [--who him,her] [--tag v2]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from filmtools.unreal import client

from stills import IDLE, SHOW, ok

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "host-studio" / "bodycheck"
REMOTE = r"C:\UEProjects\HostStudio\Saved\BodyCheck"
VERT = [13.365, 23.76]
VIEWS = {  # name: (location, look-at, focal mm, width, height) for a presenter at the origin facing +X
    "full": ([330, 0, 95], [0, 0, 92], 35.0, 1080, 1920),
    "threeq": ([250, 215, 100], [0, 0, 92], 35.0, 1080, 1920),
    "side": ([0, 330, 95], [0, 0, 92], 35.0, 1080, 1920),
    "waist": ([150, 25, 140], [0, 0, 128], 35.0, 1080, 1350),
}
WHO = {"him": "Host", "her": "Presenter"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", default="him,her")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (loc, at, focal, w, h) in VIEWS.items():
        ok(client.op("look.camera", label=f"BodyCheck_{name}", loc=loc, look_at=at, focal=focal, aperture=8.0,
                     filmback=VERT if h > w else [VERT[0], VERT[0] * h / w], pilot=False))
    for who in a.who.split(","):
        her = who != "her"
        ok(client.exec_code(SHOW.format(hidden={"Host": who != "him", "Presenter": her, "HerEarL": her,
                                                "HerEarR": her, "HerWatch": her, "Stool": True})))
        for name, (_, _, _, w, h) in VIEWS.items():
            # one shot per view: the viewport follows the sequence's camera cut, whatever camera the still names
            seq = f"/Game/Studio/Stills/SEQ_BodyCheck_{name}"
            ok(client.op("seq.close"))
            ok(client.op("seq.shot", path=seq, actor_label=WHO[who], anims={"Body": IDLE}, camera=f"BodyCheck_{name}",
                         seconds=2.0))
            remote = rf"{REMOTE}\{who}_{name}.png"
            ok(client.op("seq.still", path=seq, frame=24, camera=f"BodyCheck_{name}", out=remote, width=w, height=h))
            local = OUT / f"{who}_{name}{'_' + a.tag if a.tag else ''}.png"
            client.pull(remote, str(local))
            print(local)
    ok(client.op("seq.close"))
    ok(client.exec_code(SHOW.format(hidden={"Host": False, "Presenter": True, "HerEarL": True, "HerEarR": True,
                                            "HerWatch": True, "Stool": True})))


if __name__ == "__main__":
    main()
