"""Check the halo's letter-by-letter ignition (S11) and the terminal's cursor blink (S08): what SignHalo and Terminal
wear and what the wipe parent is, then viewport stills of SEQ_Reel. Through Reel_S11 at f725 only k should glow, at
f745 k a r, at f770 all five; through Reel_S08 the cursor is off at f566 and f580, on at f572 and f588.

    cd tools && uv run python ../films/host-studio/reel/halo_check.py [--frames 725,745,770] [--no-stills]
    cd tools && uv run python ../films/host-studio/reel/halo_check.py --camera Reel_S08 --frames 566,572,580,588
    cd tools && uv run python ../films/host-studio/reel/halo_check.py --tracks   # the material tracks themselves
    cd tools && uv run python ../films/host-studio/reel/halo_check.py --isolate --camera Reel_V05 --frames 700

--mpc (with --camera and --frames): does the card read MPC_FM, and does SEQ_Reel's collection track reach it? It
prints M_FM_GlowWipe's fm_rev and the CollectionParameter nodes in its graph, and SEQ_Reel's collection tracks; then
at each frame a still as it is and one with MPC_FM's default WipeOn set to 0 (put back to 1 afterwards, whatever
happens). Dark only in the second: the graph reads the collection and the track is not applied. Lit in both: the
graph does not read it (the rev 3 rebuild did not happen).

--isolate: is the glow SignHalo's? At each frame, three stills: as it is, with SignHalo hidden, and with SignHalo and
Halo0-8 hidden (temporarily, in the editor only: both are shown again afterwards, whatever happens), plus SignHalo's
visibility and MPC_FM's values as the editor has them.

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

from filmtools.unreal import client, workstation as ws


def _j(*parts: str) -> str:
    """A path on the box in its own style (Linux or Windows)."""
    from filmtools.unreal.boxpaths import BoxPaths
    return BoxPaths.current().join(*parts)

HERE = Path(__file__).resolve().parent
SEQ = "/Game/Reel/SEQ_Reel"
REMOTE = ws.project("Saved", "Previs", "halo_check")

# a scalar parameter's value on a MIC (MaterialEditingLibrary) or a MID (the one Sequencer makes): neither reader
# takes the other
VALUE = r'''
import unreal
def value(m, p):
    try:
        if isinstance(m, unreal.MaterialInstanceDynamic):
            return m.get_scalar_parameter_value(p)
        return unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(m, p)
    except Exception as e:
        return f"!{type(e).__name__}: {e}"
'''

STATE = VALUE + r'''
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
                row[param] = value(mi, param)
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
out = {"engine": unreal.SystemLibrary.get_engine_version(),
       "bare_info": props(unreal.MaterialParameterInfo(), ("name", "association", "index"))}
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
                    # the parameter info each curve is stored under: Sequencer matches the MID's on all three
                    sr["infos"] = tryit(lambda: [props(c.get_editor_property("parameter_info"),
                                                       ("name", "association", "index"))
                                                 for c in sec.get_editor_property("scalar_parameter_names_and_curves")])
                    tr["sections"].append(sr)
            tracks.append(tr)
        # a list: two bindings of one name (an old possessable beside a new one) must both show
        row.setdefault(key, []).append({"guid": tryit(lambda: str(b.get_id())), "bound": objs, "tracks": tracks})
    out[label] = row
LSE.open_level_sequence(seq)
LSE.set_current_time(725)
result = out
'''

LIVE = VALUE + r'''
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
            if isinstance(m, unreal.MaterialInstance):
                r["parent"] = m.get_editor_property("parent").get_path_name()
                r.update({p: value(m, p) for p in ("Reveal", "Intensity", "Softness", "Blink")})
            rows.append(r)
    out[label] = rows
# the world's MPC_FM, which the halo's GlowWipe reads (light.py keys WipeOn and WipeReveal there)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
mpc = unreal.EditorAssetLibrary.load_asset("/Game/FM/Materials/MPC_FM")
def mpc_value(p):  # KismetMaterialLibrary is not in every engine's Python (5.8's lacks it): the instance, else none
    try:
        return unreal.KismetMaterialLibrary.get_scalar_parameter_value(world, mpc, p)
    except AttributeError:
        pass
    try:
        return world.get_parameter_collection_instance(mpc).get_scalar_parameter_value(p)
    except Exception as e:
        return f"!unreadable here ({type(e).__name__}): judge it by the stills"
out["MPC_FM"] = {p: mpc_value(p) for p in ("WipeOn", "WipeReveal")} if mpc else \
    "(no MPC_FM: install the bridge, run rig.py)"
result = out
'''


# M_FM_GlowWipe's emissive graph, walked from the output: each node's class, parameter name and mask channels
GRAPH = r'''
import unreal
MEL = unreal.MaterialEditingLibrary
m = unreal.EditorAssetLibrary.load_asset("/Game/FM/Materials/M_FM_GlowWipe")
def node(e, depth=0):
    if e is None or depth > 12:
        return None
    d = {"class": e.get_class().get_name()}
    for k in ("parameter_name", "coordinate_index", "const_a", "const_b"):
        try:
            d[k] = str(e.get_editor_property(k))
        except Exception:
            pass
    if isinstance(e, unreal.MaterialExpressionComponentMask):
        d["mask"] = "".join(c for c in "rgba" if e.get_editor_property(c))
    try:
        d["in"] = [node(i, depth + 1) for i in MEL.get_inputs_for_material_expression(m, e)]
    except Exception as x:
        d["in"] = f"!{x}"
    return d
result = {"blend": str(m.get_editor_property("blend_mode")), "shading": str(m.get_editor_property("shading_model")),
          "emissive": node(MEL.get_material_property_input_node(m, unreal.MaterialProperty.MP_EMISSIVE_COLOR))}
'''

# every mesh in the level wearing a Glow or GlowWipe material, or the halo texture: a second glow behind the sign?
GLOWS = r'''
import unreal
out = []
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    for c in a.get_components_by_class(unreal.MeshComponent):
        for i in range(c.get_num_materials()):
            m = c.get_material(i)
            if m is None:
                continue
            base = m.get_base_material().get_path_name() if hasattr(m, "get_base_material") else m.get_path_name()
            if "Glow" in base or "Halo" in m.get_path_name():
                p = a.get_actor_location()
                out.append({"actor": a.get_actor_label(), "component": c.get_name(), "slot": i,
                            "material": m.get_path_name(), "base": base, "loc": [round(p.x), round(p.y), round(p.z)],
                            "visible": c.is_visible()})
result = out
'''


HIDE = r'''
import unreal
from fmbridge.ops import level as L
out = {}
for label in LABELS:
    try:
        a = L.actor(label)
    except Exception as e:
        out[label] = f"no actor: {e}"
        continue
    a.set_is_temporarily_hidden_in_editor(HIDDEN)
    out[label] = {"hidden_in_game": a.get_editor_property("hidden"),
                  "visible": [c.is_visible() for c in a.get_components_by_class(unreal.SceneComponent)][:1]}
result = out
'''


def isolate(camera: str, frames: list, out: Path) -> None:
    halo = ["SignHalo"]
    lights = [f"Halo{k}" for k in range(9)]

    def hide(labels, hidden):
        res = client.exec_code(f"LABELS = {labels!r}\nHIDDEN = {hidden!r}\n" + HIDE)
        if not res.get("ok"):
            raise SystemExit(res.get("stdout", "") + res.get("error", ""))
        return res["result"]

    def still(f, tag):
        remote = _j(REMOTE, f"{camera}_f{f}_{tag}.png")
        r = client.op("seq.still", path=SEQ, frame=f, camera=camera, out=remote, width=1280, height=720, settle=40)
        if not r.get("ok"):
            raise SystemExit(r.get("stdout", "") + r.get("error", ""))
        print(client.pull(remote, str(out / f"{camera}_f{f}_{tag}.png")))

    res = client.exec_code(f"SEQ = {SEQ!r}\nLABELS = []\n" + LIVE)  # MPC_FM's values (and nothing else)
    print(json.dumps(res.get("result"), indent=1, default=str) if res.get("ok") else res.get("error"))
    print(json.dumps(hide(halo, False), indent=1, default=str))  # SignHalo as the level has it
    try:
        for f in frames:
            still(f, "warm")  # thrown away: the first evaluation after opening can miss tracks
            still(f, "as_is")
            hide(halo, True)
            still(f, "no_card")
            hide(lights, True)
            still(f, "no_card_no_lights")
            hide(halo + lights, False)
    finally:
        hide(halo + lights, False)


MPC_STATE = r'''
import unreal
EAL, MEL = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary
m = EAL.load_asset("/Game/FM/Materials/M_FM_GlowWipe")
out = {"fm_rev": EAL.get_metadata_tag(m, "fm_rev")}
nodes, seen = [], set()
def walk(e):
    if e is None or e.get_name() in seen:
        return
    seen.add(e.get_name())
    if isinstance(e, unreal.MaterialExpressionCollectionParameter):
        c = e.get_editor_property("collection")
        nodes.append({"param": str(e.get_editor_property("parameter_name")),
                      "collection": c.get_path_name() if c else None})
    for i in MEL.get_inputs_for_material_expression(m, e):
        walk(i)
walk(MEL.get_material_property_input_node(m, unreal.MaterialProperty.MP_EMISSIVE_COLOR))
out["collection_nodes"] = nodes
seq = EAL.load_asset(SEQ)
trs = []
for t in seq.find_tracks_by_type(unreal.MovieSceneMaterialParameterCollectionTrack):
    c = t.get_editor_property("mpc")
    trs.append({"mpc": c.get_path_name() if c else None,
                "sections": [{"class": x.get_class().get_name(), "active": x.is_active(),
                              "range": [x.has_start_frame(), x.has_end_frame()],
                              "channels": [(ch.get_name(), ch.get_num_keys()) for ch in x.get_all_channels()]}
                             for x in t.get_sections()]})
out["collection_tracks"] = trs
result = out
'''

MPC_DEFAULT = r'''
import unreal
c = unreal.EditorAssetLibrary.load_asset("/Game/FM/Materials/MPC_FM")
ps = list(c.get_editor_property("scalar_parameters"))
for p in ps:
    if str(p.get_editor_property("parameter_name")) == "WipeOn":
        p.set_editor_property("default_value", VALUE)
c.set_editor_property("scalar_parameters", ps)
result = [(str(p.get_editor_property("parameter_name")), p.get_editor_property("default_value")) for p in ps]
'''


def mpc_probe(camera: str, frames: list, out: Path) -> None:
    def run(code):
        res = client.exec_code(code)
        if not res.get("ok"):
            raise SystemExit(res.get("stdout", "") + res.get("error", ""))
        print(json.dumps(res["result"], indent=1, default=str))

    def still(f, tag):
        remote = _j(REMOTE, f"{camera}_f{f}_{tag}.png")
        r = client.op("seq.still", path=SEQ, frame=f, camera=camera, out=remote, width=1280, height=720, settle=40)
        if not r.get("ok"):
            raise SystemExit(r.get("stdout", "") + r.get("error", ""))
        print(client.pull(remote, str(out / f"{camera}_f{f}_{tag}.png")))

    run(f"SEQ = {SEQ!r}\n" + MPC_STATE)
    try:
        for f in frames:
            still(f, "warm")
            still(f, "as_is")
            run("VALUE = 0.0\n" + MPC_DEFAULT)
            still(f, "wipeon_default_0")
            run("VALUE = 1.0\n" + MPC_DEFAULT)
    finally:
        run("VALUE = 1.0\n" + MPC_DEFAULT)


def tracks() -> None:
    head = f"SEQ = {SEQ!r}\nLABELS = ['SignHalo', 'Outside', 'Terminal']\n"
    for name, code in (("TRACKS", TRACKS), ("LIVE", LIVE), ("GRAPH", GRAPH), ("GLOWS", GLOWS)):  # separate calls:
        print(f"== {name} ==")                                  # the open sequence evaluates on a tick in between
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
    ap.add_argument("--mpc", action="store_true", help="does the card read MPC_FM, does the track reach it")
    ap.add_argument("--isolate", action="store_true", help="stills with and without SignHalo and Halo0-8")
    ap.add_argument("--tracks", action="store_true", help="dump the material tracks and what the meshes wear at f725")
    a = ap.parse_args()
    if a.tracks:
        return tracks()
    if a.mpc:
        return mpc_probe(a.camera, [int(x) for x in a.frames.split(",")], a.out)
    if a.isolate:
        return isolate(a.camera, [int(x) for x in a.frames.split(",")], a.out)
    res = client.exec_code(STATE)
    if not res.get("ok"):
        raise SystemExit(res.get("stdout", "") + res.get("error", ""))
    print(json.dumps(res["result"], indent=1))
    if a.no_stills:
        return
    frames = [int(x) for x in a.frames.split(",")]
    # a throwaway still first: the first evaluation after opening the sequence can miss the material tracks
    for f in [frames[0], *frames]:
        remote = _j(REMOTE, f"{a.camera}_f{f}.png")
        r = client.op("seq.still", path=SEQ, frame=f, camera=a.camera, out=remote, width=1280, height=720, settle=40)
        if not r.get("ok"):
            raise SystemExit(r.get("stdout", "") + r.get("error", ""))
    for f in frames:
        print(client.pull(_j(REMOTE, f"{a.camera}_f{f}.png"), str(a.out / f"{a.camera}_f{f}.png")))


if __name__ == "__main__":
    main()
