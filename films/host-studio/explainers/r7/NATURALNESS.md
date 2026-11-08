# R7 movement: what makes a code-made presenter gesture read as human

agent-13, round 7 movement director, 08 Nov. Numbers only, no face data. The measure is `r7/naturalness.py`, run
offline on agent-01's arm track (`r7/arm_track.py`; actor frame x fwd, y her right, z up, cm, joint heads).

## 1. Research, short

| Topic | What natural speakers do | Source |
|---|---|---|
| Phases | Preparation, stroke (the meaningful peak, on or just before the stressed syllable), optional post-stroke hold, retraction. Strokes chain without a full retraction when gestures come close together | Kendon 1980, 2004 (*Gesture: Visible Action as Utterance*); Kita, van Gijn & van der Hulst 1998 |
| Gesture space | Most strokes fall in McNeill's *center* and *center-center*: in front of the torso, roughly between the waist and the chest. Large or deictic gestures reach the periphery | McNeill 1992 (*Hand and Mind*), gesture-space diagram |
| Upper arm | A conversational speaker keeps the upper arm low, with the elbow near the side and a little forward. In ergonomics an upper arm 20-45 deg off hanging is "moderate", and 45-90 deg is a strained posture that people do not hold while talking. Lifting the elbows up and out to put the hands at chest height is the classic "chicken wing" | McAtamney & Corlett 1993 (RULA, upper-arm bands) |
| Elbow / forearm | With the elbow low and bent about 60-100 deg (RULA's neutral band), the forearm points up and forward toward the listener. A horizontal forearm at chest height only happens when the elbow is raised | RULA; geometry |
| Wrist | Daily tasks use about 5 deg flexion / 30 deg extension and 10 deg radial / 15 deg ulnar (functional), and most use 40 deg flexion/extension and 40 deg combined radial-ulnar. Active maxima are about radial 20-25 and ulnar 30-35. A gesturing wrist sits near neutral to slightly extended | Palmer et al. 1985 (*J Hand Surg*); Ryu et al. 1991 (*J Hand Surg*); AAOS norms |
| Hand shape | The relaxed hand has the "normal cascade": the fingers are slightly flexed, more toward the little finger, and the thumb rests beside the index. Open-palm explaining has the palm turned partly up or in. A hyperextended middle joint (a claw) or a pinch reads as deliberate | Hand-surgery convention (the resting cascade); McNeill 1992 / Kendon 2004 (palm-up open hand family) |
| Speed profile | A point-to-point hand movement has a smooth, single-peaked bell-shaped speed. Minimum jerk gives a peak/mean of 1.875. A flat (constant-speed) profile, or a sharp spike with long slow tails, reads as machine-made | Flash & Hogan 1985 (*J Neurosci*); Morasso 1981 |
| Path | Reaching paths are nearly straight but not exactly. Non-reaching movements (gestures, drawing) curve, with speed falling in the bends (the two-thirds power law). Animators draw on arcs. A perfectly straight hand path is a CG tell | Atkeson & Hollerbach 1985; Lacquaniti, Terzuolo & Viviani 1983; Thomas & Johnston 1981 (*The Illusion of Life*), "arcs" |
| Sequencing | Proximal segments lead and distal ones follow (shoulder, then elbow, then wrist and fingers), which is the kinetic chain. Animators call it overlapping action and follow-through: the hand drags behind the forearm and settles after it | Putnam 1993 (*J Biomech*); Thomas & Johnston 1981; Lasseter 1987 (SIGGRAPH) |
| Two hands | Two-handed gestures are often symmetric in form, and the hands start nearly together (Kelso et al. 1979), but they are not mirror copies: amplitude, shape and settle differ, and the dominant hand leads. A two-hand gesture with one hand parked reads as one hand plus a prop | Kelso, Southard & Goodman 1979 (*Science*); McNeill 1992 |
| Whole body | The torso, shoulders and head co-move with strokes: a small chest turn toward the gesturing side, a lean on emphasis, head nods on stresses | Kendon 2004; McNeill 1992 |
| Robotic tells | Constant speed, linear paths, both hands in sync, fingers frozen or snapping between fixed shapes, the same shape repeated, the hand placed at a target rather than carried by the arm | Thomas & Johnston 1981; Lasseter 1987 |

## 2. The rows (agent-09's gate) and why each line sits where it does

Rows apply while she speaks (speak_w > 0.5). "Apex" means mid-hold of an event. Where both hands apply, the worse
hand counts.

| Row | Line | Why |
|---|---|---|
| move.humerus_elev_stroke_deg | <= 45 | RULA's strained band starts at 45 deg; conversational strokes keep the elbow low. Apexes below upper_chest only |
| move.humerus_elev_high_deg | <= 60 | the orchestrator's ruling (08 Nov): apexes at/above upper_chest (wrist >= 16 cm over the sternum point = shoulders' mid height - 14) may lift to 60, the forearm cannot reach them from 45. n/a when there are none |
| move.upperarm_abduction_deg | <= 35 | the orchestrator's ruling: the elevation is mostly flexion (toward the camera), not abduction (chicken wings). Abduction = the upper arm's angle out of the sagittal plane, median at apexes, worse hand |
| move.humerus_elev_rest_deg | <= 30 | at rest the upper arm hangs (RULA 0-20 "neutral", 30 allows the clearance from the bust) |
| move.forearm_elev_deg | >= 15 | forearms angled up to the listener; a forearm under 15 deg at chest height is the "typing in the air" look |
| move.wrist_flexext_p90_deg | <= 25 | the brief's +-20 "mostly", with p90 allowing the strokes' brief extension; Palmer/Ryu functional ranges |
| move.wrist_ulnar_p95_deg | <= 25 | Ryu's functional ulnar range; well inside the 30-35 deg active maximum |
| move.wrist_radial_p95_deg | <= 15 | between Palmer's functional 10 deg and the ~20 deg active maximum |
| move.shape_wrong_strokes | == 0 | no claw, no pinch outside a 'pinch' gesture, no flat mannequin hand at any apex |
| move.shape_claw_frac | <= 0.02 | a finger bent back at a middle joint is never a rest shape |
| move.path_straight_frac | <= 0.30 | at most 30 % of wrist movements (chord >= 8 cm) may stray < 3 % of the chord (Atkeson & Hollerbach's reaches curve 5-10 %; gestures more) |
| move.vel_bell_frac | >= 0.60 | 60 % of movements with a peak/mean of 1.6-2.3 around minimum jerk's 1.875 |
| move.lag_hand_ms | >= 30 | the hand's rotation starts at least 30 ms (one frame) after the upper arm's (proximal to distal) |
| move.two_hand_amp_ratio | >= 0.5 | on two-hand strokes the lesser hand travels at least half as far as the greater |
| move.hold_min_speed | >= 0.3 cm/s | the orchestrator (08 Nov): p10 of the wrist speed while speaking outside every movement (holds and rests), worse hand. A live hold drifts 0.5-1 cm/s with breath and micro-motion; a frozen hand reads as placed |
| move.finger_snap_per_min | <= 2 | finger shapes that snap in and stop dead: a fingertip (DIP head) >= 90 cm/s relative to the wrist falling to <= 25 % within 2 frames, per speaking minute, worse hand. Minimum jerk (Flash & Hogan) holds for the fingers too, and "fingers snapping between fixed shapes" is the classic robotic tell (Thomas & Johnston; Lasseter). Found 08 Nov behind his 2 cm parity residual: at a snap the editor's slerped rotations and the interpolated positions split by 1-2 cm. 404db805 25.5, 52ab5ea2 11.5, 8a45d961 8.4 /min |
| move.mirror_corr_p50 | <= 0.95 | GUARD (never failed yet): two-hand velocity is not a mirror copy |
| move.fingers_frozen_frac | <= 0.15 | fingers are not dead still for >= 0.5 s while speaking. A GUARD until 08 Nov: the dumps rounded joints to 0.01 cm, ~6 deg/s of jitter on 3 cm finger bones, which hid it. At 0.1 mm every body fails (404db805 0.57, 52ab5ea2 0.60) |

The hand-to-body distance is NOT a row here. Without the mesh, a joint-head measure cannot tell "on the stomach" from
"in front of it": `body.near_frac` read 0 on every body. agent-09's mesh row `qa.hand_torso_clearance` owns it.

Measured conventions:
- **Wrist**: the 3rd metacarpal (wrist to middle knuckle) against the forearm (elbow to wrist), resolved in the hand's
  palm normal (flexion +) and its radial axis (radial +). Her stock skeleton's unposed hand reads about -11 / +5 to
  +8, a little extended and radial.
- **Fingers**: MCP and PIP from the joint heads, + toward the palm. `_03` is the DIP joint, so the pinch test is a
  DIP-to-DIP distance under 3.5 cm.

Ruling of 08 Nov on clearance (agent-02's mesh): the upper arm keeps >= 3 cm from the bust/front of the Top and
>= 0.5 cm (no penetration) from the side of the torso.

## 3. Her values (first pass; the current table is naturalness_her.json), whole take (rows4.json; TEST spans in rows4_test.json)

| Row | old 404db805 | r7F TEST 52ab5ea2 | 773091c2 | 58f6e0aa |
|---|---|---|---|---|
| humerus_elev_stroke_deg <= 45 | 60.8 F | 77.8 F | 78.0 F | 78.0 F |
| humerus_elev_rest_deg <= 30 | 58.0 F | 73.1 F | 63.7 F | 63.7 F |
| forearm_elev_deg >= 15 | -2.8 F | 17.0 | 17.1 | 17.1 |
| wrist_flexext_p90 <= 25 | 21.9 | 38.9 F | 38.1 F | 29.9 F |
| wrist_ulnar_p95 <= 25 | 30.8 F | 39.2 F | 38.8 F | 31.3 F |
| wrist_radial_p95 <= 15 | 33.7 F | 23.7 F | 25.8 F | 32.8 F |
| shape_wrong_strokes == 0 | 9 F | 9 F | 9 F | 0 |
| shape_claw_frac <= 0.02 | 0.10 F | 0.10 F | 0.10 F | 0 |
| path_straight_frac <= 0.30 | 0.12 | 0.61 F | 0.23 | 0.24 |
| vel_bell_frac >= 0.60 | 0.71 | 0.39 F | 0.52 F | 0.53 F |
| lag_hand_ms >= 30 | -1 F | -25 F | -18 F | -18 F |
| two_hand_amp_ratio >= 0.5 | 0.43 F | 0.73 | 0.26 F | 0.27 F |

Each row fails on old or TEST; the guards fail on neither. `52ab5ea2` is taken as the r7F TEST body (the state just
before agent-01's "must-fix on her TEST", 5bb9605f).

Report-only on 58f6e0aa:
- The left wrist travels 3.4 cm/s against the right's 23 (0.15).
- The chest (spine_05) moves 0.45 cm/s and the head 0.85 cm/s, each correlating only 0.19 / 0.17 with the right
  wrist's speed: the torso barely co-moves.
