"""Her Top, Trousers and Overshirt back on leader pose to Body (no anim Blueprint), as studio.py's final pass does, and each
garment's reference pose against the body's: a garment whose root carries a scale (bones in metres under a x100 root)
shrinks to nothing as soon as anything poses it. All three in one pass: touching one instance component re-creates
the others, so setting only Top/Trousers dropped the Overshirt's leader. Run with film-ue exec; nothing saved."""
import unreal

from fmbridge.ops import level as L

comps = {c.get_name(): c for c in L.actor("Presenter").get_components_by_class(unreal.SkeletalMeshComponent)}
out = {}


def ref(c, bone):
    i = c.get_bone_index(bone)
    try:
        t = c.get_ref_pose_transform(i)
        return {"t": [round(t.translation.x, 3), round(t.translation.y, 3), round(t.translation.z, 3)],
                "s": [round(t.scale3d.x, 3), round(t.scale3d.y, 3), round(t.scale3d.z, 3)]}
    except Exception as e:
        return str(e)


for n in ("Body", "Top", "Trousers", "Overshirt"):
    if n in comps:
        out[n + "_ref"] = {b: ref(comps[n], b) for b in ("root", "pelvis", "spine_01")}
for n in ("Top", "Trousers", "Overshirt"):
    c = comps[n]
    c.set_anim_instance_class(None)
    c.set_leader_pose_component(comps["Body"])
comps = {c.get_name(): c for c in L.actor("Presenter").get_components_by_class(unreal.SkeletalMeshComponent)}
for n in comps:
    lead = comps[n].get_editor_property("leader_pose_component")
    ac = comps[n].get_editor_property("anim_class")
    out[n] = {"leader": lead.get_name() if lead else None, "anim_class": ac.get_name() if ac else None}
result = out
