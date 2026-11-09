# Research index (round 5): how Unreal character shots are done properly, and what checks it

Round 4 of the karma reel shipped five faults that our numeric gates passed but the operator saw at once.
1. His lips moved ~0.7 s before his audio.
2. His tee read as armour.
3. His tee clipped at the neck.
4. Her head nodded on every blink.
5. Her hair went short at a cut.

Each track researched its fault: Epic's docs and the UE 5.8.4 source first, then forums, papers and vendors (each
labelled). The tracks then built the lessons into the tools. This page is the index and the rules. Read the doc
before you change anything in its area.

| doc | the complaint | our root cause, in one line | the helpers |
|---|---|---|---|
| [lipsync.md](lipsync.md) (T1, agent-01) | "lips are moving before even his audio starts, and he has no lip sync at all" | Every lip check measured amplitude, never timing. The face and the mix used two timebases (a whole-stem solve spliced at planned cues, while the mix plays separately built VO). The full-face solve animated the mouth in the silences. | `lipsync.check`, `lipsync.compose`, `lipsync.mouth_boxes`, `speech.to_face process_mask=mouth`, `film-ue lips cues/curves/render/gate` |
| [blinks-head-stability.md](blinks-head-stability.md) (T2, agent-04) | "every time she blinks her head nods a little down like a jitter" | Three things put head pitch inside the blink windows, all locked to the blinks by construction: gaze blinks rode the chin dip of their own turn; the speech solve's own head (one predictor run with its blinks) was kept, softened; and emphasis blinks fell on beat nods. | `perf.face blink_head=still solver_head=replace` (the defaults now), presets, `qa.head_stability`, `film-qa head / head-samples / head-gate` |
| [garment-fit.md](garment-fit.md) (T3a, agent-02) | "his chest still looks like he wore some heavy armor inside"; "clipping at the neck a little" | The neck clip was the FACE mesh, which runs ~10 cm below `neck_01`, not the body. We pushed the tee out with a material WPO, which is an even offset, not a fit: no varying ease, no folds, no motion. Our gates measured only clipping. | `film-ue garment-fit` (Blender regional-ease fit), `garment.hidden_face_maps`, `body.hide_under`, `garment.export`, `qa.clip`, `qa.garment_look` (armor index), `film-ue garment-gate` |
| [cloth-physics.md](cloth-physics.md) (T3b, agent-08) | the same "armor": no cloth behaviour, no wrinkles | His tee never simulated: it was a skinned shell with no clothing data, and nothing measured whether it moved relative to the body. Live cloth also needs a warm-up before the first rendered frame, and its step is capped at 1/30 s. | `cloth.setup / presets / settings / preroll / render_check / cache / describe / remove`, `qa.cloth` (sim vs skinned two-pass judge), the FMCloth editor plugin |
| [hair-lod.md](hair-lod.md) (T4, agent-09) | "at 01:00 her hair again becomes short!" | Round 4 pinned only the LODSync index. Auto LOD (`r.HairStrands.LODMode` 1, the default) still thins the curves on a wide shot even at LOD 0. A groom outside LODSync's `ComponentsToSync` list never gets the forced LOD, and the mode is read when the groom registers, so a cvar in the MRQ job is too late. | `groom.lock`, `groom.lock_check`, `qa.hair_continuity`, `film-qa hair`, and the review gate v2 `film-qa gate` (`qa/gate.py`) |
| [presenter-r7.md](presenter-r7.md) (round 7, the explainers) | "zombie" hands (the claw) | Hand poses were offsets on the rig's reference curl, and the hand gate read the kit rather than the placed level. | named anatomical hand poses (gesturekit), LIST gestures in the acting sheets, REST_HOLD, the hand rows on the placed dump, the head gate |

## The rules (for Claude, every character shot)

Each rule names the helper that enforces it. A rule without a check is how round 4 happened, so if you add a rule,
add its check.

**Lip sync**
1. **Lip sync is a timing claim.** Prove each line with the lag between the voice's loudness and the mouth's opening:
   |lag| <= 1 frame, corr >= 0.35, onset lead <= 0.25 s, >= 80% of aligned words moving. A big jaw range proves
   nothing: a face 17 frames late still moves "a lot on the line". *Enforced by* `lipsync.check` (editor),
   `film-ue lips curves` (offline) and `film-ue lips render` (on the frames, with a shifted-audio control).
   `diagnosis` names offset / drift / scattered.
2. **One timebase, measured.** Cues come from the stems the mix actually plays (VAD at mix position, stem hashes),
   never from a plan or an old `cues.json`. *Enforced by* `film-ue lips cues`, whose output `lipsync.compose` and
   the gate read.
3. **When perfkit owns the face, the solver gives only the mouth.** Use `speech.to_face process_mask=mouth head=false
   blinks=false`, one solve per line, placed at its cue by `lipsync.compose`. Read `timing` in the result: the
   animation must be as long as its WAV.
4. **The mouth is still in the silences.** *Enforced by* `lipsync.check`'s silence metrics (open <= 0.10 above rest,
   busy <= 25%).

**Head and blinks**

5. **No blink moves the head.** `perf.face` defaults to `blink_head=still` and `solver_head=replace`, and the presets
   (`presenter_calm`, `presenter_lively`, `listener`, `still_portrait`) keep them. *Enforced by* `qa.head_stability`
   on the master sequence: it reads the head bone as rendered, so it sees the solver, the neck and the AnimBP. On
   frames, `film-qa head` uses rigid-landmark PnP. Gate lines: `head.blink_nod_deg <= 0.6` and
   `head.blink_locked_deg <= 0.3`.

**Garments**

6. **Never fake a fit with World Position Offset.** Fit the garment with ease that varies by region (`film-ue
   garment-fit`), and hide or shrink the skin under it (`garment.hidden_face_maps` for the face mesh at the collar,
   `body.hide_under`). *Enforced by* `qa.garment_look`: it FAILS at an armor index >= 0.5 or any WPO > 0.2 cm.
7. **Clipping is measured per layer pair from the shot's camera.** The collar band counts the face as well as the
   body. *Enforced by* `qa.clip`: `neck_px == 0` every frame, pairs <= 0.001, silhouette within +-2%. `film-ue
   garment-gate` gives the gate numbers.
8. **A garment that should move must simulate.** Use `cloth.setup` with a preset (`cotton_tee`, `overshirt_light`,
   `trousers`) and rule-painted max-distance/backstop maps. *Enforced by* `qa.cloth`, which FAILS `no_clothing`,
   `not_simulating`, `dead`, `explosion`, `velocity_spike`, `nan` and `cold_start`. Gate: `garment.cloth_alive >=
   0.30 cm`, `cloth_sound == 1` and `cloth_detail_ratio >= 1.25` vs round 4.
9. **Cloth needs its warm-up before the first judged frame.** *Enforced by* `cloth.render_check`, which fails a render
   spec whose warm-up is shorter than the garment needs: `final` holds 32 frames, while `preview`/`draft` are too short
   for an overshirt. `cloth.preroll` does the same before a live check.

**Hair**

10. **Lock the hair before any render.** `groom.lock`:
    - lists every visible groom in LODSync's `components_to_sync`;
    - forces LOD 0 and turns `use_cards` off;
    - sets `r.HairStrands.LODMode 0`, `r.HairStrands.AutoLOD.Bias 1` and `r.HairStrands.UseCardsInsteadOfStrands 0`.

    Lock **before** the render starts, and pass its `render_cvars` into the render spec. *Enforced by*
    `groom.lock_check` (the gate's `hair.lock`). `build.py --lod0` refuses a lock that doesn't verify.
11. **Hair keeps its length across every cut.** Measure it by *reach*: how far the hair falls below the head, in
    head units, which is the same in a close and a wide shot. *Enforced by* `qa.hair_continuity` (editor) and
    `film-qa hair` (frames): reach may change <= 12% across a cut and <= 8% frame to frame.

**The gate**

12. **A gate is numbers with lines, and a missing number fails.** Each line must fail the round-4 value it exists
    to catch. A waiver needs a reason and a name, and is refused on anything the operator complained about.
    *Enforced by* `film-qa gate NUMBERS.json... --spec` (`qa/gate.py`, gate v2) and `film-qa gate --lines`.
13. **Never guess an engine API name.** Every UE Python/C++ name a helper calls was checked against the 5.8.4
    source (the MetaHuman plugin included) and has an `API_NOTES` row in its area doc. *Enforced by*
    `tests/test_ue_dx_apinotes_gate.py`. What only a running engine can answer is listed as a GPU probe, not
    assumed.

**Presenter hands and face (round 7, [presenter-r7.md](presenter-r7.md))**

14. **Hands are named anatomical poses, never offsets on the rig's reference curl.** Knuckle-led curl, fingers
    nearly together, rest palm down on the desk top, no palm to camera, no finger counting (LIST at the sternum), no
    hand above the chin or within ~10 cm of the face. *Enforced by* the hand gate rows run on the PLACED editor
    dump, and by the orchestrator's eye on stills.
15. **Snaps count only on camera.** Map each flagged frame to the EDL; ease the rest (time-gated eases, REST_HOLD).
16. **No GPU box without a 0-issue offline build.** The box is for the finals and the box-side Host_Op sweeps, not for
    finding bugs.

## Where the probes are

The engine questions only the GPU box can answer are listed as probes:
- in the docs: P1..P3 (lipsync), P-C0..P-C7 (cloth), G1..G6 (garment), P3 (hair);
- in the film plan: T2's (`films/host-studio/reel/r5/blinks.md`).

The IDs are per track (lipsync's P3 is not hair's P3), so the plan prefixes them with the track. The orchestrator
runs them in one session, from
[films/host-studio/reel/r5/PLAN.md](../../../films/host-studio/reel/r5/PLAN.md) on `film/host-studio`.
