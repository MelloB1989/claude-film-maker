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
