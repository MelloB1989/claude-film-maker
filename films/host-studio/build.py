"""Build the host's studio on the Unreal workstation through the bridge: draw the textures and labels, send and import
them with the surfaces and the Blender props, run unreal/studio.py in the editor, and bring back a still through the
host camera.

    cd tools && uv run python ../films/host-studio/build.py [--still-only] [--frame 96]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
from pathlib import Path

from filmtools.unreal import client, workstation as ws

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


def _run(script: str) -> None:
    spec = importlib.util.spec_from_file_location(f"hs_{script}", HERE / f"{script}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


def halo() -> None:
    """The sign's halo: its letters' silhouette (props/out/karma_halo.png) spread into a soft glow."""
    from PIL import Image, ImageFilter
    src = HERE / "props" / "out" / "karma_halo.png"
    if src.exists():
        im = Image.open(src).convert("L")
        w, h = im.size
        pad = Image.new("L", (int(w * 1.3), int(h * 1.6)), 0)  # the card is 1.3 x 1.6 the letters' bounds
        pad.paste(im, ((pad.width - w) // 2, (pad.height - h) // 2))
        glow = pad.filter(ImageFilter.GaussianBlur(w / 100 * 2.2))  # ~2 cm on a 100 cm sign
        glow = Image.eval(glow, lambda v: min(255, int(v * 1.8)))
        glow.convert("RGB").save(OUT / "textures" / "T_KarmaHalo.png")


def push_import(files: list, dest: str, sub: str) -> list:
    """Send files in one go through S3 (into REMOTE\\sub) and import them into `dest`."""
    if not files:
        return []
    stage = OUT / "_stage" / sub
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    for p in files:
        shutil.copy2(p, stage / p.name)
    ws.push_dir(str(stage), f"{REMOTE}\\{sub}")
    return _ok(client.op("assets.import", files=[f"{REMOTE}\\{sub}\\{p.name}" for p in files], dest=dest))


def textures() -> list:
    for script in ("textures", "labels"):
        _run(script)
    halo()
    out = push_import(sorted((OUT / "textures").glob("T_*.png")) + sorted((HERE / "props" / "out").glob("T_*.png")),
                      "/Game/Studio/Textures", "textures")
    return out + push_import(sorted((HERE / "surfaces").glob("T_*.png")), "/Game/Studio/Surfaces", "surfaces")


RETIRED = {"keyboard", "mic_boom", "mug", "plant_floor"}  # the first studio's props, not in the karma room


def props(only: list | None = None) -> dict:
    """Send the Blender props (props/out/*.fbx, with their placement notes *.json) through S3 and import each into its
    own folder (their material names overlap)."""
    src = HERE / "props" / "out"
    fbx = [p for p in sorted(src.glob("*.fbx")) if p.stem not in RETIRED and (not only or p.stem in only)]
    stage = OUT / "_stage" / "props"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    for p in fbx + sorted(src.glob("*.json")):
        shutil.copy2(p, stage / p.name)
    ws.push_dir(str(stage), f"{REMOTE}\\props")
    return {p.stem: _ok(client.op("assets.import", files=[f"{REMOTE}\\props\\{p.name}"], dest=f"/Game/Studio/Props/{p.stem}"))
            for p in fbx}


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
    ap.add_argument("--props", default="", help="comma list: import only these props")
    ap.add_argument("--skip", default="", help="comma list of steps to skip: textures,props")
    a = ap.parse_args()
    if not a.still_only:
        if "textures" not in a.skip:
            print("textures:", len(textures()))
        if "props" not in a.skip:
            print("props:", json.dumps(props(a.props.split(",") if a.props else None)))
        _ok(client.op("seq.close"))
        print("studio:", json.dumps(_ok(client.exec_code((HERE / "unreal" / "studio.py").read_text(), 600))))
    print(still(a.frame, a.name))


if __name__ == "__main__":
    main()
