# Mocap pilot: Epic's MetaHuman Animator Markerless Motion Capture

Task 20261108-pilot-epics-metahuman-animator-bc42 (agent-12, 08 Nov 2026). The goal: our own performances (the
operator, a performer, or a generated test video filmed or made as a plain video) become body and hand animation on
the MetaHuman skeleton, which then goes through our existing layers and gates. Canned motion libraries stay banned
("we can't show same animations"); a take of our own is a performance, not a library.

Confidence tags: **confirmed** (Epic's docs or the Fab listing), **reported** (forum, press or users; not ours),
**ours, untested** (written here and not yet run against the plugin), **measured** (run in this pilot).

## 0. Status and verdict

**Prepared, not yet solved.** The research, the automation and the Linux-side rows are done and tested offline. The
solve is waiting on five things, none of which an agent can do alone:

1. **The test clip.** The operator is supplying an AI-generated video (no real person) of a seated presenter at a
   desk: 10-15 s, 1080p, locked-off camera, hands always visible.
2. **The spot quota.** Tonight's T/T2 renders come first, so nothing starts until the orchestrator says go.
3. **AWS.** The agent containers have no AWS CLI or credentials. Whoever runs the farm's AWS calls on kali runs the
   §9 commands.
4. **The operator's Epic sign-in** (about 10 minutes on the box). The plugin comes only from Fab.
5. **The licence for the generated animation.** The listing shows none (§2).

**Feasibility, from the research:**

- **Likely yes for hands-in-front-of-chest presenter takes.** The plugin solves body and fingers from one video,
  locally, onto the MetaHuman skeleton, and its export retargets onto an existing MetaHuman skeleton. The Linux side
  needs nothing new: `assets.import` → Body track → `seq.sample` → our rows.
- **The two real risks:**
  - **Framing.** Epic's guidelines want the whole body in frame, with nothing in front of it, "including furniture".
    A presenter behind a desk breaks that rule. §5 covers what we test and the fallback.
  - **Maturity.** The plugin is experimental, with reported install and ingest failures, GPU resets and long solves.
    Budget one retry per step.

| Number | Value | Basis |
|---|---|---|
| Time per second of video | ~40 s of solve per second at 1080p (one RX 6750 XT report); "under a minute per second" (press) | reported. Measure it with `solve_s_per_video_s` in the result JSON. |
| $ per minute of footage | **~$0.35** on g5.2xlarge Windows spot ($0.51/h, ap-south-1, 08 Nov), plus ~30 min of box setup per session | computed from the above |
| Pilot spend | **~$1-2**: ~2 h of g5.2xlarge spot, plus a 300 GB gp3 volume for 2 h (~$0.08) | computed; the cap is $5 |
| Fingers | captured; "not finished… usable" with a pose layer for cleanup (anim.works); "held up well at a distance and occluded" (CG Channel) | reported. Measure with `fingers.*` rows and the eye (§6). |

## 1. What the plugin is

- **Listing:** "MetaHuman Animator Markerless Motion Capture Plugin", by Epic Games. Free on Fab. **confirmed**
- **What it does:** full-body animation including hands, from standard video (a phone or a studio camera), without
  markers or suits. It runs locally, with no cloud. **confirmed**
- **Status:** experimental, UE 5.8 or later, **Windows only**. **confirmed**
- **Automation:** Python and Blueprint. **confirmed**
- **Hardware:** for MetaHuman Animator in general, an RTX 3070-class GPU with 8 GB VRAM, 16 cores, 32 GB RAM and
  DX12. **confirmed**
- **Inference:** ONNX Runtime on DirectML (`DmlExecutionProvider` in user logs), so no CUDA is needed. **reported**
- **VRAM:** one report went from 9 to 12 GB on a 10 s clip. A 12 GB RTX 5070 reset its GPU at stage 4. **reported**
- **AWS choice:** a g5 (A10G, 24 GB) or g6 (L4, 24 GB) is the safe pick. g4dn (T4, 16 GB, below a 3070) is risky.
  No AWS report was found.
- **Pipeline:**
  1. **Ingest.** Live Link Hub → Capture Manager → **Mono Video Ingest** makes a Footage Capture Data asset. It
     takes .mp4 and .mov, with no calibration or lens setup.
  2. **Solve.** A **MetaHuman Performance** asset (`InputType = MonoFootage`, **Body Tracking** on) runs **Process**.
  3. **Export.** **Export Animation** with **Existing Skeleton** retargets automatically onto a MetaHuman.
     **Performer Skeleton** instead builds a mesh with the performer's own proportions. **confirmed**
- **Outputs:**
  - An AnimSequence. Hands are part of the body solve; there is no separate switch. **confirmed / reported**
  - **Root:** one reviewer had to rotate the root 90° after export. **reported**
  - **Feet:** "some floating feet" were reported. They do not matter to us, because seatkit owns the seat and legs.
  - **Output rate:** follows the capture data's rate. **reported**

## 2. Fit with our rules

- **No motion libraries:** satisfied. Every take is a new performance of our own script.
- **No non-commercial model output anywhere** (agent-10's survey ruling, `explainers/r7/gesture_model.md`):
  - **Open.** The Fab listing shows no licence ("-"). Press (CG Channel, Digital Production) says it is free
    including commercial use. Fab's Standard License allows commercial end products. No term speaks to the
    *generated animation* itself.
  - **The operator should confirm this before a published video uses a solved take.** The pilot itself (a test clip,
    nothing published) is fine.
- **The face stays ours:**
  - We solve **body only**: Face Tracking off, Head Movement Mode `DISABLED`.
  - In 5.8.0, an Audio-to-Lip Sync animation placed on the **Body** track overrides the markerless body and hands
    (forum 2733267). So our face anim stays on the Face track, and nothing audio-driven goes on Body.
- **Face data:**
  - An operator take shows their face. The raw video, its ingest (PNG frames) and any by-eye frames of it stay on the
    box and in `s3://…/ue-linux/private/` (SSE-KMS). The face-data rule applies as for renders. **They never come
    to kali or into this repo.**
  - The solved AnimSequence/FBX holds no face (bones only), so it may travel.
  - The contact sheet is rendered on a **stock** MetaHuman.
  - The AI test clip shows no real person. Even so, it stays out of this public repo.

## 3. The Windows box

**Engine:**

- Snapshot `snap-00f13e5427f61953a` (300 GB, the old HostStudio workstation's C:) holds an Epic **binary UE 5.8.4**
  (CL 58902052) at `C:\Program Files\Epic Games\UE_5.8`, plus the Epic Launcher. **confirmed** (`docs/linux/inventory.md`)
- It has **no Fab plugins** (`Engine/Plugins/Marketplace` is absent), so the Markerless plugin must be installed
  either way.
- **Do not register an AMI from that snapshot.** A Windows AMI made from a bare snapshot loses its Windows billing
  code.
- Instead:
  1. Launch a **fresh Windows Server 2022 GPU spot box**.
  2. **Attach a volume made from the snapshot as D:**.
  3. Run the editor from `D:\Program Files\Epic Games\UE_5.8`. An installed build is relocatable.
- This saves the ~40 GB engine download. The first reads from a fresh snapshot volume are slow (lazy load). The
  editor's first start may take 10+ min.

**Instance:**

| Type | GPU / RAM | Windows spot, ap-south-1, 08 Nov | Note |
|---|---|---|---|
| **g5.2xlarge** (pilot) | A10G 24 GB / 32 GB, 8 vCPU | $0.514/h | Matches the 32 GB guideline. Only 4 physical cores (the guideline is 16): watch the ingest. |
| g5.4xlarge | A10G 24 GB / 64 GB, 16 vCPU | $0.931/h | If 32 GB runs out on longer takes (one report: a 20k-frame clip committed ~340 GB) |
| g6.2xlarge | L4 24 GB / 32 GB | $0.530/h | Equivalent; the L4 is slower than the A10G on raster |
| g4dn.xlarge | T4 16 GB / 16 GB | $0.263/h | Too little RAM; not recommended |

**Rules for the box:**

- **Persistent** spot with `InstanceInterruptionBehavior=stop`. A one-time spot box cannot be stopped, so the reaper
  could not stop it (`docs/FARM.md` §8).
- Tags: `Project=ue-linux-poc`. Leave the kill switch on (no `KillSwitch=off`), so the reaper's idle and TTL stops
  apply. Add `TTLHours=3`.
- **The NVIDIA driver:** the AWS-hosted GRID/gaming driver for G5/G6. It is free for EC2 customers, downloaded on the
  box from AWS's `ec2-windows-nvidia-drivers` bucket. DX12 needs it; the basic display adapter will not run the
  solve.

**Plugin install (the operator's step):**

1. Prepare: an RDP session over an SSM port forward (no open port). The operator signs in with the Administrator
   password, which the operator decrypts with the box's key.
2. Open `D:\…\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe` on `C:\UEProjects\Mocap\Mocap.uproject`, which is
   made by `win_setup.ps1 -Apply`.
3. **Window → Fab**, sign in, find "MetaHuman Animator Markerless Motion Capture", then **Add / Install to engine**.
4. If the install leaves the plugin in a project, copy its folder to `Engine\Plugins\Marketplace\` (a forum
   workaround).
5. `win_setup.ps1` (read-only by default) then reports the plugin, the GPU, the RAM and the RHI.

**Install routes we rejected:**

- **Signing in without the operator:** impossible.
- **`fabcli`** (unofficial, GPL): a terms-of-service risk.
- **`filmtools.unreal.fab_shim`:** it needs the editor's signed-in token, so it saves no sign-in.

**After a successful pilot,** bake the readied box into an AMI (`create-image` from the running instance keeps the
billing code). Later sessions then need no engine copy and no sign-in. The image is a ~300 GB snapshot at about
$15/month: keep it only if production goes ahead.

## 4. The solve, automated

These are in `tools/filmtools/mocap/` (all **ours, untested** against the plugin; the names come from Epic's
Blueprint page and our audio solve in `unreal/fmbridge/ops/speech.py`):

- **`prep.py`:** turns a phone or generated take into the clip the ingest wants:
  - a constant whole frame rate, the source's own (phones record VFR, and the 29.97/30 mismatch is a known ingest
    failure; a 24 fps CFR source stays at 24);
  - `--height 1080` for an upscale A/B;
  - H.264 at CRF 18, 8-bit yuv420p, rotation baked in, no audio, an optional trim;
  - `check` lists what the metadata breaks.
- **`win_setup.ps1`:** checks the box (engine, GPU and driver, RAM, cores, the plugins' .uplugin files). With
  `-Apply`, it makes `C:\UEProjects\Mocap` (the plugins enabled, DX12 the default RHI) and `C:\mocap\{in,out}`.
- **`ue_solve.py`:** one job, run in the editor, which then quits. In order:
  1. `CaptureManagerIngestBlueprintLibrary.ingest_mono_video_sync`
  2. `MetaHumanPerformance` (`input_type` MONO_FOOTAGE, `footage_capture_data`, `body_tracking` on, `face_tracking`
     off, `head_movement_mode` DISABLED), `set_blocking_processing(True)`, `start_pipeline(True)`
  3. `MetaHumanPerformanceExportUtils.export_animation_sequence` onto the target skeleton, then an FBX via
     `AnimSequenceExporterFBX`
  4. It writes `<slate>.result.json` with `ok`, `anim`, `fbx`, `frames`, `seconds`, `solve_s`,
     `solve_s_per_video_s` and any error.
  - When a property name is wrong, the error lists what the object has.
  - The plugin ships its own `Content/Python/process_monocular_performance.py`: compare against it on first run.

```
UnrealEditor.exe C:/UEProjects/Mocap/Mocap.uproject -ExecutePythonScript="C:/mocap/ue_solve.py C:/mocap/job.json"
```

- **Run it in a logged-in desktop session, not as SYSTEM over SSM.** The solve needs the GPU's DX12 device. The old
  workstation did this with a scheduled task (Interactive, Highest), `\OpenHostStudio`; use the same pattern with the
  command above.
- **Target skeleton:** a MetaHuman body skeleton asset in the Mocap project. Migrate a **stock** MetaHuman's
  `Common/Body`; no presenter's face assets are needed.

## 5. Inputs, and the desk problem

**What Epic's Video Capture Guidelines say** (confirmed):

- HD or 4K at **60 fps**; H.264 at CRF 18 or better (~25 Mbps at HD).
- A **tripod**, fixed for the whole take; straight on, at neutral height.
- **The whole body, head to feet, with a margin**, unobstructed: "including from props, furniture".
- One person; even, diffuse light; no backlight, harsh shadows or motion blur.
- Form-fitting clothes that contrast with the background; no all-white room, no reflective surfaces.

No guidance was found for seated or upper-body-only framing, or for a maximum length. Long clips run out of memory;
chunk at ≤ 3,000 frames.

**The test clip breaks the full-body rule.** It is seated, at a desk, upper body only. So the pilot measures exactly
the case we care about:

- **What we want from it:** shoulders, arms, wrists and fingers, plus some spine and neck. seatkit owns the pelvis,
  legs and seat, and the desk rest is ours.
- **Expected failures:**
  - the legs and root (no feet in the picture);
  - jitter when a hand passes in front of the torso (the mono-depth complaint);
  - generated-video hand artifacts (extra or merged fingers) copied into the solve.
- **If the arms and hands come out but the root and legs are garbage,** that is fine: we keep only the upper-body
  chain (§7).
- **If the solve fails or the arms are wrong,** the fallback is a take that follows the guidelines: the performer
  seated on a desk-height chair with **no desk** in front of them, the whole body in frame. Our layers put the desk
  back. §8's recording guide is written for that case.

**The pilot clip as received** (Kling 4.0, AI-generated, no real person; kept outside this repo):

- **Format:** 10.0 s, 1280x720, 24 fps CFR, H.264, with audio.
- **Framing:** locked-off, a plain grey wall, an open-front light-wood desk, framed head to mid-thigh.
- **Hands:** about 60-80 px at 720p, with some motion blur on the fast moves. She wears a watch on her left wrist.
- **Contrast:** a white tee on a light-grey wall, which the guidelines advise against.
- **prep:** kept 24 fps (re-timing to 60 would only duplicate frames) and dropped the audio. It made a 1080p lanczos
  upscale as an A/B: more pixels, no more detail.

**Finger honesty for the AI clip:** generated video often morphs fingers from frame to frame. If `fingers.*`
jitter is high or the contact sheet shows impossible poses, check the source frames first: the solve may be faithful
to bad input. Only a real take settles finger quality.

## 6. Linux side: import, rows, the eye

Everything here runs with tools we already have (`film-ue op …` on a Linux UE 5.8 box):

1. **Import:**
   `assets.import files=[<take>.fbx] dest=/Game/Mocap kind=skeletal animations=true skeleton=<the stock MetaHuman body skeleton>`.
2. **Place it.** Put the AnimSequence on a stock MetaHuman's **Body** track in a Level Sequence, first deleting the
   Control Rig tracks (Epic's apply step). The face stays as it is.
3. **Sample it.** `seq.sample` the Body component for `filmtools.mocap.rows.ROWS_BONES`: the head, neck, spine, both
   hands, both forearms and every finger joint.
4. **Rows (`rows.py`):**

   ```
   uv run python -m filmtools.mocap.rows samples.json --desk-z 71 --fps 24 [--speaking spans.json] --forward 1,0,0
   ```

   - **The body rows we gate on today** (`qa_perf.body_rows`): `body.gesture_onsets_per_s`,
     `body.hands_above_desk_frac`, `body.wrist_travel_cm_per_s`.
   - **Fingers:** `fingers.curl_range_deg_p50`, `fingers.moving_frac` and `fingers.curl_jitter_deg_p95`, per finger
     too. The curl is the bend at joints 01 and 02 from the bone positions.
   - **Wrists:** `wrist.jitter_cm_p95` (mono depth noise), `wrist.speed_cm_s_p95`, and
     `wrist.below_desk_top_frac`, which says how much the desk layer will have to lift.
   - **Face:** `face.fingertip_clear_cm_min` against gesturekit's face shell, which says how much face-avoid will
     move.
   - A `verdict` of first-guess lines (`WANT`) points at frames. The eye decides.
5. **The eye:** a contact sheet of the hands at 12 evenly spaced frames, MCU and a hands close-up, rendered on the
   stock MetaHuman. Agents may view this sheet; it holds no presenter face.
6. **Parity:** once the take runs through the layers (§7), `qa_perf.parity` compares the editor's sampled bones with
   the layered offline track, as for the generated performances.

## 7. Into our layers (the production design; follow-up work, not in this pilot)

**gesturekit today *generates* the arms.** Its `Performer` plans gestures from the acting sheet and the prosody
timing, then solves the arms under the constraints: desk rest, mic and boom, face shell, upper-arm/torso clearance
≥ 3 cm, hands in frame. A mocap take would replace the *generator*, not the constraints:

1. **Source.** The solved take is exported onto *her* skeleton (Existing Skeleton, so the export's retarget handles
   proportions), then sampled to a per-frame arm, hand and finger track: `gesturekit.track_doc`'s format, with the
   same bones as `arm_track.json`.
2. **Time.** The take is recorded to the same VO, so it is on the script's clock. A small offset, fitted by
   cross-correlating wrist speed against the prosody planner's stroke times, absorbs the recording's lead or lag.
3. **Constraints as corrections.** A `MocapPerformer` (a gesturekit `Performer` whose `pose(t)` reads the track
   instead of the plan) keeps every check. Where the take breaks a check, the existing corrections move the wrist:
   - a wrist under the desk top → lifted to the desk rest;
   - in front of the mic → the MIC_DIRS search;
   - inside the face shell → pushed out;
   - an upper arm into the torso → the elbow swivel.
   Each correction is blended over ~0.2 s so it does not pop. The rows count the corrections. A take that needs many
   of them is a bad take: re-shoot rather than repair.
4. **Fingers.** The take's own fingers, smoothed (a one-euro filter) only where `fingers.curl_jitter` flags them.
   agent-08's finger layer is the fallback per segment, not a blanket override.
5. **Gates, unchanged:** the body rows, clearance, hands-in-frame, desk, mic and knee contact, and parity.

## 8. The operator's recording guide

For the production takes (the operator or a performer, phone on a tripod):

**Camera:**

- A phone on a tripod, **landscape**, **1080p60** (4K60 if the phone holds it without overheating), **SDR, not
  HDR** (prep converts to 8-bit; HDR tone-maps badly).
- Lock exposure and focus (tap and hold), and turn stabilisation off.
- Place it **straight on, at chest height, 2.5-3 m away**, far enough that **head to feet is in frame with a hand's
  width of margin** on every side.
- **No desk in front:** sit on a chair whose seat matches our set (the desk top is 71 cm; the seat height is in
  seatkit). If you want something to rest your hands on, use a small open stand or a taped mark in the air. Nothing
  may hide the hands, forearms, legs or feet.

**Light:**

- Even and soft: a window to the front-side, or two lamps bounced off a wall.
- No window behind you, no hard shadows on the hands.

**Wardrobe:**

- Fitted clothes that contrast with the wall: dark top on a light wall, or the reverse.
- Bare forearms if possible, sleeves no further than the elbow.
- No rings, watches or bracelets.
- Hair off the shoulders.

**Background:** plain and matte, nothing reflective, nobody else in the frame.

**Performance:**

- Read the actual script, with energy, as on camera: eyes to the lens, hands up in front of the chest on the stressed
  words, resting low between thoughts.
- Do **2-3 takes** of each line group.
- Clap once in view at the start (a sync mark for the VO).
- Keep each take under 2 minutes; the solve chunks long clips.
- Your face is in the take, so it is face data: the files go only to the private bucket (§2).

**Handing over:**

- Send the original files (not a messaging-app copy, which recompresses and drops frames), named
  `<script>_<lines>_t<N>.mov`.
- prep does the rest.

## 9. Pilot runbook

**On kali,** by whoever holds the AWS CLI (profile nani, region ap-south-1), **only after the orchestrator's go**:

```
# 1. a volume from the snapshot, in the AZ the box will use
aws ec2 create-volume --snapshot-id snap-00f13e5427f61953a --availability-zone ap-south-1a --volume-type gp3 \
  --tag-specifications 'ResourceType=volume,Tags=[{Key=Project,Value=ue-linux-poc},{Key=Name,Value=mocap-pilot-d}]'
# 2. a Windows Server 2022 g5.2xlarge, persistent spot that stops on interruption
AMI=$(aws ssm get-parameter --name /aws/service/ami-windows-latest/Windows_Server-2022-English-Full-Base \
  --query Parameter.Value --output text)
aws ec2 run-instances --image-id $AMI --instance-type g5.2xlarge --subnet-id <a subnet in ap-south-1a> \
  --iam-instance-profile Name=ue-workstation --key-name <the workstation key> \
  --instance-market-options 'MarketType=spot,SpotOptions={SpotInstanceType=persistent,InstanceInterruptionBehavior=stop}' \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=100,VolumeType=gp3}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Project,Value=ue-linux-poc},{Key=Name,Value=mocap-pilot},{Key=TTLHours,Value=3}]'
# 3. attach the snapshot volume as the second disk (Windows brings it online as D:)
aws ec2 attach-volume --volume-id <vol> --instance-id <i> --device xvdf
```

**On the box** (`docs/linux/runps.py` over SSM, as SYSTEM):

1. Install the NVIDIA driver from AWS's bucket (`ec2-windows-nvidia-drivers`, latest, the G5 GRID package), then
   reboot.
2. Bring D: online (`Get-Disk | Where IsOffline | Set-Disk -IsOffline $false`).
3. Run `win_setup.ps1 -Engine 'D:\Program Files\Epic Games\UE_5.8'`, then again with `-Apply`.
4. Copy `ue_solve.py` and the prepped clip into `C:\mocap\`.

**The operator:** the RDP sign-in and the Fab install (§3). After that, `win_setup.ps1` must report the Markerless
plugin.

**The solve:**

1. The scheduled task runs `ue_solve.py` with `job.json` in the desktop session.
2. Read `C:\mocap\out\<slate>.result.json`.
3. Copy the FBX to `s3://…/ue-linux/` (private, if the clip shows a real person).

**Close down:**

```
aws ec2 cancel-spot-instance-requests --spot-instance-request-ids <sir>   # first, or the request relaunches it
aws ec2 terminate-instances --instance-ids <i>
aws ec2 delete-volume --volume-id <vol>          # after the instance is gone; the snapshot stays
```

Optionally bake an AMI before terminating (§3).

**Linux:** §6 on the existing Linux UE box, when it is up for other work anyway (no extra box for a 15 s import).

## 10. Recommended production pipeline

1. **Record:** the operator or a performer, by §8: 2-3 takes per line group, read to the final script.
2. **Prep:** `prep make` on kali. Operator takes stay in private storage.
3. **Solve:** a Windows g5.2xlarge spot box from the baked AMI. Batch every take of a script in one session:
   setup ~15 min, then ~40 min of box per minute of footage (to be measured). Export onto *her* skeleton. Terminate.
4. **Pick:** the rows (§6) and a stick or stock-MetaHuman preview per take. The operator picks the take per line
   group.
5. **Layer:** a MocapPerformer (§7): constraints as corrections, fingers smoothed only where flagged, parity.
6. **Gate and render** as today, on the Linux boxes.

**Per finished minute,** the solve costs well under $1 of spot, plus a ~$0.15 setup share per session. The real
costs are the operator's recording time and the first build of §7.

## 11. Risks and open questions

- **The licence of the generated animation** (§2). The operator decides.
- **A seated performer at a desk:** unsupported by the guidelines. The pilot measures it, and the fallback is the
  no-desk take (§5, §8).
- **The plugin is experimental.** Reported failures:
  - ingest stuck at 75% (errors 5/7/8; workarounds: U8_Mono, ffmpeg encoder, unique names);
  - "capture data frame rate is zero" (prep's constant whole rate is our guard);
  - the Body Tracking option missing;
  - Smart App Control blocking an unsigned DLL;
  - GPU resets on 12 GB cards.
- **Mono depth:** limbs look wrong from other angles. Our cameras sit near the phone's angle (front, MCU and CU), so
  record from where the film's camera will be.
- **The root rotated 90°** after export (one report): `anim.retarget` or a root fix-up on import.
- **Speed is unmeasured.** It is the first number the pilot writes (`solve_s_per_video_s`).
- **The operator ruled out a Windows *fallback for rendering*** (2026-11-04, `docs/linux/engine.md`). This box is a
  capture tool only, and nothing renders on it. Raise it with the operator if that ruling is meant to cover this too.

## Sources (read 08 Nov 2026)

- Fab listing: https://www.fab.com/listings/4095b8e0-3eff-44f1-acb4-cb40b99228b9
- Mono video capture: https://dev.epicgames.com/documentation/metahuman/metahuman-animation-from-mono-video-capture-in-unreal-engine
- Video capture guidelines: https://dev.epicgames.com/documentation/metahuman/metahuman-animator-video-capture-guidelines-in-unreal-engine
- Import footage: https://dev.epicgames.com/documentation/metahuman/metahuman-animator-01-import-your-footage-in-unreal-engine
- Process and export: https://dev.epicgames.com/documentation/metahuman/metahuman-animator-02-process-and-export-your-animation-in-unreal-engine
- Apply to a MetaHuman: https://dev.epicgames.com/documentation/metahuman/metahuman-animator-03-apply-your-animation-to-a-metahuman-in-unreal-engine
- Ingest from Python: https://dev.epicgames.com/documentation/metahuman/download-and-ingest-metahuman-animator-takes-with-blueprints-and-python
- Process with Blueprints: https://dev.epicgames.com/documentation/metahuman/process-and-export-metahuman-animation-with-blueprints-in-unreal-engine
- Python scripting: https://dev.epicgames.com/documentation/metahuman/python-scripting-for-metahuman-animator
- Hardware: https://dev.epicgames.com/documentation/metahuman/metahuman-hardware-requirements-in-unreal-engine
- Fab licences: https://dev.epicgames.com/documentation/fab/licenses-and-pricing-in-fab
- Forum thread (pages 1-3: speed, memory, DirectML): https://forums.unrealengine.com/t/epic-games-metahuman-animator-markerless-motion-capture-plugin/2729293
- GPU reset: https://forums.unrealengine.com/t/ue-5-8-2-metahuman-markerless-motion-capture-stage-4-causes-gpu-reset-and-black-screens-on-rtx-5070/2749272
- Lip sync on the Body track: https://forums.unrealengine.com/t/ue-5-8-0-metahuman-audio-to-lip-sync-on-the-body-track-overrides-markerless-body-hand-animation/2733267
- Ingest failures: https://forums.unrealengine.com/t/live-link-hub-capture-manager-wont-accept-video/2729749
- Body Tracking missing: https://forums.unrealengine.com/t/body-tracking-missing-from-metahuman-performance-for-markerless-mocap/2737745
- CG Channel: https://www.cgchannel.com/2026/06/get-the-free-metahuman-animator-markerless-mocap-plugin/
- anim.works review: https://anim.works/unreal-engine-5-8-markerless-motion-capture/
- Digital Production: https://digitalproduction.com/2026/06/23/metahuman-gets-markerless-mocap/
- Spot prices: https://website.spot.ec2.aws.a2z.com/spot.json (08 Nov 2026 snapshot)
