"""Where she is and what hides her: every actor with a skeletal mesh or a stool-ish label, its hidden flags, its
components' visibility and its location. Read-only. Run with film-ue exec."""
import unreal

out = []
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    lab = a.get_actor_label()
    sk = a.get_components_by_class(unreal.SkeletalMeshComponent)
    if not sk and "stool" not in lab.lower() and not lab.startswith("Her"):
        continue
    p = a.get_actor_location()
    out.append({"label": lab, "class": a.get_class().get_name(), "at": [round(p.x), round(p.y), round(p.z)],
                "hid_ed": a.is_temporarily_hidden_in_editor(), "hid_game": a.get_editor_property("hidden"),
                "parent": a.get_attach_parent_actor().get_actor_label() if a.get_attach_parent_actor() else None,
                "comps": {c.get_name(): [c.is_visible(), c.get_editor_property("hidden_in_game")] for c in sk}})
cur = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()
result = {"actors": out, "seq": cur.get_path_name() if cur else None}
# what she wears and at which detail level: her body's materials (the MetaHuman body carries underwear in its
# texture), and the LOD each of her parts draws at (a garment fitted to LOD0 can be crossed by a coarser body)
for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    if a.get_actor_label() != "Presenter":
        continue
    parts = {}
    for c in a.get_components_by_class(unreal.SkeletalMeshComponent):
        m = c.get_skeletal_mesh_asset()
        info = {"mesh": m.get_path_name() if m else None,
                "slots": {str(n): (x.get_path_name() if x else None) for n, x in zip(c.get_material_slot_names(), c.get_materials())}}
        for k in ("forced_lod_model", "min_lod_model"):
            try:
                info[k] = c.get_editor_property(k)
            except Exception:
                pass
        try:
            info["lods"] = m.get_editor_property("lod_info").__len__() if m else None
        except Exception:
            pass
        parts[c.get_name()] = info
    others = [c.get_class().get_name() + ":" + c.get_name() for c in a.get_components_by_class(unreal.ActorComponent)
              if "LOD" in c.get_class().get_name() or "Groom" in c.get_class().get_name()]
    result["parts"], result["lod_comps"] = parts, others
