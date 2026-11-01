"""Previs stills of the reel's key shots: a scratch camera (`Previs_<shot>`) placed as shots.py plans it, a viewport
still through a scratch sequence cut to it (seq.still, not Movie Render Queue), the still brought back, the camera deleted. Nothing else in the scene is
touched: the light is whatever the level has now, and the presenters stand where they stand.

The presenters' reel marks (shots.py MARK_HIM, MARK_HER) are not set in the level: both stand on one mark, her hidden.
A shot with a presenter is therefore shifted by (where he stands - his reel mark), so he is framed as planned; her
shots use him as a stand-in, lifted by the difference in eye height. Two-shots show him only.

    cd tools && uv run python ../films/host-studio/reel/previs.py [--only S03,S04] [--width 1920] [--animations]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from filmtools.unreal import client

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from shots import EYES_HER, EYES_HIM, FULL_FRAME, MARK_HER, MARK_HIM, SHOTS  # noqa: E402

OUT = HERE / "previs"
REMOTE = r"C:\UEProjects\HostStudio\Saved\Previs\reel"
ANIMS = "/MetaHumanCharacter/Optional/Animation"
IDLE = f"{ANIMS}/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_b_idle"
SEQ = "/Game/Reel/Previs/SEQ_Previs_agent11"  # scratch, deleted after each run


def ok(res: dict):
    if not res.get("ok"):
        raise SystemExit(res.get("stdout", "") + res.get("error", ""))
    return res.get("result")


def where(label: str) -> list:
    code = f"from fmbridge.ops import level as L\np = L.actor({label!r}).get_actor_location()\nresult = [p.x, p.y, p.z]"
    return ok(client.exec_code(code))


def focus_at(shot, frame: float):
    if not shot.focus:
        return None
    ks = shot.focus
    if frame <= ks[0][0]:
        return ks[0][1]
    for (f0, d0), (f1, d1) in zip(ks, ks[1:]):
        if frame <= f1:
            return d0 + (d1 - d0) * (frame - f0) / (f1 - f0)
    return ks[-1][1]


def place(shot, host: list):
    loc, at = shot.at(shot.previs)
    shift = [0.0, 0.0, 0.0]
    if shot.cast:
        mark = MARK_HER if shot.cast == ("her",) else MARK_HIM
        shift = [host[0] - mark[0], host[1] - mark[1], host[2] - mark[2]]
        if shot.cast == ("her",):
            shift[2] += EYES_HIM - EYES_HER
    return [p + s for p, s in zip(loc, shift)], [p + s for p, s in zip(at, shift)]


def sheet(cols: int = 3, w: int = 640) -> Path:
    """previs/contact.jpg: every previs still in shot order, captioned with its shot, time, lens and light."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(str(HERE.parents[2] / "fonts" / "src" / "Geist[wght].ttf"), 17)
    pick = lambda s: next((p for p in (OUT / f"{s.id}.jpg", OUT / f"{s.id}.png") if p.exists()), None)  # noqa: E731
    items = [(s, pick(s)) for s in SHOTS if pick(s)]
    h, cap, pad = w * 9 // 16, 30, 8
    rows = -(-len(items) // cols)
    img = Image.new("RGB", (cols * (w + pad) + pad, rows * (h + cap + pad) + pad), (16, 16, 17))
    d = ImageDraw.Draw(img)
    for k, (s, p) in enumerate(items):
        x, y = pad + k % cols * (w + pad), pad + k // cols * (h + cap + pad)
        img.paste(Image.open(p).convert("RGB").resize((w, h), Image.LANCZOS), (x, y))
        t = f"{s.id}  {s.title}  ·  {s.start / 24:.1f}s  ·  {s.lens:g}mm T{s.stop:g}  ·  {s.light}"
        d.text((x + 2, y + h + 6), t, fill=(225, 220, 210), font=font)
    out = OUT / "contact.jpg"
    img.save(out, quality=88)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", action="store_true", help="only make previs/contact.jpg from the stills (no bridge)")
    ap.add_argument("--only", default="")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--animations", action="store_true", help="list the engine's MetaHuman animations (read only)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.sheet:
        print(sheet())
        return
    if a.animations:
        found = ok(client.op("assets.list", path=ANIMS, cls="AnimSequence", limit=2000))
        (OUT / "metahuman_animations.json").write_text(json.dumps(found, indent=1))
        print(len(found), "animations")
        return
    want = set(a.only.split(",")) if a.only else None
    shots = [s for s in SHOTS if s.previs is not None and (want is None or s.id in want)]
    host = where("Host")
    made = []
    try:
        for s in shots:
            loc, at = place(s, host)
            label = f"Previs_{s.id}"
            d = focus_at(s, s.previs * s.frames)
            ok(client.op("look.camera", label=label, loc=loc, look_at=at, focal=float(s.lens), aperture=float(s.stop),
                         focus=d, filmback=list(FULL_FRAME), pilot=False))
            made.append(label)
            # look.still alone takes the viewport's field of view; a still through a sequence cut to the camera
            # (locked to the viewport) uses the cine lens: a throwaway sequence per shot, deleted at the end
            ok(client.op("seq.close"))
            ok(client.op("seq.shot", path=SEQ, actor_label="Host", anims={"Body": IDLE}, camera=label, seconds=1.0))
            remote = rf"{REMOTE}\{s.id}.png"
            ok(client.op("seq.still", path=SEQ, frame=12, camera=label, out=remote, width=a.width,
                         height=a.width * 9 // 16))
            client.pull(remote, str(OUT / f"{s.id}.png"))
            print(s.id, [round(v) for v in loc], "->", [round(v) for v in at], f"{s.lens:g}mm", flush=True)
    finally:
        ok(client.op("seq.close"))
        ok(client.exec_code(f"import unreal\nE = unreal.EditorAssetLibrary\n"
                            f"result = E.delete_asset({SEQ!r}) if E.does_asset_exist({SEQ!r}) else None"))
        if made:
            ok(client.op("level.delete", labels=made))


if __name__ == "__main__":
    main()
