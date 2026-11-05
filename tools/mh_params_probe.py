# film-ue exec tools/mh_params_probe.py   -- read-only: why mh.item_params is empty on a real groom. Set CH to the selftest character (or leave "" for the last MH under /Game)
CH = ""
import unreal, traceback
from fmbridge.ops.mh import _core as K, wardrobe as W
R = {}
def t(k, f):
    try: R[k] = K.plain(f()) if hasattr(K, "plain") else str(f())
    except Exception as e: R[k] = "ERR " + repr(e)[:300]
if not CH:
    from fmbridge.ops.assets import list_assets
    chs = [p for c, p in list_assets("/Game", "MetaHumanCharacter")]
    R["characters"] = chs[:10]; CH = chs[-1] if chs else ""
R["ch"] = CH
c = K.char(CH); coll = W._coll(c); inst = W._inst(coll)
R["inst_class"] = inst.get_class().get_name()
R["inst_dir"] = [n for n in dir(inst) if any(w in n.lower() for w in ("param", "assembl", "overrid", "selection", "item"))]
R["lib_dir"] = [n for n in dir(unreal.MetaHumanCharacterInstanceBlueprintLibrary)
                if not n.startswith("_")] if hasattr(unreal, "MetaHumanCharacterInstanceBlueprintLibrary") else "no lib"
sel = W._selected(inst).get("Hair")
R["hair_sel"] = str(sel)
if sel is not None:
    t("hair_key", lambda: W._key_name(sel.get_editor_property("selected_item")))
    try: path = sel.get_selected_item_path()
    except AttributeError: path = unreal.MetaHumanPipelineSlotSelectionBlueprintLibrary.get_selected_item_path(sel)
    R["path"] = str(path)
    t("path_props", lambda: {n: str(path.get_editor_property(n)) for n in ("parent_item_path", "item", "path_entries")
                             if True})
    t("params_method", lambda: [str(p.get_editor_property("name")) for p in inst.get_instance_parameters(path)])
    t("params_lib", lambda: [str(p.get_editor_property("name")) for p in
        unreal.MetaHumanCharacterInstanceBlueprintLibrary.get_instance_parameters_for_item(inst, path)])
    # every no-arg getter that mentions params, in case the map is keyed differently
    for n in R["inst_dir"]:
        if "param" in n.lower() and n.startswith("get"):
            t("call:" + n, lambda n=n: str(getattr(inst, n)())[:600])
t("assembly_output", lambda: str(inst.get_assembly_output())[:400])
result = R
