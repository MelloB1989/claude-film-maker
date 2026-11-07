# Acting sheets (round 7: performance)

The operator rejected her Netflix v2b on acting: a flat face (mouth-only solves), hands clasped and upper arms pinned to
the torso (00:44), her right upper arm into her breast, and the waist fit. This is the director's sheet the face
(agent-04) and body (agent-01, agent-10) builds follow, line by line. `acting.py` writes it from the VO alignment
(`acting/<who>.json` is the machine copy, with every time in seconds and frames); re-run it after a VO change.

**Smiles:** a warm base (0.2-0.4) all the way through; FULL Duchenne (>= 0.8: cheeks up, eyes squint) only on the
five payoffs; mid-line smiles 0.4-0.6, varied in shape and asymmetry. Confident, not giddy. **Gestures:** the
amplitude varies (`amp` 0-1: small 0.3, medium 0.55, big 0.85), and the HELD strokes keep the shape after the stroke
for `hold_s` before retracting: deliberate, confident.

**Gesture space (side A review):** the apex of every stroke sits chest-to-collarbone in front of the torso, never at
desk height: in `CAM_MCU` the frame's bottom edge is about her bust line, so medium/big strokes peak at the sternum or
higher and the hands sit in the frame's lower third; beats can be lower but stay in frame; in `CAM_CU` the key strokes
rise to the collarbone. Each gesture carries its `apex_height`; each on-camera line its `hands_in_frame_min` (at least
one hand fully in frame: MCU/MCU_L 0.6, CU 0.3, WIDE 1.0 of the speaking frames). The high rest is hands together at
bust height, in frame.

**Staging, for every line:** hands off the body and above the desk while she speaks, rest (hands loosely together,
forearms on the desk edge) only in the pauses; elbows out so the upper arms clear the torso and breasts by >= 3 cm;
shoulders back and down, chest open, 4-8° forward lean on emphasis; the shoulders and torso move with every gesture.
The mic is on HER LEFT: big gestures are the right hand, or both hands in front of the sternum inside the shoulder
line, never past her left shoulder line; the left hand alone only small and low. The graphic panel (`CAM_MCU_L`) is on
frame right = her left: a deictic to it is the right hand across the body, open palm, chest height, stopping ~15 cm
left of the sternum, under the mic head, the head and eyes turning ~10° with it and straight back to the lens. Off-camera
lines (graphics full frame) keep her alive for continuity: the next on-camera shot can open mid-gesture.

## Her (Netflix, Tripti)

Arc: hook = **curiosity**, body = **confident clarity**, payoff = **satisfied delight**. Times are seconds on the VO clock (t 0 = sequence frame 0); `f` is the 24 fps frame.

**Before the first word (0-0.75 s):** Already alive when the cut opens: a soft closed-mouth smile building, a small head tilt to her right (4 deg), an inhale with the shoulders rising 1 cm, hands loosely together at bust height in front of her (fingertips touching, elbows out), already in the bottom of the MCU frame, not on the desk. A small lean in from 0.4 s.

### N01  0.75-3.94 s  ·  CAM_MCU

> Netflix has over three hundred million paying members.

- **curious, conspiratorial warmth: 'you'll like this'**, intensity 0.75 (hook: curiosity); base smile 0.25, brows 0.1
- **Face:** brow flash on *Netflix* 0.75 s (f18); brow one R on *over* 1.77 s (f43) (the conspiratorial one brow); tilt R 6° on *over* 1.77 s (f43); nod on *million* 2.69 s (f65); smile 0.5 (lopsided R, closed) on *million* 2.69 s (f65); smile 0.85 on *members.* 3.47 s (f83) (full Duchenne (payoff 1/5): cheeks up, eyes squint)
- **Gestures:** open palm [R, small 0.3, to camera] stroke on *Netflix* 0.75 s (f18), apex at the bust, prep from 0.45: palm up and slightly out, chest height, presenting; size [both, big 0.85, to front] HELD 0.6 s stroke on *million* 2.69 s (f65), apex at the upper chest, prep from 1.92 (from *three*): hands start 15 cm apart in front of her sternum on 'three', spread to shoulder width on 'million': a huge number; L hand stays below the mic; beat [R, small 0.3, to camera] stroke on *paying* 3.10 s (f74), apex at the bust, prep from 2.79
- **Lean:** 7° on *over* 1.77 s, 4° on *members.* 3.47 s

### N02  4.25-5.75 s  ·  CAM_CU

> Hit play, and it just starts.

- **delight, easy confidence: the magic moment**, intensity 0.8 (hook: curiosity); base smile 0.4, brows 0.1
- **Face:** brow flash on *Hit* 4.25 s (f102); smile 0.9 on *starts.* 5.47 s (f131) (Duchenne, squint); nod on *starts.* 5.47 s (f131)
- **Gestures:** press [R, small 0.3, to camera] stroke on *play,* 4.54 s (f109), apex at the upper chest, prep from 4.24: index finger presses an imaginary play button toward the lens, collarbone height so it enters the CU; release [both, medium 0.55, to front] stroke on *starts.* 5.47 s (f131), apex at the collarbone, prep from 5.17: fingers spring open outward, 'ta-da', shoulders lift
- **Lean:** 6° on *Hit* 4.25 s, 3° on *starts.* 5.35 s

### N03  6.04-7.81 s  ·  None

> But the video doesn't come from the cloud.

- **intrigue, a twist**, intensity 0.7 (hook: curiosity); base smile 0.15, brows 0.15
- **Face:** brow one R on *But* 6.04 s (f145); shake on *doesn't* 6.68 s (f160) (a small head shake, 2 deg); smile soft 0.5 on *cloud.* 7.48 s (f180) (a knowing half smile)
- **Gestures:** raise finger [R, small 0.3, to up] stroke on *But* 6.04 s (f145), apex at the bust, prep from 5.74: 'wait a second'; wave off [R, medium 0.55, to her right, up] stroke on *cloud.* 7.48 s (f180), apex at the sternum, prep from 7.18: a light palm-down wave away to her right
- **Lean:** 6° on *But* 6.04 s, 3° on *cloud.* 7.48 s

### N04  8.54-12.56 s  ·  CAM_MCU

> Netflix builds its own servers, called Open Connect Appliances.

- **confident clarity with insider pride**, intensity 0.7 (body: confident clarity); base smile 0.25, brows 0.05
- **Face:** brow flash on *own* 9.57 s (f230); nod on *servers,* 9.85 s (f236); smile 0.5 (closed, proud) on *called* 10.72 s (f257); brow flash on *Open* 11.11 s (f267); nod on *Appliances.* 12.07 s (f290)
- **Gestures:** place [both, medium 0.55, to front] HELD 0.5 s stroke on *builds* 9.06 s (f218), apex at the sternum, prep from 8.76: palms facing, shoulder width, setting a box down in front of her on 'builds', firm on 'servers'; open palm [R, small 0.3, to camera] stroke on *own* 9.57 s (f230), apex at the bust, prep from 9.28; beat [R, small 0.3, to camera] stroke on *Open* 11.11 s (f267), apex at the bust, prep from 10.81; beat [R, small 0.3, to camera] stroke on *Appliances.* 12.07 s (f290), apex at the bust, prep from 11.77: two descending beats, the naming
- **Lean:** 6° on *own* 9.57 s, 4° on *Appliances.* 11.80 s

### N05  12.83-16.56 s  ·  off camera (graphic `oca`): continuity only

> Internet providers get them free, inside their own networks.

- **generous surprise**, intensity 0.65 (body: confident clarity); base smile 0.3, brows 0.1
- **Face:** brow flash on *free,* 14.35 s (f344); smile 0.5 (open lips) on *free,* 14.35 s (f344); nod on *networks.* 16.15 s (f388)
- **Gestures:** open palm [R, medium 0.55, to camera] stroke on *free,* 14.35 s (f344), apex at the sternum, prep from 14.05: offering; sweep [both, medium 0.55, to front] stroke on *inside* 15.02 s (f360), apex at the sternum, prep from 14.72: hands circle a space in front of her
- **Lean:** 5° on *free,* 14.35 s

### N06  17.29-20.87 s  ·  CAM_MCU_L

> Every night, Netflix predicts what your area will watch.

- **curious, clever: a neat trick**, intensity 0.75 (body: confident clarity); base smile 0.3, brows 0.1
- **Face:** brow flash on *Every* 17.29 s (f415) (the bar names this one); glance on *Every* 17.29 s (f415) (agent-04's THINK beat; back on the lens by 'Netflix'); smile 0.45 (sly, lopsided R) on *predicts* 18.83 s (f452) (sly); tilt L 5° on *area* 19.70 s (f473) (toward the panel); nod on *watch.* 20.50 s (f492)
- **Gestures:** deictic [R, medium 0.55, to panel (her left)] HELD 0.7 s stroke on *Every* 17.29 s (f415), apex at the sternum, prep from 16.99: introduces the panel: cross-body open palm, chest height, stops 15 cm left of the sternum, under the mic head; head and eyes turn 10 deg with it, back by 'Netflix'; open palm [R, medium 0.55, to front] stroke on *predicts* 18.83 s (f452), apex at the sternum, prep from 18.53: a small circle, palm up: a crystal ball; point viewer [R, small 0.3, to camera] stroke on *your* 19.49 s (f468), apex at the bust, prep from 19.19: open hand toward the lens, not a jabbing finger
- **Lean:** 4° on *Every* 17.29 s, 8° on *your* 19.49 s, 5° on *watch.* 20.50 s

### N07  21.17-22.79 s  ·  CAM_MCU_L

> And copies it to the box near you.

- **satisfied: it's already there**, intensity 0.7 (body: confident clarity); base smile 0.35, brows 0.05
- **Face:** nod on *box* 22.12 s (f531); smile 0.8 on *near* 22.42 s (f538) (Duchenne)
- **Gestures:** carry [both, medium 0.55, to front] stroke on *copies* 21.42 s (f514), apex at the sternum, prep from 21.12: lifts a box from her right and carries it in an arc to the centre front, set down on 'box' (in front of the sternum, never past her left shoulder line); open palm [R, small 0.3, to camera] stroke on *you.* 22.63 s (f543), apex at the bust, prep from 22.33
- **Lean:** 6° on *near* 22.42 s

### N08  23.54-27.20 s  ·  CAM_CU

> Each title is encoded at many sizes and bitrates.

- **explaining, crisp clarity**, intensity 0.7 (body: confident clarity); base smile 0.2, brows 0.1
- **Note:** CU: gestures held high (collarbone to chin) so the hands enter the bottom of the frame; the shoulders carry the rest
- **Face:** glance on *Each* 23.54 s (f565) (agent-04's THINK beat; back on the lens by 'title'); nod on *encoded* 24.82 s (f596); brow flash on *many* 25.52 s (f612); smile 0.45 (lopsided L) on *bitrates.* 26.65 s (f640)
- **Gestures:** size [both, small 0.3, to front] stroke on *many* 25.52 s (f612), apex at the upper chest, prep from 25.22: hands frame a small box on 'many'...; size [both, big 0.85, to front] HELD 0.5 s stroke on *sizes* 25.81 s (f619), apex at the collarbone, prep from 25.51: ...and widen to shoulder width on 'sizes'; ladder [R, medium 0.55, to up] stroke on *bitrates.* 26.65 s (f640), apex at the collarbone, prep from 26.35: flat palm steps up three rungs
- **Lean:** 5° on *many* 25.52 s

### N09  27.50-32.57 s  ·  off camera (graphic `ladder`): continuity only

> A cartoon needs fewer bits than an action film, so each gets its own ladder.

- **playful contrast**, intensity 0.75 (body: confident clarity); base smile 0.35, brows 0.1
- **Face:** smile 0.55 (amused, lopsided L) on *cartoon* 27.64 s (f663); brow flash on *action* 29.54 s (f709); smile soft 0.5 on *each* 31.30 s (f751); nod on *ladder.* 32.21 s (f773)
- **Gestures:** pinch [R, small 0.3, to front] stroke on *fewer* 28.65 s (f688), apex at the bust, prep from 28.35; size [both, big 0.85, to front] stroke on *action* 29.54 s (f709), apex at the upper chest, prep from 29.24; ladder [R, medium 0.55, to up] stroke on *ladder.* 32.21 s (f773), apex at the sternum, prep from 31.91
- **Lean:** 5° on *action* 29.54 s

### N10  33.33-36.04 s  ·  off camera (graphic `abr`): continuity only

> The video is cut into chunks a few seconds long.

- **matter-of-fact clarity**, intensity 0.6 (body: confident clarity); base smile 0.2, brows 0.05
- **Face:** brow flash on *chunks* 34.45 s (f827); nod on *long.* 35.76 s (f858)
- **Gestures:** chop [R, medium 0.55, to front] stroke on *cut* 33.99 s (f816), apex at the sternum, prep from 33.70; size [both, small 0.3, to front] stroke on *few* 35.14 s (f843), apex at the bust, prep from 34.84: a few seconds: hands a short span apart

### N11  36.33-39.61 s  ·  off camera (graphic `abr`): continuity only

> Your player picks the right rung for every chunk.

- **clever, personal**, intensity 0.65 (body: confident clarity); base smile 0.3, brows 0.05
- **Face:** smile 0.45 (closed) on *picks* 37.23 s (f893); nod on *rung* 37.99 s (f912)
- **Gestures:** point viewer [R, small 0.3, to camera] stroke on *Your* 36.33 s (f872), apex at the bust, prep from 36.03; pinch [R, small 0.3, to front] stroke on *picks* 37.23 s (f893), apex at the bust, prep from 36.93
- **Lean:** 6° on *Your* 36.33 s

### N12  39.92-42.95 s  ·  CAM_MCU_L

> Network dips? The next chunk is a little softer.

- **question, then easy reassurance**, intensity 0.8 (body: confident clarity); base smile 0.25, brows 0.1
- **Face:** brow hold on *Network* 39.92 s (f958) (brows up and held through 'dips?', the bar names this one); tilt R 6° on *dips?* 40.46 s (f971); smile 0.55 (closed, reassuring) on *little* 42.11 s (f1011); squint on *softer.* 42.41 s (f1018); nod on *softer.* 42.41 s (f1018)
- **Gestures:** deictic [R, medium 0.55, to panel (her left)] stroke on *dips?* 40.46 s (f971), apex at the sternum, prep from 40.16: flat palm-down hand dips toward the panel (cross-body, chest height, under the mic head); open palm [R, medium 0.55, to camera] stroke on *next* 41.29 s (f991), apex at the sternum, prep from 40.99: it's fine; pinch [R, small 0.3, to camera] HELD 0.6 s stroke on *little* 42.11 s (f1011), apex at the bust, prep from 41.81: thumb and index almost touching
- **Lean:** 2° on *Network* 39.92 s, 6° on *next* 41.29 s

### N13  43.71-48.28 s  ·  CAM_WIDE

> Your login, profile, recommendations: that all runs on AWS.

- **confident, brisk list, then a clean landing**, intensity 0.75 (body: confident clarity); base smile 0.3, brows 0.05
- **Note:** THE 00:44 SHOT (WIDE): the rejected v2b sat here with hands clasped and upper arms pinned into the torso. Elbows 20+ cm off the torso the whole line; the count hand out to her right at chest height; the shoulders and torso turn a little with each count
- **Face:** brow flash on *login,* 44.00 s (f1056); glance on *Your* 43.71 s (f1049) (agent-04's THINK beat, quick); nod on *profile,* 44.58 s (f1070); brow flash on *recommendations:* 45.85 s (f1100); smile 0.85 on *AWS.* 47.61 s (f1143) (Duchenne); nod on *AWS.* 47.61 s (f1143)
- **Gestures:** count [R, medium 0.55, to her right, chest height] stroke on *login,* 44.00 s (f1056), apex at the sternum, prep from 43.70: index up (1); count [R, medium 0.55, to her right, chest height] stroke on *profile,* 44.58 s (f1070), apex at the sternum, prep from 44.28: + middle (2); count [R, medium 0.55, to her right, chest height] HELD 0.5 s stroke on *recommendations:* 45.85 s (f1100), apex at the sternum, prep from 45.55: + ring (3); open palm [both, big 0.85, to front] HELD 0.7 s stroke on *that* 46.55 s (f1117), apex at the sternum, prep from 46.25: palms up, spread to shoulder width: 'all of it'; L hand below and inside the mic line; beat [R, medium 0.55, to camera] stroke on *AWS.* 47.61 s (f1143), apex at the sternum, prep from 47.31
- **Lean:** 4° on *login,* 44.00 s, 8° on *that* 46.55 s, 5° on *AWS.* 47.61 s

### N14  48.58-52.85 s  ·  off camera (graphic `planes`): continuity only

> Press play, and AWS points you to that box. It streams the video.

- **clear, simple mechanics**, intensity 0.65 (body: confident clarity); base smile 0.25, brows 0.05
- **Face:** brow flash on *AWS* 49.59 s (f1190); nod on *box.* 51.07 s (f1226); smile 0.5 (open lips) on *streams* 51.91 s (f1246)
- **Gestures:** press [R, small 0.3, to camera] stroke on *play,* 48.91 s (f1174), apex at the bust, prep from 48.61; deictic [R, medium 0.55, to her right] stroke on *points* 50.24 s (f1206), apex at the sternum, prep from 49.94; open palm [both, medium 0.55, to front] stroke on *streams* 51.91 s (f1246), apex at the sternum, prep from 51.62
- **Lean:** 5° on *points* 50.24 s

### N15  53.62-56.20 s  ·  CAM_MCU

> The cloud decides. The box next door delivers.

- **satisfied clarity: the two halves click**, intensity 0.8 (payoff: satisfied delight); base smile 0.4, brows 0.05
- **Face:** brow flash on *cloud* 53.81 s (f1291); nod on *decides.* 54.25 s (f1302); smile 0.45 (closed) on *box* 54.99 s (f1320); nod on *delivers.* 55.89 s (f1341); smile 0.6 (open lips, building to N16) on *delivers.* 55.89 s (f1341)
- **Gestures:** high low [R, medium 0.55, to up, her right] HELD 0.5 s stroke on *cloud* 53.81 s (f1291), apex at the chin, prep from 53.51: open palm raised to chin height: up there; place [both, medium 0.55, to front] stroke on *box* 54.99 s (f1320), apex at the bust, prep from 54.70: both hands come down to the bust line, still in frame: right here; beat [both, medium 0.55, to front] stroke on *delivers.* 55.89 s (f1341), apex at the sternum, prep from 55.59
- **Lean:** 4° on *cloud* 53.81 s, 7° on *box* 54.99 s

### N16  56.50-57.45 s  ·  CAM_CU

> That's why it just plays.

- **satisfied delight**, intensity 0.9 (payoff: satisfied delight); base smile 0.6, brows 0.05
- **Face:** brow flash on *That's* 56.50 s (f1356); smile 0.9 on *just* 57.00 s (f1368) (the last full Duchenne, held into the cut); tilt R 5° on *plays.* 57.16 s (f1372); nod on *plays.* 57.16 s (f1372)
- **Gestures:** release [both, medium 0.55, to front] HELD 1.0 s stroke on *plays.* 57.16 s (f1372), apex at the collarbone, prep from 56.86: palms up, a small outward 'ta-da', the shoulders lift; held to the cut
- **Lean:** 6° on *That's* 56.50 s, 4° on *plays.* 57.16 s

### The plan against the R7 rows

- smiles 19.4/min (>= 4), brow flashes 20.6/min (>= 6)
- gesture onsets 0.87/s over the speech (0.5-1.2)
- longest planned neutral stretch inside a line 1.41 s (<= 1.5)
- the same gesture twice in a row: none

### The TEST span

- CAM_MCU frames 0-196 (8.17 s, N01 N02 N03): the hook on one camera: curiosity, the one brow, the 'three hundred million' spread, the play press and the 'just starts' Duchenne, then the 'But...' twist
- CAM_WIDE frames 1040-1162 (5.08 s, N13): the rejected 00:44 shot: the count, elbows off the torso, arm-breast clearance, the waist fit
- total 13.25 s. Optional: CAM_MCU 196-305 (N04), append for a literal 'lines 1-4' (+4.5 s, 17.8 s total)

## Him (WhatsApp, Tarun)

Arc: hook = **curiosity**, body = **confident clarity**, payoff = **satisfied delight**. Times are seconds on the VO clock (t 0 = sequence frame 0); `f` is the 24 fps frame.

**Before the first word (0-0.75 s):** Already alive when the cut opens: an easy closed-mouth grin building, a small head tilt to his right (4 deg), an inhale with the shoulders rising 1 cm, hands loosely together at bust height in front of him (fingers loosely laced, elbows out), already in the bottom of the MCU frame, not on the desk. A small lean in from 0.4 s.

### W01  0.75-3.75 s  ·  CAM_MCU

> Every day, WhatsApp moves over a hundred billion messages.

- **curious, friendly: 'guess how many'**, intensity 0.75 (hook: curiosity); base smile 0.3, brows 0.1
- **Face:** brow flash on *Every* 0.75 s (f18); brow one R on *over* 2.28 s (f55); tilt R 5° on *over* 2.28 s (f55); nod on *billion* 2.92 s (f70); smile 0.5 (lopsided R, open lips) on *billion* 2.92 s (f70); smile 0.85 on *messages.* 3.26 s (f78) (full Duchenne (payoff 1/5))
- **Gestures:** open palm [R, small 0.3, to camera] stroke on *Every* 0.75 s (f18), apex at the bust, prep from 0.45; size [both, big 0.85, to front] HELD 0.6 s stroke on *billion* 2.92 s (f70), apex at the upper chest, prep from 2.45 (from *hundred*): hands start 15 cm apart in front of his sternum, spread to shoulder width; L hand below the mic; beat [R, small 0.3, to camera] stroke on *messages.* 3.26 s (f78), apex at the bust, prep from 2.96
- **Lean:** 7° on *over* 2.28 s, 4° on *messages.* 3.26 s

### W02  4.04-6.20 s  ·  off camera (graphic `title`): continuity only

> And almost none of them stay on its servers.

- **intrigue, the twist**, intensity 0.7 (hook: curiosity); base smile 0.2, brows 0.15
- **Face:** brow one L on *almost* 4.48 s (f108); shake on *none* 4.88 s (f117); smile soft 0.45 on *servers.* 5.77 s (f139)
- **Gestures:** pinch [R, small 0.3, to front] stroke on *almost* 4.48 s (f108), apex at the bust, prep from 4.18; wave off [R, medium 0.55, to her right, low] stroke on *none* 4.88 s (f117), apex at the sternum, prep from 4.58: palm-down sweep out to his right: none
- **Lean:** 6° on *almost* 4.48 s

### W03  6.50-7.07 s  ·  CAM_CU

> Here's how.

- **conspiratorial delight: 'let me show you'**, intensity 0.8 (hook: curiosity); base smile 0.4, brows 0.1
- **Note:** CU, half a second of speech: the face carries it; the hands only enter at the bottom of the frame
- **Face:** brow flash on *Here's* 6.50 s (f156); smile 0.85 on *how.* 6.86 s (f165) (full Duchenne (payoff 2/5)); nod on *how.* 6.86 s (f165)
- **Gestures:** open palm [both, small 0.3, to camera] HELD 0.5 s stroke on *how.* 6.86 s (f165), apex at the upper chest, prep from 6.56: palms up, collarbone height: here it is
- **Lean:** 7° on *Here's* 6.50 s

### W04  7.83-11.23 s  ·  CAM_MCU_L

> Open the app, and your phone keeps one connection open to WhatsApp.

- **clear, friendly walkthrough**, intensity 0.7 (body: confident clarity); base smile 0.3, brows 0.05
- **Face:** brow flash on *Open* 7.83 s (f188); smile 0.45 (closed) on *phone* 9.10 s (f218); nod on *connection* 10.10 s (f242); tilt L 5° on *WhatsApp.* 10.91 s (f262) (toward the panel)
- **Gestures:** press [R, small 0.3, to front] stroke on *app,* 8.31 s (f199), apex at the bust, prep from 8.01: a thumb tap on an imaginary phone; raise finger [R, small 0.3, to up] stroke on *one* 9.72 s (f233), apex at the bust, prep from 9.43: one finger: one; deictic [R, medium 0.55, to panel (his left)] HELD 0.7 s stroke on *connection* 10.10 s (f242), apex at the sternum, prep from 9.80: draws the line from his chest toward the panel: cross-body, chest height, stops 15 cm left of the sternum under the mic head
- **Lean:** 6° on *your* 8.96 s

### W05  11.54-15.06 s  ·  off camera (graphic `erlang`): continuity only

> On the server, each connection is its own tiny Erlang process.

- **fascinated, nerdy delight**, intensity 0.65 (body: confident clarity); base smile 0.3, brows 0.05
- **Face:** tilt L 4° on *each* 12.55 s (f301); brow flash on *tiny* 13.83 s (f332); smile soft 0.5 on *Erlang* 14.21 s (f341); nod on *process.* 14.55 s (f349)
- **Gestures:** place [both, medium 0.55, to front] stroke on *server,* 11.88 s (f285), apex at the sternum, prep from 11.58; pinch [R, small 0.3, to front] HELD 0.5 s stroke on *tiny* 13.83 s (f332), apex at the bust, prep from 13.53; beat [R, small 0.3, to camera] stroke on *process.* 14.55 s (f349), apex at the bust, prep from 14.25
- **Lean:** 5° on *tiny* 13.83 s

### W06  15.33-17.19 s  ·  off camera (graphic `erlang`): continuity only

> One server once held two million of them.

- **impressed: a big number**, intensity 0.75 (body: confident clarity); base smile 0.3, brows 0.1
- **Face:** brow flash on *two* 16.37 s (f393); smile 0.55 (open lips) on *million* 16.55 s (f397); nod on *them.* 17.02 s (f408)
- **Gestures:** raise finger [R, small 0.3, to up] stroke on *One* 15.33 s (f368), apex at the bust, prep from 15.03; size [both, big 0.85, to front] stroke on *million* 16.55 s (f397), apex at the upper chest, prep from 16.22 (from *two*)
- **Lean:** 6° on *two* 16.37 s

### W07  17.96-19.86 s  ·  CAM_WIDE

> You hit send. Is your friend online?

- **playful question**, intensity 0.75 (body: confident clarity); base smile 0.3, brows 0.1
- **Note:** WIDE: elbows 20+ cm off the torso, hands up the whole line (the same fix as her 00:44 shot)
- **Face:** smile soft 0.4 on *You* 17.96 s (f431); brow flash on *send.* 18.39 s (f441); glance on *Is* 18.86 s (f453) (agent-04's THINK beat); brow hold on *friend* 19.19 s (f461); tilt R 6° on *online?* 19.48 s (f467)
- **Gestures:** point viewer [R, small 0.3, to camera] stroke on *You* 17.96 s (f431), apex at the lower chest, prep from 17.66: open hand; press [R, medium 0.55, to front] stroke on *send.* 18.39 s (f441), apex at the sternum, prep from 18.09: a thumb press, crisp; open palm [both, medium 0.55, to front] stroke on *online?* 19.59 s (f470), apex at the sternum, prep from 19.29: palms up, a small shrug: well, is he?
- **Lean:** 6° on *You* 17.96 s, 3° on *online?* 19.48 s

### W08  20.17-21.94 s  ·  off camera (graphic `store`): continuity only

> Then it goes straight down their connection.

- **simple, direct**, intensity 0.6 (body: confident clarity); base smile 0.25, brows 0.05
- **Face:** brow flash on *straight* 20.72 s (f497); nod on *connection.* 21.59 s (f518)
- **Gestures:** sweep [R, medium 0.55, to front, down] stroke on *straight* 20.72 s (f497), apex at the sternum, prep from 20.42: a flat hand slides straight forward
- **Lean:** 5° on *straight* 20.72 s

### W09  22.25-25.21 s  ·  off camera (graphic `store`): continuity only

> If not, it waits. And once it's delivered, it's deleted.

- **patient, then a tidy satisfaction**, intensity 0.7 (body: confident clarity); base smile 0.25, brows 0.05
- **Face:** brow one R on *not,* 22.47 s (f539); tilt L 4° on *waits.* 23.04 s (f553); nod on *delivered,* 24.26 s (f582); smile 0.55 (closed) on *deleted.* 24.93 s (f598)
- **Gestures:** wave off [R, small 0.3, to her right] stroke on *not,* 22.47 s (f539), apex at the bust, prep from 22.17; open palm [R, small 0.3, to camera] HELD 0.5 s stroke on *waits.* 23.04 s (f553), apex at the bust, prep from 22.74: palm out: it waits; chop [R, medium 0.55, to front] stroke on *deleted.* 24.93 s (f598), apex at the sternum, prep from 24.63: a crisp wipe: gone
- **Lean:** 5° on *once* 23.74 s

### W10  25.96-28.28 s  ·  CAM_MCU_L

> Your ticks? One: the server has it.

- **playful, knowing: everyone wonders this**, intensity 0.75 (body: confident clarity); base smile 0.3, brows 0.1
- **Face:** glance on *Your* 25.96 s (f623) (agent-04's THINK beat, toward the ticks); brow hold on *ticks?* 26.23 s (f629); smile 0.45 (lopsided L) on *server* 27.61 s (f663); nod on *it.* 28.19 s (f676)
- **Gestures:** deictic [R, medium 0.55, to panel (his left)] HELD 0.5 s stroke on *ticks?* 26.23 s (f629), apex at the sternum, prep from 25.93: cross-body open palm toward the ticks, under the mic head; count [R, medium 0.55, to his right, chest height] stroke on *One:* 26.95 s (f647), apex at the sternum, prep from 26.64: index up (1), the hand back on his right; beat [R, small 0.3, to camera] stroke on *has* 27.97 s (f671), apex at the bust, prep from 27.67
- **Lean:** 5° on *Your* 25.96 s

### W11  28.58-31.68 s  ·  CAM_MCU_L

> Two: it reached their phone. Blue: they've read it.

- **building to a little reveal**, intensity 0.8 (body: confident clarity); base smile 0.3, brows 0.05
- **Face:** nod on *phone.* 29.87 s (f717); brow flash on *Blue:* 30.52 s (f733); smile 0.85 on *read* 31.40 s (f754) (full Duchenne (payoff 3/5): the blue ticks)
- **Gestures:** count [R, medium 0.55, to his right, chest height] stroke on *Two:* 28.58 s (f686), apex at the sternum, prep from 28.28: + middle (2); deictic [R, medium 0.55, to panel (his left)] HELD 0.5 s stroke on *Blue:* 30.52 s (f733), apex at the sternum, prep from 30.22: the two fingers turn toward the panel's blue ticks; open palm [R, small 0.3, to camera] stroke on *read* 31.40 s (f754), apex at the bust, prep from 31.10
- **Lean:** 7° on *Blue:* 30.52 s

### W12  32.42-35.88 s  ·  off camera (graphic `group`): continuity only

> In a group, your phone encrypts once. The server fans it out to everyone.

- **clever efficiency**, intensity 0.7 (body: confident clarity); base smile 0.3, brows 0.05
- **Face:** brow flash on *once.* 33.75 s (f810); nod on *once.* 33.75 s (f810); smile 0.5 (open lips) on *everyone.* 35.39 s (f849)
- **Gestures:** raise finger [R, small 0.3, to up] HELD 0.5 s stroke on *once.* 33.75 s (f810), apex at the bust, prep from 33.45; sweep [both, big 0.85, to front] stroke on *fans* 34.72 s (f833), apex at the upper chest, prep from 34.42: both hands fan out from the centre
- **Lean:** 5° on *once.* 33.75 s

### W13  36.62-38.58 s  ·  CAM_CU

> And the server can't read a word of it.

- **reassuring, a little conspiratorial**, intensity 0.8 (body: confident clarity); base smile 0.3, brows 0.05
- **Note:** CU: the 'no' is the face and a small hand at the bottom of the frame
- **Face:** brow hold on *can't* 37.40 s (f898); shake on *can't* 37.40 s (f898); smile 0.6 (closed, knowing) on *word* 37.99 s (f912)
- **Gestures:** wave off [R, small 0.3, to camera] stroke on *can't* 37.40 s (f898), apex at the upper chest, prep from 37.10: palm out, a small side-to-side 'no'; beat [R, small 0.3, to camera] stroke on *word* 37.99 s (f912), apex at the upper chest, prep from 37.70
- **Lean:** 6° on *And* 36.62 s

### W14  38.88-41.16 s  ·  off camera (graphic `e2e`): continuity only

> The Signal protocol keeps the keys on your phones.

- **confident trust**, intensity 0.7 (body: confident clarity); base smile 0.3, brows 0.05
- **Face:** brow flash on *Signal* 39.06 s (f937); smile 0.5 (closed) on *keys* 40.28 s (f967); nod on *phones.* 40.76 s (f978)
- **Gestures:** open palm [R, small 0.3, to camera] stroke on *Signal* 39.06 s (f937), apex at the bust, prep from 38.76; point viewer [R, small 0.3, to camera] stroke on *your* 40.63 s (f975), apex at the bust, prep from 40.33
- **Lean:** 5° on *your* 40.63 s

### W15  41.92-46.34 s  ·  CAM_MCU_L

> Photos go to a blob store, encrypted. Only the key rides in the message.

- **clear, a neat detail**, intensity 0.7 (body: confident clarity); base smile 0.25, brows 0.05
- **Face:** glance on *Photos* 41.92 s (f1006) (agent-04's THINK beat, with the deictic); brow flash on *blob* 42.85 s (f1028); nod on *encrypted.* 43.82 s (f1052); brow flash on *Only* 44.67 s (f1072); smile 0.5 (lopsided R) on *key* 45.12 s (f1083)
- **Gestures:** deictic [R, small 0.3, to panel (his left)] stroke on *Photos* 41.92 s (f1006), apex at the bust, prep from 41.62: cross-body, under the mic head; place [both, medium 0.55, to front] HELD 0.5 s stroke on *store,* 43.17 s (f1036), apex at the sternum, prep from 42.87: sets a box down in front of him; pinch [R, small 0.3, to camera] HELD 0.6 s stroke on *Only* 44.67 s (f1072), apex at the bust, prep from 44.37: just the key: thumb and index; open palm [R, small 0.3, to front] stroke on *message.* 45.96 s (f1103), apex at the bust, prep from 45.66
- **Lean:** 6° on *Only* 44.67 s

### W16  47.08-52.01 s  ·  CAM_MCU

> Tiny processes. Messages that don't linger. Keys that never leave your hands.

- **satisfied, the three ideas land**, intensity 0.8 (payoff: satisfied delight); base smile 0.35, brows 0.05
- **Face:** brow flash on *Tiny* 47.08 s (f1130); nod on *processes.* 47.55 s (f1141); brow flash on *Messages* 48.63 s (f1167); shake on *don't* 49.29 s (f1183); smile 0.5 (open lips) on *linger.* 49.57 s (f1190); brow flash on *Keys* 50.33 s (f1208); smile 0.85 on *hands.* 51.58 s (f1238) (full Duchenne (payoff 4/5)); nod on *hands.* 51.58 s (f1238)
- **Gestures:** count [R, small 0.3, to his right, chest height] stroke on *Tiny* 47.08 s (f1130), apex at the bust, prep from 46.78: index (1); count [R, medium 0.55, to his right, chest height] stroke on *Messages* 48.63 s (f1167), apex at the sternum, prep from 48.33: + middle (2); count [R, medium 0.55, to his right, chest height] HELD 0.5 s stroke on *Keys* 50.33 s (f1208), apex at the sternum, prep from 50.03: + ring (3); open palm [both, medium 0.55, to front] HELD 0.6 s stroke on *hands.* 51.58 s (f1238), apex at the sternum, prep from 51.28: both palms up, showing his hands: literal
- **Lean:** 4° on *Tiny* 47.08 s, 7° on *Keys* 50.33 s

### W17  52.29-54.30 s  ·  CAM_CU

> That's over a hundred billion messages a day.

- **satisfied delight, the bookend**, intensity 0.9 (payoff: satisfied delight); base smile 0.55, brows 0.05
- **Face:** brow flash on *That's* 52.29 s (f1255); smile 0.9 on *billion* 53.27 s (f1278) (full Duchenne (payoff 5/5), held into the cut); tilt R 5° on *day.* 54.13 s (f1299); nod on *day.* 54.13 s (f1299)
- **Gestures:** size [both, medium 0.55, to front] stroke on *billion* 53.27 s (f1278), apex at the collarbone, prep from 52.81 (from *hundred*): the hook's spread again, smaller (CU); release [both, small 0.3, to front] HELD 1.0 s stroke on *day.* 54.13 s (f1299), apex at the upper chest, prep from 53.83: palms open, held to the cut
- **Lean:** 6° on *That's* 52.29 s

### The plan against the R7 rows

- smiles 19.7/min (>= 4), brow flashes 28.9/min (>= 6)
- gesture onsets 0.94/s over the speech (0.5-1.2)
- longest planned neutral stretch inside a line 1.18 s (<= 1.5)
- the same gesture twice in a row: none

### The TEST span

- CAM_MCU frames 0-179 (7.46 s, W01 W02 W03): his hook on one camera: the 'hundred billion' spread, the one brow, the twist and 'Here's how'
- CAM_WIDE frames 422-480 (2.42 s, W07): his WIDE: hands up, elbows off the torso, the playful question
- total 9.88 s. Optional: CAM_MCU 179-273 (W04), append for the first panel deictic (+3.9 s)
