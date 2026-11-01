"""Read-only: his MetaHuman (Host): its components, the garment's mesh, material slots and sections, the character's
wardrobe slots."""
import unreal

EAL = unreal.EditorAssetLibrary
host = next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
            if a.get_actor_label() == "Host")
out = {"class": host.get_class().get_path_name(), "hidden_in_game": host.is_hidden_ed()}
comps = {}
for c in host.get_components_by_class(unreal.SkeletalMeshComponent):
    m = c.get_skeletal_mesh_asset()
    d = {"mesh": m.get_path_name() if m else None,
         "parent": c.get_attach_parent().get_name() if c.get_attach_parent() else None,
         "visible": c.is_visible(),
         "leader": (c.get_editor_property("leader_pose_component").get_name()
                    if c.get_editor_property("leader_pose_component") else None)}
    if m:
        d["slots"] = [str(s.material_slot_name) for s in m.materials]
        d["mats"] = [x.get_path_name() if x else None for x in c.get_materials()]
        try:
            d["sections"] = m.get_num_sections(0)
        except Exception as e:
            d["sections"] = str(e)
        try:
            d["skeleton"] = m.skeleton.get_path_name()
        except Exception:
            pass
        b = m.get_bounds()
        d["bounds"] = [[round(b.origin.x, 1), round(b.origin.y, 1), round(b.origin.z, 1)],
                       [round(b.box_extent.x, 1), round(b.box_extent.y, 1), round(b.box_extent.z, 1)]]
    comps[c.get_name()] = d
out["components"] = comps
assets = {}
for p in EAL.list_assets("/Game/Host", recursive=False, include_folder=True):
    assets[p] = 1
out["host_dir"] = sorted(assets)
try:
    c = unreal.load_asset("/Game/Host/Host_Trey")
    coll = c.get_editor_property("internal_collection")
    out["slots"] = [str(x) for x in coll.get_slot_names()]
    inst = coll.get_editor_property("default_instance")
    out["selections"] = [str(x) for x in inst.get_editor_property("slot_selections")]
except Exception as e:
    out["char_err"] = str(e)
result = out
