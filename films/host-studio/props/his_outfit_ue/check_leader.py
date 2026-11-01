"""Read-only: after a studio rebuild, his garments' leader, their reference root (scale 1) and whether they sit on his
body; the default garment's shorts slots. Run with film-ue exec; changes and saves nothing."""
import unreal
from fmbridge.ops import level as L

comps = {c.get_name(): c for c in L.actor("Host").get_components_by_class(unreal.SkeletalMeshComponent)}
out = {"components": sorted(comps)}
for n, c in comps.items():
    if n in ("Body", "Face"):
        continue
    lead = c.get_editor_property("leader_pose_component")
    t = c.get_ref_pose_transform(c.get_bone_index("root"))
    out[n] = {"leader": lead.get_name() if lead else None,
              "mesh": c.get_skeletal_mesh_asset().get_path_name().split(".")[-1] if c.get_skeletal_mesh_asset() else None,
              "root_scale": round(t.scale3d.x, 3),
              "off_body_cm": [round((c.get_socket_location(b) - comps["Body"].get_socket_location(b)).length(), 3)
                              for b in ("pelvis", "calf_l", "foot_r")]}
g = comps.get("SkeletalMesh")
if g is not None:
    out["shorts"] = sorted({m.get_name() if m else None for s, m in zip(g.get_material_slot_names(), g.get_materials())
                            if "short" in str(s).lower()})
result = out
