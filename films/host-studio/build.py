"""Build the host's studio on the Unreal workstation through the bridge: draw the textures and labels, send and import
them with the surfaces and the Blender props, run unreal/studio.py in the editor, and bring back a still through the
host camera.

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


def push_import(files: list, dest: str) -> list:
    remote = []
    for p in files:
        client.push(str(p), f"{REMOTE}\\{p.name}")
        remote.append(f"{REMOTE}\\{p.name}")
    return _ok(client.op("assets.import", files=remote, dest=dest)) if remote else []


def textures() -> list:
    for script in ("textures", "labels"):
        _run(script)
    halo()
    out = push_import(sorted((OUT / "textures").glob("T_*.png")) + sorted((HERE / "props" / "out").glob("T_*.png")),
                      "/Game/Studio/Textures")
    return out + push_import(sorted((HERE / "surfaces").glob("T_*.png")), "/Game/Studio/Surfaces")


def props() -> dict:
    """Send the Blender props (props/out/*.fbx) and import each into its own folder (their material names overlap)."""
    out = {}
    for p in sorted((HERE / "props" / "out").glob("*.json")):  # placement notes (the halo's bounds, the note's patch)
        client.push(str(p), f"{REMOTE}\\props\\{p.name}")
    for p in sorted((HERE / "props" / "out").glob("*.fbx")):
        remote = f"{REMOTE}\\props\\{p.name}"
        client.push(str(p), remote)
        out[p.stem] = _ok(client.op("assets.import", files=[remote], dest=f"/Game/Studio/Props/{p.stem}"))
    return out


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
        print("props:", json.dumps(props()))
        _ok(client.op("seq.close"))
        print("studio:", json.dumps(_ok(client.exec_code((HERE / "unreal" / "studio.py").read_text(), 600))))
    print(still(a.frame, a.name))


if __name__ == "__main__":
    main()
