"""The operator's MetaHuman (round 3, note 2), from their Live Link Face capture (MetaHuman Animator mode: video +
depth) to a MetaHuman Character, in the editor on the box. Run a stage at a time; each prints only structure, counts
and asset paths, never image data:

    film-ue exec films/host-studio/unreal/operator_mh.py      (edit STAGE first, or: STAGE=... via film-ue exec -c)

Stages: inspect (read-only), ingest, identity, conform, character. PRIVATE: the capture stays on the box (TAKE_DIR
outside Content); its assets live under /Game/Host/OperatorCapture and are never pushed, rendered for review or
logged. Only Epic's cloud (rig, textures) sees the face, through the MetaHuman services.
"""
import json
import os

import unreal

STAGE = globals().get("STAGE", "inspect")
TAKE_DIR = "/srv/ue/projects/HostStudio/Capture/operator-face/MySlate_3"
CAPTURE_FOLDER = "/Game/Host/OperatorCapture"
IDENTITY = CAPTURE_FOLDER + "/MHI_Operator"
CHARACTER = "/Game/Host/Host_Op"
# promoted frames (60 fps take): neutral front ~1 s, turned left ~6 s, turned right ~11.5 s; teeth ~16 s
FRAMES = {"front": 60, "left": 360, "right": 690}
TEETH_FRAME = 960

R = {"stage": STAGE}
EAL = unreal.EditorAssetLibrary
lib = unreal.CaptureManagerIngestBlueprintLibrary


def props(obj_or_cls, n=900):
    """The editor properties a type documents (names and types from its docstring), for the report."""
    d = (getattr(obj_or_cls, "__doc__", "") or "")
    i = d.find("**Editor Properties:**")
    return d[i:i + n] if i >= 0 else d[:n]


def t(k, f):
    try:
        R[k] = f()
    except Exception as e:  # report and go on: a stage is a probe as much as a step
        R[k] = "ERR " + repr(e)[:400]


def plain(v):
    try:
        return json.loads(json.dumps(v, default=str))
    except Exception:
        return str(v)


def footage():
    a = EAL.load_asset(R.get("footage_path") or _find_footage())
    if a is None:
        raise RuntimeError("no FootageCaptureData under " + CAPTURE_FOLDER + ": run STAGE=ingest")
    return a


def _find_footage():
    for p in EAL.list_assets(CAPTURE_FOLDER, True, False):
        a = EAL.find_asset_data(p)
        if str(a.asset_class_path.asset_name) == "FootageCaptureData":
            return p.split(".")[0]
    return ""


if STAGE == "inspect":
    t("conversion_params", lambda: props(unreal.CaptureManagerConversionParams, 2500))
    t("takes", lambda: [plain({k: str(getattr(x, k, "")) for k in dir(x) if not k.startswith("_") and k.islower()
                                and not callable(getattr(x, k, None))}) for x in lib.find_take_directories(TAKE_DIR)][:3])
    t("take_info_props", lambda: props(unreal.CaptureManagerTakeDirectoryInfo, 1500))
    for cls in ("MetaHumanIdentityFootageFrame", "MetaHumanIdentityPromotedFrame", "MetaHumanIdentityPose",
                "MetaHumanIdentityFace", "MetaHumanIdentity", "FootageCaptureData", "ImgMediaSource",
                "MetaHumanIdentityFactoryNew"):
        t("props:" + cls, lambda cls=cls: props(getattr(unreal, cls), 2500))
    t("img_media_methods", lambda: [n for n in dir(unreal.ImgMediaSource) if "path" in n or "sequence" in n])

elif STAGE == "ingest":
    # Linux UE cannot decode the iPhone's H.264/AAC .mov itself (day 3: 'Video file format is unsupported ... Consider
    # enabling Third Party Encoder in Capture Manager settings'): point Capture Manager at the box's ffmpeg
    import shutil
    ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
    st = unreal.get_default_object(unreal.CaptureManagerEditorSettings)
    R["settings_props"] = props(unreal.CaptureManagerEditorSettings, 3000)
    for k in [ln.split("``")[1] for ln in R["settings_props"].splitlines() if ln.startswith("- ``")]:
        low, v = k.lower(), None
        try:
            cur = st.get_editor_property(k)
        except Exception:
            continue
        if isinstance(cur, bool) and ("third" in low or "encoder" in low):
            v = True
        elif ("encoder" in low or "ffmpeg" in low) and ("path" in low or "binary" in low or "executable" in low):
            v = ffmpeg if isinstance(cur, str) else unreal.FilePath(file_path=ffmpeg)
        if v is not None:
            st.set_editor_property(k, v)
            R.setdefault("settings_set", {})[k] = str(v)
    t("settings_saved", lambda: (st.save_config(), True)[1])
    params = unreal.CaptureManagerConversionParams()
    R["params_before"] = plain(params.to_dict()) if hasattr(params, "to_dict") else str(params)
    for k in list(R["params_before"]) if isinstance(R["params_before"], dict) else []:
        if any(w in k.lower() for w in ("package", "content", "asset_path", "destination", "target_folder")):
            params.set_editor_property(k, CAPTURE_FOLDER)
            R.setdefault("set", []).append(k)
    fcd, err = lib.ingest_live_link_face_sync(TAKE_DIR, params)
    R["error"] = str(err)
    if fcd is not None:
        R["footage_path"] = fcd.get_path_name().split(".")[0]
        t("views", lambda: len(fcd.get_editor_property("image_sequences") or []))
        t("depth_views", lambda: len(fcd.get_editor_property("depth_sequences") or []))
        t("image_seq", lambda: [s.get_path_name() for s in fcd.get_editor_property("image_sequences")])
        t("depth_seq", lambda: [s.get_path_name() for s in fcd.get_editor_property("depth_sequences")])
        t("calibrations", lambda: [c.get_path_name() for c in fcd.get_editor_property("camera_calibrations")])
        t("seq_dirs", lambda: [s.get_sequence_path() for s in fcd.get_editor_property("image_sequences")
                               + fcd.get_editor_property("depth_sequences")])
        t("frames_on_disk", lambda: [len(os.listdir(p)) if os.path.isdir(p) else p for p in R["seq_dirs"]])
        EAL.save_loaded_asset(fcd)

R["done"] = True
result = R
