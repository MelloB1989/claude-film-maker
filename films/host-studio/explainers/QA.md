# Explainer QA (round 6)

Owner: agent-09 (gate + QA). This applies to both explainers before the orchestrator sees them:
**whatsapp** (him, box A) and **netflix** (her, box B). The orchestrator reviews only a film whose gate run says SIGN,
apart from the rows that are the orchestrator's own eye.

The gate is `qa/gate.py` with `gate_spec.json` (this folder): one run per film, numbers only, no waivers on a
complaint area (lips, head, garment, hair, set, eye).

    film-qa gate numbers/<film>/*.json --spec films/host-studio/explainers/gate_spec.json --out numbers/<film>/verdict.json

## Rules

- **A missing number fails.** "Not measured" is not a pass, and neither is an error. An INFO row is reported but
  never blocks. The reason is written in its row, and only the orchestrator turns a row into INFO.
- **Face rule.** Presenter frames, composites and cuts stay on the boxes and under
  `s3://…/ue-linux/private/`. Every check that reads a presenter image runs **on the box** and writes **numbers
  only**. The `numbers/<film>/*.json` files hold numbers and words only, never pixels, so they can go in git.
  Captions, facts, VO and graphics-only renders are not face data.
- **Numbers contract.** Each producer writes `{"gate": {"<item>": {"value": v, "where": "<shot fN-M / line id>"}}}`,
  or `{"value": null, "error": "<why>"}` when it could not measure.
- **Review.** Every image or video goes to the orchestrator by presign under `private/renders/r6/review/<track>/`
  before anything is called done.

## What is checked, who measures it, how

Lines and full definitions are in `gate_spec.json`. "ON" means the presenter's on-screen spans
(`edl/<film>.json`).

### Lips (agent-01 curves, the orchestrator's eye)

| item | line | how |
|---|---|---|
| lips.lead_in_cm, onset_lead_ms, lag_frames, track_r, silence_open, silence_busy, cues_fresh, measured_against | as on the karma reel | perfkit / cast_gate on each on-camera line (the curve items stay HARD) |
| lips.eye_onsets | == 1 | the orchestrator's strip, signed: every on-camera line has a 0-2 f lead (mouth opens before the sound), or is occluded with what hides it. Run `../reel/r6/eye_onsets.py STRIP --lines W04,W05,…` |
| lips.render_lag_frames | INFO | invalid measure (the orchestrator's ruling, 07 Nov) until agent-01's landmark measure is validated |

### Head, eyes, blinks (agent-04, `head.py`)

`head.py judge CUE --head head.json --eyes eyes.json --gate numbers/<film>/head.json`, run on ON spans:

| item | line | what it catches |
|---|---|---|
| head.blink_nod_deg / blink_locked_deg | ≤ 0.6 / ≤ 0.3 | a nod on each blink |
| head.buzz_rms_deg | ≤ 0.08 | jitter |
| head.drift_deg | 0.15-1.5 | frozen (mannequin) or wandering |
| head.frozen_s | ≤ 1.5 | a dead hold |
| head.nods_per_min | 3-24 | emphasis nods with the speech |
| eyes.on_lens_share | ≥ 0.75 | talking to the viewer |
| eyes.saccades_per_s | 0.4-3.0 | eyes alive |
| eyes.glances_per_min | 2-8 | thinking glances off the lens and back |
| blinks.per_min | 10-30 | natural blink rate while talking |

Two-sided lines use the gate's `range` op (core `0b3bbf5c`).

### Body (agent-01)

| item | line | how |
|---|---|---|
| body.breath_cycles_per_min | 8-22 | seated-body sampler on spine_05 and the clavicles: the dominant 0.13-0.37 Hz cycle |
| body.breath_amp_mm | ≥ 2.0 | median sternum rise per cycle: visible, not a heave |
| body.desk_through, body.mic_touch, body.knee_desk | == 0 | `perform.py` (seatkit): bones against the set boxes on every frame, a hand through the desk, a touch on the mic or its arm, a knee through the desk |

### Garments in the SEATED pose (agent-02 his, agent-07/01 hers)

A seated pose bunches the tee at the waist and pulls the collar forward. So everything is measured **on the explainer
sequence, every presenter camera**, not on the karma shots:

- `qa.clip` gives garment.neck_px (== 0) and garment.pair_fraction (≤ 0.001: Trousers>tee at the waist, Body>tee at
  the shoulders when he leans).
- `qa.garment_look` gives garment.collar_gap_cm (≤ 0.8), collar_roll (== 0), armor_index (≤ 0.5), wpo_cm (≤ 0.2) and
  hem_flare_ratio (≤ 1.15).
- **His neck: garment.open_edge_shrunk == 0.** This is the operator's "cut". agent-02's r6 root fix turns the backstop
  off (MaxShrink 0), so the row reads 0 only when `shrink_live` proves 0 verts moved. His explainer moves to box B (the
  orchestrator, 07 Nov), so **garment.head_state_parity == 1** comes first: box A's head files match on box B by checksum,
  and cull_live reads the same culled count and lowest z on both boxes.
- **Netflix V2 (the orchestrator's pick, 07 Nov): her fitted white ribbed Top with NO overshirt.** clip_r7's
  occlusion baseline was taken with the overshirt, so it no longer applies. Every pair counts raw again until the
  orchestrator rules a V2 occlusion by eye on a fresh run. **Ruled (07 Nov): r6b_v2_clip is V2's baseline.** Body>Top at
  MCU f1330 / MCU_L f1015 is her forearm in front of the top, and Trousers>Top at WIDE f1176 is her hands in front of the
  hem: occlusions. Later runs are judged against it +0.01.
- **(Superseded by V2) Her occlusions (the orchestrator, by eye on box B clip_r7):** Top>Overshirt at the open front, Body>Top where the
  wrist sits in front of the torso, and Trousers>Top at the waist are occlusions, not clipping. From then on these
  pairs count only their excess over clip_r7's own worst (`qa.clip before=…/clip_r7/clip.json`), so a NEW poke still
  fails.
- garment.silhouette_pct is INFO: there is no seated reference yet.
- The cloth rows are NOT ATTEMPTED (the orchestrator's ruling: his tee is Epic's default garment, her overshirt stays
  skinned).

### Hair (as on the karma reel)

hair.lock == 1 and hair.render_cvars == 1 (read before every render). hair.pop_reach_pct ≤ 8 and hair.cut_reach_pct ≤
12 come from `../reel/r5/gate_numbers.py hair` on the final frames. hair.cut_pop_ratio ≤ 1.8 applies at every cut
where the camera holds, and each render job should cover the cuts.

### Set: chair, desk, mic (agent-07 measures, agent-05 for the props)

Both checks are the core `qa.clip` extension (`0ce1c3ae`, branch `fleet/agent-09/r6-qa-clip-set`):

    film-ue op qa.clip label=<presenter> sequence=<SEQ> n=8 \
      'props={"Chair":"<chair label>","Desk":"<desk label>","Mic":"<mic label>"}' \
      'pairs=[["Body","Chair"],["Trousers","Chair"],["Chair","Trousers"],["Body","Desk"],["Desk","tee"]]' \
      'mouth={"blocker":"Mic","radius_cm":2.0}' out_dir=/srv/ue/qa/expl/<film>/clip

- **set.clip_px == 0**: the worst pair px across those pairs. The presenter must never sink into the seat or the desk,
  and the chair must never poke through the trousers.
- **set.mic_mouth_px == 0**: `metrics.worst.mouth.blocked_px`, the pixels of a 2 cm disc round the lip bones where the
  mic is nearer than the face, in every camera. A missing lip bone is an error, never a pass. The default bones are
  `FACIAL_C_LipUpper/LipLower/L_LipCorner/R_LipCorner`; pass `"bones"` if the face names them otherwise.
- **set.props_overlap == 0**: `qa.overlaps` on the set props (the mic arm in the desk, the chair in the desk).
  Confirm any hit with a still.

### Streaming (box drivers)

**shot.streaming_settled == 1**: every final job warms texture and virtual-texture streaming before its first frame.
That first frame, in every camera, shows no hard-edged rectangular block. Netflix V2's CU f1300 had two (a pale one and a
wood mosaic) at the bottom centre.

### Grain (box B, before the batch)

**shot.grain_sigma ≤ 1.0 levels (the orchestrator)** is the worst Immerkaer noise sigma over fixed flat patches, picked by projection
through each camera: the wall, under her jaw, and the desk top. `qa_av.py grain FRAMES --patches patches.json`
measures it. Calibrated on box B: the f300 speckle reads 3.10 and MCU_1330 reads 14.55 (both must fail), against
0.689 on the finals-spec MCU test, which the orchestrator passed at 1:1. Measure the first and last frame of each final job; a FAIL re-renders that job. A FAIL blocks
the 9-shot batch.

**WIDE shots (the orchestrator's ruling, 07 Nov):** grain is read on flat patches only (the wall, plus a second
plaster patch), with line **0.8**:

- f300's wall at 1.002 must FAIL.
- Netflix V2 shot 11 reads 0.55 and passes.

At that scale the neck and desk patches hold texture (jaw line, hair edges, walnut pores), so they are reported as
INFO. The evidence is the orchestrator's 1:1 look at shot 11 f1100: the desk shadow is smooth and the pores are real.
Close shots stay at wall + neck ≤ 1.0.

### Exposure (agent-09 runs it on the box)

    python3 qa_av.py exposure <final frames> --shots shots.json --box <face box x0,y0,x1,y1> --out numbers/<film>/exposure.json

- shot.exposure_jump_stops ≤ 0.05: frame-to-frame change inside a shot, which catches auto-exposure pumping or a
  light popping.
- shot.exposure_drift_stops ≤ 0.15: the 12-frame moving average inside a shot.

Lock the exposure in the render spec, with no eye adaptation.

### Audio, captions, facts, delivery (agent-11 produces, agent-09 checks)

| item | line | how |
|---|---|---|
| audio.lufs_err_lu | ≤ 0.5 (−14 LUFS ± 0.5) | `qa_av.py loudness CUT.mp4` |
| audio.true_peak_dbtp | ≤ −1.0 | same |
| captions.text_match | == 1 | `qa_av.py captions CUT.srt audio/<film>/cues.json`: the caption words, in order, are the VO words |
| captions.onset_ms | ≤ 200 | same: the worst gap between a caption start and its line start |
| facts.sourced | == 1 | `qa_av.py facts audio/<film>/cues.json facts_<film>.json`: every number is softened ("over", "about", "nearly"…) or has a claim with a source |
| gfx.caption_band_clear | == 1 | agent-08 / agent-12 from their layout: no diagram text below y 0.85 (the caption band) in any frame, full and panel layouts |
| deliver.format_ok | == 1 | `qa_av.py format CUT.mp4`: 1920x1080, 16:9, 24/25/30 fps, 48 kHz |
| deliver.qc_ok | == 1 | `film-post qc CUT.mp4 --edl … --captions …`: no black or frozen runs, captions in the safe area |
| deliver.duration_s | 50-70 s, INFO | same as format |

**Captions ruling (the orchestrator, 07 Nov):** every VO line is captioned, over the graphics too (people watch
muted), in one consistent band at the bottom; the graphics keep that band clear.

The facts file (agent-11) is `facts_<film>.json`:

    {"claims": [{"said": "two million", "text": "2M+ connections on one server (2012)", "source": "<url>"}]}

### The orchestrator's eye (signed strip)

    python3 signed.py STRIP.json --out numbers/<film>/eye.json
    # STRIP = {"by": "cc-64d05f6e", "film": "<film>", "gate": {"eye.real_person": 1, …}, "notes": {…}}

- **eye.real_person**: reads as a real person speaking, at full speed and in 2x crops.
- **eye.light**: soft key, a visible rim, catchlights in both eyes, shallow depth of field.
- **eye.hair_garment**: no popping hair, no armour, collar on the neck, no cut or gap at his neck.
- **eye.graphics**: high-end, correct, in sync with the VO, no text errors.

## First read of the scripts (agent-09, 07 Nov, on `fleet/agent-11/r6-explainers` b803f5a6)

`qa_av.py facts` with an empty facts file flags:

- **W06** "One server once held two million of them": needs a source in `facts_whatsapp.json`. WhatsApp's 2012
  engineering post reports 2M+ connections on one server. Alternatively, soften it to "over two million".
- **W17** "That's a hundred billion messages a day": not softened. W01 says "over a hundred billion", so say "over"
  here too, unless a source pins the exact figure.

Checked by reading against public sources, and right as written:

- the ticks (W10-W11);
- the group fan-out with sender keys, where the phone encrypts once and the server fans it out (W12);
- media in a blob store, with the key in the message (W15);
- Open Connect appliances, free to ISPs, filled every night (N04-N07);
- per-title ladders (N09);
- chunks of a few seconds (N10);
- the control plane on AWS steering the player to the OCA (N13-N14).

N01 says "over three hundred million paying members", which is softened. Netflix reported 301.6M paid memberships at
the end of 2024.

## Order of a film's QA (per box)

1. His film on box B: garment.head_state_parity (box A's head files by checksum, the same cull_live), and setplan's
   sign rule re-enabled for him (FACE_ESTIMATED empty once his seated eyes are measured).
2. Editor, read before the render: garment.leaders_ok (every garment leader == Body; the r6n0 lesson), hair.lock, render_cvars, cameras_ok, set.props_overlap.
3. Editor, after the performance is placed: qa.clip (garments + set + mouth) and qa.garment_look, seated.
4. agent-04 head.py and agent-01 lips/body on the placed performance.
5. Finals, from a freshly restarted editor (the karma lesson): exposure, hair numbers.
6. Composite on the box, then the cut: loudness, format, qc, captions, facts.
7. `film-qa gate` → SIGN on everything but the eye rows → the review to the orchestrator → the signed strip → SIGN.
