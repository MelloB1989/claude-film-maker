"""Read-only: is she dressed as the reel needs? Each of her skeletal mesh components (leader, anim mode/class, mesh),
her hair's materials, her accessories' parents and offsets, and what SEQ_Reel binds under Presenter (a track on a
garment, e.g. an animation or visibility track, overrides or re-creates what the level set). Run with film-ue exec."""
import unreal

from fmbridge.ops import level as L

her = L.actor("Presenter")
out = {"components": {}, "hair": None, "accessories": {}, "seq": {}}
for c in her.get_components_by_class(unreal.SkeletalMeshComponent):
    lead = c.get_editor_property("leader_pose_component")
    ac = c.get_editor_property("anim_class")
    m = c.get_skeletal_mesh_asset()
    out["components"][c.get_name()] = {"leader": lead.get_name() if lead else None,
                                       "mode": str(c.get_editor_property("animation_mode")),
                                       "anim_class": ac.get_name() if ac else None,
                                       "mesh": m.get_name() if m else None,
                                       "parent": c.get_attach_parent().get_name() if c.get_attach_parent() else None}
hair = next((g for g in her.get_components_by_class(unreal.GroomComponent) if g.get_name() == "Hair"), None)
if hair:
    out["hair"] = [str(hair.get_material(i).get_name()) if hair.get_material(i) else None for i in range(3)]
for lab in ("HerEarL", "HerEarR", "HerWatch"):
    try:
        a = L.actor(lab)
    except ValueError:
        continue
    rc = a.root_component
    p = rc.get_attach_parent()
    out["accessories"][lab] = {"parent": p.get_name() if p else None, "socket": str(rc.get_attach_socket_name()),
                               "rel": [round(v, 2) for v in (rc.relative_location.x, rc.relative_location.y,
                                                             rc.relative_location.z)]}
seq = unreal.load_asset("/Game/Reel/SEQ_Reel")
if seq:
    for b in seq.get_bindings():
        name = str(b.get_display_name())
        parent = b.get_parent()
        pname = str(parent.get_display_name()) if parent and parent.get_id() != b.get_id() else ""
        if "Presenter" in (name, pname) or name in ("Top", "Trousers", "Overshirt", "Body", "Face", "Hair"):
            tracks = []
            for t in b.get_tracks():
                secs = t.get_sections()
                tracks.append([t.get_class().get_name(), len(secs),
                               [[s.get_start_frame(), s.get_end_frame()] for s in secs][:4]])
            out["seq"][f"{pname}/{name}" if pname else name] = tracks
result = out
