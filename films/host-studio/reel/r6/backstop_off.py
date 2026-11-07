"""Round 6, K1 (agent-02): the neck backstop OFF. Sets MaxShrinkDistance 0 on his neck wardrobe item (the round-5b
WI_Host_DefaultGarment_Neck, loop 2's T_Host_NeckHidden on it): a WI SETTING change, so mh.build re-bakes it (a
texture-only change did not: r5/garment.md §9). The mask never goes below 1/255 and MaxCull is 0.0, so nothing is
culled either: his face comes out of the build exactly as MetaHuman made it. Then: mh.build force=true, assets.save
folder=/Game/Host BEFORE any level step, and prove it with shrink_live.py (by_surface moved_gt_0.5cm 0).

    film-ue exec films/host-studio/reel/r6/backstop_off.py
"""
import unreal

WI = globals().get("WI", "/Game/Host/Fit/WI_Host_DefaultGarment_Neck")
EAL = unreal.EditorAssetLibrary


def gp(o, n):
    for k in (n, "".join(w[:1].upper() + w[1:] for w in n.split("_"))):
        try:
            return o.get_editor_property(k)
        except Exception:  # noqa: BLE001
            pass
    raise KeyError(n)


def sp(o, n, v):
    for k in (n, "".join(w[:1].upper() + w[1:] for w in n.split("_"))):
        try:
            o.set_editor_property(k, v)
            return
        except Exception:  # noqa: BLE001
            pass
    raise KeyError(n)


wi = EAL.load_asset(WI)
ed = gp(gp(wi, "pipeline"), "editor_pipeline")
h = gp(ed, "head_hidden_face_map_texture")
s = gp(h, "settings")
before = gp(s, "max_shrink_distance")
sp(s, "max_shrink_distance", 0.0)
sp(s, "max_cull_value", 0.0)
sp(h, "settings", s)
sp(ed, "head_hidden_face_map_texture", h)
EAL.save_asset(WI)
bs = gp(gp(ed, "head_hidden_face_map_texture"), "settings")
result = {"wi": WI, "max_shrink_distance": [before, gp(bs, "max_shrink_distance")],
          "max_cull_value": gp(bs, "max_cull_value"), "min_keep_value": gp(bs, "min_keep_value"),
          "next": "mh.build force=true; assets.save folder=/Game/Host; level.open; host_swap; shrink_live (0 moved)"}
