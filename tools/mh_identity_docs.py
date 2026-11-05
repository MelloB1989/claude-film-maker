# film-ue exec tools/mh_identity_docs.py -- READ-ONLY: docstrings of the footage -> identity -> character route
import unreal
R = {}
def doc(cls, names):
    c = getattr(unreal, cls, None)
    if c is None:
        R[cls] = "missing"; return
    for n in names:
        try: R[f"{cls}.{n}"] = (getattr(c, n).__doc__ or "")[:900]
        except Exception as e: R[f"{cls}.{n}"] = "ERR " + repr(e)[:200]
doc("CaptureManagerIngestBlueprintLibrary", ["ingest_live_link_face_sync", "ingest_live_link_face", "find_take_directories",
                                            "ingest_take_archive_sync"])
doc("MetaHumanIdentity", ["get_or_create_part_of_class", "start_frame_tracking_pipeline", "set_blocking_processing",
                          "create_dna_for_identity", "log_in_to_auto_rig_service", "is_logged_in_to_service",
                          "is_auto_rigging_in_progress", "is_frame_tracking_pipeline_processing", "export_dna_data_to_files"])
doc("MetaHumanIdentityFace", ["add_pose_of_type", "find_pose_by_type", "conform", "initialize", "run_predictive_solver_training",
                              "is_conformal_rig_valid", "export_template_mesh"])
doc("MetaHumanIdentityPose", ["add_new_promoted_frame", "set_capture_data", "load_default_tracker", "fit_eyes",
                              "remove_promoted_frame"])
doc("MetaHumanCharacterEditorSubsystem", ["import_from_identity", "import_from_template", "import_from_face_dna",
                                          "fit_face_state_from_body_with_eyes_teeth_dna", "conform_to_target_meshes"])
for s in ("ImportFromIdentityParams", "IdentityPoseType", "IdentityErrorCode", "CaptureManagerIngestType", "TeethMode",
          "ConformType", "MetaHumanCaptureSourceType"):
    c = getattr(unreal, s, None)
    R["type:" + s] = "missing" if c is None else [n for n in dir(c) if not n.startswith("_")][:60]
    R["typedoc:" + s] = "" if c is None else (c.__doc__ or "")[:900]
result = R
