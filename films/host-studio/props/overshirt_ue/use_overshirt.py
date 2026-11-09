"""Put an overshirt mesh on her Overshirt component: round 3's (SKM_Presenter_Overshirt, the default) or, to go back,
round 2's (pass via film-ue exec -c "WHICH='r2'" or edit WHICH). Run dress_her.py and seq_dress.py after: changing
the component re-creates her components. Run with film-ue exec."""
import unreal

from fmbridge.ops import level as L

WHICH = globals().get("WHICH", "r3")
MESH = "/Game/Host/Presenter_Overshirt/SKM_Presenter_Overshirt" + ("_r2" if WHICH == "r2" else "")
m = unreal.load_asset(MESH)
if m is None:
    raise RuntimeError(f"use_overshirt: no {MESH}")
c = next(c for c in L.actor("Presenter").get_components_by_class(unreal.SkeletalMeshComponent)
         if c.get_name() == "Overshirt")
c.set_skeletal_mesh_asset(m)
result = {"overshirt": MESH}
