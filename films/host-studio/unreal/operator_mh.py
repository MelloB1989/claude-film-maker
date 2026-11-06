"""The operator's MetaHuman (round 3, note 2), from their Live Link Face capture (MetaHuman Animator mode: video +
depth) to a MetaHuman Character, in the editor on the box. Run a stage at a time; each prints only structure, counts
and asset paths, never image data:

    film-ue exec films/host-studio/unreal/operator_mh.py      (edit STAGE first, or: STAGE=... via film-ue exec -c)

Stages: inspect (read-only), ingest, identity, conform, character. PRIVATE: the capture stays on the box (TAKE_DIR
outside Content); its assets live under /Game/Host/OperatorCapture and are never pushed, rendered for review or
logged. Only Epic's cloud (rig, textures) sees the face, through the MetaHuman services.
"""
# STATUS (round 3, 2026-11-05, UE 5.8.4 Linux on the GPU box) - read before round 4
# Works: inspect; ingest (CD_MySlate_3 + IS_V_/IS_D_ sequences + CC_ calibration; 1508 video frames at 60 fps, 755
#   depth at 30). Needs Capture Manager's third-party encoder: CaptureManagerEditorSettings enable_third_party_encoder
#   = True and third_party_encoder = FilePath(ffmpeg >= 5.1: the engine passes -fps_mode; the box's apt 4.4 fails,
#   the static 8.1 at /srv/ue/tools/ffmpeg works). Frames land in ~/.config/Epic/CaptureManager/Media (private).
# Fails: identity. The pose takes the footage (capture valid, camera "Video", config "iPhone 13", default tracker
#   GenericFaceContourTracker, can_track true), promoted frames are added (add_new_promoted_frame, frame_number set),
#   start_frame_tracking_pipeline(pixels, 720, 1280, depth exr, pose, frame, False) returns, but the frames never get
#   contours (frame_contours_contain_active_data false, also in a later exec and after the tracker's NNE models were
#   warmed through the Creator's track_face_landmarks_from_image, which does find the face); conform -> DEPTH_INPUT.
#   Log: only 'Detected mismatch in image media frame rates ... exclude some frames' (expected: 60 vs 30; even frames
#   are paired). Lead: the frames' contour data is not initialised for the capture config in a scripted promote (the
#   toolkit does it on promote); look for the call in unreal.PromotedFrameUtils and Epic's MetaHuman Python samples
#   (Engine/Plugins/MetaHuman*/**/Python). MetaHumanContourData has no Python-visible fields.
# UPDATE (round 3, later the same night): FIXED. The missing call was
#   PromotedFrameUtils.initialize_contour_data_for_footage_frame(pose, frame) (Epic's
#   MetaHumanAnimator/Content/Python/create_identity_for_performance.py); with Epic's sequence (the identity stage now)
#   all 3 frames tracked and conform = NONE. character: import_from_identity SUCCESS; bodies.py --who op: rig 75 s,
#   textures 5 s, build 94 s -> /Game/Host/Unpacked/Host_Op/BP_Host_Op (the build was refused once right after the
#   textures; bodies.py now retries). The blank character wears nothing: STAGE='grooms' (OUTFIT + GROOMS, a hair/beard/
#   brows PLACEHOLDER) then mh.build; colours need a built collection (grooms, build, grooms, build).
#   Not swapped in on round 3 (the operator's decision): tomorrow, grooms -> build -> host_swap.py HOST='op' -> save ->
#   clip checks -> save -> STAGE='measure' -> agent-11's heights -> agent-01's calibration on Host_Op.
#   The state (OperatorCapture/**, Host_Op*, Unpacked/Host_Op/**, the CaptureManager Media frames) is saved under
#   ue-linux/private/ only.
# CORRECTION (round 3 overnight): mh.build does NOT build the editing instance's collection, so groom/garment colours
#   (instance parameters) cannot be set on the character even after a (forced) build: 'assembly failed (collection not
#   built)'. Tonight's workaround: colour on the placed actor, groom.set label=Host melanin=0.9 redness=0.1 (per
#   instance, saved with the level). Lead for the real fix: the editor's preview collection
#   (MetaHumanCharacterEditorSubsystem.get_preview_collection / assemble_for_preview), which the Creator UI colours.
# ROUND 3 END STATE (saved, synced to private 21:09 UTC): Host_Op wears HAIR WI_Hair_S_SlickBack, BROWS
#   WI_Eyebrows_M_Full, MUSTACHE WI_Mustache_M_Stubble, no beard (groom.set melanin 1.0 redness 0.05 on the placed actor),
#   SKIN_UV (0.62, 0.58), IRIS_UV (0.92, 0.12), chest 104. Iris palette so far: (0.08, 0.95) renders light blue/grey;
#   (0.92, 0.12) unverified (check an iris crop's hue on the box). Tee hem patches: NOT slot holes (the tee's slots are
#   M_DG_bodyShapeF_Shirt kept + M_DG_bodyShapeF_Short hidden), so if they persist it is the trousers' waistband (fitted
#   to Trey's tee) through Host_Op's tee: slim the trousers' waist band or lower it under the hem tomorrow.
# Not viable: the no-depth route (the Creator's ConformTargetParams wants a target head mesh + 2D curves from a known
#   camera, i.e. a head mesh built from the depth by hand). Untested: the teeth pose (needs the solved identity).
import json
import os

import unreal

STAGE = globals().get("STAGE", "inspect")
TAKE_DIR = "/srv/ue/projects/HostStudio/Capture/operator-face/MySlate_3"
CAPTURE_FOLDER = "/Game/Host/OperatorCapture"
FOOTAGE = CAPTURE_FOLDER + "/CD_MySlate_3"  # what the ingest made (day 3: 1508 video frames at 60 fps, 755 depth at 30)
IDENTITY = CAPTURE_FOLDER + "/MHI_Operator"
CHARACTER = "/Game/Host/Host_Op"
# promoted frames (60 fps take): neutral front ~1 s, turned left ~6 s, turned right ~11.5 s; teeth ~16 s
FRAMES = {"front": 60, "left": 360, "right": 690}
TEETH_FRAME = 960
# what he wears and his grooms: ONE place, so the operator's correction is one STAGE='grooms' run + one rebuild.
# PLACEHOLDER (round 3): the operator's hair, facial hair and brows are not known yet (asked; no answer by the build):
# short dark hair, stubble, medium brows. The outfit is the default garment (the tee; its shorts are hidden by studio.py).
OUTFIT = "WI_DefaultGarment"
GROOMS = {"Hair": ("WI_Hair_S_BuzzCut", 0.9), "Beard": ("WI_Beard_S_Stubble", 0.9),
          "Eyebrows": ("WI_Eyebrows_M_Unruly", 0.9), "Eyelashes": ("WI_Eyelashes_S_Fine", None),
          "Peachfuzz": ("WI_Peachfuzz_M_Thin", None)}  # slot: (item, melanin or None)
# his body (keep in step with films/host-studio/bodies.py "op")
BODY = {"Height": 180, "Across Shoulder": 45, "Front Interscye Length": 40, "Chest": 100, "Underbust": None,
        "Waist": 75, "High Hip": 80, "Hip": 92, "Neck Base": 40, "Neck": 38, "Bicep": 31.5, "Forearm": 27.5,
        "Thigh": 56, "Knee": 34, "Calf": 37, "Fat": -1.4, "Muscularity": 0.7, "Masculine/Feminine": -1.5}

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
    a = EAL.load_asset(FOOTAGE) if EAL.does_asset_exist(FOOTAGE) else EAL.load_asset(_find_footage())
    if a is None:
        raise RuntimeError("no FootageCaptureData under " + CAPTURE_FOLDER + ": run STAGE=ingest")
    return a


def _find_footage():
    """The ingested take: the FootageCaptureData named after the slate, wherever the ingest put it."""
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    hits = [str(a.package_name) for a in reg.get_assets_by_class(unreal.TopLevelAssetPath("/Script/CaptureDataCore",
                                                                                            "FootageCaptureData"))
            if "MySlate_3" in str(a.asset_name)]
    return sorted(hits)[-1] if hits else ""


def abs_dir(p: str) -> str:
    p = p.replace("{project_dir}", unreal.Paths.project_dir()).replace("{engine_dir}", unreal.Paths.engine_dir())
    return os.path.normpath(p if os.path.isabs(p) else os.path.join(unreal.Paths.project_dir(), p))


def frames(seq) -> list:
    d = abs_dir(seq.get_sequence_path() if hasattr(seq, "get_sequence_path") else str(seq))
    return [os.path.join(d, f) for f in sorted(os.listdir(d)) if not f.startswith(".")]


def png_rgba(path: str):
    """(width, height, [unreal.Color]) of an 8-bit RGB/RGBA PNG, decoded with the standard library (no PIL in the
    editor's Python). Only what the ingest writes (8-bit, non-interlaced)."""
    import struct
    import zlib
    with open(path, "rb") as f:
        data = f.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    i, idat, w = 8, [], 0
    while i < len(data):
        n, typ = struct.unpack(">I4s", data[i:i + 8])
        body = data[i + 8:i + 8 + n]
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", body)
            assert depth == 8 and inter == 0 and ctype in (2, 6), (depth, ctype, inter)
            bpp = 4 if ctype == 6 else 3
        elif typ == b"IDAT":
            idat.append(body)
        i += 12 + n
    raw = zlib.decompress(b"".join(idat))
    stride = w * bpp
    out = bytearray(h * stride)
    prev = bytearray(stride)
    for y in range(h):
        ft = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if ft == 1:
                line[x] = (line[x] + a) & 255
            elif ft == 2:
                line[x] = (line[x] + b) & 255
            elif ft == 3:
                line[x] = (line[x] + ((a + b) >> 1)) & 255
            elif ft == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out[y * stride:(y + 1) * stride] = line
        prev = line
    cols = [unreal.Color(r=out[k], g=out[k + 1], b=out[k + 2], a=out[k + 3] if bpp == 4 else 255)
            for k in range(0, len(out), bpp)]
    return w, h, cols


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
    # the engine passes -fps_mode (ffmpeg >= 5.1); the box's apt ffmpeg is 4.4, so prefer the static build
    ffmpeg = next((p for p in ("/srv/ue/tools/ffmpeg/bin/ffmpeg", shutil.which("ffmpeg")) if p and os.path.exists(p)),
                  "/usr/bin/ffmpeg")
    st = unreal.get_default_object(unreal.CaptureManagerEditorSettings)
    R["settings_props"] = props(unreal.CaptureManagerEditorSettings, 3000)
    want = {"enable_third_party_encoder": True,  # live 5.8.4 field names (agent-07's ingest output, day 3)
            "third_party_encoder": unreal.FilePath(file_path=ffmpeg),
            "import_directory": unreal.DirectoryPath(path=CAPTURE_FOLDER),
            "auto_save_assets": True}
    for k, v in want.items():
        try:
            st.set_editor_property(k, v)
            R.setdefault("settings_set", {})[k] = str(v)
        except Exception as e:
            R.setdefault("settings_err", {})[k] = repr(e)[:200]
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

elif STAGE == "identity":
    # Epic's sequence (MetaHumanAnimator/Content/Python/create_identity_for_performance.py, 5.8.4): the neutral pose on
    # the footage, promoted frames whose contour data is initialised for the capture config
    # (PromotedFrameUtils.initialize_contour_data_for_footage_frame - round 3's missing call), each frame's image and its
    # timecode-paired depth path from PromotedFrameUtils, tracking, then the identity solve (conform) - local, editor
    fcd = footage()
    R["footage_path"] = fcd.get_path_name().split(".")[0]
    PFU = unreal.PromotedFrameUtils
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    if EAL.does_asset_exist(IDENTITY):
        EAL.delete_asset(IDENTITY)  # a clean identity each run (round 3 left one with empty frames)
    ident = tools.create_asset(IDENTITY.rsplit("/", 1)[1], CAPTURE_FOLDER, unreal.MetaHumanIdentity,
                               unreal.MetaHumanIdentityFactoryNew())
    face = ident.get_or_create_part_of_class(unreal.MetaHumanIdentityFace)
    pose = unreal.new_object(type=unreal.MetaHumanIdentityPose, outer=face)
    face.add_pose_of_type(unreal.IdentityPoseType.NEUTRAL, pose)
    pose.set_capture_data(fcd)
    pose.set_editor_property("fit_eyes", True)
    pose.load_default_tracker()
    t("capture_valid", lambda: pose.is_capture_data_valid())
    cam = pose.get_editor_property("camera")
    align = pose.get_editor_property("timecode_alignment")
    ident.set_blocking_processing(True)
    R["tracked"] = {}
    for name, n in FRAMES.items():
        pf, _ = pose.add_new_promoted_frame()
        pf.set_editor_property("is_front_view", name == "front")
        pf.set_navigation_locked(True)
        pf.set_editor_property("frame_number", n)
        pf.set_editor_property("frame_name", name)
        ok_init = PFU.initialize_contour_data_for_footage_frame(pose, pf)
        e = {"frame": n, "init": bool(ok_init)}
        if ok_init:
            img = PFU.get_image_path_for_frame(fcd, cam, n, True, align)
            dep = PFU.get_image_path_for_frame(fcd, cam, n, False, align)
            got = PFU.get_promoted_frame_as_pixel_array_from_disk(img)
            if got:
                size, px = got
                e["size"] = [size.x, size.y]
                ident.start_frame_tracking_pipeline(px, size.x, size.y, dep, pose, pf, False)
                e["contours"] = pf.frame_contours_contain_active_data()
        R["tracked"][name] = e
    t("conform", lambda: str(face.conform(unreal.ConformType.SOLVE)))
    t("is_conformed", lambda: face.get_editor_property("is_conformed"))
    EAL.save_loaded_asset(ident)
    R["identity"] = IDENTITY

elif STAGE == "solve":
    ident = EAL.load_asset(IDENTITY)
    face = ident.get_or_create_part_of_class(unreal.MetaHumanIdentityFace)
    pose = face.find_pose_by_type(unreal.IdentityPoseType.NEUTRAL)
    t("processing", lambda: ident.is_frame_tracking_pipeline_processing())
    R["contours"] = {str(f.get_editor_property("frame_name")): f.frame_contours_contain_active_data()
                     for f in pose.get_editor_property("promoted_frames")}
    for tp in ("ConformTargetParams", "MetaHumanCharacterFitToVerticesParams", "MetaHumanCharacterTargetMeshKey"):
        t("type:" + tp, lambda tp=tp: props(getattr(unreal, tp), 1500))  # the no-depth fallback's inputs (docs)
    if any(R["contours"].values()) and not R.get("processing") is True:
        t("conform", lambda: str(face.conform(unreal.ConformType.SOLVE)))
        t("is_conformed", lambda: face.get_editor_property("is_conformed"))
        EAL.save_loaded_asset(ident)

elif STAGE == "diag":
    # read-only: why tracking gave no contours (day 3: conform DEPTH_INPUT, contours false on every frame)
    ident = EAL.load_asset(IDENTITY)
    face = ident.get_or_create_part_of_class(unreal.MetaHumanIdentityFace)
    pose = face.find_pose_by_type(unreal.IdentityPoseType.NEUTRAL)
    for k in ("camera", "capture_data_config", "default_tracker", "fit_eyes", "pose_transform"):
        t("pose." + k, lambda k=k: str(pose.get_editor_property(k)))
    pfs = pose.get_editor_property("promoted_frames")
    R["n_promoted"] = len(pfs)
    if pfs:
        pf = pfs[0]
        tr = pf.get_editor_property("contour_tracker")
        R["tracker"] = str(tr)
        if tr is not None:
            R["tracker_members"] = [n for n in dir(tr) if not n.startswith("_") and "editor_propert" not in n][:80]
            R["tracker_props"] = props(type(tr), 2500)
            for n in dir(tr):
                if any(w in n.lower() for w in ("load", "can_process", "valid", "ready")) and not n.startswith("_"):
                    t("tracker." + n + ".__doc__", lambda n=n: (getattr(tr, n).__doc__ or "")[:500])
        t("pf.contour_data", lambda: props(type(pf.get_editor_property("contour_data")), 1500))
        t("pf.can_track", lambda: pf.can_track())
        t("pf.frame_number", lambda: pf.get_editor_property("frame_number"))
        t("pf.depth_diag", lambda: str(pf.get_editor_property("depth_map_diagnostics")))
    fcd = footage()
    t("calib", lambda: [str(c) for c in fcd.get_editor_property("camera_calibrations")])
    t("calib_props", lambda: props(unreal.CameraCalibration, 1500))
    t("metadata", lambda: str(fcd.get_editor_property("metadata"))[:800])
    t("depth_first", lambda: frames(fcd.get_editor_property("depth_sequences")[0])[:2])
    t("image_first", lambda: [os.path.basename(x) for x in frames(fcd.get_editor_property("image_sequences")[0])[:2]])
    t("start_doc", lambda: (unreal.MetaHumanIdentity.start_frame_tracking_pipeline.__doc__ or "")[:600])
    t("pose_members", lambda: [n for n in dir(pose) if not n.startswith("_")])
    # the fallback without footage tracking: the 5.8 Creator fits a face from landmarks tracked on an image
    sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
    for n in ("track_face_landmarks_from_image", "translate_face_landmarks", "commit_target_mesh_keypoints",
              "fit_state_to_target_vertices", "align_to_target_meshes", "get_face_landmarks"):
        t("sub." + n, lambda n=n: (getattr(sub, n).__doc__ or "")[:900])

elif STAGE == "grooms":
    # wear OUTFIT and GROOMS; their colours need a built collection, so on a character not built yet run this, mh.build,
    # this again (the colours then apply), and mh.build again
    from fmbridge.ops import call
    R["outfit"] = plain(call("mh.add_item", character=CHARACTER, item=OUTFIT, slot="Outfits"))
    for slot, (item, melanin) in GROOMS.items():
        r = call("mh.groom", character=CHARACTER, slot=slot, item=item)
        R.setdefault("grooms", {})[slot] = plain(r) if isinstance(r, dict) else "assembling"
        if melanin is not None:
            try:
                c = call("mh.groom", character=CHARACTER, slot=slot, melanin=melanin)
                R.setdefault("colours", {})[slot] = "set" if isinstance(c, dict) else "assembling"
            except Exception as e:  # not_ready before the first build: run again after it
                R.setdefault("colours", {})[slot] = "later: " + str(e)[:120]

elif STAGE == "look":
    # his look (round 3 review against the capture): grooms (beard off unless BEARD is set), skin tone, dark iris; then
    # the cloud textures again (a skin change discards them) and the build. Values overridable per run by globals.
    from fmbridge.ops import call
    hair = globals().get("HAIR", GROOMS["Hair"][0])
    brows = globals().get("BROWS", GROOMS["Eyebrows"][0])
    must = globals().get("MUSTACHE", "")
    beard = globals().get("BEARD", "none")
    for slot, item in (("Hair", hair), ("Eyebrows", brows), ("Mustache", must or "none"), ("Beard", beard)):
        r = call("mh.groom", character=CHARACTER, slot=slot, item=item)
        R.setdefault("grooms", {})[slot] = (r.get("item"), r.get("changed")) if isinstance(r, dict) else "assembling"
    su, sv = globals().get("SKIN_UV", (0.62, 0.58))
    R["skin"] = plain({k: v for k, v in call("mh.skin", character=CHARACTER, u=su, v=sv).items()
                       if k in ("changed", "u", "v")})
    iu, iv = globals().get("IRIS_UV", (0.08, 0.95))
    R["eyes"] = plain(call("mh.eyes", path=CHARACTER, both={"iris": {"primary_color_u": iu, "primary_color_v": iv,
                                                                       "secondary_color_u": iu,
                                                                       "secondary_color_v": iv}}).get("changed"))
    if globals().get("BODY_SET"):  # round 4: the slim body the photos show (a body change wants mh.rig again)
        R["body"] = plain(call("mh.body", character=CHARACTER, measurements={**BODY, **globals()["BODY_SET"]}).get("changed"))
    R["next"] = ("(after a body change: film-ue op mh.rig character=" + CHARACTER + "), "
                 "film-ue op mh.textures character=" + CHARACTER + " (multi-tick), then mh.build character=" + CHARACTER
                 + " name=Host_Op force=true, then host_swap.py HOST='op', groom.set label=Host melanin=1.0 redness=0.05")

elif STAGE == "character":
    # the character: blank, its face fitted to the identity's conformed mesh (metric scale, eyes), then his body
    # (bodies.py "op": 180 cm, fit) by the parametric constraints. The cloud rig/textures/build follow (bodies.py).
    from fmbridge.ops import call
    from fmbridge.ops.mh import _core as K
    R["add"] = plain(call("mh.add", path=CHARACTER, blank=True))
    c = K.char(CHARACTER)
    ident = EAL.load_asset(IDENTITY)
    prm = unreal.ImportFromIdentityParams()
    prm.set_editor_property("use_eye_meshes", True)
    prm.set_editor_property("use_metric_scale", False)  # Epic's example: MetaHuman-sized head on his 180 cm body
    prm.set_editor_property("use_teeth_mesh", False)  # no teeth pose solved yet
    R["import"] = str(K.sub().import_from_identity(c, ident, prm))
    R["body"] = plain(call("mh.body", character=CHARACTER, measurements=BODY))
    K.save(CHARACTER)
    R["character"] = CHARACTER

elif STAGE == "measure":
    # for the cameras (agent-11): his eye, head-top and knee heights (cm above his mark's floor) on the placed actor
    from fmbridge.ops._util import actor
    a = actor(globals().get("LABEL", "Host"))
    floor = a.get_actor_location().z
    comps = {c.get_name(): c for c in a.get_components_by_class(unreal.SkeletalMeshComponent)}
    R["components"] = sorted(comps)

    def z(bone):
        for c in comps.values():
            if c.does_socket_exist(bone):
                return round(c.get_socket_location(bone).z - floor, 1)
        return None
    eyes = [v for v in (z("FACIAL_L_Eye"), z("FACIAL_R_Eye")) if v is not None]
    R["eye_cm"] = round(sum(eyes) / len(eyes), 1) if eyes else None
    R["knee_cm"] = z("calf_l")
    def top():  # the actor's bounds (hair included): its highest point above the mark's floor
        o_, e_ = a.get_actor_bounds(False)
        return round(o_.z + e_.z - floor, 1)
    t("top_cm", top)
    R["head_bone_cm"] = z("head")

R["done"] = True
result = R
