import math

import numpy as np
import pytest

from lib import cels


def test_colours():
    assert cels.rgb("#ff8000") == pytest.approx((1.0, 128 / 255, 0.0))
    assert cels.rgb((0.2, 0.4, 0.6, 1.0)) == (0.2, 0.4, 0.6)
    assert cels.linear("#ffffff") == pytest.approx((1.0, 1.0, 1.0))
    assert cels.linear((0.5, 0.0, 0.04))[0] == pytest.approx(0.214, abs=1e-3)
    assert cels.linear((0.5, 0.0, 0.04))[2] == pytest.approx(0.04 / 12.92)
    assert cels.mix("#000000", "#ffffff", 0.25) == pytest.approx((0.25, 0.25, 0.25))


def test_flash_bleaches_lit_sinks_shade_keeps_ink():
    skin = "#d0b0a0"
    assert cels.flash(skin, 0.0) == cels.rgb(skin)
    lit = cels.flash(skin, 1.0, "lit")
    dark = cels.flash(skin, 1.0, "shade")
    assert sum(lit) > sum(cels.rgb(skin)) > sum(dark)
    assert cels.flash(cels.INK, 1.0, "ink") == cels.rgb(cels.INK)


def test_open_spline_passes_through_its_points_and_keeps_corners():
    pts = [(0, 0), (1, 0.5), (2, 0), (3, 1)]
    P = cels.spline(pts, step=0.05)
    for p in pts:
        assert np.min(np.linalg.norm(P - p, axis=1)) < 1e-9
    assert np.allclose(P[0], pts[0]) and np.allclose(P[-1], pts[-1])
    # sampled about every step
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    assert seg.max() < 0.08
    # a corner: the curve's direction jumps there
    C = cels.spline(pts, corners=(1,), step=0.02)
    i = int(np.argmin(np.linalg.norm(C - pts[1], axis=1)))
    d0, d1 = C[i] - C[i - 1], C[i + 1] - C[i]
    turn = math.degrees(math.acos(np.dot(d0, d1) / np.linalg.norm(d0) / np.linalg.norm(d1)))
    assert turn > 30


def test_closed_spline_starts_at_its_first_point_and_does_not_repeat_it():
    pts = [(0, 1), (1, 0), (0, -1), (-1, 0)]
    for corners in ((), (2,)):
        P = cels.spline(pts, closed=True, corners=corners, step=0.05)
        assert np.allclose(P[0], pts[0])
        assert not np.allclose(P[-1], P[0])
        for p in pts:
            assert np.min(np.linalg.norm(P - p, axis=1)) < 1e-9


def test_taper_runs_from_tip_to_full():
    P = np.c_[np.linspace(0, 1, 101), np.zeros(101)]
    w = cels.taper(P, 0.2, 0.3, tip=0.1)
    assert w[0] == pytest.approx(0.1) and w[-1] == pytest.approx(0.1)
    assert w[50] == pytest.approx(1.0)
    assert np.all(np.diff(w[:21]) >= -1e-12)


def test_ribbon_and_offset():
    C = np.c_[np.linspace(0, 1, 11), np.zeros(11)]
    R = cels.ribbon(C, 0.2)
    assert len(R) == 22
    assert R[5][1] == pytest.approx(0.1) and R[-6][1] == pytest.approx(-0.1)
    assert cels.offset(C, 0.3)[:, 1] == pytest.approx(np.full(11, 0.3))


def test_between_wraps_round_a_closed_outline():
    P = np.array([(0, 0), (1, 0), (1, 1), (0, 1)], float)
    assert cels.between(P, (1, 0), (1, 1)).tolist() == [[1, 0], [1, 1]]
    assert cels.between(P, (0, 1), (1, 0)).tolist() == [[0, 1], [0, 0], [1, 0]]


def test_lock_runs_root_to_tip_to_root_and_its_inner_part_stays_inside():
    lk = cels.lock((0, 0), (0.2, 0), (0.1, 1.0), bow=0.1)
    out = lk.outline
    assert np.allclose(out[0], (0, 0)) and np.allclose(out[-1], (0.2, 0))
    assert np.allclose(lk.tip, (0.1, 1.0))
    inner = lk.inner(0.5)
    assert inner[:, 0].min() >= out[:, 0].min() - 1e-9 and inner[:, 0].max() <= out[:, 0].max() + 1e-9
    assert np.allclose(lk.edge("a")[0], (0, 0)) and np.allclose(lk.edge("b")[0], (0.2, 0))


def test_bend_wave_blend_move_mirror():
    P = np.c_[np.zeros(11), np.linspace(0, 1, 11)]
    B = cels.bend(P, (0, 0), 90.0, power=1.0)
    assert np.allclose(B[0], (0, 0)) and np.allclose(B[-1], (-1, 0), atol=1e-9)
    W = cels.wave(P, 0.1, 0.5, 0.0)
    assert np.allclose(W[0], P[0]) and np.abs(W[:, 0]).max() > 0.01
    assert np.allclose(cels.blend(P, B, 0.0), P) and np.allclose(cels.blend(P, B, 1.0), B)
    assert np.allclose(cels.move([(1, 0)], (1, 1), scale=2, rotate=90), [(1, 3)])
    M = cels.mirror([(1, 0), (2, 1)], x=0.5)
    assert M.tolist() == [[-1, 1], [0, 0]]


def test_zig_and_teeth():
    P = np.c_[np.linspace(0, 1, 50), np.zeros(50)]
    Z = cels.zig(P, 0.1, 5, sharp=0.0, base=0.0)
    # teeth reach down (right of a line drawn left to right) to the full depth, and back up to the line between
    assert Z[:, 1].min() == pytest.approx(-0.1, abs=5e-3) and Z[:, 1].max() == pytest.approx(0.0, abs=5e-3)
    T = cels.teeth(P, 0.1, 5)
    assert len(T) == 2 * len(cels.resample(P, 50))


def test_eye_pieces_and_closing():
    e = cels.Eye(center=(0, 0), width=0.2)
    parts = e.pieces()
    assert set(parts) == {"eye_white", "eye_iris", "eye_light", "eye_lines"}
    assert parts["eye_white"] and parts["eye_iris"] and parts["eye_lines"]
    up, lo = e.lids()
    assert np.all(up[:, 1] >= lo[:, 1] - 1e-12)
    shut = cels.Eye(center=(0, 0), width=0.2, open=0.0).pieces()
    assert not shut["eye_white"] and shut["eye_lines"]
    # the eye spans its width round its centre, mirrored by side
    right = cels.Eye(center=(1, 0), width=0.2, side=1).pieces()["eye_white"][0].points
    left = cels.Eye(center=(1, 0), width=0.2, side=-1).pieces()["eye_white"][0].points
    assert right[:, 0].min() == pytest.approx(0.9) and right[:, 0].max() == pytest.approx(1.1)
    assert np.allclose(np.sort(right[:, 0]), np.sort(2 - left[:, 0]))


def test_drawing_layers_masks_bounds_and_recolor():
    d = cels.Drawing()
    d.add("skin", cels.fill([(0, 0), (1, 0), (1, 1), (0, 1)], "#ffffff", smooth=False))
    d.add("shade", cels.Fill(np.array([(0.5, 0), (1.5, 0), (1.5, 1)], float), "#888888"), mask=("skin",))
    d.add("lines", cels.line([(0, 0), (2, 2)], 0.01))
    assert list(d.layers) == ["skin", "shade", "lines"]
    assert d.layers["shade"].mask == ("skin",)
    assert d.bounds() == pytest.approx((0.0, 0.0, 2.0, 2.0))
    d.eye(cels.Eye(center=(0.5, 0.5), width=0.2), "l_")
    assert d.layers["l_eye_iris"].mask == ("l_eye_white",)
    d.recolor(lambda c: "#000000")
    assert all(p.color == "#000000" for L in d.layers.values() for p in L.pieces)


def test_order_merges_layer_names_across_drawings():
    a, b = cels.Drawing(), cels.Drawing()
    for n in ("back", "body", "front"):
        a.layer(n)
    for n in ("back", "fx", "body"):
        b.layer(n)
    assert cels.order([a, b]) == ["back", "fx", "body", "front"]


def test_twos():
    assert cels.twos(36, 44) == [36, 38, 40, 42]
    assert cels.twos(0, 7, 3) == [0, 3, 6]


def test_shift_moves_pieces_on_chosen_layers():
    d = cels.Drawing()
    d.add("a", cels.Fill(np.array([(0, 0), (1, 0), (1, 1)], float)))
    d.add("b", cels.Fill(np.array([(0, 0), (1, 0), (1, 1)], float)))
    d.shift(0.5, -1.0, layers=("a",))
    assert np.allclose(d.layers["a"].pieces[0].points[0], (0.5, -1.0))
    assert np.allclose(d.layers["b"].pieces[0].points[0], (0.0, 0.0))


def test_zig_down_hangs_its_teeth_down_either_way_round():
    P = np.c_[np.linspace(0, 1, 40), np.zeros(40)]
    for line_ in (P, P[::-1]):
        Z = cels.zig_down(line_, 0.1, 4, sharp=0.0, base=0.0)
        assert Z[:, 1].min() == pytest.approx(-0.1, abs=5e-3) and Z[:, 1].max() <= 1e-9
        assert np.allclose(Z[0], line_[0], atol=1e-6)


def test_fringe_hangs_below_its_top():
    outline, top, hang = cels.fringe([(0, 0), (0.5, 0.05), (1, 0)], 0.3, 6, tooth=0.05)
    assert len(top) == len(hang)
    assert np.allclose(hang[:, 1], top[:, 1] - 0.3)
    assert outline[:, 1].min() == pytest.approx(top[:, 1].min() - 0.35, abs=0.02)


def test_soft_stacks_fills_from_inside_out_to_its_opacity():
    circle = cels.ellipse((0, 0), 0.5, 0.5, n=180)
    for pts in (circle, circle[::-1]):   # either way round
        parts = cels.soft(pts, "#000000", spread=0.2, opacity=0.6, steps=6, smooth=False)
        assert len(parts) == 6
        widths = [np.ptp(p.points[:, 0]) for p in parts]
        assert widths[0] == pytest.approx(0.8, abs=1e-3) and widths[-1] == pytest.approx(1.2, abs=1e-3)
        assert 1 - (1 - parts[0].opacity) ** 6 == pytest.approx(0.6)


def test_hatch_covers_its_box_with_parallel_strokes():
    lines = cels.hatch((0, 0, 1, 1), angle=45, spacing=0.1, jitter=0.0)
    # a stroke every 0.1 across the box (but one that would only touch a corner), each clipped to the box
    n = int(2 * math.hypot(1, 1) / 2 / 0.1) + 1
    assert n - 2 <= len(lines) <= n
    for ln in lines:
        d = ln.points[-1] - ln.points[0]
        assert d[0] == pytest.approx(d[1])
        assert ln.widths[0] == 0.0 and ln.widths.max() == pytest.approx(1.0, abs=0.05)
        assert ln.points.min() >= -1e-9 and ln.points.max() <= 1 + 1e-9
    longest = max(np.linalg.norm(ln.points[-1] - ln.points[0]) for ln in lines)
    assert longest == pytest.approx(math.hypot(1, 1), abs=0.15)


def test_bolt_runs_from_sky_to_foot_with_its_forks():
    d = cels.bolt((0, 10), (1, 0), width=0.1, branches=3, seed=4)
    assert list(d.layers) == ["bolt_halo", "bolt"]
    main = d.layers["bolt"].pieces[0]
    assert np.allclose(main.points[0], (0, 10)) and np.allclose(main.points[-1], (1, 0))
    assert len(d.layers["bolt"].pieces) == 4 and len(d.layers["bolt_halo"].pieces) == 4
    assert main.widths[0] > main.widths[-1]


def test_pressure_wanders_about_one():
    P = np.c_[np.linspace(0, 1, 200), np.zeros(200)]
    w = cels.pressure(P, amount=0.3, seed=3)
    assert len(w) == 200 and abs(w.mean() - 1.0) < 0.15
    assert w.min() >= 0.7 - 1e-9 and w.max() <= 1.3 + 1e-9 and np.ptp(w) > 0.05


def test_strands_run_between_their_lines():
    a = np.c_[np.linspace(0, 1, 20), np.ones(20)]
    b = np.c_[np.linspace(0, 1, 20), np.zeros(20)]
    out = cels.strands(a, b, 30, width=0.01, seed=2, colors=["#111111", "#eeeeee"], opacity=(0.4, 0.9))
    assert len(out) == 30
    for s in out:
        assert s.points[:, 1].max() <= 1 + 1e-9 and s.points[:, 1].min() >= -1e-9
        assert s.points[0, 1] > s.points[-1, 1]           # from a toward b
        assert s.color in ("#111111", "#eeeeee") and 0.4 <= s.opacity <= 0.9
    xs = sorted(s.points[0, 0] for s in out)
    assert xs[0] < 0.1 and xs[-1] > 0.9                    # spread along the lines


def test_ragged_hangs_uneven_points_to_the_right():
    P = np.c_[np.linspace(0, 1, 40), np.zeros(40)]
    R = cels.ragged(P, 0.2, 8, seed=5)
    assert R[:, 1].max() <= 1e-9 and R[:, 1].min() == pytest.approx(-0.2, abs=0.02)
    assert np.allclose(R[0], (0, 0)) and np.allclose(R[-1], (1, 0))
    # the points are not all alike: local minima at differing depths
    y = R[:, 1]
    tips = [y[i] for i in range(1, len(y) - 1) if y[i] < y[i - 1] and y[i] <= y[i + 1]]
    assert len(tips) >= 4 and np.ptp(tips) > 0.02


def test_drip_swells_then_falls():
    hanging = cels.drip((0, 0), 0.5, period=1.0)
    falling = cels.drip((0, 0), 0.9, period=1.0, fall=0.3)
    assert all(p.points[:, 1].max() <= 1e-6 for p in hanging)
    assert min(p.points[:, 1].min() for p in falling) < -0.05
    assert any(isinstance(p, cels.Line) and p.points[0, 1] - p.points[1, 1] > 0 for p in falling)


def test_brush_varies_its_width_and_lifts_over_its_gaps():
    whole = cels.brush([(0, 0), (1, 0.2), (2, 0)], 0.02, seed=3)
    assert len(whole) == 1
    w = whole[0].widths
    assert w[0] < 0.2 and w[-1] < 0.2 and np.ptp(w[len(w) // 4: 3 * len(w) // 4]) > 0.02   # tapered, and uneven
    broken = cels.brush([(0, 0), (1, 0.2), (2, 0)], 0.02, gaps=((0.4, 0.55),), seed=3)
    assert len(broken) == 2
    first, second = broken
    assert first.widths[-1] == pytest.approx(0.0, abs=1e-9) and second.widths[0] == pytest.approx(0.0, abs=1e-9)
    assert first.points[-1, 0] < second.points[0, 0]


def test_contour_is_thin_where_it_faces_the_light_and_heavy_below():
    circle = cels.ellipse((0, 0), 1.0, 1.0, n=120)
    for P in (circle, circle[::-1]):
        ln = cels.contour(P, 0.01, light=(0, 1), lit=0.3, dark=1.4)
        top, bottom = np.argmax(P[:, 1]), np.argmin(P[:, 1])
        assert ln.closed and ln.widths[top] == pytest.approx(0.3, abs=0.03)
        assert ln.widths[bottom] == pytest.approx(1.4, abs=0.03)
    # an open line: told which side is out
    arc_ = cels.arc((0, 0), 1.0, 1.0, 0, 180, n=60)       # counterclockwise over the top: outside is its right
    w = cels.lit_widths(arc_, (0, 1), closed=False, outward=-1, lit=0.3, dark=1.4)
    assert w[30] == pytest.approx(0.3, abs=0.05) and w[30] < w[0]


def test_strips_cut_the_band_between_two_lines():
    a = np.c_[np.linspace(0, 1, 20), np.zeros(20)]
    b = np.c_[np.linspace(0, 1, 20), np.ones(20)]
    parts = cels.strips(a, b, 4, seed=3, vary=0.3, n=32)
    assert len(parts) == 4
    # they tile the band: the first starts on a, the last ends on b, each shares its edge with the next
    assert np.allclose(parts[0][:32], cels.resample(a, 32)) and np.allclose(parts[-1][32:][::-1], cels.resample(b, 32))
    for p, q in zip(parts[:-1], parts[1:]):
        assert np.allclose(p[32:][::-1], q[:32])
    assert sum(np.ptp(p[:, 1]) for p in parts) > 0.99


def test_lumpy_pushes_out_in_bumps_and_holds_its_ends():
    P = np.c_[np.linspace(0, 1, 200), np.zeros(200)]
    L = cels.lumpy(P, 0.1, 5, seed=2)
    assert np.allclose(L[0], P[0]) and np.allclose(L[-1], P[-1])
    assert L[:, 1].min() >= -1e-9 and 0.02 < L[:, 1].max() <= 0.1 + 1e-9    # to the left of a line run +x: up


def test_clumps_hang_at_two_scales():
    P = np.c_[np.linspace(0, 1, 40), np.zeros(40)]
    C = cels.clumps(P, 0.2, 5, fine=0.3, fine_count=30, seed=1)
    assert np.allclose(C[0], (0, 0)) and np.allclose(C[-1], (1, 0))
    assert C[:, 1].max() <= 1e-9 and -0.2 - 1e-6 <= C[:, 1].min() < -0.08
    y = C[:, 1]
    tips = [i for i in range(1, len(y) - 1) if y[i] < y[i - 1] and y[i] <= y[i + 1]]
    assert len(tips) > 8                                                       # more points than clumps


def test_tufts_stick_out_of_their_line():
    P = np.c_[np.linspace(0, 1, 50), np.zeros(50)]
    out = cels.tufts(P, 12, length=(0.05, 0.1), width=(0.02, 0.03), droop=0.0, seed=3)
    assert len(out) == 12
    for T in out:
        assert abs(T[0, 1]) < 1e-9 and abs(T[-1, 1]) < 1e-9                # rooted on the line
        assert T[2, 1] > 0.02                                                # the tip out to the left (up)
    down = cels.tufts(P, 6, droop=1.0, seed=3)
    assert all(T[2, 1] < 0 for T in down)                                    # hanging
