"""fmbridge.qa.clip (qa.clip's rules) and fmbridge.qa.garment_look (the armor index) on synthetic layers."""
import math

import pytest

from _qa_load import load

load()
from fmqa import clip, garment_look as GL  # noqa: E402

E = clip.EMPTY
W, H = 40, 30


def layer(fill=E):
    return [fill] * (W * H)


def rect(L, x0, y0, x1, y1, z):
    for y in range(y0, y1):
        for x in range(x0, x1):
            L[y * W + x] = z
    return L


def torso():
    """A tee (front at 100 cm) over a body 1 cm under it, the body cut away under the tee except a rim."""
    tee = rect(layer(), 10, 10, 30, 30, 100.0)
    body = rect(layer(), 10, 10, 30, 30, 101.0)
    return tee, body


def test_pairs_defaults():
    p = clip.pairs(["Body", "Face", "tee", "Trousers", "shoes"])
    assert ("Body", "tee") in p and ("Face", "tee") in p and ("Body", "shoes") in p
    assert ("Face", "Trousers") not in p and ("Trousers", "tee") in p and ("shoes", "Trousers") in p


def test_clean_frame_has_no_clip():
    tee, body = torso()
    r = clip.judge_pair({"Body": body, "tee": tee}, "Body", "tee", W, H)
    assert r["px"] == 0 and r["fraction"] == 0 and r["g_px"] == 400


def test_poke_at_an_intersection_edge_counts():
    tee, body = torso()
    rect(body, 15, 15, 18, 18, 99.0)  # 1 cm out through the tee, next to body just under it
    r = clip.judge_pair({"Body": body, "tee": tee}, "Body", "tee", W, H)
    assert r["px"] == 9 and r["fraction"] == pytest.approx(9 / 400) and r["clusters"][0]["worst_cm"] == 1.0
    assert r["seen"] == 1.0


def test_arm_in_front_of_a_cut_torso_does_not_count():
    tee = rect(layer(), 10, 10, 30, 30, 100.0)
    body = layer()  # the torso skin is cut away under the tee
    rect(body, 15, 12, 19, 28, 98.0)  # an arm 2 cm in front: in band, but no intersection edge
    r = clip.judge_pair({"Body": body, "tee": tee}, "Body", "tee", W, H)
    assert r["raw"] > 0 and r["px"] == 0


def test_opening_beyond_band_is_not_clip():
    tee, body = torso()
    rect(body, 15, 15, 18, 18, 85.0)  # 15 cm nearer: seen through an opening, not through the cloth
    assert clip.judge_pair({"Body": body, "tee": tee}, "Body", "tee", W, H)["px"] == 0


def neck_scene(patch_rows=0):
    """Face (neck) above a tee whose front collar rim is at row 12; the tee's inside back seen at 108 above it.
    patch_rows > 0: the face comes 1 cm out through the tee that many rows from row 20 (well under the band)."""
    tee = layer()
    rect(tee, 10, 12, 30, 30, 100.0)
    rect(tee, 14, 8, 26, 12, 108.0)  # the inside of the back collar seen over the front rim
    face = layer()
    rect(face, 14, 0, 26, 12, 103.0)  # the neck, in front of the back collar, behind nothing
    rect(face, 14, 12, 26, 30, 100.8)  # the face mesh's lower neck under the tee
    if patch_rows:
        rect(face, 17, 20, 23, 20 + patch_rows, 99.0)
    return {"Face": face, "tee": tee}


def test_neck_px_zero_on_a_clean_collar_and_counts_a_patch():
    L = neck_scene()
    fr = clip.judge_frame(L, W, H, 30.0)
    assert fr["neck_px"]["px"] == 0 and fr["neck_px"]["rim_cols"] > 0
    L = neck_scene(patch_rows=3)
    fr = clip.judge_frame(L, W, H, 30.0)
    assert fr["neck_px"]["px"] == 18 and fr["Face>tee"]["px"] == 18
    issues = clip.gate({"Reel_S15": {1082: fr}}, "Host")
    assert [i["code"] for i in issues] == ["clip.neck"] and "garment.fit" in issues[0]["fix"]


def test_neck_clip_hugging_the_opening_is_at_opening():
    L = neck_scene()
    rect(L["Face"], 14, 12, 16, 13, 99.5)  # in the collar band: the neck at the collar's edge
    assert clip.judge_frame(L, W, H, 30.0)["neck_px"]["px"] == 0
    rect(L["Face"], 14, 12, 16, 15, 99.5)  # 2 rows under the band, but hugging the opening (3 px at this scale)
    assert clip.judge_frame(L, W, H, 30.0)["neck_px"]["px"] == 4
    n = clip.judge_frame(L, W, H, 30.0, at_open_960=72.0)["neck_px"]
    assert n["px"] == 0 and n["at_opening"] == 4


def test_gate_pairs_before_and_silhouette():
    tee, body = torso()
    rect(body, 15, 15, 18, 18, 99.0)
    fr = clip.judge_frame({"Body": body, "tee": tee}, W, H, 30.0)
    fr.pop("_mask")
    frames = {"S1": {10: fr}}
    assert [i["code"] for i in clip.gate(frames, "Ada")] == ["clip.pair"]
    assert clip.gate(frames, "Ada", before=frames) == []  # judged against its own before
    fr["silhouette"] = clip.silhouette(tee, rect(layer(), 10, 10, 30, 29, 1.0))  # the reference 5% smaller
    assert fr["silhouette"]["pct"] == 5.26
    codes = [i["code"] for i in clip.gate(frames, "Ada", before=frames)]
    assert codes == ["clip.silhouette"]
    s = clip.summarize(frames)
    assert s["Body>tee"]["at"] == "S1@10" and s["silhouette"]["pct"] == 5.26


def test_gate_flags_a_shot_error_and_missing_neck():
    fr = {"Face>tee": {"fraction": 0.0, "px": 0}}
    codes = [i["code"] for i in clip.gate({"S1": {"error": "no camera cut"}, "S2": {5: fr}}, "Host")]
    assert codes == ["clip.shot_error", "clip.neck_missing"]


# --- armor index ----------------------------------------------------------------------------------------------------

def test_project_px_center_and_offsets():
    cam = {"loc": [0, 0, 0], "rot": {"pitch": 0, "yaw": 0, "roll": 0}, "fov": 90.0}
    x, y, z = clip.project_px(cam, (100, 0, 0), 160, 90)
    assert (round(x, 3), round(y, 3), z) == (80.0, 45.0, 100.0)
    x, y, _ = clip.project_px(cam, (100, 50, 0), 160, 90)  # half-way to the right edge at tan(45) = 1
    assert round(x, 3) == 120.0
    x, y, _ = clip.project_px(cam, (100, 0, 25), 160, 90)  # up: 25 / 100 of the half-width, scaled to the height
    assert round(y, 3) == round(45 - 0.25 * 80, 3)
    assert clip.project_px(cam, (-10, 0, 0), 160, 90)[2] < 0


def test_mouth_blocked_by_a_mic_in_front_and_clear_below():
    face = rect(layer(), 10, 5, 30, 25, 100.0)
    mic = rect(layer(), 17, 16, 23, 30, 80.0)  # a mic in front, its head at rows 16+
    centers = [(20, 12, 100.0)]  # the mouth at row 12, radius 3: clear of the mic
    r = clip.mouth_blocked({"Face": face, "Mic": mic}, centers, 3, w=W, h=H)
    assert r["blocked_px"] == 0 and r["disc_px"] > 20
    r = clip.mouth_blocked({"Face": face, "Mic": mic}, [(20, 16, 100.0)], 3, w=W, h=H)
    assert r["blocked_px"] > 0 and r["box"]
    behind = rect(layer(), 17, 10, 23, 30, 120.0)  # behind the face: never covers the mouth
    assert clip.mouth_blocked({"Face": face, "Mic": behind}, [(20, 12, 100.0)], 3, w=W, h=H)["blocked_px"] == 0


def test_gate_mouth_and_set_pairs():
    frames = {"WA_C1": {10: {"Body>Chair": {"fraction": 0.0, "px": 0},
                             "mouth": {"disc_px": 30, "blocked_px": 0, "share": 0.0}},
                        20: {"Body>Chair": {"fraction": 0.02, "px": 12, "clusters": [{"worst_cm": 1.1}]},
                             "mouth": {"disc_px": 30, "blocked_px": 4, "share": 0.13, "blocker": "Mic"}},
                        30: {"mouth": {"error": "the face has no bone 'X'"}}}}
    codes = [(i["code"], i["frame"]) for i in clip.gate(frames, "Host")]
    assert ("clip.pair", 20) in codes and ("clip.mouth", 20) in codes and ("clip.mouth", 30) in codes
    assert ("clip.mouth", 10) not in codes
    w = clip.summarize(frames)
    assert w["mouth"]["blocked_px"] == 4 and w["Body>Chair"]["fraction"] == 0.02


def test_ease_stats_shell_vs_drape():
    shell = GL.ease_stats([1.0 + 0.05 * math.sin(i) for i in range(500)])
    drape = GL.ease_stats([0.3 + 4.0 * (i / 499) ** 2 for i in range(500)])
    assert shell["spread"] < 0.2 and drape["spread"] > 1.0
    assert GL.ease_stats([20.0, float("nan")])["n"] == 0


def test_silhouette_ratio():
    body = rect(layer(), 15, 5, 25, 25, 100.0)
    tee = rect(layer(), 14, 10, 26, 20, 99.0)
    r = GL.silhouette_ratio(tee, body, W, H)
    assert r["rows"] == 10 and r["ratio"] == pytest.approx(120 / 100)


def test_detail_energy_smooth_vs_wrinkled():
    mask = {y * W + x for y in range(5, 25) for x in range(5, 35)}
    flat = ([0.0] * (W * H), [0.0] * (W * H), [1.0] * (W * H))
    wr = ([0.3 * math.sin(x * 1.7) for y in range(H) for x in range(W)], [0.0] * (W * H), [1.0] * (W * H))
    assert GL.detail_energy(flat, mask, W, H)["energy"] == 0.0
    assert GL.detail_energy(wr, mask, W, H)["energy"] > 0.1


def test_secondary_motion_skinned_vs_simulated():
    body = [[[f * 2.0, 0.0, 0.0]] * 4 for f in range(6)]
    skinned = [[[p[0], p[1] + 1.0, p[2]] for p in fr] for fr in body]
    sim = [[[p[0] - 0.6 * math.sin(f), p[1] + 1.0, p[2]] for p in fr] for f, fr in enumerate(body)]
    assert GL.secondary_motion(skinned, body)["ratio"] == 0.0
    assert GL.secondary_motion(sim, body)["ratio"] > 0.15
    assert GL.secondary_motion(body, body[:1])["ratio"] is None


def test_round4_tee_reads_as_armor_and_a_draped_sim_tee_as_cloth():
    armor = GL.look({"ease": GL.ease_stats([0.9 + 0.1 * math.sin(i) for i in range(400)]), "thickness_cm": 0.7,
                     "silhouette": 1.16, "detail": 0.008, "motion": 0.0,
                     "wpo": {"FM_Inflate": 0.15, "FM_Neck": 0.75, "FM_Patch": 1.76}}, "Host tee")
    assert armor["verdict"] == "armor" and not armor["pass"]
    codes = [i["code"] for i in armor["issues"]]
    assert codes[0] == "garment.wpo_inflate" and "garment.armor_detail" in codes and "garment.armor_motion" not in codes
    cloth = GL.look({"ease": GL.ease_stats([0.4 + 3.5 * (i / 399) ** 1.5 for i in range(400)]), "thickness_cm": 0.15,
                     "silhouette": 1.06, "detail": 0.11, "motion": 0.2, "wpo": {"FM_Inflate": 0.0}}, "Host tee")
    assert cloth["verdict"] == "cloth" and cloth["pass"] and cloth["index"] < 0.1 and not cloth["issues"]


def test_armor_without_wpo_still_fails_on_the_index():
    r = GL.look({"ease": GL.ease_stats([1.2] * 50), "thickness_cm": 0.9, "silhouette": 1.3, "detail": 0.005})
    assert r["verdict"] == "armor" and r["issues"][0]["code"] == "garment.armor" and "motion" in r["missing"]
    assert GL.look({})["pass"] is False


def test_box_calibration_round5():
    """The box's G3/G3b numbers (06 Nov): his round-4 WPO tee reads armor on the index alone, her fitted Top cloth;
    silhouette and motion (broken reference-body capture) are reported, not scored."""
    his = GL.look({"ease": {"n": 1500, "median": 0.775, "spread": 4.867}, "thickness_cm": 0.336, "silhouette": 2.2986,
                   "detail": 0.04971, "motion": 0.2258, "wpo": {"FM_Inflate": 0.15, "FM_Neck": 0.75, "FM_Patch": 1.76}})
    hers = GL.look({"ease": {"n": 1500, "median": 0.307, "spread": 4.103}, "thickness_cm": 0.159, "silhouette": 1.3914,
                    "detail": 0.10504, "motion": 0.0964, "wpo": {}})
    assert his["verdict"] == "armor" and his["index"] >= 0.5 and his["terms"]["silhouette"]["score"] is None
    assert hers["verdict"] == "cloth" and hers["index"] < 0.1
    no_wpo = GL.look({**{"ease": {"n": 1500, "median": 0.775, "spread": 4.867}}, "thickness_cm": 0.336,
                      "detail": 0.04971})
    assert no_wpo["verdict"] == "borderline" and no_wpo["index"] >= 0.35  # the smooth shell alone, no WPO


def ring(r0, gap, n=60, thick=0.3, axial=0.0):
    """A collar ring round the neck axis: inner wall at radial r0 (its gap to the skin `gap`), outer wall `thick`
    further out."""
    ax, rad, gp = [], [], []
    for k in range(n):
        for w in (0.0, thick):
            ax.append(axial)
            rad.append(r0 + w)
            gp.append(gap + w)
    return ax, rad, gp


def test_collar_hugging_vs_floating_vs_rolled():
    hug = GL.collar_stats(*ring(6.0, 0.2))
    assert hug["gap_cm"] <= 0.5 and hug["spread_cm"] <= 0.31 and not hug["roll"]
    floating = GL.collar_stats(*ring(7.6, 1.8))
    assert floating["gap_cm"] > 0.8 and floating["roll"]
    a, r, g = ring(6.0, 0.3)
    a2, r2, g2 = ring(7.8, 2.0, thick=0.4)  # a rolled lip standing out of the band
    rolled = GL.collar_stats(a + a2, r + r2, g + g2)
    assert rolled["spread_cm"] > GL.COLLAR_SPREAD_CM and rolled["roll"]
    assert GL.collar_stats([20.0], [5.0], [0.1])["n"] == 0  # outside the window
    a, r, g = ring(6.0, 0.2)
    stray = GL.collar_stats(a + [0.0], r + [1.1], g + [5.3])  # one vertex near the axis does not make the ring
    assert stray["n"] == hug["n"] and stray["gap_cm"] == hug["gap_cm"]
    assert GL.collar_stats([0.0], [1.1], [5.3]) == {"n": 0, "too_few": 1}
    # a small band (30 v) among many shoulder verts further out: the ring is still the band
    a, r, g = ring(6.0, 0.2, n=15)
    a3, r3, g3 = ring(9.0, 2.6, n=600)
    small = GL.collar_stats(a + a3 + [0.0], r + r3 + [1.1], g + g3 + [5.3])
    assert small["n"] == 30 and small["gap_cm"] <= 0.5


def band(rx=5.5, ry=7.5, gap=0.2, wall=0.34, heights=(0.0, -0.5, -1.0, -1.5, -2.0), n=72, lip=0.0, fold=0.0):
    """An elliptic collar band (the neck is not round): inner + outer wall at each height and angle; `lip`: a rolled
    lip standing that far out of the band at its top, all round; plus shoulders sloping out below the band."""
    ax, rad, gp, ang = [], [], [], []
    for h in heights:
        for k in range(n):
            t = 2 * math.pi * k / n
            r0 = rx * ry / math.hypot(ry * math.cos(t), rx * math.sin(t))
            walls = (0.0, wall) + ((lip, lip + wall) if lip and h == heights[0] else ()) + \
                ((fold, fold + wall) if fold and h in (-0.5, -1.0) else ())
            for w in walls:
                ax.append(h)
                rad.append(r0 + w)
                gp.append(gap + w)
                ang.append(math.degrees(t) % 360)
    for k in range(n):  # the shoulders: below the band, sloping out
        t = 2 * math.pi * k / n
        for d in (1.0, 2.0, 3.0, 4.0):
            ax.append(-2.5 - d)
            rad.append(7.0 + 2 * d)
            gp.append(1.0)
            ang.append(math.degrees(t) % 360)
    return ax, rad, gp, ang


def test_collar_roll_is_local():
    a, r, g, ang = band()
    window = GL.collar_stats(a, r, g)
    local = GL.collar_stats(a, r, g, angle=ang)
    assert window["spread_cm"] > GL.COLLAR_SPREAD_CM and window["roll"]  # the old reading: a false roll
    assert local["spread_cm"] < 0.8 and not local["roll"] and local["spread_cells"] > 0, local
    a, r, g, ang = band(lip=1.8)  # a rolled lip at the same height and angle: still a roll
    rolled = GL.collar_stats(a, r, g, angle=ang)
    assert rolled["spread_cm"] > GL.COLLAR_SPREAD_CM and rolled["roll"]
    a, r, g, ang = band(fold=1.6)  # a two-layer fold inside the band, below its top: a roll
    folded = GL.collar_stats(a, r, g, angle=ang)
    assert folded["spread_cm"] > GL.COLLAR_SPREAD_CM and folded["roll"] and folded["spread_where"]["below_top_cm"] > 0
    a, r, g, ang = band(gap=2.447, lip=1.2)  # a cowl like Fit5 (its saved gap 2.447): fails
    assert GL.collar_stats(a, r, g, angle=ang)["roll"]
    a, r, g, ang = band(gap=1.8)  # a floating collar: the gap still fails it
    assert GL.collar_stats(a, r, g, angle=ang)["roll"]
    a, r, g, ang = band(n=12, heights=(0.0,))  # sparse (2 verts per 30 deg): no cell judged -> NOT measured, never 0
    sparse = GL.collar_stats(a, r, g, angle=ang)
    assert sparse["spread_cells"] == 0 and sparse["spread_cm"] is None and sparse["roll"] is None
    a, r, g, ang = band(n=12, heights=(0.0,), gap=1.8)  # ... but a floating gap still fails it
    assert GL.collar_stats(a, r, g, angle=ang)["roll"] is True
    m = {"collar": {"frames": 2, "gap_cm": 0.5, "spread_cm": None, "roll_frames": 0, "roll_unmeasured": 1}}
    look = GL.look(m, "Host")
    assert look["terms"]["collar_roll"]["value"] is None
    assert any(i["code"] == "garment.collar_roll" and i["severity"] == "fail" for i in look["issues"])


def test_look_fails_a_floating_collar_hard():
    base = {"ease": GL.ease_stats([0.4 + 3.5 * (i / 399) ** 1.5 for i in range(400)]), "thickness_cm": 0.15,
            "detail": 0.11, "wpo": {"FM_Inflate": 0.0}}
    ok = GL.look({**base, "collar": {"frames": 3, "gap_cm": 0.4, "spread_cm": 0.4, "roll_frames": 0}}, "Host tee")
    assert ok["pass"] and ok["terms"]["collar_gap"]["value"] == 0.4
    bad = GL.look({**base, "collar": {"frames": 3, "gap_cm": 1.9, "spread_cm": 1.7, "roll_frames": 3}}, "Host tee")
    assert not bad["pass"] and bad["verdict"] == "armor" and bad["issues"][0]["code"] == "garment.collar"
    assert "--keep-regions collar" in bad["issues"][0]["fix"]


def test_hem_flare():
    st = GL.hem_stats([19.4] * 40, [16.0] * 40)
    assert st["ratio"] == pytest.approx(1.2125) and st["ease_cm"] == 3.4
    assert GL.hem_stats([], [16.0])["n"] == 0
    base = {"detail": 0.11, "wpo": {}, "thickness_cm": 0.15}
    bad = GL.look({**base, "hem": {"frames": 2, "ratio": 1.21, "ease_cm": 3.4, "ref": "body"}})
    assert not bad["pass"] and any(i["code"] == "garment.hem_flare" for i in bad["issues"])
    assert GL.look({**base, "hem": {"frames": 2, "ratio": 1.11, "ease_cm": 1.8, "ref": "body"}})["pass"]


def test_hem_angle_independent_of_the_body():
    st = GL.hem_stats([19.5] * 20, [], upper_r=[16.0] * 20)
    assert st["angle_deg"] == pytest.approx(20.2, abs=0.1) and "ratio" not in st
    straight = GL.hem_stats([17.0] * 20, [16.0] * 20, upper_r=[16.6] * 20)
    assert straight["angle_deg"] < 3 and straight["ratio"] == pytest.approx(1.0625)


def yoke(a, r, g, ang, n=72, top=0.0):
    """The yoke of a crew neck flowing out over the shoulder at the side/back, inside the roll depth: a near-flat
    surface 0.3-1.6 cm below the band's top, from just outside the band to 4 cm out (its normals ALONG the neck)."""
    wall = [True] * len(a)
    for k in range(n):
        t = 2 * math.pi * k / n
        if not (math.cos(t) > 0.3):  # one side only, like the shoulder
            continue
        for j in range(8):
            a.append(top - 0.3 - 0.15 * j)
            r.append(6.0 + 0.5 * j)
            g.append(1.0)
            ang.append(math.degrees(t) % 360)
            wall.append(False)
    return a, r, g, ang, wall


def test_collar_roll_ignores_the_yoke_but_not_a_lip():
    # round 6 box A: Epic's hugging crew neck read spread 3.1-3.9 cm at the side/back (roll 6/6) with gap 0.29-0.30:
    # the yoke over the shoulder, not a layer. With the wall flags it is not judged; lips, folds, Fit5 still fail
    a, r, g, ang, wall = yoke(*band())
    assert GL.collar_stats(a, r, g, angle=ang)["roll"]  # without flags: the false roll
    ok = GL.collar_stats(a, r, g, angle=ang, wall=wall)
    assert not ok["roll"] and ok["spread_cm"] < 0.8 and ok["wall_verts"] < len(a), ok
    a, r, g, ang, wall = yoke(*band(lip=1.8))
    assert GL.collar_stats(a, r, g, angle=ang, wall=wall)["roll"]
    a, r, g, ang, wall = yoke(*band(fold=1.6))
    assert GL.collar_stats(a, r, g, angle=ang, wall=wall)["roll"]
    a, r, g, ang, wall = yoke(*band(gap=2.447, lip=1.2))  # Fit5
    assert GL.collar_stats(a, r, g, angle=ang, wall=wall)["roll"]


def test_neck_visible_counts_islands_and_deep_tongues_not_the_rim_hug():
    # round 6 (orchestrator): r6n1's blob, a skin ISLAND under the collar, must fail; r6n2's neck continuing a little
    # over the hugging collar's edge (one cluster joined to the opening) must pass; a long tongue still fails
    L = neck_scene()
    assert clip.judge_frame(L, W, H, 30.0)["neck_visible"]["px"] == 0
    L = neck_scene(patch_rows=3)  # 18 px enclosed by cloth, rows 20-22
    nv = clip.judge_frame(L, W, H, 30.0)["neck_visible"]
    assert nv["px"] == 18 and nv["island_px"] == 18 and nv["islands"] == 1 and nv["clusters"][0]["kind"] == "island"
    L = neck_scene()
    rect(L["Face"], 14, 12, 26, 14, 99.5)  # the neck 2 rows (~2.7 cm here) over the collar edge, joined to the opening
    fr = clip.judge_frame(L, W, H, 30.0)
    assert fr["neck_visible"]["px"] == 0 and fr["neck_visible"]["max_tongue_cm"] < 4.0
    assert fr["neck_px"]["px"] > 0  # the old rim rule counted this hug
    L = neck_scene()
    rect(L["Face"], 17, 12, 23, 22, 99.5)  # a tongue of skin 10 rows (~13 cm) down from the rim: fails
    nv = clip.judge_frame(L, W, H, 30.0)["neck_visible"]
    assert nv["tongue_px"] > 0 and nv["island_px"] == 0 and nv["max_tongue_cm"] > 4.0
    L = neck_scene(patch_rows=3)  # hair over the island: not seen, not counted
    L["Hair"] = rect(layer(), 15, 18, 25, 25, 90.0)
    assert clip.judge_frame(L, W, H, 30.0, pair_list=[("Face", "tee")])["neck_visible"]["px"] == 0


def test_gate_neck_rule_visible():
    L = neck_scene()
    rect(L["Face"], 14, 12, 26, 14, 99.5)  # the hug: neck_px > 0, neck_visible 0
    fr = clip.judge_frame(L, W, H, 30.0)
    assert [i["code"] for i in clip.gate({"S15": {1128: fr}}, "Host")] == ["clip.neck"]
    assert clip.gate({"S15": {1128: fr}}, "Host", neck_rule="visible") == []
    fr = clip.judge_frame(neck_scene(patch_rows=3), W, H, 30.0)
    assert [i["code"] for i in clip.gate({"S15": {1128: fr}}, "Host", neck_rule="visible")] == ["clip.neck"]
    old = {k: v for k, v in fr.items() if k != "neck_visible"}  # an out_dir judged before this measure: refused
    assert "clip.neck_missing" in [i["code"] for i in clip.gate({"S15": {1128: old}}, "Host", neck_rule="visible")]
    assert clip.summarize({"S15": {1128: fr}})["neck_visible"]["island_px"] == 18


def test_collar_camera_facing_scope():
    # round 6 (orchestrator): the collar rows judge the half of the band facing the shot camera. His neck turning
    # inside a static crew-neck opens the far side (S15 f1150): passes; a stand-off, a lip, a fold or Fit5 on the
    # camera side still fail; a frame with too few facing verts is not measured (refused)
    def facing(ang, cam_deg):  # outward direction at `ang` faces a camera at `cam_deg` round the neck
        return [math.cos(math.radians(x - cam_deg)) > 0 for x in ang]

    def standoff(a, r, g, ang, side_deg, extra):  # the band stands `extra` cm off the neck on one half
        f = facing(ang, side_deg)
        return a, [x + extra if s else x for x, s in zip(r, f)], [x + extra if s else x for x, s in zip(g, f)], ang

    a, r, g, ang = standoff(*band(), 180.0, 1.5)  # the far (back) half stands off on the turn
    assert GL.collar_stats(a, r, g, angle=ang)["roll"]  # the whole band: fails (kept as INFO)
    ok = GL.collar_stats(a, r, g, angle=ang, facing=facing(ang, 0.0))
    assert not ok["roll"] and ok["gap_cm"] <= GL.COLLAR_GAP_CM and ok["facing"], ok
    a, r, g, ang = standoff(*band(), 0.0, 1.5)  # a FRONT stand-off facing the camera: fails
    front = GL.collar_stats(a, r, g, angle=ang, facing=facing(ang, 0.0))
    assert front["roll"] and front["gap_cm"] > GL.COLLAR_GAP_CM
    for kw in ({"lip": 1.8}, {"fold": 1.6}, {"gap": 2.447, "lip": 1.2}):  # lip, fold, Fit5 on the camera side
        a, r, g, ang = band(**kw)
        assert GL.collar_stats(a, r, g, angle=ang, facing=facing(ang, 0.0))["roll"], kw
    a, r, g, ang = band(n=12, heights=(0.0,))
    blind = GL.collar_stats(a, r, g, angle=ang, facing=[False] * len(a))  # nothing faces the camera
    assert blind["n"] == 0


def test_collar_one_sloped_surface_is_not_a_roll_and_the_culled_hole_is_not_a_gap():
    # round 6 box A (collar_cells at f1082/1150/1397): the worst wall-only cells were ONE surface whose radius rose
    # steadily with depth (the crew neck's front on the chest): raw p90-p10 2.2-3.2 cm. The gap's worst ring verts had
    # their nearest skin 1.0-1.24 cm ABOVE them (the face culled under the collar)
    ax, rad, gp, ang = [], [], [], []
    for k in range(72):
        t = 2 * math.pi * k / 72
        for j in range(12):  # 3 cm of band, its radius rising 2.5 cm per cm of depth (a sloped front), both walls
            d = 0.25 * j
            for w in (0.0, 0.34):
                ax.append(-d)
                rad.append(6.0 + 2.5 * d + w)
                gp.append(0.2 + w)
                ang.append(math.degrees(t) % 360)
    assert GL.local_spread(ax, rad, ang, 0.0)[0] < 0.8  # one surface: thin
    raw = []
    for key in {(int(math.floor(a)), int(g // 10)) for a, g in zip(ax, ang)}:
        rs = [r for a, r, g in zip(ax, rad, ang) if (int(math.floor(a)), int(g // 10)) == key]
        raw.append(GL.percentile(rs, 0.9) - GL.percentile(rs, 0.1))
    assert max(raw) > GL.COLLAR_SPREAD_CM  # what the raw spread read
    lip_a = ax + [0.0] * 72
    lip_r = rad + [6.0 + 1.8] * 72  # a rolled lip standing out at the top of the same sloped band: still a roll
    lip_g = ang + [5.0 * k for k in range(72)]
    assert GL.local_spread(lip_a, lip_r, lip_g, 0.0)[0] > GL.COLLAR_SPREAD_CM
    # the gap: a hugging ring whose lower verts face the culled hole (nearest skin 1.2 cm above, gap 2 cm)
    a, r, g, an = band()
    dt = [1.2 if x <= -1.0 else 0.1 for x in a]
    g2 = [x + 1.8 if x0 <= -1.0 else x for x, x0 in zip(g, a)]
    assert GL.collar_stats(a, r, g2, angle=an)["gap_cm"] > GL.COLLAR_GAP_CM  # without skin_dt: the hole reads as a gap
    ok = GL.collar_stats(a, r, g2, angle=an, skin_dt=dt)
    assert ok["gap_cm"] <= GL.COLLAR_GAP_CM and not ok["roll"], ok
    a, r, g, an = band(gap=2.447, lip=1.2)  # Fit5 floats at its own height (skin beside it): still fails
    assert GL.collar_stats(a, r, g, angle=an, skin_dt=[0.0] * len(a))["roll"]
    a, r, g, an = band()  # every ring vert over a hole: not measured, never a pass
    assert GL.collar_stats(a, r, g, angle=an, skin_dt=[2.0] * len(a))["n"] == 0


def test_collar_ring_is_found_per_sector_front_dip():
    # round 6 box A: his crew neck's FRONT sits further from the (posterior) neck axis and dips ~3 cm; one innermost
    # radius for the camera-facing half took the chest as the ring (n 323-491, 'gap' 2.4-4.5 cm to the culled skin)
    a, r, g, ang = [], [], [], []
    for k in range(72):
        deg = 5.0 * k
        front = math.cos(math.radians(deg)) > 0.5  # the front 120 deg
        r0, top = (9.0, -3.0) if front else (5.5, 0.0)
        for h in (0.0, -0.5, -1.0, -1.5, -2.0):
            for w in (0.0, 0.34):
                a.append(top + h)
                r.append(r0 + w)
                g.append(0.2 + w)
                ang.append(deg)
        if front:  # the tee's chest under the front neckline, over culled skin: far from any skin
            for d in (1.0, 2.0, 3.0):
                a.append(top - 2.0 - d)
                r.append(r0 + 0.6 * d)
                g.append(3.5)
                ang.append(deg)
    face = [math.cos(math.radians(x)) > 0 for x in ang]
    st = GL.collar_stats(a, r, g, angle=ang, facing=face)
    assert st["gap_cm"] <= GL.COLLAR_GAP_CM and not st["roll"] and st["sectors"] >= 5, st
    g2 = [x + 1.5 if f and abs(x - 0.2) < 0.5 else x for x, f in zip(g, face)]  # the camera-facing ring stands off
    assert GL.collar_stats(a, r, g2, angle=ang, facing=face)["roll"]
