"""Why do her garments lose their leader pose? On a scratch copy of her Blueprint (deleted after; the Presenter is only
read): add a garment component under Body with leader pose as studio.py does, then move the copy (the editor re-runs
its construction script) and see whether the link and the Body object survive. Also lists anim Blueprints that could
copy a pose from a parent mesh instead, and checks the watch's rotation helper. Nothing saved. Run with film-ue exec."""
import unreal

HER_BP = "/Game/Host/Unpacked/Presenter/BP_Presenter"
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
out = {}


def comps(a):
    return {c.get_name(): c for c in a.get_components_by_class(unreal.SkeletalMeshComponent)}


def lead(c):
    x = c.get_editor_property("leader_pose_component")
    return x.get_name() if x else None


her = next(a for a in EAS.get_all_level_actors() if a.get_actor_label() == "Presenter")
out["presenter"] = {n: lead(c) for n, c in comps(her).items()}
tmp = EAS.spawn_actor_from_object(unreal.load_asset(HER_BP), unreal.Vector(0, 0, -5000), unreal.Rotator(0, 0, 0))
tmp.set_actor_label("ZZ_Agent02_LeaderProbe")
try:
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    SDL = unreal.SubobjectDataBlueprintFunctionLibrary
    body_h = next(h for h in sds.k2_gather_subobject_data_for_instance(tmp)
                  if str(SDL.get_variable_name(SDL.get_data(h))) == "Body")
    new_h, _ = sds.add_new_subobject(unreal.AddNewSubobjectParams(parent_handle=body_h,
                                                                  new_class=unreal.SkeletalMeshComponent))
    sds.rename_subobject(new_h, unreal.Text("Top"))
    c = comps(tmp)
    c["Top"].set_skeletal_mesh_asset(unreal.load_asset("/Game/Host/Presenter_Outfit/SKM_Presenter_Top"))
    c["Top"].set_leader_pose_component(c["Body"])
    body0 = c["Body"].get_path_name()
    out["after_set"] = lead(comps(tmp)["Top"])
    tmp.set_actor_location(unreal.Vector(0, 0, -4990), False, False)
    tmp.rerun_construction_scripts()
    c = comps(tmp)
    out["after_rerun"] = {"top_leader": lead(c["Top"]) if "Top" in c else "component gone",
                          "same_body_object": c["Body"].get_path_name() == body0, "components": sorted(c)}
finally:
    EAS.destroy_actor(tmp)

# anim Blueprints that might copy a pose from the attach parent (a garment's own AnimBP survives re-construction)
ar = unreal.AssetRegistryHelpers.get_asset_registry()
flt = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "AnimBlueprint")], recursive_paths=True,
                      package_paths=["/Game", "/MetaHumanCharacter", "/MetaHuman"])
out["anim_bps"] = sorted(str(d.package_name) for d in ar.get_assets(flt))[:80]

# the watch helper: make_rot_from_yz(fwd, up) should put the actor's Y along fwd
fwd, up = unreal.Vector(0.3, 0.9, -0.3).normal(), unreal.Vector(0, 0, 1)
up = (up - fwd * up.dot(fwd)).normal()
r = unreal.MathLibrary.make_rot_from_yz(fwd, up)
out["rot_from_yz"] = {"x.fwd": round(r.get_forward_vector().dot(fwd), 3), "y.fwd": round(r.get_right_vector().dot(fwd), 3),
                      "z.up": round(r.get_up_vector().dot(up), 3)}
w = next((a for a in EAS.get_all_level_actors() if a.get_actor_label() == "HerWatch"), None)
if w is not None:
    rc = w.root_component
    out["watch"] = {"rel_rot": str(rc.get_editor_property("relative_rotation")), "parent_socket": str(rc.get_attach_socket_name()),
                    "mobility": str(rc.get_editor_property("mobility"))}
result = out
