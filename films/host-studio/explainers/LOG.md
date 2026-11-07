# Explainers (round 6): log

Times IST. Box B driver: agent-07 (set, light, cameras, HER explainer). Box A: agent-06 (HIS explainer, replays set.py).

## Set, light, cameras (agent-07)

| IST | What |
|---|---|
| 16:20 | Brief in. Layout agreed with agent-01 (actor root on the chair mark (20,-20,0), yaw 0, forearms on the desk), agent-05 (SM_PodcastChair seat 45, SM_WalnutDesk 110x55 top 74, SM_MicBoom posed from the clamp (70,32.6,74) on the desk's +Y edge to a capsule at (44,-6,99)), agent-11 (EDL: CAM_MCU / CAM_CU / CAM_WIDE + CAM_MCU_L for the PANEL shots) |
| 16:30 | `setplan.py` (numbers + offline framing check) and `set.py` (the box driver) written. `python3 setplan.py --check --who her|him`: all rules pass (mic below and >2 mouth-heights clear of the mouth in every camera, eyes in the upper third, the lowered sign at u 0.71 in the MCU, CAM_MCU_L keeps her and the mic left of x 940) |
| 16:41 | Box B up (orchestrator): i-0d7684b44eacf7043, g6e.4xlarge L40S, persistent spot. kali driver `/tmp/fleet-agent-07-ue/r6/fu` (profile `boxb`, port 18817); first editor start compiled shaders ~10 min |
| 16:47-16:48 | **assets.duplicate of the open Studio map, then level.open of the copy, crashed the editor twice** (EditorServer.cpp:2544, the old world still referenced). set.py now saves the open Studio AS the new map (EditorLoadingAndSavingUtils.save_map) and opens it: no crash |
| 16:50 | set.py level/props/light/cameras/seq/save on box B: studio host lights + Karma*/Reel_ cameras + Host deleted in the copy, sign lowered, agent-05's props imported with PBR instances (mat.pbr from props.json, Tiling 1), cameras from the EDL (9 cuts, PANEL → CAM_MCU_L), drift keyed |
| 16:52 | agent-01's body/life/preview: bodycheck FAIL (wrists 30-50 cm off). Cause 1 (mine): **a MetaHuman BP faces +Y at actor yaw 0** (her eye bones split along X) → actor yaw -90. Cause 2 (agent-01): her mesh's bones are longer than the skeleton reference (pelvis +7.48 cm) → fe5ab6c0. Re-run: **bodycheck PASS** (desk/mic/knee 0) |
| 16:57 | Her seated eyes measured at f60: (30.55,-18.76,120.43), mouth (32.5,-18.7,113.6) → setplan FACE; cameras re-aimed; **focus track offsets re-taken on the scrubbed seated pose** (unscrubbed they held her standing eye, z 158: ~2.7 cm focus error at the CU's ±1.2 cm depth of field). Garment leaders had dropped after agent-01's steps → dress_her.py (set.py `dress` step now) |
| 16:59-17:04 | Exposure: physical-camera exposure OFF (f/2 and f/2.8 cameras cut with no jump), bias is compensation (higher = brighter); her rig x2 (channel 1) and bias -1.4 → face ~150/255 in the MCU. The daylight window + sheers top-left of the MCU clip (~26 % of the frame) and do not answer the outside card or the sun; left as a soft bright window for the orchestrator's eye |
| 17:00 | **seq.still's `camera` loses to the sequence's camera cut track**: r1/r2 stills were all the MCU. set.py stills now set the cut track to each camera alone and put the edit back |
| 17:05 | Review stills r3 (MCU, CU, WIDE, MCU_L, SIDE; f60) → `private/renders/r6/review/explain/r3/` (KMS) → orchestrator. agent-01's face chain (`perform.py all --who her --from cams`) started on box B |

## The set (setplan.py)

- Level `/Game/Explainer/ExplainerSet`: a duplicate of `/Game/Studio/Studio` (so her round-4 overshirt and his loop-2
  neck come along as the box has them); the studio's standing-host lights (Key, Fill, HairLight, RimWarm, RimWindow,
  EyeLight), its Karma* cameras, every Reel_ camera and the other presenter are deleted in the duplicate only. The
  karma sign (+ SignHalo, Halo0-8) comes down 78 cm so it sits in the seated MCU's background (u 0.71, v 0.17).
- Presenter seated on the chair mark (20,-20,0) facing +X; cameras on her right-front (azimuth -20° MCU, -17° CU, -9°
  WIDE), the mic from her left (+Y), low: from every camera the capsule is below and to screen-left of the mouth.
- Light (channel 1 only; the presenter on 0+1, the set's practicals as in the studio): ExpKey 160x120 soft box at
  +45° / 28° up from her left (the window side, short lighting), ExpFill 180x180 from the camera side at -55°, ExpRim
  warm 3100 K strip back-right, ExpHair 3600 K top-back, ExpEye 22x22 by the lens for catchlights. Candela from the
  studio's host rig scaled by distance squared. Exposure manual (bias 8.3, locked).
- Cameras (full-frame 16:9, focus tracking her camera-side eye bone FACIAL_R_Eye):
  CAM_MCU 60 mm f/2 at 165 cm, CAM_CU 85 mm f/2 at 128 cm, CAM_WIDE 35 mm f/2.8 at 320 cm, CAM_MCU_L = CAM_MCU turned
  so her eyes sit at u 0.27. A very subtle drift (≤0.4 cm lens, ≤0.3 cm aim, slow sines 3.7-9.1 s) keyed every 6 f.
- Hand-off to box A (agent-06): `cd tools && uv run python ../films/host-studio/explainers/set.py --box <A profile>
  --instance i-0284d544cdf14905e --who him --edl ../films/host-studio/explainers/edl/whatsapp.json` (all steps; Host
  on the mark at yaw -90, Presenter deleted in HIS copy). Then agent-01's `perform.py body/life/preview --who him`,
  then measure his seated eyes (level.bone Face FACIAL_L/R_Eye, FACIAL_C_LipUpper at f60 after seq.scrub) into
  setplan FACE["him"], and re-run `--steps cameras,seq,dress,save` so the cameras and the focus offsets follow his
  real eyes. Stills: `--stills <tag> --frame 60 --extra-cams CAM_SIDE --edl …`. Renders: render.py.
- Gotchas: duplicate+open of the open map crashes (set.py does save-as); seq.still ignores `camera` under a cut track
  (set.py handles it); any perform/body step can drop the garment leaders (run `--steps dress,save` after it); an
  unsaved change is lost when a tool reopens the level (save after every step).
