"""Casting stills of the presenters' bodies: each one alone on the mark in the idle loop (not the A-pose), seen full
length from the front, three-quarter and profile, and waist-up, at viewport quality (quick: for judging a body
between MetaHuman rebuilds, not for posting). They land in out/host-studio/bodycheck/<who>_<view>.png.

    cd tools && uv run python ../films/host-studio/bodycheck.py [--who him,her] [--tag v2]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from filmtools.unreal import client, workstation as ws


def _j(*parts: str) -> str:
    """A path on the box in its own style (Linux or Windows)."""
    from filmtools.unreal.boxpaths import BoxPaths
    return BoxPaths.current().join(*parts)

from stills import IDLE, SHOW, ok

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "host-studio" / "bodycheck"
REMOTE = ws.project("Saved", "BodyCheck")
VERT = [13.365, 23.76]
VIEWS = {  # name: (location, look-at, focal mm, width, height) for a presenter at the origin facing +X
    "full": ([330, 0, 95], [0, 0, 92], 35.0, 1080, 1920),
    "threeq": ([250, 215, 100], [0, 0, 92], 35.0, 1080, 1920),
    "side": ([0, 330, 95], [0, 0, 92], 35.0, 1080, 1920),
    "waist": ([150, 25, 140], [0, 0, 128], 35.0, 1080, 1350),
}
WHO = {"him": "Host", "her": "Presenter"}
GARMENT = '''
from fmbridge.ops import level as L
for c in L.actor({label!r}).get_components_by_class(unreal.SkeletalMeshComponent):
    if c.get_name() == "SkeletalMesh":
        c.set_visibility({show!r})
result = True
'''


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", default="him,her")
    ap.add_argument("--tag", default="")
    ap.add_argument("--bare", action="store_true", help="hide the garment: judge the body itself (a diagnostic)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (loc, at, focal, w, h) in VIEWS.items():
        ok(client.op("look.camera", label=f"BodyCheck_{name}", loc=loc, look_at=at, focal=focal, aperture=8.0,
                     filmback=VERT if h > w else [VERT[0], VERT[0] * h / w], pilot=False))
    for who in a.who.split(","):
        her = who != "her"
        ok(client.exec_code(SHOW.format(hidden={"Host": who != "him", "Presenter": her, "HerEarL": her,
                                                "HerEarR": her, "HerWatch": her, "Stool": True})))
        ok(client.exec_code(GARMENT.format(label=WHO[who], show=not a.bare)))
        for name, (_, _, _, w, h) in VIEWS.items():
            # one shot per view: the viewport follows the sequence's camera cut, whatever camera the still names
            seq = f"/Game/Studio/Stills/SEQ_BodyCheck_{name}"
            ok(client.op("seq.close"))
            ok(client.op("seq.shot", path=seq, actor_label=WHO[who], anims={"Body": IDLE}, camera=f"BodyCheck_{name}",
                         seconds=2.0))
            remote = _j(REMOTE, f"{who}_{name}.png")
            ok(client.op("seq.still", path=seq, frame=24, camera=f"BodyCheck_{name}", out=remote, width=w, height=h))
            local = OUT / f"{who}_{name}{'_' + a.tag if a.tag else ''}.png"
            client.pull(remote, str(local))
            print(local)
        ok(client.exec_code(GARMENT.format(label=WHO[who], show=True)))
    ok(client.op("seq.close"))
    ok(client.exec_code(SHOW.format(hidden={"Host": False, "Presenter": True, "HerEarL": True, "HerEarR": True,
                                            "HerWatch": True, "Stool": True})))


if __name__ == "__main__":
    main()
