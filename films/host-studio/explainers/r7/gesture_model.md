# Round 7: speech-driven gestures, the model choice (agent-10, 07 Nov)

**Decision (the orchestrator, 07 Nov): no machine-learned speech-to-gesture model, and no non-commercial model output
anywhere in the pipeline, not even as a reference.** The operator publishes monetised videos, and every open model
with body and finger output is non-commercial (the survey below). Instead, `gesture/` is a **planner over licensed
motion capture**:

- agent-08 sources the mocap (Mixamo, Rokoko, CMU, etc.), checks the licence per clip and retargets it to MetaHuman.
- The planner picks clips for each gesture in agent-11's acting sheet (`acting/her.json`): beat, open palm, count,
  deictic, size, rest and the rest of the sheet's types.
- It time-warps each clip's stroke onto the stressed syllable, using the VO's word times and the prosody of `vo.wav`.
- It blends neighbouring clips with co-articulation.
- It then applies the seated limits: upper body only, upper arms >= 3 cm off the torso, big motion on her right hand
  (the mic is on her left).
- Procedural motion is used only for transitions and micro-beats. A purely procedural curve synth is what made v2b
  robotic.

## The survey (web, 07 Nov 2026)

| Model | Code / weights / data licence | Output | Emotion / style input |
|---|---|---|---|
| EMAGE, CaMN, DisCo (PantoMatrix) | Code: no licence stated. Data: BEAT2 (the BEAT project says non-commercial; BEAT is CC BY-NC 4.0) | SMPL-X `.npz`, 30 fps, with fingers | Speaker ID only |
| GestureLSM (ICCV 25) | Code: MIT. Weights trained on BEAT2 | SMPL-X | None |
| SemTalk (ICCV 25), RAG-Gesture (CVPR 25) | Licence unstated. Data: BEAT2 | SMPL-X | None |
| AMUSE (CVPR 24), TalkSHOW | MPI non-commercial research licence | SMPL-X | AMUSE: emotion |
| ZeroEGGS (Ubisoft) | Code, weights and data CC BY-NC-ND-style | BVH with fingers | 19 styles from an example clip |
| DiffuseStyleGesture / DSG+ | Code: MIT. Weights trained on ZEGGS (non-commercial) | BVH (ZEGGS skeleton) | Style label |
| Audio2Photoreal (Meta) | Code and data CC BY-NC 4.0 | Its own joint-angle skeleton | None |
| 2025-26 work (GlobalDiff, StreamTalk, LiveGesture, PersonaGest) | All trained on BEAT2 / SMPL-X; weights unconfirmed | SMPL-X | — |

NVIDIA has no open audio-to-body-gesture release.

The SMPL-X body model itself is free only for non-commercial research, education and art. Its licence names
animations, so a commercial artifact needs a Meshcapade licence. A route through SMPL-X therefore carries two
licences: BEAT2's and SMPL-X's.

The only commercially clean ML route would be to train an MIT-licensed model (GestureLSM, DiffuseStyleGesture) on mocap
we own or license, on a BVH skeleton. That is out of scope for this round.

Sources: github.com/PantoMatrix/PantoMatrix, huggingface.co/datasets/H-Liu1997/BEAT2, pantomatrix.github.io/BEAT,
smpl-x.is.tue.mpg.de/modellicense.html, github.com/ubisoft/ubisoft-laforge-ZeroEGGS (License.md),
github.com/andypinxinliu/GestureLSM, github.com/Xiangyue-Zhang/SemTalk, huggingface.co/m-hamza-mughal/rag-gesture-weights,
github.com/kiranchhatre/amuse, github.com/yhw-yhw/TalkSHOW, github.com/YoungSeng/DiffuseStyleGesture,
github.com/facebookresearch/audio2photoreal.

## The path to her MetaHuman

The clips come in already retargeted to the MetaHuman body skeleton (agent-08's IK Retargeter), so no SMPL-X is
involved.

1. Headless Blender on box B, beside the editor, never touching it (coordinated with agent-06), bakes each FBX to
   per-frame local rotations.
2. The planner composes them on the VO clock at 30 fps.
3. It exports an FBX on her body skeleton for agent-01 to import as an AnimSequence, plus a BVH with the same bone
   names.
4. The preview is a stick mannequin rendered from the same joints, frame-synced to `vo.wav`.
