"""Build the host's studio on the Unreal workstation through the bridge: draw the textures, send and import them, run
unreal/studio.py in the editor, and bring back a still through the host camera.

    cd tools && uv run python ../films/host-studio/build.py [--still-only] [--frame 96]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

from filmtools.unreal import client

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "out" / "host-studio"
REMOTE = r"C:\UEProjects\HostStudio\Saved\Import\host-studio"


def _ok(res: dict):
    if not res.get("ok"):
        raise SystemExit(res.get("stdout", "") + res.get("error", ""))
    if res.get("stdout"):
        print(res["stdout"], end="")
    return res.get("result")


def textures() -> list:
    spec = importlib.util.spec_from_file_location("hs_textures", HERE / "textures.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()
    remote = []
    for p in sorted((OUT / "textures").glob("T_*.png")):
        client.push(str(p), f"{REMOTE}\\{p.name}")
        remote.append(f"{REMOTE}\\{p.name}")
    return _ok(client.op("assets.import", files=remote, dest="/Game/Studio/Textures"))


def still(frame: int, name: str, sequence: str = "/Game/Studio/SEQ_Line2") -> Path:
    remote = rf"C:\UEProjects\HostStudio\Saved\Stills\{name}.png"
    _ok(client.op("seq.still", path=sequence, frame=frame, camera="HostCam", out=remote))
    local = OUT / "stills" / f"{name}.png"
    client.pull(remote, str(local))
    return local


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--still-only", action="store_true")
    ap.add_argument("--frame", type=int, default=96)
    ap.add_argument("--name", default="studio")
    a = ap.parse_args()
    if not a.still_only:
        print("textures:", json.dumps(textures()))
        _ok(client.op("seq.close"))
        print("studio:", json.dumps(_ok(client.exec_code((HERE / "unreal" / "studio.py").read_text(), 600))))
    print(still(a.frame, a.name))


if __name__ == "__main__":
    main()
