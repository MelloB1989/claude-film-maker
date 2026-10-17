"""The outro's letter schedule and timeline (bpy-free): order, stagger, durations, end frame, ends black."""
import math

from amv import outro_schedule as sch

N = 88


def test_word_and_order_cover_every_letter_once():
    assert sch.WORD == "SAU_EDITZ"
    assert sorted(sch.ORDER) == list(range(9))      # ORDER = slots in launch order
    assert len(sch.STARTS) == 9


def test_launch_order_is_e_a_t_underscore_i_s_d_z_u():
    fl = sorted(sch.flights(), key=lambda f: f.rank)
    assert "".join(f.ch for f in fl) == "EAT_ISDZU"


def test_stagger_is_three_or_four_frames_and_flights_overlap():
    starts = [f.f0 for f in sorted(sch.flights(), key=lambda f: f.rank)]
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert starts[0] == 0
    assert all(3 <= g <= 4 for g in gaps), gaps
    assert max(gaps) < sch.LDUR                      # never one at a time


def test_every_flight_lasts_34_frames_and_the_last_lands_at_62():
    fl = sch.flights()
    assert all(f.f1 - f.f0 == 34 for f in fl)
    assert max(f.f1 for f in fl) == 62 == sch.LAND
    assert 0.7 * N <= 62 <= 0.8 * N                  # assembled by 70-80 % of the outro


def test_letters_are_independent_not_a_uniform_cascade():
    fl = sch.flights()
    assert len({f.start for f in fl}) == 9 and len({f.spin for f in fl}) == 9
    for f in fl:
        dx, dy, dz = f.start
        assert 300 <= abs(dx) <= 900 and 300 <= abs(dy) <= 900 and -2500 <= dz <= -800
        assert all(40 <= abs(a) <= 160 for a in f.spin)


def test_flight_is_deterministic_and_lands_exactly():
    a, b = sch.flights(), sch.flights()
    assert a == b
    for fl in a:
        s = sch.letter_state(fl, fl.f1)
        assert all(abs(v) < 1e-9 for v in s["off"] + s["rot"] + s["tilt"])
        assert s["opacity"] == 1.0
        s0 = sch.letter_state(fl, fl.f0)
        assert s0["opacity"] == 0.0 and math.dist(s0["off"], (0, 0, 0)) > 3.0


def test_expo_ease_is_monotonic_with_no_overshoot_and_snaps_fast():
    prev = 0.0
    for i in range(0, 101):
        v = sch.expo(i / 100)
        assert prev - 1e-9 <= v <= 1.0 + 1e-9
        prev = v
    assert sch.expo(0.0) == 0.0 and sch.expo(1.0) == 1.0
    assert sch.expo(0.25) > 0.6                      # expo out: most of the travel in the first quarter


def test_fade_in_takes_eight_frames():
    fl = sch.flights()[0]
    assert sch.letter_state(fl, fl.f0 + 4)["opacity"] == 0.5
    assert sch.letter_state(fl, fl.f0 + 8)["opacity"] == 1.0


def test_dissolve_runs_d_minus_10_to_d_minus_2_and_ends_black():
    assert sch.end_fx(N - 11, N)["dissolve"] == 0.0
    assert sch.end_fx(N - 10, N)["dissolve"] == 0.0
    assert sch.end_fx(N - 2, N)["dissolve"] == 1.0
    mid = [sch.end_fx(f, N)["dissolve"] for f in range(N - 10, N - 1)]
    assert mid == sorted(mid)
    assert sch.end_fx(N - 2, N)["black"] == 1.0 and sch.end_fx(N - 1, N)["black"] == 1.0
    assert sch.end_fx(N - 3, N)["black"] == 0.0


def test_word_is_settled_and_still_for_the_legibility_window():
    # last letter landed at 62, dissolve starts at 78: the letters hold still for 16 frames
    for f in range(sch.LAND, N - 10):
        for fl in sch.flights():
            s = sch.letter_state(fl, f)
            assert s["opacity"] == 1.0 and max(abs(v) for v in s["off"]) < 1e-9


def test_camera_never_stops_but_eases_in_and_drifts_after_landing():
    c0, c62, c87 = (sch.camera(f, N) for f in (0, 62, N - 1))
    assert c0["scale"] == 114 and abs(c62["scale"] - 100) < 1e-6 and c87["scale"] < c62["scale"]
    assert c87["orbit"] != c62["orbit"]


def test_sweep_crosses_the_word_between_f48_and_f70():
    assert sch.sweep(48)["x"] < -15 and sch.sweep(70)["x"] > 15
    assert sch.sweep(40)["level"] == 0 and sch.sweep(60)["level"] == 1 and sch.sweep(75)["level"] == 0


def test_rings_fade_in_staggered():
    ops = [sch.ring(i, 10, N)["opacity"] for i in range(3)]
    assert ops[0] > ops[1] > ops[2]


def test_sparks_are_born_at_landings_and_finite():
    fl = sch.flights()
    sp = sch.sparks(fl, N)
    assert len(sp) == 9 * 9
    for s in sp:
        land = fl[s["slot"]].f1
        assert land - 1 <= s["born"] <= land + 1
        assert sch.spark_state(s, s["born"] - 1)[3] == 0.0
        assert sch.spark_state(s, s["born"] + s["life"] + 1)[3] == 0.0
        assert s["born"] + s["life"] <= N - 10
