# film-ue exec tools/mh_params_probe2.py -- step 2: ASSEMBLES the instance of CH (changes only its transient assembly
# output, on a selftest character) and lists the instance parameters afterwards. Read the doc lines first if unsure.
CH = "/Game/_Selftest/mh/MH_ST_mh_A"
import unreal, importlib, time
from fmbridge.ops.mh import _core as K
W = importlib.import_module("fmbridge.ops.mh.wardrobe")
R = {}
def t(k, f):
    try: R[k] = K.plain(f())
    except Exception as e: R[k] = "ERR " + repr(e)[:400]
c = K.char(CH); coll = W._coll(c); inst = W._inst(coll)
for n in ("assemble", "is_assembled", "get_instance_parameter_item_paths", "get_instance_parameters",
          "try_get_instance_parameter", "get_assembly_output", "get_existing_assembly_output", "clear_assembly_output"):
    t("doc:" + n, lambda n=n: (getattr(inst, n).__doc__ or "")[:700])
t("doc:MetaHumanPaletteItemPath", lambda: (unreal.MetaHumanPaletteItemPath.__doc__ or "")[:700])
t("path_dir", lambda: [n for n in dir(unreal.MetaHumanPaletteItemPath) if not n.startswith("_")])
t("enums", lambda: [n for n in dir(unreal) if "MetaHuman" in n and ("Quality" in n or "Assembl" in n)])
t("is_assembled_before", lambda: inst.is_assembled())
# assemble: try the signatures the doc may show; the first that does not raise wins
tried = []
def _assemble():
    q = getattr(unreal, "MetaHumanCharacterPaletteBuildQuality", None)
    for args in ([], [q.PREVIEW] if q and hasattr(q, "PREVIEW") else None,
                 [q.PRODUCTION] if q and hasattr(q, "PRODUCTION") else None):
        if args is None: continue
        try:
            r = inst.assemble(*args); tried.append((str(args), "ok")); return str(r)
        except Exception as e:
            tried.append((str(args), repr(e)[:300]))
    return None
t("assemble", _assemble)
R["assemble_tried"] = tried
t0 = time.time()
t("is_assembled_after", lambda: inst.is_assembled())
t("item_paths_after", lambda: [str(p) for p in inst.get_instance_parameter_item_paths()])
def _all():
    out = {}
    for p in inst.get_instance_parameter_item_paths():
        out[str(p)] = {str(x.get_editor_property("name")): K.enum_name(x.get_editor_property("type"))
                       for x in inst.get_instance_parameters(p)}
    return out
t("params_after", _all)
sel = W._selected(inst).get("Hair")
if sel is not None:
    t("hair_sel_props", lambda: {n: str(sel.get_editor_property(n)) for n in ("slot_name", "selected_item")})
    t("hair_selected_path", lambda: str(sel.get_selected_item_path()))
t("assembly_output_after", lambda: str(inst.get_assembly_output())[:400])
result = R
