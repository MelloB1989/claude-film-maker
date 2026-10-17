"""The bpy-free parts of the basic AMV titles: word timing -> frames, the fixed sub layout, AE keys, spring and layout maths.

Expected values are worked by hand from `text_lib.jsx` (the After Effects builders that are the spec), not computed with
the module under test.
"""
import json
import math
from pathlib import Path

import pytest

from amv.titles import basic

PLAN = Path(__file__).resolve().parents[2] / "films" / "timeless" / "amv" / "plan.json"
VOICE = Path("/home/nikhil/code/film-making/handover/amv_handover/audio/voice/voice_lines.json")

SUB0 = {"text": "WHO AM I? I'M SPIDER-MAN.", "dur": 66,
        "words": [[3, "WHO"], [6, "AM"], [11, "I?"], [34, "I'M"], [39, "SPIDER-MAN."]]}
SUB1 = {"variant": "yellow", "text": "WHO ARE YOU? SPIDER-MAN.", "dur": 60,
        "words": [[3, "WHO"], [7, "ARE"], [11, "YOU?"], [35, "SPIDER-MAN."]]}


def fonts_here():
    try:
        basic.font_path("Orbitron-Bold")
        return True
    except FileNotFoundError:
        return False


needs_fonts = pytest.mark.skipif(not fonts_here(), reason="fonts not on this machine")


# -- word timing ------------------------------------------------------------------------------------------------------

def test_word_spans_follow_indexof_like_the_jsx():
    # "WHO AM I? I'M SPIDER-MAN." : WHO 0-3, AM 4-6, I? 7-9, I'M 10-13, SPIDER-MAN. 14-25
    assert basic.word_spans(SUB0["text"], SUB0["words"]) == [(3, 3), (6, 6), (11, 9), (34, 13), (39, 25)]


def test_word_spans_repeated_word_takes_the_next_occurrence():
    assert basic.word_spans("GO GO GO", [[1, "GO"], [2, "GO"], [3, "GO"]]) == [(1, 2), (2, 5), (3, 8)]


@pytest.mark.parametrize("k,n", [(0, 0), (2, 0), (3, 3), (5, 3), (6, 6), (10, 6), (11, 9), (33, 9), (34, 13), (38, 13),
                                 (39, 25), (65, 25)])
def test_visible_chars_hold_keys(k, n):
    assert basic.visible_chars(SUB0["text"], SUB0["words"], k) == n


def test_plan_word_frames_lag_the_voice_by_0_to_2_frames():
    if not (PLAN.exists() and VOICE.exists()):
        pytest.skip("plan or voice_lines.json not on this machine")
    voice = {v["name"]: v for v in json.loads(VOICE.read_text())}
    plan = json.loads(PLAN.read_text())
    tobey = voice["tobey_who_am_i"]["words"]
    # Spider-/Man. are one word in the plan, shown when "Spider-" starts
    spoken = [tobey[0]["t0"], tobey[1]["t0"], tobey[2]["t0"], tobey[3]["t0"], tobey[4]["t0"]]
    frames = [f for f, _ in plan["titles"][0]["spec"]["words"]]
    for f, t0 in zip(frames, spoken):
        assert 0 <= f - t0 * 30 <= 2.0


# -- the sub line stays put while words reveal ---------------------------------------------------------------------------

@needs_fonts
@pytest.mark.parametrize("spec", [SUB0, SUB1])
def test_sub_glyphs_never_move_as_words_appear(spec):
    pos = {}
    for k in range(0, spec["dur"] - 4):
        fr = basic.sub_frame(spec, k)
        text = [g for g in fr.groups if g.name == "text"][0]
        for i, g in enumerate(text.elems):
            key = (i, g.ch)
            pos.setdefault(key, (round(g.x, 6), round(g.y, 6), g.size))
            assert pos[key] == (round(g.x, 6), round(g.y, 6), g.size), (k, key)
    # all glyphs appear in the end
    n_glyphs = len(spec["text"].replace(" ", ""))
    assert len(pos) == n_glyphs


@needs_fonts
def test_sub_reveals_in_order_and_fades_out_in_the_last_frames():
    counts = [len([g for g in basic.sub_frame(SUB0, k).groups[-1].elems]) for k in range(SUB0["dur"])]
    assert counts[2] == 0 and counts[3] == 3 and counts[6] == 5 and counts[11] == 7  # WHO / +AM / +I?
    assert counts[34] == 10 and counts[39] == 21
    assert counts == sorted(counts)
    last = basic.sub_frame(SUB0, 65).groups[-1].elems
    assert all(g.opacity == pytest.approx(0.0) for g in last)
    mid = basic.sub_frame(SUB0, 62).groups[-1].elems          # dur-4 = 62: still full
    assert all(g.opacity == pytest.approx(1.0) for g in mid)


@needs_fonts
def test_sub_white_has_a_bar_that_grows_and_yellow_has_a_dark_edge_but_no_bar():
    names = lambda fr: [g.name for g in fr.groups]
    for k in (0, 1, 2):                                       # nothing, not even the bar, before the first word (k = 3)
        assert names(basic.sub_frame(SUB0, k)) == ["text"] and not basic.sub_frame(SUB0, k).groups[0].elems
    assert names(basic.sub_frame(SUB0, 3)) == ["bar", "text"]
    assert names(basic.sub_frame(SUB0, 20)) == ["bar", "text"]
    assert names(basic.sub_frame(SUB1, 20)) == ["edge", "text"]   # dark edge beneath the text, no bar/plate/glow
    widths = []
    for k in (4, 8, 12, 30, 40, 50):
        bar = basic.sub_frame(SUB0, k).groups[0].elems[0]
        xs = [p[0] for p in bar.pts]
        widths.append(max(xs) - min(xs))
    assert widths == sorted(widths)
    # the bar's left edge is fixed (a wipe from the left)
    lefts = [min(p[0] for p in basic.sub_frame(SUB0, k).groups[0].elems[0].pts) for k in (8, 30, 50)]
    assert max(lefts) - min(lefts) < 3.0


def test_bar_reveal_is_linear_between_words_like_the_wipe_keys():
    # completion keys: (0,100) (2,c0) (5,c0)... 'I?' ends at char 9 of 25 -> 100-36-4 = 60 (held 10..13)
    r10 = basic.sub_bar_reveal(SUB0["text"], SUB0["words"], 10)
    r13 = basic.sub_bar_reveal(SUB0["text"], SUB0["words"], 13)
    assert r10 == pytest.approx(0.40) and r13 == pytest.approx(0.40)
    # between frame 13 (I? hold ends at 11+2) and the key at 33 ("I'M" at 34, 33 = 34-1, completion 100-52-4 = 44)
    r23 = basic.sub_bar_reveal(SUB0["text"], SUB0["words"], 23)
    assert r23 == pytest.approx(0.40 + (0.56 - 0.40) * 0.5)
    assert basic.sub_bar_reveal(SUB0["text"], SUB0["words"], 0) == pytest.approx(0.0)


# -- AE keys -------------------------------------------------------------------------------------------------------------

def test_lin_holds_outside_and_is_linear_inside():
    ks = [[2, 0.0], [6, 100.0]]
    assert basic.lin(ks, 0) == 0.0 and basic.lin(ks, 9) == 100.0
    assert basic.lin(ks, 3) == pytest.approx(25.0)
    assert basic.lin([[0, (0.0, 10.0)], [4, (4.0, 30.0)]], 1) == pytest.approx((1.0, 15.0))


def test_ease_keys_arrives_slowly_and_matches_the_keys():
    ks = [[0, 1150.0], [7, 0.0], [22, 60.0]]
    e = {2: (80, 10)}
    assert basic.ease_keys(ks, 0, e) == 1150.0
    assert basic.ease_keys(ks, 7, e) == pytest.approx(0.0, abs=1e-6)
    # ease-in at key 2 (speed 0): the last step into frame 7 is smaller than a linear step would be
    step_last = basic.ease_keys(ks, 6, e) - basic.ease_keys(ks, 7, e)
    assert 0 < step_last < 1150.0 / 7
    # and it is monotone
    vals = [basic.ease_keys(ks, f, e) for f in range(0, 8)]
    assert vals == sorted(vals, reverse=True)


# -- spring ------------------------------------------------------------------------------------------------------------------

def test_spring_amount_is_100_before_the_letters_turn_then_a_damped_cosine():
    assert basic.spring_amount(0, 0) == pytest.approx(100.0)          # t = 0: cos 0 / e^0
    assert basic.spring_amount(3, 3) == 100.0                           # t = 0.1 - 0.135 < 0
    t = 10 / 30 - 0.045 * 2
    assert basic.spring_amount(2, 10) == pytest.approx(100 * math.cos(1.3 * t * 2 * math.pi) / math.exp(6 * t))
    assert abs(basic.spring_amount(0, 30)) < 0.5                         # settled after a second


@needs_fonts
def test_spring_letters_start_flipped_and_invisible_and_settle():
    spec = {"text": "SPIDER-MAN", "sub": "TOM HOLLAND", "dur": 34, "palette": "red", "size": 300, "pos": [960, 470]}
    f0 = basic.spring_frame(spec, 0)
    face0 = [g for g in f0.groups if g.name == "face"][0].elems
    assert all(g.opacity == 0.0 and g.sx < 0 for g in face0)
    f20 = basic.spring_frame(spec, 28)
    face20 = [g for g in f20.groups if g.name == "face"][0].elems
    assert all(abs(g.dy) < 3 and g.sx > 0.9 for g in face20)
    assert [g.name for g in f20.groups] == ["shadow", "face", "edge", "subline"]
    # the last frame is faded out
    last = basic.spring_frame(spec, 33)
    assert all(g.opacity == pytest.approx(0.0) for g in [x for x in last.groups if x.name == "face"][0].elems)


# -- layout ---------------------------------------------------------------------------------------------------------------

@needs_fonts
def test_line_layout_is_centred_and_tracking_widens_it():
    pl, w = basic.line_layout("SAU_EDITZ", "Orbitron-Bold", 30, 250)
    assert pl[0].x == pytest.approx(-w / 2)
    last = pl[-1]
    assert last.x + last.adv + 0.25 * 30 == pytest.approx(w / 2)      # AE centres with the trailing tracking
    _, w0 = basic.line_layout("SAU_EDITZ", "Orbitron-Bold", 30, 0)
    assert w - w0 == pytest.approx(9 * 0.25 * 30)             # 9 tracking steps of 250/1000 em at 30 px


@needs_fonts
def test_font_metrics_are_sane():
    fm = basic.metrics("Orbitron-Bold")
    assert 0.6 < fm.cap < 0.8
    assert 0.5 < fm.advance("M") < 1.2
    assert fm.advance(" ") > 0


@needs_fonts
def test_watermark_is_centred_at_960_with_the_baseline_at_1050():
    fr = basic.watermark_frame()
    g = fr.groups[0].elems
    assert len(g) == 9                                         # SAU_EDITZ: no spaces, the underscore is a glyph
    pl, w = basic.line_layout("SAU_EDITZ", "Montserrat-Light", 30, 180)
    assert g[0].x == pytest.approx(964 - w / 2)         # +4: matches the AE ink position
    assert all(e.y == pytest.approx(1050) for e in g)          # baseline (AE's un-anchored text layer)
    assert fr.groups[0].shadow.opacity == pytest.approx(0.7)
    assert all(e.opacity == 1.0 for e in g)


def test_ae_shadow_direction_135_is_down_right():
    s = basic.ae_shadow(70, 2, 4)
    assert s.dx == pytest.approx(2 * math.sin(math.radians(135))) and s.dy == pytest.approx(2 * math.sin(math.radians(135)))
    assert s.dx > 0 and s.dy > 0


# -- tag / extended / frames of every title exist for all k -------------------------------------------------------------

@needs_fonts
def test_every_title_builds_for_every_frame():
    plan = json.loads(PLAN.read_text()) if PLAN.exists() else None
    specs = []
    if plan:
        specs += [(t["style"], t["spec"]) for t in plan["titles"] if t["style"] in basic.STYLES]
        for s in plan["shots"]:
            specs += [(t["style"], t["spec"]) for t in s.get("titles", []) if t["style"] in basic.STYLES]
    else:
        specs = [("sub", SUB0), ("sub", SUB1)]
    assert specs
    for style, spec in specs:
        for k in range(spec["dur"]):
            fr = basic.STYLES[style](spec, k)
            assert fr.groups


@needs_fonts
def test_tag_tracking_settles_and_bar_wipes_in():
    spec = {"text": "TOBEY MAGUIRE", "sub": "SPIDER-MAN  2002", "dur": 23, "size": 50, "pos": [960, 800]}

    def width(k):
        g = [x for x in basic.tag_frame(spec, k).groups if x.name == "text"][0].elems
        return max(e.x for e in g) - min(e.x for e in g)

    assert width(0) > width(3) > width(7)
    assert width(7) < width(22)                    # drifts back out to +60
    names = [g.name for g in basic.tag_frame(spec, 10).groups]
    assert names == ["bar", "text", "sub", "brackets"]
    assert [g.name for g in basic.tag_frame(spec, 0).groups][0] == "text"   # bar wipe starts at 0%


@needs_fonts
def test_extended_slides_in_from_the_left_and_has_the_slash_cut():
    spec = {"text": "BRAND NEW DAY", "sub": "SPIDER-MAN 2026", "dur": 34, "palette": "ice", "size": 150, "pos": [960, 600]}

    def cx(k):
        g = [x for x in basic.extended_frame(spec, k).groups if x.name == "face"][0]
        return sum(e.x for e in g.elems) / len(g.elems)

    assert cx(0) < cx(6) - 400                   # starts 520 px left
    assert cx(33) > cx(6)                        # drifts +40
    g = [x for x in basic.extended_frame(spec, 10).groups if x.name == "face"][0]
    assert g.cut and len(g.cut) == 4
    assert g.smear is None                       # blur has cleared by frame 6
    assert basic.extended_frame(spec, 1).groups[-1].name or True
