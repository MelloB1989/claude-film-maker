"""Her hair's green ends (round 3, gate c): at full size the ends read green only where they lie over the olive
overshirt (cast3 S16 f1240/1280/1302): the strands thin to their tips and the shirt shows through, so no hair
material parameter changed it (hair_teal_ab.py). This renders S16 f1240-1243 at the finals' quality once per strand
coverage variant on her Hair groom (thicker tips, wider strands), puts the groom back exactly as it was, and makes
one sheet of full-size crops of the ends. Run on the box, from tools/ (the bridge and the frames are local):

    uv run --with pillow --with numpy python ../films/host-studio/reel/hair_cover_ab.py --out /srv/ue/reel/r3/hair_cover

Each run renders into <out>/<HHMMSS>/<variant>; only <out>/<HHMMSS>/hair_cover.jpg and hair_cover.json need to
leave the box.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from filmtools.unreal import client

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import qa_review  # noqa: E402

SPEC = HERE / "r3" / "45-hair-cover.yaml"
VARIANTS = [  # GroomGroupsDesc fields on her Hair groom, every group
    {"name": "base"},
    {"name": "tips_1.0", "hair_tip_scale": 1.0},
    {"name": "width_x1.6", "width_mul": 1.6},
    {"name": "tips_1.0_width_x1.6", "hair_tip_scale": 1.0, "width_mul": 1.6},
]
ENDS_BOX = (0.32, 0.45, 0.68, 0.95)  # S16: her face and the lengths over her shoulders (qa_review crop)

SNAP = """
import unreal
a = next(x for x in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
         if x.get_actor_label() == "Presenter")
c = next(g for g in a.get_components_by_class(unreal.GroomComponent) if g.get_name() == "Hair")
F = ("hair_width", "hair_width_override", "hair_root_scale", "hair_root_scale_override", "hair_tip_scale",
     "hair_tip_scale_override")
result = [{f: d.get_editor_property(f) for f in F} for d in c.get_editor_property("groom_groups_desc")]
"""

PUT = """
import unreal
a = next(x for x in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
         if x.get_actor_label() == "Presenter")
c = next(g for g in a.get_components_by_class(unreal.GroomComponent) if g.get_name() == "Hair")
descs = list(c.get_editor_property("groom_groups_desc"))
for d, want in zip(descs, GROUPS):
    for f, v in want.items():
        d.set_editor_property(f, v)
c.set_editor_property("groom_groups_desc", descs)
# a groom property change re-creates its render state; put her MI_K_HerHair* back on every slot (dress_her: a
# re-created component loses its materials, which renders the preset's teal-green) and say what each slot has
c = next(g for g in a.get_components_by_class(unreal.GroomComponent) if g.get_name() == "Hair")
for i, p in enumerate(HAIR):
    c.set_material(i, unreal.load_asset(p))
MEL = unreal.MaterialEditingLibrary
mats = []
for i in range(c.get_num_materials()):
    m = c.get_material(i)
    mats.append([m.get_path_name() if m else None, MEL.get_material_instance_scalar_parameter_value(m, "hairMelanin")
                 if isinstance(m, unreal.MaterialInstance) else None])
result = {"groups": [{f: d.get_editor_property(f) for f in want}
                     for d, want in zip(c.get_editor_property("groom_groups_desc"), GROUPS)], "materials": mats}
"""
HAIR = [f"/Game/Studio/Materials/MI_K_HerHair{s}" for s in ("", "_Cards", "_Helmet")]


def ok(res):
    if not res.get("ok"):
        raise SystemExit(res.get("stdout", "") + res.get("error", ""))
    return res.get("result")


def groups_for(v: dict, orig: list) -> list:
    out = []
    for g in orig:
        w = dict(g)
        if "hair_tip_scale" in v:
            w["hair_tip_scale"], w["hair_tip_scale_override"] = float(v["hair_tip_scale"]), True
        if "width_mul" in v:
            w["hair_width"], w["hair_width_override"] = float(g["hair_width"]) * v["width_mul"], True
        out.append(w)
    return out


def put(groups: list) -> dict:
    """Set the groups, then pin the presenters back to LOD 0 (build.py --lod0 on): a groom property change re-creates
    the component, which drops its forced LOD as well as its materials (cast4's S16: long blue-black strands at f1200,
    shorter green hair, the cards, from f1217), so an unpinned A/B would compare the cards, not the strands."""
    import build
    r = ok(client.exec_code(f"GROUPS = {groups!r}\nHAIR = {HAIR!r}\n" + PUT))
    r["lod0"] = build.lod0(True)
    return r


def render(tag: str, run: str) -> None:
    """One variant's render; a non-zero exit from film-ue apply is only a failure if its frames did not land."""
    from filmtools.unreal.cli import main as cli
    argv = sys.argv
    try:
        sys.argv = ["film-ue", "apply", str(SPEC), "--set", f"tag={tag}", "--set", f"run={run}"]
        cli()
    except SystemExit as e:
        if e.code not in (0, None):
            print(f"film-ue apply {tag}: exit {e.code} (checking the frames)", flush=True)
    finally:
        sys.argv = argv


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="on the box: the renders' parent dir (the spec's out) and the sheet")
    a = ap.parse_args()
    import time
    run = time.strftime("t%H%M%S")  # a letter first: --set run=002736 would read as the number 2736 (another dir)
    out = Path(a.out) / run
    orig = ok(client.exec_code(SNAP))
    rep = {"original": orig, "variants": {}}
    try:
        for v in VARIANTS:
            r = put(groups_for(v, orig))
            render(v["name"], run)
            if 1241 not in qa_review.frames(str(out / v["name"])):
                raise SystemExit(f"{v['name']}: no frame 1241 under {out / v['name']}")
            rep["variants"][v["name"]] = {"groups": groups_for(v, orig), "put": r}
    finally:
        rep["restored"] = put(orig)
    cells = []
    for v in VARIANTS:
        p = qa_review.crop(str(out / v["name"]), str(out / f"_{v['name']}.jpg"), [1241], ENDS_BOX, 640)
        cells.append((v["name"], p))
    from PIL import Image, ImageDraw
    ims = []
    for name, p in cells:
        im = Image.open(p).convert("RGB")
        ImageDraw.Draw(im).text((8, 22), name, fill=(255, 255, 0))
        ims.append(im)
    w, h = ims[0].size
    sheet = Image.new("RGB", (2 * w + 12, 2 * h + 12), (24, 24, 24))
    for k, im in enumerate(ims):
        sheet.paste(im, (4 + (k % 2) * (w + 4), 4 + (k // 2) * (h + 4)))
    sheet.save(out / "hair_cover.jpg", quality=90)
    (out / "hair_cover.json").write_text(json.dumps(rep, indent=1, default=str))
    print(json.dumps({"sheet": str(out / "hair_cover.jpg"), "restored": rep["restored"]}, default=str))


if __name__ == "__main__":
    main()
