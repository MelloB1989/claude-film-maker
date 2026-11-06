# Round 4 (06 Nov, Linux GPU box): log and state

Box driver and integrator: agent-06. Orchestrator: cc-64d05f6e. Times UTC (IST = UTC+5:30).
Box i-0284d544cdf14905e (g6.4xlarge, L4), launched 02:27, TTL tag 6 h. Box tree `/srv/ue/r3tree`; frames under
`/srv/ue/reel/r4/` (and `/srv/ue/reel/r3/final_d` for the finals, so cut.sh's paths hold).
Driven from kali with agent-06's profile: `/tmp/fleet-agent-06-ue/r4/fu film-ue …` (FILM_UE_CONF_DIR under it,
face_data=yes), the kali tree is agent-06's worktree `fleet/agent-06/r4-integrate`.

## Log

| UTC | What |
|---|---|
| 02:34 | `film-ue provision` (engine 5.8.4 restored 274 s, project 5.2 GB from private/project/HostStudio, Epic sign-in restored, rhi ok) |
| 02:35 | idle-guard installed (`/usr/local/bin/idle-guard.sh`, `/etc/cron.d/idle-guard`; rewritten from HANDOVER's description: the night-1 script was not kept) |
| 02:44 | **Differs from HANDOFF:** the driver step installed nvidia modules for kernel 1069 while the box ran 1066, so no GPU. Fixed without a reboot: `linux-modules-nvidia-580-server-6.8.0-1066-aws`, modprobe, then the EGL ICD divert by hand (setup.sh's driver step had not diverted). L4, 580.178.04, Vulkan on NVIDIA. |
| 02:44 | `sync ddc restore` started (private/ddc/5.8.4) |
| 02:45 | Box tree from film/host-studio via S3 tmp (`ue-linux/tmp/agent06/r4/`, code only); uv + ffmpeg installed on the box |
| 02:45 | Merged (--no-ff) into film/host-studio: agent-09 r4-gate 2a45937b, agent-04 r4-look 58fd03af, agent-01 r4-look 49af7e31, agent-02 r4-clip 3cf665f7 → 9a0047fb (reel tests 43 pass) |
| 02:47 | Merged agent-02 3fdb2d52 → 41a5b3da; agent-01 b41a9300 (torso turn) → b6a3ab4e; agent-02 73295418 → 834cc2ca. Box tree at 834cc2ca. |
| 02:50 | DDC restored; editor + bridge (install 139 files) 02:51; shaders 8 s |
| 02:52 | level.open Studio: Host = BP_Host_Op (no TRASH_), Presenter placed, Trey's BP_Host in project. probe_cam --check 13/13 OK. **Box ready.** |
| 02:52-02:56 | agent-02 BEFORE clip passes (Host, Presenter; read-only) + qa.parts; numbers in `/srv/ue/reel/r4/clip/*_before` |
| 02:56 | agent-04 look_sheet list OK; iris + hair renders died at `op()` (name clash) and restore (`_PREVIEWS`); fixed by agent-04 e724e597, merged |
| 02:58 | Blender 4.2.23 LTS at /srv/ue/tools/blender-4.2 (for agent-02's fit) |
| 02:59 | level.open from disk (drop any lab state), probe V01/V02/S11 OK, **set finals V01/V02/S11 1080p at C into /srv/ue/reel/r3/final_d** (30-final.yaml batch d_set1) |
| 03:11 | Set finals V01/V02/S11 done: 432 frames in 697 s (~1.6 s/frame), converged, `final_d/_render/r3_final_d_set1.report.json` |
| 03:12-03:13 | agent-02: Host before2 clip pass; export_body (his_outfit_op). neck_probe/export_alt_body failed only because `film-ue exec FILE` reads the KALI path: use the kali tree's path for exec FILE |
| 03:14, 03:16 | **Editor crashed twice** in agent-04's look_sheet render: loading Host_Op's MetaHuman Identity (MHI_Operator) asks PromotedFrameUtils for a capture frame, and its footage isn't initialised on a fresh box → assertion in PromotedFrameUtils.cpp:148, SIGSEGV. Editor restarted itself, reopening the level from disk. agent-04 fixed it (51424063: render never touches the identity). private/operator-face restored to `/srv/ue/projects/HostStudio/Capture/operator-face/MySlate_3` (box only) |
| 03:16-03:18 | agent-02 before3 clip pass, neck_probe (before), export_alt_body |
| 03:18 | agent-04's look queue on 51424063: iris grid OK 03:21 (25 cells, numbers only) |
| | Merges: agent-04 832695c6, e724e597, 51424063; agent-02 3fdb2d52, 73295418, 250b7570, 63507bb8, 8de260a8, 1135a1b4; agent-01 b41a9300. film/host-studio 748f5a9f |
| 03:26-03:41 | **GPU hang:** MRQ draft render of the set camcheck (Reel_V03) froze the editor at 03:26:52; kernel NVIDIA Xid 109 CTX SWITCH TIMEOUT at 03:39:43. Editor restarted 03:41 (level from disk). Decision: no copy from final_c; V03/V04/V05/S12/N01 are re-rendered into final_d (night-1 S12/N01 bindings sat on Test cameras for part of the night, so a copy can't be proven) |
| 03:41-04:04 | agent-04's look sheets moved from the untextured live preview (bald, placeholder materials: the orchestrator rejected look_hair.jpg) to `--target build` (scratch copy rebuilt per variant). H1 hair check 03:44; H2 killed twice on the "groom not worn" check (unsaved edits; first variant built before its grooms), fixed in cd2327e0/ac736b5b. **look_hairfacial.jpg** 04:04 → orchestrator picks: hair B S_SideSweptFringe, mustache S_Full, light stubble, brows M_SlightArch, skin lighter |
| 03:54-03:56 | agent-02 before4 (Host still cast_op4): neck out 463 verts (rule since refined, 086c318c); tee neckline test failed (wrong UE class name), fixed d0584a06, rerun 04:20 (cleaned, ClothOpTest empty) |
| 04:07 | IRISSKIN killed (all skins too dark per orchestrator); **look_skin2.jpg** 04:20 (5 builds) → orchestrator |
| 04:20 | Set finals V03/V04/V05/S12/N01 into final_d (batch d_set2), probe 5/5 OK after level.open from disk |
| 04:21 | **GPU crash #2:** set finals d_set2 died at the start (Reel_V03 first): `FVulkanDynamicRHI.TerminateOnGPUCrash`, editor auto-restarted 04:21:36. Both GPU faults today hit Reel_V03 at its render start (03:26 draft, 04:21 final); V01/V02/S11 fine. Orchestrator: retry V03 once, last; on a third crash prove final_c's V03 (camera transform/focal/filmback/binding vs its report, 1-frame diff) and copy it |
| 04:23-04:27 | agent-02: trousers re-fit to Host_Op imported (SKM_Host_Trousers_Op); tee neckline test ok (366a3e7c). **Final look APPLY** (agent-04, orchestrator's picks: hair S_SideSweptFringe, brows M_SlightArch, mustache S_Full, no beard, iris 0.92/0.12, skin 0.30/0.45, default lips): look 50 s, mh.rig up to date, textures, forced build 117 s, host_swap (tee inflated, his trousers, leader_pass, no TRASH_). Heights eye 166.5 / knee 49.2 / top 180.7 → shots.py via framing.py (rules pass) |
| 04:27-04:28 | Neck: postrig NECK_ONLY out 644 → host_swap NECK_CM=2.5 (agent-02) → groom.set melanin 1.0 redness 0.08 again (a host_swap respawn drops it). agent-02's 3e91dedf models the WPO inflate (read-only test: out 0) |
| 04:28 | look_final.jpg (applied BP, front + 3/4) → orchestrator |
| 04:28-04:35 | agent-01: step 0 was 90° off (actor forward vs body front), fixed 14fdd6ef. VO stems were not on the box (Saved/ lost): copied from agent-11's reel-sound audio/vo into the kali tree out/, perf.py push. solve him/L2/L4a, compose him, calibrate her OK; **calibrate him failed: head curves move his head 0 cm** (likely drive_faces dropped by the groom.set re-registering components) |
| 04:35 | level.save (post-apply state); set finals V04/V05/S12/N01 into final_d (d_set3) |
| 04:47-04:54 | Set finals d_set3 (V04/V05/S12/N01, 420 frames, 678 s) and the ONE V03 retry (120 frames, 270 s, clean): final_d holds all 8 set shots, final_check clean (no missing/black/jumps) |
| 04:55-05:22 | agent-01's calibrate fixes (weak HeadRoll; then the head is 1° per HeadRoll unit: yaw_table identity); agent-04 sculpt sheet (S3 + hair 0.85 picked); agent-09 found the teal hair = TerminalGlow (attenuation 120 cm: green_px 0.000), applied + saved 05:20 |
| 05:23-05:27 | S3 sculpt apply (fe0af841 waits for groom bindings); groom verify PASS (crown, mustache); look_final2 → orchestrator |
| 05:28-05:46 | agent-01 loop (steps 0-7): turns now the right way and on plan for him; her over-turn found; agent-02 AFTER clip passes (trousers 0, neck patch remains); save→open found **TRASH_LODSync on Host** → respawn (host_swap NECK_CM 3.0 INFLATE_CM 0.5) + re-dress → lod0 clean, probe 13/13 |
| 05:46 | **cast_op5** gate pre-check (612 frames S13-S18, MP4 + mix → private/renders/r4/review/cast_op5.mp4); agent-09 REFUSE: her turns, his neck patch, lips |
| 05:50-06:06 | agent-02: his tee's WPO had NO effect (master uses Material Attributes; the plain pin is dead) → neck_fix.py via ClothOp2. agent-01: yaw table loop → heads within 5° of plan (her eyes still ~20° over) |
| 06:13 | **Power cut**: fleet down; the orchestrator STOPPED the box at 06:33 (operator's request) after syncing /srv/ue/reel/r4 → private/renders/r4/box_r4, final_d → private/renders/r4/final_d, the project on disk → private/project_r4_snapshot/HostStudio |
| 07:35 | Back. **/srv/ue was on the instance-store NVMe (nvme1n1): the stop wiped it.** Lesson: on g6 put /srv/ue on the root EBS (or an EBS data volume), never on instance store, and sync before ANY stop |
| 07:44-07:52 | Re-provisioned on the root EBS (fstab ue-data line commented; /srv/ue a dir on /): engine 274 s, project from project_r4_snapshot (5.9 GB), rhi, service; final_d and box_r4 restored; box tree 202fabae |
