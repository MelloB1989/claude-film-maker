"""Off-box tests of garment_measure.py's pure helpers (synthetic meshes, no editor):
    python3 -m pytest films/host-studio/reel/r7/test_garment_measure.py -q"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import garment_measure as gm  # noqa: E402


def sphere(c, r, n=16):
    """UV sphere (P, T) with outward winding."""
    P = [(c[0], c[1], c[2] + r)]
    for i in range(1, n):
        ph = math.pi * i / n
        for j in range(n):
            th = 2 * math.pi * j / n
            P.append((c[0] + r * math.sin(ph) * math.cos(th), c[1] + r * math.sin(ph) * math.sin(th),
                      c[2] + r * math.cos(ph)))
    P.append((c[0], c[1], c[2] - r))
    T = []
    for j in range(n):
        T.append((0, 1 + j, 1 + (j + 1) % n))
    for i in range(n - 2):
        for j in range(n):
            a, b = 1 + i * n + j, 1 + i * n + (j + 1) % n
            T += [(a, a + n, b), (b, a + n, b + n)]
    last = len(P) - 1
    base = 1 + (n - 2) * n
    for j in range(n):
        T.append((base + j, last, base + (j + 1) % n))
    return P, T


def test_closest_on_tri_regions():
    a, b, c = (0, 0, 0), (1, 0, 0), (0, 1, 0)
    assert math.dist(gm.closest_on_tri((0.2, 0.2, 5), a, b, c), (0.2, 0.2, 0)) < 1e-9
    assert gm.closest_on_tri((-1, -1, 0), a, b, c) == a
    q = gm.closest_on_tri((0.5, -1, 0), a, b, c)
    assert math.dist(q, (0.5, 0, 0)) < 1e-9
    q = gm.closest_on_tri((1, 1, 0), a, b, c)
    assert math.dist(q, (0.5, 0.5, 0)) < 1e-9


def test_sphere_winding_is_outward():
    P, T = sphere((0, 0, 0), 5.0)
    for t in T[:40]:
        n = gm.tri_normal(*(P[i] for i in t))
        m = tuple(sum(P[i][k] for i in t) / 3 for k in range(3))
        assert gm.dot(n, m) > 0


def test_clearance_sign_outside_and_inside():
    P, T = sphere((0, 0, 0), 10.0, 24)
    keep = set(range(len(P)))
    grid = gm.TriGrid(gm.torso_tris(P, T, keep, "Body"), 2.0)
    worst, neg, lt3 = gm.clearance(grid, [(0, (14.0, 0, 0)), (1, (0, 16.0, 0))])
    assert abs(worst[0] - 4.0) < 0.2 and neg == 0 and lt3 == 0
    worst, neg, lt3 = gm.clearance(grid, [(0, (14.0, 0, 0)), (1, (8.0, 0, 0))])
    assert -2.3 < worst[0] < -1.7 and neg == 1 and lt3 == 1


def test_shell_normals_turned_out_from_spine():
    P, T = sphere((0, 0, 0), 10.0, 24)
    T = [(a, c, b) for a, b, c in T]  # inward winding: a garment's inner face
    keep = set(range(len(P)))
    chain = [(0, 0, -20.0), (0, 0, 20.0)]
    grid = gm.TriGrid(gm.torso_tris(P, T, keep, "Top", chain), 2.0)
    worst, neg, _ = gm.clearance(grid, [(0, (8.0, 0, 0))])
    assert worst[0] < 0 and neg == 1
    worst, neg, _ = gm.clearance(grid, [(0, (13.0, 0, 0))])
    assert worst[0] > 0 and neg == 0


def test_label_and_arm_sets():
    segs = {"spine:pelvis": ((0, 0, 0), (0, 0, 50)), "upperarm_r": ((-20, 0, 45), (-30, 0, 20)),
            "clavicle_r": ((0, 0, 45), (-20, 0, 45))}
    P = [(0, 5, 20), (-27, 0, 27), (-21, 0, 43), (-3, 0, 44), (-30, 3, 21), (-31, 0, 23)]
    lab = gm.label_rest(P, segs)
    assert lab[0][0] == "spine:pelvis" and lab[1][0] == "upperarm_r" and lab[3][0] == "clavicle_r"
    arm, torso = gm.arm_sets(lab, P, (-20, 0, 45), "r", 0.3, 7.0)
    assert arm == [1, 4, 5]    # vertex 2 is at the shoulder end (t < 0.3)
    assert sorted(torso) == [0, 3]


def test_arm_radius_keeps_side_skin_out_of_the_arm():
    """v2b run 1: her side under the A-pose arm was nearest the upper arm's bone and counted as arm (-10.4 cm)."""
    segs = {"spine:pelvis": ((0, 0, 0), (0, 0, 50)), "upperarm_r": ((-20, 0, 45), (-30, 0, 20))}
    skin = [(-30 + 3.5 * math.cos(a), 3.5 * math.sin(a), 22.0) for a in (0, 1.5, 3.0, 4.5)]  # arm skin, t ~ 0.9
    side = [(-16.0, 0.0, 27.0)]                                                              # side, 10 cm off
    P = skin + side
    lab = gm.label_rest(P, segs)
    assert lab[4][0] == "upperarm_r"
    r = gm.arm_radius(lab, "r")
    assert abs(r - 3.5) < 0.3
    arm, torso = gm.arm_sets(lab, P, (-20, 0, 45), "r", 0.3, 7.0, r * 1.3)
    assert arm == [0, 1, 2, 3] and torso == [4]


def ring(t, r, n=72, dth=0.0):
    return [(t, r, -180.0 + 360.0 * k / n + dth) for k in range(n)]


def test_waist_fitted_band_reads_small():
    skin = [x for t in range(-10, 20) for x in ring(t + 0.5, 12.0)]
    top = [x for t in range(-4, 20) for x in ring(t + 0.5, 12.4)]
    trou = [x for t in range(-20, 6) for x in ring(t + 0.5, 12.8) + ring(t + 0.5, 13.0)]
    secs = gm.waist_sectors(trou, top, skin, 4.0)
    s0 = secs[0]
    assert s0["deg"] == 0 and abs(s0["edge_t"] - 5.5) < 1e-6
    assert abs(s0["gap_max"] - 0.4) < 1e-6 and s0["poke_max"] < 0 and s0["tuck"] == 9.0
    score, why, poke, _ = gm.waist_score(secs)
    assert score == 0.4 and why.startswith("gap") and poke < 0


def test_waist_loose_front_and_bare_skin():
    skin = [x for t in range(-10, 20) for x in ring(t + 0.5, 12.0)]
    top = [x for t in range(3, 20) for x in ring(t + 0.5, 12.4)]  # rides up: hem above the edge
    trou = [(t, (15.0 if abs(th) < 40 else 12.8), th) for t in [x + 0.5 for x in range(-20, 2)]
            for _, _, th in ring(0, 0)]
    secs = gm.waist_sectors(trou, top, skin, 4.0)
    front = secs[0]
    assert front["tuck"] == -2.0 and abs(front["gap_max"] - 3.0) < 1e-6
    score, why, _, _ = gm.waist_score(secs)
    assert score == 3.0 and "gap at" in why
    back = secs[12]
    assert back["deg"] == 180 and abs(back["gap_max"] - 0.8) < 1e-6


def test_waist_poke_and_arms_ignored():
    skin = [x for t in range(-10, 20) for x in ring(t + 0.5, 12.0)]
    skin += [(0.5, 13.6, 0.0)]          # belly through the band, front
    skin += [(0.5, 25.0, 90.0)]         # a hand at her side: not a poke
    trou = [x for t in range(-20, 3) for x in ring(t + 0.5, 12.6) + ring(t + 0.5, 12.8)]
    secs = gm.waist_sectors(trou, [], skin, 4.0)
    assert abs(secs[0]["poke_max"] - 0.8) < 1e-6
    assert secs[6]["deg"] == 90 and secs[6]["poke_max"] < 0
    fit, _, poke, where = gm.waist_score(secs)
    assert fit == 0.6 and poke == 0.8 and where.startswith("skin at 0 deg")


def test_natural_waist_and_cyl():
    skin = [x for t in range(-10, 20) for x in ring(t + 0.5, 10.0 + abs(t - 6) * 0.3)]
    nw = gm.natural_waist(skin, -10, 20)
    assert nw[0] == 6.5
    cy = gm.Cyl((0, 0, 0), (0, 0, 10), (1, 0, 0), (0, 1, 0))
    t, r, th = cy((0, 5, 3))
    assert (t, r, round(th)) == (3, 5, 90)
    t, r, th = cy((0, -5, 3))
    assert round(th) == -90


def test_parse_frames():
    assert gm.parse_frames("29,1290-1300:5, 7") == [29, 1290, 1295, 1300, 7]


def test_point_beside_an_open_patch_is_not_inside():
    """v2b2 ref pose: an arm point beside the torso patch's cut edge read as 13.7 cm 'inside'."""
    P = [(0, 0, 0), (10, 0, 0), (0, 10, 0), (10, 10, 0)]   # a flat patch facing +z, open edges all round
    T = [(0, 1, 2), (1, 3, 2)]
    grid = gm.TriGrid(gm.torso_tris(P, T, {0, 1, 2, 3}, "Top"), 2.0)
    worst, neg, _ = gm.clearance(grid, [(0, (20.0, 5.0, -2.0))])   # off the edge, a little below the plane
    assert worst[0] > 0 and neg == 0
    worst, neg, _ = gm.clearance(grid, [(0, (5.0, 5.0, -2.0))])    # right behind the face
    assert abs(worst[0] + 2.0) < 1e-6 and neg == 1


def test_deltoid_near_the_shoulder_is_not_torso():
    """v2b r7w ref pose: a point at t 0.25, 5.1 cm off the upper-arm bone counted as torso beside arm points at t 0.3."""
    segs = {"spine:pelvis": ((0, 0, 0), (0, 0, 50)), "upperarm_r": ((-20, 0, 45), (-30, 0, 20))}
    lab = {0: ("upperarm_r", 0.25, 5.1), 1: ("upperarm_r", 0.6, 7.0), 2: ("upperarm_r", 0.33, 2.9)}
    P = [(-40, 0, 40), (-40, 0, 20), (-40, 0, 30)]   # all far from the shoulder joint: only the t rule decides
    arm, torso = gm.arm_sets(lab, P, (-20, 0, 45), "r", 0.3, 7.0, 4.08)
    assert arm == [2] and torso == [1]


def test_far_point_behind_a_curved_patch_is_not_inside():
    """R7 f1104: a raised arm 13.9 cm off the torso patch read 'behind' a face: inside needs nearer the spine too."""
    P = [(0, 0, 0), (10, 0, 0), (0, 10, 0), (10, 10, 0)]    # a patch facing +z, the spine far below it at z -10
    T = [(0, 1, 2), (1, 3, 2)]
    chain = [(5, 5, -10.0), (5, 5, -9.0)]
    grid = gm.TriGrid(gm.torso_tris(P, T, {0, 1, 2, 3}, "Top"), 2.0)
    worst, neg, _ = gm.clearance(grid, [(0, (5.0, 5.0, -2.0))], chain=chain)       # between face and spine
    assert worst[0] < 0 and neg == 1
    chain2 = [(5, 5, 10.0), (5, 5, 11.0)]                                         # spine on the other side
    worst, neg, _ = gm.clearance(grid, [(0, (5.0, 5.0, -2.0))], chain=chain2)
    assert worst[0] > 0 and neg == 0


def test_front_deg_is_square_to_a_leaning_spine():
    chain = [(0, 0, 0), (0, 0, 10), (3, 0, 20)]           # X forward, spine leaning forward up top
    fwd = (1, 0, 0)
    assert abs(gm.front_deg((10, 0, 5), chain, fwd)) < 1e-6
    assert abs(gm.front_deg((0, 10, 5), chain, fwd) - 90) < 1e-6
    assert abs(gm.front_deg((-10, 0, 5), chain, fwd) - 180) < 1e-6
    assert abs(gm.front_deg((5, 5, 5), chain, fwd) - 45) < 1e-6
    assert gm.front_deg((5, 0, 25), chain, fwd) < 1e-6      # past the top: still in front of the leaning segment


def test_zones_split_bust_from_side():
    """ee99f626: an arm 1 cm off her side is fine (side >= 0.5); the bust zone is what the 3 cm line is for."""
    P, T = sphere((0, 0, 0), 10.0, 24)
    keep = set(range(len(P)))
    chain = [(0, 0, -20.0), (0, 0, 20.0)]
    ents = gm.torso_tris(P, T, keep, "Body")
    fr, sd = gm.split_front(ents, ents, chain, (1, 0, 0), 60.0)
    assert fr and sd and len(fr) + len(sd) == len(ents)
    arm = [(0, (0, 11.0, 0))]                              # beside her, 1 cm off the side
    side_w, _, _ = gm.clearance(gm.TriGrid(sd, 2.0), arm, chain=chain)
    front_w, _, _ = gm.clearance(gm.TriGrid(fr, 2.0), arm, chain=chain)
    assert abs(side_w[0] - 1.0) < 0.2 and front_w[0] > 3.0
    arm = [(0, (8.0, 0, 0))]                               # into the bust
    front_w, neg, _ = gm.clearance(gm.TriGrid(fr, 2.0), arm, chain=chain)
    assert front_w[0] < 0 and neg == 1
