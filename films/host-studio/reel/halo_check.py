"""Check the halo's letter-by-letter ignition (S11) and the terminal's cursor blink (S08): what SignHalo and Terminal
wear and what the wipe parent is, then viewport stills of SEQ_Reel. Through Reel_S11 at f725 only k should glow, at
f745 k a r, at f770 all five; through Reel_S08 the cursor is off at f566 and f580, on at f572 and f588.

    cd tools && uv run python ../films/host-studio/reel/halo_check.py [--frames 725,745,770] [--no-stills]
    cd tools && uv run python ../films/host-studio/reel/halo_check.py --camera Reel_S08 --frames 566,572,580,588
    cd tools && uv run python ../films/host-studio/reel/halo_check.py --tracks   # the material tracks themselves

--tracks (no stills): for SignHalo, Outside and Terminal, the sequence's bindings and whether they resolve to the
level's actor and component, each material track's slot info (its material_type must be INDEXED_MATERIAL: an EMPTY
one reaches nothing) and sections (their class and channels), then, with the sequence open at f725, what each
component actually wears (a MID once a track reaches it) and its parameter values.

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


TRACKS = r'''
import unreal
from fmbridge.ops import level as L
LSE = unreal.LevelSequenceEditorBlueprintLibrary
seq = unreal.EditorAssetLibrary.load_asset(SEQ)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
def tryit(f):
    try:
        return f()
    except Exception as e:
        return f"!{type(e).__name__}: {e}"
def props(o, names):
    return {n: tryit(lambda n=n: str(o.get_editor_property(n))) for n in names}
out = {"engine": unreal.SystemLibrary.get_engine_version()}
for label in LABELS:
    row = {}
    try:
        a = L.actor(label)
    except Exception as e:
        out[label] = f"no actor: {e}"
        continue
    row["actor"] = a.get_path_name()
    for b in seq.get_bindings():
        parent = tryit(lambda: b.get_parent())
        ok_parent = parent is not None and not isinstance(parent, str)
        pname = tryit(lambda: str(parent.get_display_name())) if ok_parent else ""
        name = str(b.get_display_name())
        if name != label and pname != label:
            continue
        key = f"{pname}/{name}" if pname else name
        objs = tryit(lambda: [o.get_path_name() for o in seq.locate_bound_objects(b, world)])
        tracks = []
        for t in b.get_tracks():
            tr = {"class": t.get_class().get_name(), "name": tryit(lambda: str(t.get_display_name()))}
            if isinstance(t, unreal.MovieSceneComponentMaterialTrack):
                info = tryit(lambda: t.get_material_info())
                tr["info"] = props(info, ("material_slot_index", "material_slot_name", "material_type")) \
                    if not isinstance(info, str) else info
                tr["sections"] = []
                for sec in t.get_sections():
                    sr = {"class": sec.get_class().get_name(), "active": tryit(lambda: sec.is_active()),
                          "range": tryit(lambda: [sec.has_start_frame(), sec.has_end_frame()])}
                    sr["channels"] = tryit(lambda: [(ch.get_name(), ch.get_num_keys())
                                                    for ch in sec.get_all_channels()])
                    tr["sections"].append(sr)
            tracks.append(tr)
        row[key] = {"bound": objs, "tracks": tracks}
    out[label] = row
LSE.open_level_sequence(seq)
LSE.set_current_time(725)
result = out
'''

LIVE = r'''
import unreal
from fmbridge.ops import level as L
out = {}
for label in LABELS:
    try:
        comps = L.actor(label).get_components_by_class(unreal.StaticMeshComponent)
    except Exception as e:
        out[label] = str(e)
        continue
    rows = []
    for c in comps:
        for i in range(c.get_num_materials()):
            m = c.get_material(i)
            r = {"component": c.get_name(), "slot": i, "class": m.get_class().get_name() if m else None,
                 "material": m.get_path_name() if m else None}
            if isinstance(m, unreal.MaterialInstanceDynamic):
                r.update({p: m.k2_get_scalar_parameter_value(p) for p in ("Reveal", "Intensity", "Blink")})
            rows.append(r)
    out[label] = rows
result = out
'''


def tracks() -> None:
    head = f"SEQ = {SEQ!r}\nLABELS = ['SignHalo', 'Outside', 'Terminal']\n"
    for code in (TRACKS, LIVE):  # two calls: the open sequence evaluates on the editor's tick in between
        res = client.exec_code(head + code)
        if not res.get("ok"):
            raise SystemExit(res.get("stdout", "") + res.get("error", ""))
        print(json.dumps(res["result"], indent=1, default=str))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", default="Reel_S11")
    ap.add_argument("--frames", default="725,745,770")
    ap.add_argument("--no-stills", action="store_true")
    ap.add_argument("--out", type=Path, default=HERE / "halo_check")
    ap.add_argument("--tracks", action="store_true", help="dump the material tracks and what the meshes wear at f725")
    a = ap.parse_args()
    if a.tracks:
        return tracks()
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
