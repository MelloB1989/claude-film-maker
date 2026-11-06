"""lib/garmentfit: the numbers behind blender/garment_fit.py, without Blender."""
import numpy as np
import pytest

from lib import garmentfit as GF


def test_regions_from_dominant_bone():
    groups = ["neck_01", "clavicle_l", "upperarm_l", "spine_05", "spine_02", "pelvis", "foo"]
    W = np.eye(7)
    W[3, 0] = 0.4  # chest with some neck: still chest
    r = GF.regions(W, groups)
    assert [GF.REGIONS[i] for i in r] == ["collar", "shoulder", "sleeve", "chest", "waist", "hem", "other"]
    assert GF.regions(np.zeros((1, 7)), groups)[0] == GF.REGIONS.index("other")


def test_targets_and_displacement():
    reg = np.array([GF.REGIONS.index("collar"), GF.REGIONS.index("hem"), GF.REGIONS.index("chest"),
                    GF.REGIONS.index("chest")])
    t = GF.targets(reg, {"chest": 2.0})
    assert list(t) == [0.8, 2.8, 2.0, 2.0]
    dist = np.array([-0.5, 3.0, 1.0, 9.0])  # inside at the collar, fine at the hem, tight, very loose
    d = GF.fit_displacement(dist, t, slack=3.0, pull=0.5)
    assert d[0] == pytest.approx(1.3) and d[1] == 0 and d[2] == pytest.approx(1.0) and d[3] == pytest.approx(-2.0)


def grid(n=6):
    xs, ys = np.meshgrid(np.arange(n), np.arange(n))
    X = np.c_[xs.ravel(), ys.ravel(), np.zeros(n * n)].astype(float)
    T = []
    for y in range(n - 1):
        for x in range(n - 1):
            i = y * n + x
            T += [(i, i + 1, i + n), (i + 1, i + n + 1, i + n)]
    return X, np.array(T)


def test_smooth_field_keeps_pins_and_floor():
    X, T = grid()
    nb = GF.neighbours(len(X), T)
    v = np.zeros(len(X))
    v[14] = 6.0
    pinned = np.zeros(len(X), bool)
    pinned[0] = True
    v[0] = 1.0
    s = GF.smooth_field(v, nb, iters=5, pinned=pinned, floor=np.full(len(X), 0.1))
    assert s[0] == 1.0 and s.min() >= 0.1 and s[14] < 6.0 and s[15] > 0.1


def test_transfer_weights_barycentric():
    bx = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], float)
    bt = np.array([[0, 1, 2]])
    bw = np.array([[1, 0], [0, 1], [0, 1]], float)
    W = GF.transfer_weights(np.array([[0.25, 0.25, 0.3], [5, 5, 5]], float), [((0.25, 0.25, 0.0), 0), None], bx, bt, bw)
    assert W[0] == pytest.approx([0.5, 0.5]) and W[1] == pytest.approx([0, 1])


def test_limit_normalize():
    W = GF.limit_normalize(np.array([[0.5, 0.3, 0.2, 0.005], [0, 0, 0, 0]]), max_inf=2)
    assert W[0] == pytest.approx([0.625, 0.375, 0, 0]) and W[1].sum() == 0


def test_colours_encoding():
    c = GF.colours(np.array([0.0, 2.5, 9.0]), np.array([True, False, False]))
    assert c[:, 0] == pytest.approx([0, 0.5, 1]) and list(c[:, 1]) == [1, 0, 0] and (c[:, 3] == 1).all()


def test_ease_report_and_gate():
    reg = np.array([GF.REGIONS.index("chest")] * 100)
    shell = GF.ease_report(np.full(100, 1.0) + np.linspace(0, 0.1, 100), reg)
    assert shell["chest"]["median"] == pytest.approx(1.05, abs=0.01)
    assert any("shell" in p for p in GF.fit_gate(shell))
    drape = GF.ease_report(np.linspace(0.6, 4.0, 100), reg)
    assert GF.fit_gate(drape) == []
    bad = GF.ease_report(np.r_[np.full(5, -0.2), np.linspace(0.6, 4, 95)], reg)
    assert any("inside" in p for p in GF.fit_gate(bad))
    assert GF.fit_gate(GF.ease_report(np.full(3, 50.0), reg[:3]))[0].startswith("no garment vertex")


def test_harmonic_fill_interpolates_a_hole():
    X, T = grid(7)
    E = GF.edges_of(T)
    known = np.ones(len(X), bool)
    known[[16, 17, 23, 24, 30, 31]] = False  # a hole in the middle
    v = X[:, 0].copy()  # a linear field: the fill must reproduce it
    v[~known] = 0.0
    f = GF.harmonic_fill(v, known, E, iters=500)
    assert np.allclose(f, X[:, 0], atol=1e-3)


def test_morph_onto_a_cut_body():
    X, T = grid(7)
    ref = X.copy()  # another person: flat
    target = X + np.array([0, 0, 0.5])  # ours: 0.5 cm higher, and cut in the middle (no surface there)
    cut = set([16, 17, 23, 24, 30, 31])

    def nearest(p):
        i = int(np.argmin(((X - p) ** 2).sum(1)))
        return None if i in cut else target[i]
    M, known, st = GF.morph_onto(ref, T, nearest, match_cm=1.0)
    assert not known[list(cut)].any() and np.allclose(M[:, 2], 0.5, atol=1e-3) and st["fill_median_cm"] == 0.5


def test_blend_weights_by_region():
    X, T = grid(4)
    nb = GF.neighbours(len(X), T)
    region = np.array([GF.REGIONS.index("collar")] * 8 + [GF.REGIONS.index("hem")] * 8)
    a = GF.region_alpha(region, ("collar",), nb, smooth_iters=0)
    assert list(a[:8]) == [1] * 8 and list(a[8:]) == [0] * 8
    Wa, ga = np.tile([[1.0, 0.0]], (16, 1)), ["neck_01", "spine_05"]
    Wb, gb = np.tile([[1.0, 0.0]], (16, 1)), ["pelvis", "spine_05"]
    W, names = GF.blend_weights(Wa, ga, Wb, gb, a)
    assert names == ["neck_01", "spine_05", "pelvis"]
    assert W[0] == pytest.approx([1, 0, 0]) and W[15] == pytest.approx([0, 0, 1])
    a2 = GF.region_alpha(region, ("collar",), nb, smooth_iters=3)
    W2, _ = GF.blend_weights(Wa, ga, Wb, gb, a2)
    assert np.allclose(W2.sum(1), 1) and 0 < a2[8] < 1


def test_keep_factor_ramps_from_the_kept_band():
    X = np.array([[0, 0, z] for z in range(8)], float)
    region = np.array([GF.REGIONS.index("collar")] * 2 + [GF.REGIONS.index("chest")] * 6)
    f = GF.keep_factor(X, region, ("collar",), ramp_cm=4.0)
    assert list(f[:2]) == [1, 1] and f[2] == pytest.approx(0.75) and f[5] == 0 and f[7] == 0
    assert not GF.keep_factor(X, region, (), 4.0).any()
