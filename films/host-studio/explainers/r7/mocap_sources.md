# R7 mocap gesture library: sources and licences (agent-08)

Seated "talking / presenting" motion for her (later his) body, retargeted to the MetaHuman body skeleton. Only
licensed sources; no binaries in git (FBX and retargeted assets live in `s3://…/ue-linux/assets/gesture/`).
Checked 07 Nov 2026.

## Sources considered

| Source | Licence for a commercial video | Fit | Verdict |
|---|---|---|---|
| **Adobe Mixamo** | Royalty-free for personal, commercial and non-profit projects, films and videos included; the one limit is that the raw character/animation files may not be redistributed (so: no FBX in this public repo, only on the box / private S3). Governed by the Adobe Terms of Use at the time of download. Free with an Adobe ID; downloads need a logged-in Adobe ID. <https://helpx.adobe.com/creative-cloud/faq/mixamo-faq.html>, <https://community.adobe.com/t5/mixamo-discussions/mixamo-faq-licensing-royalties-ownership-eula-and-tos/td-p/13234775> | 14 seated clips (talking, desk meeting, pointing, rests) + standing talking/gesture clips whose upper body is usable seated (count to five, two-hand forward, arm to side, asking with one/two hands, telling a secret). 30 fps, Mixamo skeleton: UE has a Mixamo→MetaHuman IK Retargeter path. | **Primary.** |
| Rokoko free packs (263 assets; idle, TV-themed packs) | Page text: "use them in any animation, VFX, game, 3D art or other 3D project you want, including for commercial use". No formal licence file seen before download. Download needs a sign-up form (name, e-mail, role). FBX 30 fps, Mixamo/UE/HIK skeletons. <https://www.rokoko.com/mocap/free-mocap-assets>, <https://rokoko.com/resources/rokoko-mocap-free-tv-themed-animations> | Unknown clip list (behind the form); the TV pack (reality TV / courtroom / documentary) may hold presenter talk. | Secondary, only if the operator OKs registering an e-mail. |
| CMU Graphics Lab mocap | CMU's notice: free for research, may be included in commercially sold products, may not be resold directly. Third-party conversions differ (the 4TU FBX conversion is CC BY-NC: not usable). <http://mocap.cs.cmu.edu> | No conversational/speech-gesture subset; no fingers. | Not used. |
| MetaHuman template animations (in the project) | Epic content under the UE EULA (UE-rendered output OK). | Only idles, ROM, locomotion and facial loops (`reel/previs/metahuman_animations.json`): no talking gestures. | Not used for gestures. |
| BEAT, ZEGGS, Talking With Hands, Trinity (co-speech datasets) | Non-commercial licences (agent-10 confirmed for the models built on them). | Ideal content, wrong licence. | **Excluded.** |
| Fab paid seated-dialogue packs | Per-listing Fab licence; paid. | Seated dialogue gestures. | Only if bought by the operator. |

## Mixamo shortlist (request for approval)

Download settings: FBX Binary, **Without Skin**, 30 fps, keyframe reduction none, on the stock Mixamo character
(Y Bot). Ids are Mixamo motion ids; length from the Mixamo catalogue. Mixamo builds each FBX on request, so the
exact byte size is known only after export; estimate ~0.1-0.3 MB per second of motion (35 clips, 390.7 s: about
40-120 MB in all). Seat-adapt (upper body only) is done in the retarget for the standing ones.

| # | file (to be saved as) | Mixamo motion (id) | description | frames @30 | s | use | posture |
|---|---|---|---|---|---|---|---|
| 1 | mx_talk_seated_a.fbx | Sitting Talking (`c9cd76b1-b96c-11e4-a802-0aaa78deedf9`) | Sitting And Talking To Another Person | 1321 | 44.03 | beat / conversational base | seated |
| 2 | mx_talk_seated_b.fbx | Sitting Talking (`c9cd7793-b96c-11e4-a802-0aaa78deedf9`) | Sitting And Talking To Another Person | 1349 | 44.97 | beat / conversational base | seated |
| 3 | mx_talk_seated_m.fbx | Talking (`c9c6500d-b96c-11e4-a802-0aaa78deedf9`) | Male Talking While Seated | 150 | 5.0 | beat | seated |
| 4 | mx_meeting_desk_f.fbx | Having A Meeting, Female (`c9ca5210-b96c-11e4-a802-0aaa78deedf9`) | Having A Meeting W/ Another At A Desk | 1400 | 46.67 | beat / open palm, at a desk | seated |
| 5 | mx_meeting_desk_m.fbx | Having A Meeting, Male (`c9ca50c4-b96c-11e4-a802-0aaa78deedf9`) | Having A Meeting W/ Another At A Desk | 1400 | 46.67 | beat / open palm, at a desk | seated |
| 6 | mx_ask_table.fbx | Asking Question (`c9c79aea-b96c-11e4-a802-0aaa78deedf9`) | Seated Idle With Hands On A Table | 160 | 5.33 | open palm question, hands on table | seated |
| 7 | mx_rest_table.fbx | Seated Idle (`c9c7972b-b96c-11e4-a802-0aaa78deedf9`) | Seated Idle With Hands On A Table | 131 | 4.37 | rest, hands on table | seated |
| 8 | mx_rest_breathe.fbx | Sitting Idle (`c9ccab1b-b96c-11e4-a802-0aaa78deedf9`) | Sitting With Breathing Idle | 128 | 4.27 | rest | seated |
| 9 | mx_rest_thighs.fbx | Sitting Idle (`c9cb9783-b96c-11e4-a802-0aaa78deedf9`) | Sitting In Chair Hands Resting On Thighs | 191 | 6.37 | rest (hands low) | seated |
| 10 | mx_rest_still.fbx | Sitting Idle (`c9cb95c1-b96c-11e4-a802-0aaa78deedf9`) | Sitting Still In A Chair | 89 | 2.97 | rest | seated |
| 11 | mx_point_seated.fbx | Pointing (`c9c78d87-b96c-11e4-a802-0aaa78deedf9`) | Pointing While Seated | 110 | 3.67 | deictic | seated |
| 12 | mx_point_seated_fwd.fbx | Sitting And Pointing (`c9c914f6-b96c-11e4-a802-0aaa78deedf9`) | Sitting And Pointing Forward | 90 | 3.0 | point_viewer / press | seated |
| 13 | mx_thumbs_seated.fbx | Sitting Thumbs Up (`c9c7f29d-b96c-11e4-a802-0aaa78deedf9`) | Giving Thumbs Up While Sitting | 103 | 3.43 | place / approval | seated |
| 14 | mx_laugh_seated.fbx | Sitting Laughing (`c9c70079-b96c-11e4-a802-0aaa78deedf9`) | Sitting While Laughing | 249 | 8.3 | delight (payoff) | seated |
| 15 | mx_talk_general.fbx | Talking (`c9c88301-b96c-11e4-a802-0aaa78deedf9`) | General Conversation | 312 | 10.4 | beat / conversational base | standing (upper body) |
| 16 | mx_talk_watercooler.fbx | Talking At Watercooler (`c9c9f1c9-b96c-11e4-a802-0aaa78deedf9`) | Having A Chat At The Watercooler | 1336 | 44.53 | beat / conversational base | standing (upper body) |
| 17 | mx_argue_a.fbx | Standing Arguing (`c9cd7855-b96c-11e4-a802-0aaa78deedf9`) | Standing And Arguing With Another Person | 623 | 20.77 | beat (high energy) | standing (upper body) |
| 18 | mx_argue_b.fbx | Standing Arguing (`c9cd7919-b96c-11e4-a802-0aaa78deedf9`) | Standing Arguing With Another Person | 623 | 20.77 | beat (high energy) | standing (upper body) |
| 19 | mx_ask_question.fbx | Talking (`c9c6de72-b96c-11e4-a802-0aaa78deedf9`) | Asking A Question | 170 | 5.67 | open palm | standing (upper body) |
| 20 | mx_ask_one_hand.fbx | Talking (`c9c6ffbe-b96c-11e4-a802-0aaa78deedf9`) | Asking A Question With One Hand | 118 | 3.93 | open palm (one hand) | standing (upper body) |
| 21 | mx_ask_two_hands.fbx | Talking (`c9c6fd7b-b96c-11e4-a802-0aaa78deedf9`) | Asking A Question With Two Hands | 118 | 3.93 | open palm both / size | standing (upper body) |
| 22 | mx_talk_funny.fbx | Talking (`c9c6ddb2-b96c-11e4-a802-0aaa78deedf9`) | Talking Finding Something Funny | 170 | 5.67 | delight / beat | standing (upper body) |
| 23 | mx_happy_hand.fbx | Happy Hand Gesture (`c9c91ba2-b96c-11e4-a802-0aaa78deedf9`) | Happy Forward Hand Gesture | 88 | 2.93 | open palm / release | standing (upper body) |
| 24 | mx_two_hand_forward.fbx | Hands Forward Gesture (`c9c90a7c-b96c-11e4-a802-0aaa78deedf9`) | Two Handed Forward Gesture | 92 | 3.07 | size / two-hand present | standing (upper body) |
| 25 | mx_acknowledge.fbx | Acknowledging (`c9c91c6e-b96c-11e4-a802-0aaa78deedf9`) | Acknowledging Gesture | 57 | 1.9 | beat / place | standing (upper body) |
| 26 | mx_arm_to_side.fbx | Arm Gesture (`c9c922a9-b96c-11e4-a802-0aaa78deedf9`) | Gesturing With Arm To The Side | 102 | 3.4 | deictic to the side / sweep | standing (upper body) |
| 27 | mx_reach_out.fbx | Reaching Out (`c9ce7dba-b96c-11e4-a802-0aaa78deedf9`) | Reaching Out Gesture | 120 | 4.0 | open palm to viewer | standing (upper body) |
| 28 | mx_shrug.fbx | Shrugging (`c9c69537-b96c-11e4-a802-0aaa78deedf9`) | Shoulder Shrug | 66 | 2.2 | release / wave_off | standing (upper body) |
| 29 | mx_count_five.fbx | Counting (`c9c6db74-b96c-11e4-a802-0aaa78deedf9`) | Counting To Five On One Hand | 153 | 5.1 | count | standing (upper body) |
| 30 | mx_point_bent.fbx | Pointing (`c9c6947c-b96c-11e4-a802-0aaa78deedf9`) | Pointing With Arm Bent | 82 | 2.73 | deictic / raise_finger | standing (upper body) |
| 31 | mx_point_thumb.fbx | Pointing (`c9c693bf-b96c-11e4-a802-0aaa78deedf9`) | Pointing Behind With Thumb | 107 | 3.57 | deictic behind (thumb) | standing (upper body) |
| 32 | mx_secret_lean.fbx | Telling A Secret (`c9c6f90e-b96c-11e4-a802-0aaa78deedf9`) | Telling A Secret | 293 | 9.77 | lean-in (conspiratorial hook) | standing (upper body) |
| 33 | mx_nod_yes.fbx | Head Nod Yes (`c9c90d7b-b96c-11e4-a802-0aaa78deedf9`) | Nodding Head Yes | 77 | 2.57 | head nod | standing (head/neck only) |
| 34 | mx_nod_thoughtful.fbx | Thoughtful Head Nod (`c9c91939-b96c-11e4-a802-0aaa78deedf9`) | Thoughtfully Nodding Head Yes | 87 | 2.9 | head nod | standing (head/neck only) |
| 35 | mx_agree_yes.fbx | Agreeing (`c9c91ec4-b96c-11e4-a802-0aaa78deedf9`) | Agreeing Yes | 54 | 1.8 | head nod + small beat | standing (upper body) |

Gaps in Mixamo: no explicit "small vs big" two-hand size, no press / release / pinch. Plan: take the nearest
takes (two_hand_forward, ask_two_hands) and make the size/press/release variants as edited derivatives of the
licensed clips (the licence covers modification), tagged `derived_from`.
