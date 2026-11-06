"""Round 4 (agent-09): does TerminalGlow's 120 cm attenuation (was 2000) change the set shots? One still per set shot,
its middle frame through its Reel_ camera, with the old radius and the new, everything else equal (the same renderer
and settings, so only the light differs), then CIE76 dE per pixel: the frame's mean, and the worst 32x32-pixel block's
mean (the shelf's spill is local). Visible: a block above ~2.

    render (the editor; agent-06):  cd tools && uv run python ../films/host-studio/reel/r4/glow_dE.py render --out DIR
    compare (files, on the box):    cd tools && uv run --with pillow --with numpy python \\
                                        ../films/host-studio/reel/r4/glow_dE.py compare DIR

render leaves the light at 120 (the fix) and saves nothing. With Host_Op on the level the stills are box-only; only
dE.json leaves.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shots import SHOTS  # noqa: E402

SEQ = "/Game/Reel/SEQ_Reel"
SET = [s for s in SHOTS if not getattr(s, "cast", ())]
RADII = {"old": 2000.0, "new": 120.0}
BLOCK = 32
VISIBLE = 2.0

RADIUS = """
import unreal
a = next(x for x in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
         if x.get_actor_label() == "TerminalGlow")
c = a.get_component_by_class(unreal.LightComponent)
c.set_editor_property("attenuation_radius", R)
result = c.get_editor_property("attenuation_radius")
"""


def render(out: str, width: int) -> dict:
    from filmtools.unreal import client

    def ok(res):
        if not res.get("ok"):
            raise SystemExit(res.get("stdout", "") + res.get("error", ""))
        return res.get("result")
    rep = {}
    try:
        for tag, r in RADII.items():
            got = ok(client.exec_code(f"R = {r}\n" + RADIUS))
            for s in SET:
                f = (s.start + s.end) // 2
                p = ok(client.op("view.still", out=f"{out}/{s.id}_{f:04d}_{tag}.png", sequence=SEQ, frame=f,
                                 camera=f"Reel_{s.id}", width_px=width, height_px=width * 9 // 16, mode="mrq",
                                 level="/Game/Studio/Studio"))
                rep[f"{s.id}_{tag}"] = {"radius": got, "path": p["path"]}
                print(s.id, tag, flush=True)
    finally:
        ok(client.exec_code(f"R = {RADII['new']}\n" + RADIUS))
    return rep


def lab(rgb):
    import numpy as np
    c = rgb / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = c @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]])
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def compare(d: str) -> dict:
    import numpy as np
    from PIL import Image
    res = {}
    for old in sorted(Path(d).glob("*_old.png")):
        new = old.with_name(old.name.replace("_old", "_new"))
        if not new.exists():
            continue
        a = lab(np.asarray(Image.open(old).convert("RGB"), np.float32))
        b = lab(np.asarray(Image.open(new).convert("RGB"), np.float32))
        de = np.sqrt(((a - b) ** 2).sum(-1))
        h, w = de.shape
        blk = de[:h // BLOCK * BLOCK, :w // BLOCK * BLOCK].reshape(h // BLOCK, BLOCK, w // BLOCK, BLOCK).mean((1, 3))
        y, x = np.unravel_index(int(blk.argmax()), blk.shape)
        sid = old.name.split("_")[0]
        res[sid] = {"frame": int(old.name.split("_")[1]), "mean_dE": round(float(de.mean()), 3),
                    "p99_dE": round(float(np.percentile(de, 99)), 2), "max_block_dE": round(float(blk.max()), 2),
                    "max_block_at": [round(x * BLOCK / w, 3), round(y * BLOCK / h, 3)],
                    "visible": bool(blk.max() > VISIBLE)}
    out = {"shots": res, "rerender": [k for k, v in res.items() if v["visible"]], "block_px": BLOCK,
           "visible_dE": VISIBLE}
    (Path(d) / "dE.json").write_text(json.dumps(out, indent=1))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--out", required=True)
    r.add_argument("--width", type=int, default=1920)
    c = sub.add_parser("compare")
    c.add_argument("dir")
    a = ap.parse_args()
    print(json.dumps(render(a.out, a.width) if a.cmd == "render" else compare(a.dir), indent=1))


if __name__ == "__main__":
    main()
