"""Timeless v3: the edit decision list. Same footage, song, cuts and voice as v2; new camera and transitions.

The user on v2: "the transitions are not smooth at all, also the transitions are simple, something more 3d crazy would be
nice. use best of blender and effectcraft. everything must be mesmerising. it has to be perfect."
v3 moves the camera and every transition into one Blender 3D stage (each shot is a card in 3D space, one camera, real
motion blur), and EffectCraft does the finishing (grade, lens FX, glow, 2D titles). EDIT.md explains the intent.

Run `python films/timeless/amv3/edl.py` to write edl.json next to this file. Change the edit here, never in edl.json.
Frames are comp frames at 30 fps, [a, b) half-open. Source times are seconds in the clip's own timeline
(handover footage_clips/clip_<ID>.mp4, 1080p60; $AMV2_DATA/src240/clip_<ID>.mp4 = RIFE 240 fps, same timeline).
"""
import json
import os

FPS, W, H, DUR = 30, 1920, 1080, 900
HANDLE = 16  # plate frames rendered before a and after b, so transitions can show a shot outside [a, b)
CLIPS = "/home/nikhil/code/film-making/handover/amv_handover/footage_clips"
SONG = "/home/nikhil/code/film-making/handover/amv_handover/audio/timeless_full.wav"
VOICE = "/home/nikhil/code/film-making/handover/amv_handover/audio/voice"
SFX = "/home/nikhil/code/film-making/handover/amv_handover/project/sfx"

ACTS = [
    dict(id="tobey", f0=0, f1=252, earth="EARTH-96283", name="TOBEY MAGUIRE", years="2002 - 2007",
         look="nostalgia: warm gold highlights, deep teal shadows, soft bloom", leak="warm_gold",
         motion="floating: long eased drifts, transitions 12-16 f, light leaks, nothing snaps"),
    dict(id="andrew", f0=252, f1=480, earth="EARTH-120703", name="ANDREW GARFIELD", years="2012 - 2014",
         look="electric: cool cyan/blue, sunset amber accents, crisp contrast, cyan bloom", leak="cyan_amber",
         motion="rising: rolls, dives and a cube; transitions tighten 14 -> 10 f into the drop"),
    dict(id="tom", f0=480, f1=819, earth="EARTH-199999", name="TOM HOLLAND", years="2016 - 2026",
         look="impact: rich red/orange vs steel blue, punchy contrast, hard highlights", leak="red_orange",
         motion="hard: zoom-throughs and whips on every hit, 8-11 f, punches and shakes inside shots"),
    dict(id="outro", f0=819, f1=900, look="3D SAU_EDITZ outro (Blender)"),
]

# ---------------------------------------------------------------------------------------------------------------------
# SHOTS. speed: const | velocity (fast-slow-fast) | land (fast -> slow) | launch (slow -> fast) | reverse (src0 > src1).
# focus: [x, y] clip pixels that zooms centre on (eye, lens) at the shot's first frame; None = frame centre. The
#   moving point per frame is $AMV3_DATA/tracks/<id>.json (tracks.py); use the track, not this seed, when it exists.
# move: the HOLD intent between transitions. The stage solves each hold as a C1 curve that starts with the incoming
#   transition's exit velocity and ends with the outgoing transition's entry velocity, so the camera never stops.
#   drift: "in" (slow push) | "out" (slow pull) | "auto" (whatever joins the two transitions without a reversal)
#   roll: degrees of camera roll drift over the hold; pan: [dx, dy] picture pixels of drift over the hold
#   depth: 0..1, 2.5D parallax from the depth map during the hold (a "3D photo" dolly); 0 = flat card
# fx: hits inside the shot, handled by the stage camera: punch@F (scale kick +7 % in 2 f, settles in 6 f),
#   shake@F (decaying 3D camera shake, 8 f), letterbox (finishing), source_cut@F (the clip's own cut lands on F).
S = []


def shot(id, clip, a, b, src, speed="const", focus=None, move=None, fx=(), note=""):
    m = dict(drift="auto", roll=0.0, pan=[0, 0], depth=0.0)
    m.update(move or {})
    S.append(dict(id=id, clip=clip, file=f"{CLIPS}/clip_{clip}.mp4", a=a, b=b, src=list(src), speed=speed,
                  focus=list(focus) if focus else None, move=m, fx=list(fx), note=note))


# ---------------- ACT I  TOBEY  (guitar intro, f0-252)
shot("S01", "T01_mask_night", 0, 50, (0.05, 0.75), "const", (975, 445),
     dict(drift="out", roll=-2.0, depth=0.35), [], "opens out of black: the camera pulls back through the dark with depth parallax")
shot("S02", "T02_mask_off", 50, 83, (0.08, 0.66), "land", None, dict(drift="out", roll=1.5), [], "the unmasking")
shot("S03", "T03_glove_city", 83, 118, (0.15, 0.85), "const", (920, 560), dict(drift="in", pan=[-40, 0], depth=0.3), [],
     "TOBEY MAGUIRE name card + EARTH-96283 caption")
shot("S04", "T04_flowers", 118, 151, (0.10, 0.90), "const", None, dict(drift="in", roll=-1.5), [], "gold bokeh")
shot("S05", "T05_black_lens", 151, 175, (0.15, 0.95), "const", (1029, 510), dict(drift="out", roll=2.0), [],
     "black suit: emerges from the symbiote goo")
shot("S06", "T06_bully_smirk", 175, 201, (0.10, 0.95), "land", None, dict(drift="in"), [], "Bully Maguire smirk")
shot("S07", "T07_train", 201, 235, (0.30, 0.85), "velocity", None, dict(drift="out", depth=0.25), ["shake@201"],
     "arms out against the train")
shot("S08", "T08_eye_dive", 235, 252, (0.05, 0.75), "const", (901, 390), dict(drift="in"), [],
     "push into the left iris: the iris becomes the multiverse tunnel")

# ---------------- ACT II  ANDREW  (build, f252-480)
shot("S09", "A01_lens_pullout", 252, 300, (4.45, 0.40), "land", (1036, 546), dict(drift="out", roll=3.0), [],
     "out of the tunnel through Andrew's lens, pulling out over the night city; WHO ARE YOU?")
shot("S10", "A03_sunset_mask", 300, 336, (0.02, 0.70), "const", (860, 440), dict(drift="in", depth=0.3), [],
     "3D AMAZING assembles behind his head; ANDREW GARFIELD / EARTH-120703")
shot("S11", "A02_freefall", 336, 369, (0.05, 1.30), "velocity", None, dict(drift="in", roll=-4.0), [],
     "freefall past the Empire State (we dive into it through the AMAZING letters)")
shot("S12", "A04_bridge_flip", 369, 400, (0.05, 1.25), "velocity", None, dict(drift="out", roll=3.0), [],
     "flip under the bridge (the cube turns with the flip)")
shot("S13", "A05_topdown_fall", 400, 416, (0.05, 0.75), "launch", None, dict(drift="in"), [], "top-down dive")
shot("S14", "A06_water_tower", 416, 436, (0.10, 0.80), "velocity", None, dict(drift="out"), [], "leap off the water tower")
shot("S15", "A07_electro", 436, 453, (0.05, 0.75), "const", None, dict(drift="in", roll=-2.0), [], "Electro's lightning")
shot("S16", "A08_blue_lenses", 453, 468, (0.05, 0.75), "launch", (1010, 290), dict(drift="in"), [], "blue lenses")
shot("S17", "A09_lens_pushin", 468, 480, (0.00, 1.10), "launch", (1110, 443), dict(drift="in"), [],
     "riser: slam into the lens; the lens glass shatters on the drop")

# ---------------- ACT III  TOM  (drop f480 -> f777)
shot("S18", "M01_lens_portal", 480, 519, (0.02, 1.15), "land", (1110, 443), dict(drift="out", depth=0.2), ["punch@508"],
     "DROP: pull out of Tom's lens through the glass shards; I'M SPIDER-MAN; TOM HOLLAND / EARTH-199999")
shot("S19", "M02_swing_at_cam", 519, 536, (0.03, 0.75), "velocity", None, dict(drift="in"), [], "swings at camera")
shot("S20", "M03_topdown_swing", 536, 554, (0.03, 0.75), "velocity", None, dict(drift="out", roll=-3.0), [],
     "top-down swing")
shot("S21", "M04_dome_crash", 554, 570, (0.22, 0.82), "const", None, dict(drift="out"), [],
     "crash through the dome: real glass shards burst at the camera")
shot("S22", "M07_roll_crouch", 570, 587, (0.05, 0.72), "land", None, dict(drift="in"), [], "roll into a crouch")
shot("S23", "M15_landing_crouch", 587, 604, (0.10, 0.75), "land", None, dict(drift="out", depth=0.45), ["shake@587"],
     "superhero landing: 3D-photo dolly, dust shockwave")
shot("S24", "M06_flying_kick", 604, 620, (0.05, 0.75), "velocity", None, dict(drift="in"), [], "flying kick")
shot("S25", "M08_shuriken", 620, 656, (0.02, 0.76), "const", (507, 375), dict(drift="in", depth=0.25),
     ["letterbox", "punch@631"], "slow motion through the sling-ring portal; the shuriken passes his eye; 3D SPIDER-MAN")
shot("S26", "M09_punches", 656, 672, (0.05, 0.72), "velocity", None, dict(drift="out"), ["shake@656"], "punches")
shot("S27", "M10_tank_snap", 672, 686, (0.05, 0.88), "land", None, dict(drift="in"), [], "crouch on the tank")
shot("S28", "M11_electric_mask", 686, 708, (0.02, 0.76), "const", None, dict(drift="out"), ["punch@700", "source_cut@700"],
     "the clip's own cut at 0.55 s lands on the hit at f700")
shot("S29", "M12_fire_webs", 708, 726, (0.05, 0.76), "velocity", None, dict(drift="in", roll=2.0), [], "webs in the fire")
shot("S30", "M13_mesh_lenses", 726, 744, (0.10, 0.76), "const", None, dict(drift="out"), ["punch@732", "source_cut@732"],
     "the clip's own cut at ~0.33 s lands on the kick at f732")
shot("S31", "M05_landing", 744, 760, (0.05, 0.72), "land", None, dict(drift="in", depth=0.3), [],
     "Tom unmasked on the train; 3D BRAND NEW DAY starts")
shot("S32", "M14_head_raise", 760, 777, (0.05, 0.84), "const", None, dict(drift="in"), [], "head raise under BRAND NEW DAY")

# ---------------------------------------------------------------------------------------------------------------------
# CUTS: one designed 3D transition per cut. Window [f - pre, f + post). type -> owner (EDIT.md "Transitions"):
#   core flow types (blender/amv3/stage): open, zt, whip, cube, flip, slam
#   layer (xfx/layer.py, agent-06): keep = A's matted subject stays in front while B arrives behind; sweep = B's
#     matted subject sweeps in over A near the lens (REFS: c10, c19)
#   xfx/<type>.py modules: eye_tunnel, symbiote, sling_ring, web_wipe (xfx-A); lens_shatter, lightning, triptych (xfx-B);
#   text_fly (text3d)
# over: overlay modules that only ADD objects in the window (no camera), e.g. dome_shards.
# p: parameters. zt keeps the zoom SIGN through the cut (the references do on 22-23 of ~24 cuts; v2 reversed it on 11):
#   mode "push": A pushes in to `peak` x on its focus (expo-in); B starts at `land` (~1.05) on its focus and keeps
#     pushing in, decelerating (x0.75-0.85 per frame) to `settle` at w1.
#   mode "pull": A pulls out to `peak` (< 1: the card shows mirror-tiled picture beyond its edges, smeared); B starts at
#     `land` (~2.4) and keeps pulling out, decelerating to `settle` at w1.
#   roll = degrees turned through the window (+ = clockwise on screen), carried into B's landing.
#   focus_a / focus_b default to the shots' tracks. Deliberate sign reversals: only lens_shatter (480) and the tunnel. whip: dir L|R|U|D, angle = degrees the
#   camera turns. cube: dir L|R|U|D. flip: hinge L|R. slam: depth = parallax amount, kick = landing scale.
# lens: the finishing recipe for the window (EffectCraft): ca = peak chromatic split px, zblur = radial blur boost 0..1,
#   leak = light leak (act default if None), flash = frames of white bloom at the cut (only on the biggest hits).
CUTS = []


def cut(f, type, pre, post, p=None, over=(), lens=None):
    a = next(s for s in S if s["b"] == f) if f > 0 else None
    b = next(s for s in S if s["a"] == f) if f < 777 else None
    L = dict(ca=10, zblur=0.6, leak=None, flash=0)
    L.update(lens or {})
    CUTS.append(dict(id=f"C{len(CUTS):02d}", f=f, type=type, w0=f - pre, w1=f + post,
                     a=a["id"] if a else None, b=b["id"] if b else None, p=dict(p or {}), over=list(over), lens=L))


# Act I: floating, 12-16 f windows, warm light leaks, nothing snaps
cut(0, "open", 0, 24, dict(from_scale=1.9), lens=dict(ca=4, zblur=0.2))
cut(50, "zt", 7, 11, dict(mode="pull", peak=0.45, land=2.4, settle=1.12, roll=25))
cut(83, "layer", 10, 10, dict(mode="keep"))  # Tobey stays in front while the glove city arrives behind him
cut(118, "flip", 6, 10, dict(hinge="L"), lens=dict(ca=6, zblur=0.3))
cut(151, "symbiote", 12, 10, dict(), lens=dict(ca=8, zblur=0.4, leak="none"))
cut(175, "zt", 6, 10, dict(mode="pull", peak=0.45, land=2.4, settle=1.12, roll=-180))
cut(201, "layer", 10, 9, dict(mode="keep"))  # the smirk stays in front, the train arrives behind
cut(235, "zt", 6, 1, dict(mode="push", peak=3.0, land=1.05, settle=1.1, roll=0))  # S08 keeps pushing into the iris
cut(252, "eye_tunnel", 16, 12, dict(iris=[901, 390], exit_lens=[1036, 546]), lens=dict(ca=14, zblur=0.8))
# Act II: rising energy
cut(300, "layer", 6, 10, dict(mode="sweep"))  # Andrew sweeps in over the lens and lands
cut(336, "text_fly", 9, 9, dict(title="AMAZING", exit="dive"), lens=dict(ca=12, zblur=0.7))
cut(369, "cube", 6, 9, dict(dir="U"))
cut(400, "zt", 5, 9, dict(mode="push", peak=3.0, land=1.05, settle=1.45, roll=-30))
cut(416, "whip", 4, 8, dict(dir="D", angle=75))
cut(436, "lightning", 6, 9, dict(), lens=dict(ca=14, zblur=0.6, flash=1))
cut(453, "zt", 4, 8, dict(mode="push", peak=3.0, land=1.05, settle=1.4, roll=180))
cut(468, "zt", 4, 1, dict(mode="push", peak=3.0, land=1.05, settle=1.1, roll=0))  # S17 keeps slamming into the lens
cut(480, "lens_shatter", 11, 14, dict(lens_a=[1110, 443], lens_b=[1110, 443]), lens=dict(ca=18, zblur=0.9, flash=2))
# Act III: hard and fast, 8-11 f windows
cut(519, "zt", 4, 7, dict(mode="pull", peak=0.45, land=2.4, settle=1.15, roll=-35))
cut(536, "whip", 3, 7, dict(dir="D", angle=80))
cut(554, "zt", 4, 8, dict(mode="pull", peak=0.45, land=2.6, settle=1.15, roll=200), over=["dome_shards"])
cut(570, "zt", 3, 7, dict(mode="pull", peak=0.5, land=2.2, settle=1.12, roll=-30))
cut(587, "slam", 4, 10, dict(depth=0.45, kick=1.35), lens=dict(ca=12, zblur=0.5, flash=1))
cut(604, "whip", 3, 7, dict(dir="L", angle=80))
cut(620, "sling_ring", 9, 6, dict(), lens=dict(ca=10, zblur=0.5, leak="red_orange"))
cut(656, "text_fly", 8, 6, dict(title="SPIDER-MAN", exit="through"), lens=dict(ca=16, zblur=0.8, flash=1))
cut(672, "zt", 3, 6, dict(mode="pull", peak=0.5, land=2.2, settle=1.12, roll=-180))
cut(686, "web_wipe", 6, 6, dict(dir="R"), lens=dict(ca=12, zblur=0.5))
cut(708, "zt", 3, 7, dict(mode="pull", peak=0.5, land=2.4, settle=1.12, roll=30))
cut(726, "whip", 3, 7, dict(dir="U", angle=80))
cut(744, "layer", 6, 8, dict(mode="sweep"))  # Tom sweeps in over the lens; BRAND NEW DAY follows
cut(760, "zt", 3, 7, dict(mode="push", peak=2.8, land=1.05, settle=1.4, roll=-25))
cut(777, "triptych", 3, 42, dict(), lens=dict(ca=10, zblur=0.4))

# The triptych (stage module xfx-B "triptych"): three Spider-Men as 3D comic panels that slam in on the hits
# 776.8 / 785.2 / 793.8 with camera parallax, the 3D TIMELESS lands at 802 (text3d), and on the 819.5 hit everything
# shatters into 3D shards that fly past the camera into the outro.
TRIPTYCH = dict(f0=777, f1=819, panels=[
    dict(id="P1", f=777, clip="T01_mask_night", file=f"{CLIPS}/clip_T01_mask_night.mp4", src=(0.30, 1.05), act="tobey"),
    dict(id="P2", f=785, clip="A03_sunset_mask", file=f"{CLIPS}/clip_A03_sunset_mask.mp4", src=(0.10, 0.70), act="andrew"),
    dict(id="P3", f=794, clip="M16_sunset_hero", file=f"{CLIPS}/clip_M16_sunset_hero.mp4", src=(0.05, 1.00), act="tom"),
], title=dict(f=802, text="TIMELESS"), shatter=819)

OUTRO = dict(f0=819, f1=900, text="SAU_EDITZ", hits=[828, 837, 844, 854, 860, 880, 892, 897],
             frames="$AMV2_DATA/blender/outro")  # NNNN.png, 0819-0899, opaque RGBA

# Titles. style "text3d" = a 3D title in the Blender stage (text3d module): chunky extruded condensed italic, Novax
# palette (white-to-hue gradient face, light sweep, settles to a glowing outline), lit in the scene, behind the subject
# (matte holdout) where behind=True. 2D styles (sub, namecard, caption_box) are EffectCraft (v2 TITLES lib).
TITLES = [
    dict(id="sub_tobey", f=8, f1=82, style="sub", text="WHO AM I? I'M SPIDER-MAN.", voice="tobey_who_am_i"),
    dict(id="name_tobey", f=88, f1=148, style="namecard", text="TOBEY MAGUIRE", sub="SPIDER-MAN  2002 - 2007", act="tobey"),
    dict(id="cap_tobey", f=86, f1=150, style="caption_box", text="EARTH-96283", act="tobey"),
    dict(id="sub_andrew", f=262, f1=322, style="sub", text="WHO ARE YOU? SPIDER-MAN.", voice="andrew_who_are_you_spiderman"),
    dict(id="AMAZING", f=303, f1=345, style="text3d", text="AMAZING", palette="cyan_white", behind=True, shot="S10",
         anim="assemble", exit="fly_through@336"),
    dict(id="cap_andrew", f=304, f1=334, style="caption_box", text="EARTH-120703", act="andrew"),
    dict(id="sub_tom", f=488, f1=540, style="sub", text="I'M SPIDER-MAN.", voice="tom_im_spiderman"),
    dict(id="name_tom", f=492, f1=518, style="namecard", text="TOM HOLLAND", sub="SPIDER-MAN  2016 - 2026", act="tom"),
    dict(id="cap_tom", f=484, f1=518, style="caption_box", text="EARTH-199999", act="tom"),
    dict(id="SPIDER-MAN", f=624, f1=662, style="text3d", text="SPIDER-MAN", palette="red_gold", behind=True, shot="S25",
         anim="fly_in", exit="fly_through@656"),
    dict(id="BRAND NEW DAY", f=746, f1=777, style="text3d", text="BRAND NEW DAY", palette="crimson_white", behind=True,
         shot="S31", anim="slam_letters", sub="SPIDER-MAN  2026"),
    dict(id="TIMELESS", f=802, f1=822, style="text3d", text="TIMELESS", palette="chrome", behind=False, shot=None,
         anim="slam", exit="shatter@819"),
]
WATERMARK = dict(text="SAU_EDITZ", f0=0, f1=819, pos=[960, 1040])

VOICE_CUES = [  # file stem, comp frame the clip starts at, gain dB, music duck dB under it
    dict(name="tobey_who_am_i", f=8, db=0, duck=-6),
    dict(name="andrew_who_are_you_spiderman", f=262, db=0, duck=-6),
    dict(name="tom_im_spiderman", f=488, db=0, duck=-5),
]

# Strong onsets measured on timeless_full.wav (frame, strength).
HITS = [(50, 2.5), (83, 1.9), (118, 1.8), (151, 2.2), (201, 1.6), (235, 2.1), (251, 1.8), (284, 2.4), (300, 2.3),
        (416, 1.6), (480, 3.0), (519, 2.3), (536, 2.3), (554, 2.3), (587, 2.1), (604, 2.2), (620, 2.3), (631, 2.1),
        (656, 3.2), (686, 2.7), (700, 1.8), (732, 2.0), (777, 2.4), (785, 3.2), (794, 3.2), (802, 2.0), (807, 2.2),
        (819, 3.7), (828, 3.1), (837, 2.3), (844, 3.4), (854, 2.3), (860, 2.8), (880, 2.5), (892, 3.0), (897, 3.2)]
DROP = 480


def build():
    for x, y in zip(S, S[1:]):
        assert x["b"] == y["a"], (x["id"], y["id"])
    assert S[0]["a"] == 0 and S[-1]["b"] == TRIPTYCH["f0"]
    cuts_f = [c["f"] for c in CUTS]
    assert cuts_f == [0] + [s["b"] for s in S], cuts_f
    for c, d in zip(CUTS, CUTS[1:]):
        assert c["w1"] <= d["w0"], ("windows overlap", c["id"], d["id"], c["w1"], d["w0"])
    for c in CUTS[1:-1]:
        for sid in (c["a"], c["b"]):
            s = next(s for s in S if s["id"] == sid)
            assert s["a"] - HANDLE <= c["w0"] and c["w1"] <= s["b"] + HANDLE, ("window beyond handles", c["id"], sid)
    return dict(version=3, fps=FPS, w=W, h=H, dur=DUR, handle=HANDLE, song=dict(file=SONG, t0=0.0), voice_dir=VOICE,
                sfx_dir=SFX, acts=ACTS, shots=S, cuts=CUTS, triptych=TRIPTYCH, outro=OUTRO, titles=TITLES,
                watermark=WATERMARK, voice=VOICE_CUES, hits=[list(h) for h in HITS], drop=DROP)


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "edl.json")
    with open(out, "w") as f:
        json.dump(build(), f, indent=1)
    print(out, len(S), "shots,", len(CUTS), "cuts")
