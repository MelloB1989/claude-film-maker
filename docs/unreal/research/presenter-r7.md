# Round 7: presenter hands, face and garments (the explainers, 08-09 Nov)

The operator on the round-7 explainers: "the hand movements and expressions look good, can improve but we will work
on it later". The round started from what the operator called "zombie" hands (the claw).
This page is what fixed them and what the next run starts from. The helpers live on the round-7 branches
(gesturekit, perfkit, the acting sheets, the hand gate rows) until they are merged.

## Hands

1. **Hand poses are absolute and anatomical.** Each pose is a named whole-hand pose (rest, open palm, place, list
   item), set per finger joint. Never an offset on the rig's reference curl: that is where the claw came
   from.
2. **The curl is led by the knuckles, at low closure.** The MCP joint bends first and most, and the finger tips stay
   nearly straight. Keep the fingers nearly together: the abduction between adjacent fingers is at most 5 degrees.
3. **Rest is palm down on the desk top.** The heel of the hand and the finger pads touch the desk; never the finger
   tips alone. Use the PLACED desk geometry, not a desk height assumed in seat space.
4. **No palm to camera.** Turn the palm off the lens with a forearm twist (pronation), eased over at least 0.25 s.
   A snap twist reads as a glitch.
5. **No finger counting.** "One / two / three" becomes a LIST gesture: the same hand places each item at a new spot,
   and the list apexes sit at the sternum. A raised index finger is kept only where a catalogue still passes on it.
6. **Keep hands away from the face.** No hand above the chin and none within ~10 cm of the face. A stroke that the
   sheet puts high goes to the upper chest or the collarbone instead; at most ~1/3 of the strokes at or above the
   upper chest.
7. **Ease the snaps.** Where a pose must change fast (a cut, a gesture onset), use a time-gated ease rather than a
   jump. Leaving a hold, use REST_HOLD: it eases out of the hold rather than releasing it in one frame.

## Gates

8. **Run the hand rows on the placed editor dump, not only on the kit.** The kit's own numbers can pass while the
   placed level (desk, chair, camera) fails: a rest above the desk, a hand clipping the desk edge.
9. **Measure lag from the hand itself.** The lag_hand onset is taken from the hand's own low point before the
   stroke, not from the shoulder or the sheet's time.
10. **Count snaps only on camera.** Map every flagged frame to the EDL. A snap inside a graphics shot or a handle is
    not seen and is not a failure.
11. **Judge by eye what a measure can't prove.** Measures have known artefacts: the A-pose sleeve split, the shoulder
    tube. Send stills to the orchestrator for the arms and the hands; a number alone never passes a look.
12. **Every must_fail case must fail.** A gate row that doesn't fail its must_fail case is not a gate.
13. **No box start without a 0-issue offline build.** Build and gate the sheet, the kit and the body offline; start
    a GPU box only when the offline report has no issues. On the box, the sweeps that read Host_Op run box-side.

## Face

14. **The face is three layers:**
    - a full-face audio solve, one per line;
    - a mood for each line;
    - an expression layer (smiles, brow flashes, the face beats from the acting sheet) on top.

    The operator called the result shippable.
15. **Head drift stays in the band 0.15-1.5** (the head gate's line).
16. **Nods must stay detectable.** The payoff lines get the full nod depth, so the head gate still counts them
    (its line: 3-24 nods/min).

## Garments

17. **Hide the body under a garment that pokes.** Use `body.hide_under` for the waist poke (see
    [garment-fit.md](garment-fit.md)) rather than pushing the garment out.
18. **Girth by new assets.** More arm girth (+10 %) comes from new assets, never a scale on the bones.
19. **Drop an accessory that clips.** The watch went: no fit was worth the clip.

## Privacy

20. **Host_Op data never leaves the boxes and the private S3 prefixes.** Host_Op data means the face, every render
    with a presenter, and also his rig and skeleton numbers. None of it goes to kali, pc2, git or the Mac relay.
    Box-side tools print numbers only: counts, boxes, pass/fail. Graphics-only renders are not face data.

## Mocap (later)

- MediaPipe (Apache-2.0) gives good arm directions from video, but its raw 3D fingers are unusable.
- The plan is a hybrid:
  - the arms come from the video;
  - the hands are the anatomical named poses above, driven by MediaPipe's coarse hand state.
- Epic's markerless plugin is Windows-only, so it is not an option on the Linux boxes.
