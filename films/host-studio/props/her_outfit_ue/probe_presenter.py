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
