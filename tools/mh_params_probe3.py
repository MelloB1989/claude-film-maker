# film-ue exec tools/mh_params_probe3.py -- assembles CH (selftest character) and lists every item path with params
CH = "/Game/_Selftest/mh/MH_ST_mh_A"
import unreal, importlib
from fmbridge.ops.mh import _core as K
W = importlib.import_module("fmbridge.ops.mh.wardrobe")
R = {}
def t(k, f):
    try: R[k] = K.plain(f())
    except Exception as e: R[k] = "ERR " + repr(e)[:400]
c = K.char(CH); coll = W._coll(c); inst = W._inst(coll)
st = {}
def cb(result):
    st["result"] = str(result)
d = unreal.MetaHumanCharacterAssembled(); d.bind_callable(cb)
t("assemble", lambda: str(inst.assemble(d)))
R["cb_result_sync"] = st.get("result", "NOT CALLED")
t("is_assembled", lambda: inst.is_assembled())
t("collection_pipeline", lambda: str(coll.get_editor_property("pipeline")))
t("path_dir", lambda: [n for n in dir(unreal.MetaHumanPaletteItemPath) if not n.startswith("_")])
t("item_paths", lambda: [str(p) for p in inst.get_instance_parameter_item_paths()])
def _all():
    out = []
    for p in inst.get_instance_parameter_item_paths():
        out.append({"path": str(p), "path_dir": [n for n in dir(p) if not n.startswith("_")][:40],
                    "params": [str(x.get_editor_property("name")) for x in inst.get_instance_parameters(p)]})
    return out
t("params_by_path", _all)
sel = W._selected(inst).get("Hair")
if sel is not None:
    sp = W._sel_path(sel)
    t("sel_path", lambda: str(sp))
    t("sel_params", lambda: [str(x.get_editor_property("name")) for x in inst.get_instance_parameters(sp)])
    t("sel_eq", lambda: [p == sp for p in inst.get_instance_parameter_item_paths()])
    t("key_props", lambda: str(sel.get_editor_property("selected_item")))
    t("try_get", lambda: str(inst.try_get_instance_parameter(sp, "Melanin")))
t("assembly_output", lambda: str(inst.get_assembly_output())[:600])
result = R
