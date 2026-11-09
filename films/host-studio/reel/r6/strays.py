# pre-render guard: delete FMQA_* temp actors and any Test_perf_* presenter copy whose bounds are above z -500 (on the set); save if any
import unreal
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
gone = []
for a in EAS.get_all_level_actors():
    n = a.get_actor_label(); cl = a.get_class().get_name()
    o, e = a.get_actor_bounds(False)
    if n.startswith("FMQA_") or (n.startswith("Test_perf_") and cl.startswith("BP_") and o.z > -500):
        gone.append([n, cl, [round(o.x), round(o.y), round(o.z)]]); EAS.destroy_actor(a)
if gone:
    unreal.EditorLevelLibrary.save_current_level()
result = {"deleted": gone}
