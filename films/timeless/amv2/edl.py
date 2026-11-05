"""Timeless v2: the edit decision list, written from scratch for EffectCraft + Blender.

Run `python films/timeless/amv2/edl.py` to write edl.json next to this file. Every stage reads edl.json; change the edit
here, never in the generated file. EDIT.md explains the creative intent behind each number.

Frames are comp frames at 30 fps, [a, b) half-open. Source times are seconds in the clip's own timeline
(handover footage_clips/clip_<ID>.mp4, 1080p60; the prep stage makes 240 fps RIFE copies with the same timeline).
Cut frames come from the song's measured onsets (EDIT.md, "Beat map"), not from a fixed grid: this guitar cover drifts.
"""
import json
import os

FPS, W, H, DUR = 30, 1920, 1080, 900
CLIPS = "/home/nikhil/code/film-making/handover/amv_handover/footage_clips"
SONG = "/home/nikhil/code/film-making/handover/amv_handover/audio/timeless_full.wav"
VOICE = "/home/nikhil/code/film-making/handover/amv_handover/audio/voice"
SFX = "/home/nikhil/code/film-making/handover/amv_handover/project/sfx"

# Acts: who, the Spider-Verse earth designation shown in the caption box, and the look the grade builds.
ACTS = [
    dict(id="tobey", f0=0, f1=252, earth="EARTH-96283", name="TOBEY MAGUIRE", years="2002 - 2007",
         look="nostalgia: warm gold highlights, deep teal shadows, soft bloom, film halation"),
    dict(id="andrew", f0=252, f1=480, earth="EARTH-120703", name="ANDREW GARFIELD", years="2012 - 2014",
         look="electric: cool cyan/blue, sunset amber accents, crisp contrast, cyan bloom"),
    dict(id="tom", f0=480, f1=819, earth="EARTH-199999", name="TOM HOLLAND", years="2016 - 2026",
         look="impact: rich red/orange vs steel blue, punchy contrast, hard highlights, chromatic hits"),
    dict(id="outro", f0=819, f1=900, look="3D SAU_EDITZ outro rendered in Blender"),
]

# speed profiles (the builder maps comp frames -> source time so the shot spans src[0] -> src[1] exactly):
#   const        constant speed
#   velocity     fast -> slow (middle third ~0.25x of the peak) -> fast: the velocity-edit ramp
#   land         fast -> slow (lands slow, for pull-out landings)
#   launch       slow -> fast (accelerates into the exit cut)
#   reverse      plays src[0] -> src[1] with src[0] > src[1] (A01 pull-out out of the lens)
# drift: [scale_start, scale_end] in % of the base fit, the slow push/pull that keeps the camera alive between moves.
# focus: [x, y] clip pixels the zoom transitions and portals centre on (eye, lens) - None = frame centre.
# xin / xout: the transition grammar (EDIT.md "Transitions"); the cut lands on the fastest, blurriest frame.
S = []


def shot(id, clip, a, b, src, speed="const", drift=(100, 108), focus=None, xin="cut", xout="cut", fx=(), note=""):
    S.append(dict(id=id, clip=clip, file=f"{CLIPS}/clip_{clip}.mp4", a=a, b=b, src=list(src), speed=speed,
                  drift=list(drift), focus=list(focus) if focus else None, xin=xin, xout=xout, fx=list(fx), note=note))


# ---------------- ACT I  TOBEY  (guitar intro, f0-252): floating slow motion, soft light, the camera always drifting
shot("S01", "T01_mask_night", 0, 50, (0.05, 0.75), "const", (118, 100), None, "open_lightsweep", "whip_up",
     ["lens_glint@14", "halation"], "open from black on a light sweep across the lens; WHO AM I? lands here")
shot("S02", "T02_mask_off", 50, 83, (0.08, 0.66), "land", (112, 100), None, "whip_up", "zoom_in",
     ["halation"], "the unmasking carries I'M SPIDER-MAN.")
shot("S03", "T03_glove_city", 83, 118, (0.15, 0.85), "const", (130, 100), (950, 560), "pull_out", "light_sweep",
     ["halation"], "name card TOBEY MAGUIRE + caption EARTH-96283")
shot("S04", "T04_flowers", 118, 151, (0.10, 0.90), "const", (100, 112), None, "light_sweep", "zoom_out",
     ["bokeh_bloom"], "gold bokeh, melancholy")
shot("S05", "T05_black_lens", 151, 175, (0.15, 0.95), "const", (125, 105), (980, 520), "zoom_out", "glitch_dark",
     ["symbiote_flicker"], "black suit: the mood darkens")
shot("S06", "T06_bully_smirk", 175, 201, (0.10, 0.95), "land", (115, 100), None, "glitch_dark", "spin_cw",
     ["neon_glow"], "Bully Maguire smirk, purple neon")
shot("S07", "T07_train", 201, 235, (0.30, 0.85), "velocity", (150, 100), None, "spin_cw", "zoom_in",
     ["sparks_glow", "flash@201"], "arms out against the train; sparks at the end")
shot("S08", "T08_eye_dive", 235, 252, (0.05, 0.75), "const", (100, 160), (901, 390), "zoom_in", "rift",
     ["eye_glow"], "push into the left iris; the iris tears open into the multiverse rift")

# ---------------- ACT II  ANDREW  (build, f252-480): rising energy, cuts tighten from 48 f to 12 f
shot("S09", "A01_lens_pullout", 252, 300, (4.45, 0.40), "land", (100, 100), (1036, 546), "rift", "spin_ccw",
     ["lens_flare@256"], "out of the rift through Andrew's mask lens, pulling out over the night city; WHO ARE YOU?")
shot("S10", "A03_sunset_mask", 300, 336, (0.02, 0.70), "const", (124, 104), (915, 600), "spin_ccw", "whip_l",
     ["sun_flare"], "SPIDER-MAN. + AMAZING hero title behind his head + ANDREW GARFIELD / EARTH-120703")
shot("S11", "A02_freefall", 336, 369, (0.05, 1.30), "velocity", (110, 100), None, "whip_l", "spin_cw",
     [], "freefall past the Empire State")
shot("S12", "A04_bridge_flip", 369, 400, (0.05, 1.25), "velocity", (100, 112), None, "spin_cw", "zoom_in",
     [], "flip under the bridge")
shot("S13", "A05_topdown_fall", 400, 416, (0.05, 0.75), "launch", (140, 100), None, "pull_out", "whip_d",
     ["speed_lines"], "top-down dive")
shot("S14", "A06_water_tower", 416, 436, (0.10, 0.80), "velocity", (100, 110), None, "whip_d", "glitch_electric",
     [], "leap off the water tower")
shot("S15", "A07_electro", 436, 453, (0.05, 0.75), "const", (115, 100), None, "glitch_electric", "zoom_out",
     ["electric_glow", "chroma@436"], "Electro's lightning")
shot("S16", "A08_blue_lenses", 453, 468, (0.05, 0.75), "launch", (100, 120), (990, 565), "zoom_out", "zoom_in",
     [], "blue lenses")
shot("S17", "A09_lens_pushin", 468, 480, (0.00, 1.10), "launch", (100, 260), (1110, 443), "zoom_in", "drop_portal",
     [], "riser: slam into the lens; the lens becomes the portal (SPECIAL owns shake, speed lines, flash, ring, chroma)")

# ---------------- ACT III  TOM  (drop f480 -> f819): hard cuts on hits, impact frames, velocity ramps
shot("S18", "M01_lens_portal", 480, 519, (0.02, 1.15), "land", (112, 130), (1110, 443), "drop_portal", "impact",
     ["punch@508"], "DROP: pull out of Tom's lens; I'M SPIDER-MAN; TOM HOLLAND / EARTH-199999")
shot("S19", "M02_swing_at_cam", 519, 536, (0.03, 0.75), "velocity", (110, 100), None, "impact", "whip_r",
     ["shake@519"], "swings at camera")
shot("S20", "M03_topdown_swing", 536, 554, (0.03, 0.75), "velocity", (100, 115), None, "whip_r", "spin_cw",
     ["shake@536"], "top-down swing")
shot("S21", "M04_dome_crash", 554, 570, (0.22, 0.82), "const", (120, 100), None, "spin_cw", "impact",
     ["shake@554", "glass_glint"], "crash through the dome")
shot("S22", "M07_roll_crouch", 570, 587, (0.05, 0.72), "land", (112, 100), None, "impact", "zoom_in",
     [], "roll into a crouch")
shot("S23", "M15_landing_crouch", 587, 604, (0.10, 0.75), "land", (130, 100), None, "pull_out", "whip_l",
     ["shake@587", "ink_frame@587"], "superhero landing (skip the first frames: another shot)")
shot("S24", "M06_flying_kick", 604, 620, (0.05, 0.75), "velocity", (100, 110), None, "whip_l", "zoom_in",
     ["shake@604"], "flying kick")
shot("S25", "M08_shuriken", 620, 656, (0.02, 0.76), "const", (108, 100), (700, 470), "pull_out", "impact",
     ["letterbox", "chroma@620"], "slow motion: the shuriken passes his eye; hero title SPIDER-MAN")
shot("S26", "M09_punches", 656, 672, (0.05, 0.72), "velocity", (110, 100), None, "impact", "spin_ccw",
     ["ink_frame@656", "shake@656", "flash@656"], "punches")
shot("S27", "M10_tank_snap", 672, 686, (0.05, 0.88), "land", (100, 112), None, "spin_ccw", "impact",
     [], "crouch on the tank")
shot("S28", "M11_electric_mask", 686, 708, (0.02, 0.76), "const", (115, 100), None, "impact", "glitch_electric",
     ["shake@686", "source_cut@700"], "the clip's own cut at 0.55 s lands on the hit at f700")
shot("S29", "M12_fire_webs", 708, 726, (0.05, 0.76), "velocity", (110, 100), None, "glitch_electric", "zoom_in",
     ["fire_glow"], "webs in the fire")
shot("S30", "M13_mesh_lenses", 726, 744, (0.10, 0.76), "const", (120, 100), None, "pull_out", "whip_u",
     ["source_cut@732"], "the clip's own cut at ~0.33 s lands on the kick at f732")
shot("S31", "M05_landing", 744, 760, (0.05, 0.72), "land", (100, 110), None, "whip_u", "zoom_out",
     ["shake@744"], "Tom unmasked on the train; BRAND NEW DAY starts")
shot("S32", "M14_head_raise", 760, 777, (0.05, 0.84), "const", (112, 100), None, "zoom_out", "panel_slam",
     [], "head raise under BRAND NEW DAY")

# The triptych: three Spider-Men, one panel per hit (776.8, 785.2, 793.8), TIMELESS 3D slams over them at 802.5,
# the panels shatter into the outro on the 819.5 hit.
TRIPTYCH = dict(f0=777, f1=819, panels=[
    dict(f=777, clip="T01_mask_night", file=f"{CLIPS}/clip_T01_mask_night.mp4", src=(0.30, 1.05), act="tobey"),
    dict(f=785, clip="A03_sunset_mask", file=f"{CLIPS}/clip_A03_sunset_mask.mp4", src=(0.10, 0.70), act="andrew"),
    dict(f=794, clip="M16_sunset_hero", file=f"{CLIPS}/clip_M16_sunset_hero.mp4", src=(0.05, 1.00), act="tom"),
], title=dict(f=802, text="TIMELESS", style="blender_chrome3d"), shatter=819)

OUTRO = dict(f0=819, f1=900, text="SAU_EDITZ", style="blender", hits=[828, 837, 844, 854, 860, 880, 892, 897])

# Titles (EffectCraft unless style starts with blender_). words: [frame offset from f, word] synced to the voice.
TITLES = [
    dict(f=8, f1=82, style="sub", text="WHO AM I? I'M SPIDER-MAN.", voice="tobey_who_am_i"),
    dict(f=88, f1=148, style="namecard", text="TOBEY MAGUIRE", sub="SPIDER-MAN  2002 - 2007", act="tobey"),
    dict(f=86, f1=150, style="caption_box", text="EARTH-96283", act="tobey"),
    dict(f=262, f1=322, style="sub", text="WHO ARE YOU? SPIDER-MAN.", voice="andrew_who_are_you_spiderman"),
    dict(f=303, f1=336, style="novax", text="AMAZING", palette="cyan", behind="A03_sunset_mask", act="andrew"),
    dict(f=304, f1=334, style="caption_box", text="EARTH-120703", act="andrew"),
    dict(f=488, f1=540, style="sub", text="I'M SPIDER-MAN.", voice="tom_im_spiderman"),
    dict(f=492, f1=518, style="namecard", text="TOM HOLLAND", sub="SPIDER-MAN  2016 - 2026", act="tom"),
    dict(f=484, f1=518, style="caption_box", text="EARTH-199999", act="tom"),
    dict(f=624, f1=656, style="novax", text="SPIDER-MAN", palette="red_gold", act="tom"),
    dict(f=746, f1=777, style="novax", text="BRAND NEW DAY", palette="crimson_white", sub="SPIDER-MAN  2026", act="tom"),
    dict(f=802, f1=819, style="blender_chrome3d", text="TIMELESS"),
]
WATERMARK = dict(text="SAU_EDITZ", f0=0, f1=819, pos=[960, 1040])

VOICE_CUES = [  # file stem, comp frame the clip starts at, gain dB, music duck dB under it
    dict(name="tobey_who_am_i", f=8, db=0, duck=-6),
    dict(name="andrew_who_are_you_spiderman", f=262, db=0, duck=-6),
    dict(name="tom_im_spiderman", f=488, db=0, duck=-5),
]

# Strong onsets measured on timeless_full.wav (frame, strength); FX and SFX hang off these.
HITS = [(50, 2.5), (83, 1.9), (118, 1.8), (151, 2.2), (201, 1.6), (235, 2.1), (251, 1.8), (284, 2.4), (300, 2.3),
        (416, 1.6), (480, 3.0), (519, 2.3), (536, 2.3), (554, 2.3), (587, 2.1), (604, 2.2), (620, 2.3), (631, 2.1),
        (656, 3.2), (686, 2.7), (700, 1.8), (732, 2.0), (777, 2.4), (785, 3.2), (794, 3.2), (802, 2.0), (807, 2.2),
        (819, 3.7), (828, 3.1), (837, 2.3), (844, 3.4), (854, 2.3), (860, 2.8), (880, 2.5), (892, 3.0), (897, 3.2)]
DROP = 480


def build():
    for x, y in zip(S, S[1:]):
        assert x["b"] == y["a"], (x["id"], y["id"])
        assert x["xout"] == y["xin"] or (x["xout"], y["xin"]) in {("zoom_in", "pull_out"), ("impact", "pull_out")}, \
            (x["id"], x["xout"], y["xin"])
    assert S[0]["a"] == 0 and S[-1]["b"] == TRIPTYCH["f0"]
    return dict(fps=FPS, w=W, h=H, dur=DUR, song=dict(file=SONG, t0=0.0), voice_dir=VOICE, sfx_dir=SFX,
                acts=ACTS, shots=S, triptych=TRIPTYCH, outro=OUTRO, titles=TITLES, watermark=WATERMARK,
                voice=VOICE_CUES, hits=[list(h) for h in HITS], drop=DROP)


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "edl.json")
    with open(out, "w") as f:
        json.dump(build(), f, indent=1)
    print(out, len(S), "shots")
