# Round 6 (07 Nov): his neck, the final 65 s + 45 s cut (track K, box A)

Box driver: agent-06. Orchestrator: cc-64d05f6e. Box A i-0284d544cdf14905e (gr6.4xlarge, L4), up 16:14 IST,
self-terminate 00:14 IST. In round 5b's end state (his loop-2 neck, her round-4 overshirt). Driven from kali as in
round 5b; branch `fleet/agent-06/r6-boxa` (film/host-studio 8b2bad4e + agent-04 1dad107b).

| IST | What |
|---|---|
| 16:21 | K0: editor fresh (box boot 16:14), doctor OK (5.8.4, Vulkan SM6, 371 ops, 140 GB free); trees → 8b2bad4e (kali + `/srv/ue/r5tree`); look_check ok |
| 16:22 | Leaders had dropped on the editor start (him Trousers None; her Overshirt/Top/Trousers None) → dress_him, dress_her + seq_dress → both pass; groom.lock + lock_check pass; probe_cam 13/13; framing ok |
| 16:23 | agent-05's Blender props on box A's CPU (`/srv/ue/props_r6`, nice 15, 6 threads; no face data) |
| 16:24 | K2 (agent-04 1dad107b, tree → 1dad107b): perf.calibrate Host turn_by=auto (fresh) → naturalize her / him `--no-turn-blinks` → restage/sync/gaze both → place (b22f3372) → settle → looks → head → lips |
| 16:28 | K2 stopped after sync him on my own guard ("this face turns its head itself": expected with turn_on Face since r5b's turn_by=auto calibration, rc 0); calibrate (fresh) turn_on Face, naturalize her/him, restage + sync him done. Resume from gaze him after K1 S1 |
| 16:30 | K1 S0: unshrunk face ref = `/Game/Host/Snap/SKM_Host_Op_FaceMesh_r5`; S1 (agent-02 collar_fit measure, f8349460) failed in stage `frame` (`_G` written as JSON into Python source: `true`) → fixed 24c39287 (json.loads), re-run |
| 16:35 | **S1 INVALID** (agent-02 agrees): worst need 11.0 cm, 24/24 sectors, worst frames at f960-966 / f1563-1571; 51 "head did not move" f1413-1554. Cause (agent-02): the temp ref face is a leader-pose follower whose CPU pose never updates → read at rest. New plan: measure the LIVE face with the backstop off |
| 16:35-16:43 | K2 resumed: gaze him (S13/S15/S17/S18 err p95 ≤ 0.11° after pass 2), restage/sync/gaze her, place (b22f3372) rc 0. **settle rc 1**: section starts clean (him f961 excess 0.074°, her f1081 0.088°), only f1559 fails (him 2.0°, her 4.2°, plan 0: the last frame) → agent-04. head: him blink_nod 0.0 / locked 0.084 / buzz 0.043; her 0.0 / 0.128 (gate_head blink_nod 0.466 at f1303-1307, line 0.6); lips check placed rc 0; leaders, lock, saved |
| 16:43 | S3 (agent-02 a251dd1b/2ffddb7e, tree 058e211f): snapshot → `/srv/ue/reel/r6/snap_preS3` (Host_Op, WI_Host_DefaultGarment_Neck, BP_Host_Op, Host_Op_Outfits, face mesh); backstop_off: MaxShrink 3.0 → 0.0, MaxCull 0, saved |
