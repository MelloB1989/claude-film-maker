"""Check the halo's letter-by-letter ignition (S11) and the terminal's cursor blink (S08): what SignHalo and Terminal
wear and what the wipe parent is, then viewport stills of SEQ_Reel. Through Reel_S11 at f725 only k should glow, at
f745 k a r, at f770 all five; through Reel_S08 the cursor is off at f566 and f580, on at f572 and f588.

    cd tools && uv run python ../films/host-studio/reel/halo_check.py [--frames 725,745,770] [--no-stills]
    cd tools && uv run python ../films/host-studio/reel/halo_check.py --camera Reel_S08 --frames 566,572,580,588

A wipe parent without fm_rev 2 was built before look.py's GlowWipe fix (and is never rebuilt by an older bridge):
install the bridge from this checkout (`film-ue install`) and run rig.py again, which rebuilds it in place.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from filmtools.unreal import client

HERE = Path(__file__).resolve().parent
SEQ = "/Game/Reel/SEQ_Reel"
REMOTE = r"C:\UEProjects\HostStudio\Saved\Previs\halo_check"

STATE = r'''
import unreal
from fmbridge.ops import level as L
EAL, MEL = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary
out = {}
base = "/Game/FM/Materials/M_FM_GlowWipe"
if EAL.does_asset_exist(base):
    m = EAL.load_asset(base)
    out["base_rev"] = EAL.get_metadata_tag(m, "fm_rev") or "(none: built before the fix)"
    out["base_params"] = [str(p) for p in MEL.get_scalar_parameter_names(m)]
else:
    out["base_rev"] = "(no M_FM_GlowWipe)"
for label, param in (("SignHalo", "Reveal"), ("Terminal", "Blink")):
    mats = []
    for c in L.actor(label).get_components_by_class(unreal.StaticMeshComponent):
        names = [str(n) for n in c.get_material_slot_names()]
        for i in range(c.get_num_materials()):
            mi = c.get_material(i)
            row = {"component": c.get_name(), "slot": names[i] if i < len(names) else i,
                   "material": mi.get_path_name() if mi else None}
            if isinstance(mi, unreal.MaterialInstance):
                row["parent"] = mi.get_editor_property("parent").get_path_name()
                row[param] = MEL.get_material_instance_scalar_parameter_value(mi, param)
            mats.append(row)
    out[label] = mats
result = out
'''


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", default="Reel_S11")
    ap.add_argument("--frames", default="725,745,770")
    ap.add_argument("--no-stills", action="store_true")
    ap.add_argument("--out", type=Path, default=HERE / "halo_check")
    a = ap.parse_args()
    res = client.exec_code(STATE)
    if not res.get("ok"):
        raise SystemExit(res.get("stdout", "") + res.get("error", ""))
    print(json.dumps(res["result"], indent=1))
    if a.no_stills:
        return
    frames = [int(x) for x in a.frames.split(",")]
    # a throwaway still first: the first evaluation after opening the sequence can miss the material tracks
    for f in [frames[0], *frames]:
        remote = rf"{REMOTE}\{a.camera}_f{f}.png"
        r = client.op("seq.still", path=SEQ, frame=f, camera=a.camera, out=remote, width=1280, height=720, settle=40)
        if not r.get("ok"):
            raise SystemExit(r.get("stdout", "") + r.get("error", ""))
    for f in frames:
        print(client.pull(rf"{REMOTE}\{a.camera}_f{f}.png", str(a.out / f"{a.camera}_f{f}.png")))


if __name__ == "__main__":
    main()
