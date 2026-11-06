"""Cloth (T3b, round 5): clothkit's presets and painted maps, and fmbridge.qa.cloth's verdict on a simulation, on a
synthetic garment (a tube round a stick skeleton): pure Python, no engine."""
import math
import sys
from pathlib import Path

import pytest

from _qa_load import load

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "unreal" / "fmbridge"))
from clothkit import paint, presets, topology  # noqa: E402

load()
from fmqa import cloth as qcloth  # noqa: E402

# a standing body, cm, Z up: pelvis 100, chest 135, neck 150, head 160; arms out sideways at 140 (A-pose-ish)
HEADS = {"pelvis": (0, 0, 100), "spine_01": (0, 0, 108), "spine_03": (0, 0, 122), "spine_05": (0, 0, 138),
         "neck_01": (0, 0, 150), "head": (0, 0, 160), "clavicle_l": (0, -3, 142), "upperarm_l": (0, -18, 140),
         "lowerarm_l": (0, -45, 128), "hand_l": (0, -68, 118), "clavicle_r": (0, 3, 142), "upperarm_r": (0, 18, 140),
         "lowerarm_r": (0, 45, 128), "hand_r": (0, 68, 118), "thigh_l": (0, -9, 95), "calf_l": (0, -9, 52),
         "foot_l": (0, -9, 8)}
PARENTS = {"pelvis": None, "spine_01": "pelvis", "spine_03": "spine_01", "spine_05": "spine_03",
           "neck_01": "spine_05", "head": "neck_01", "clavicle_l": "spine_05", "upperarm_l": "clavicle_l",
           "lowerarm_l": "upperarm_l", "hand_l": "lowerarm_l", "clavicle_r": "spine_05", "upperarm_r": "clavicle_r",
           "lowerarm_r": "upperarm_r", "hand_r": "lowerarm_r", "thigh_l": "pelvis", "calf_l": "thigh_l",
           "foot_l": "calf_l"}


def tee():
    """A tube torso from the hem (z 95) to the collar (z 150), r 16 cm, plus a short sleeve tube on each arm."""
    verts = []
    for z in range(95, 151, 5):
        for k in range(12):
            a = 2 * math.pi * k / 12
            verts.append((16 * math.cos(a), 16 * math.sin(a), float(z)))
    for side in (-1, 1):
        for s in range(0, 5):          # 20 cm of sleeve from the shoulder joint, out along -Y / +Y and a little down
            y = side * (18 + 4 * s)
            z = 140 - 1.8 * s
            for k in range(8):
                a = 2 * math.pi * k / 8
                verts.append((6 * math.cos(a), y, z + 6 * math.sin(a)))
    return verts


def painted(colours=None, name="cotton_tee"):
    p = presets.get(name)
    segs = paint.bone_segments(HEADS, PARENTS)
    v = tee()
    z = paint.assign(v, segs, p)
    return v, z, paint.paint(v, z, segs, p, PARENTS, colours=colours), p


# --- presets --------------------------------------------------------------------------------------------------------

def test_presets_exist_and_merge_over_the_base():
    assert presets.names() == ["cotton_tee", "overshirt_light", "trousers"]
    p = presets.get("cotton_tee", {"config": {"damping_coefficient": 0.1}, "zones": {"torso": {"to_cm": 4.0}}})
    assert p["config"]["damping_coefficient"] == 0.1 and p["config"]["edge_stiffness_weighted"] == 1.0
    assert [z for z in p["zones"] if z["name"] == "torso"][0]["to_cm"] == 4.0
    assert presets.PRESETS["cotton_tee"]["zones"][2]["to_cm"] == 3.0       # the table is not mutated


@pytest.mark.parametrize("bad", [{"config": {"dampin_coefficient": 0.1}}, {"zones": {"hemm": {"to_cm": 1}}},
                                 {"zones": {"torso": {"to": 1}}}, {"settle": 1}])
def test_preset_typos_are_errors(bad):
    with pytest.raises(KeyError):
        presets.get("cotton_tee", bad)
    with pytest.raises(KeyError, match="one of"):
        presets.get("cotton_t")


# --- paint ----------------------------------------------------------------------------------------------------------

def test_zones_follow_the_nearest_bones():
    v, z, maps, _ = painted()
    zone = dict(zip(v, [a for a, _ in z]))
    assert zone[(16.0, 0.0, 95.0)] == "torso"
    assert zone[(16.0, 0.0, 150.0)] in ("collar", "shoulder")
    sleeve = [zz for vv, zz in zone.items() if abs(vv[1]) >= 26]
    assert sleeve and set(sleeve) == {"sleeve"}


def test_max_distance_is_anchored_at_the_top_and_free_at_the_hem_and_sleeve_ends():
    v, z, maps, p = painted()
    md = dict(zip(v, maps["max_distance"]))
    assert md[(16.0, 0.0, 95.0)] == pytest.approx(3.0)               # hem: the preset's to_cm
    assert md[(16.0, 0.0, 150.0)] == pytest.approx(0.0, abs=0.05)    # collar
    assert md[(16.0, 0.0, 120.0)] < md[(16.0, 0.0, 100.0)]           # ramps down the torso
    ends = [m for vv, m in md.items() if abs(vv[1]) >= 34]
    root = [m for vv, m in md.items() if abs(vv[1]) == 18 and vv[2] > 130]
    assert min(ends) > 1.0 and max(root) < 0.6
    assert paint.check_maps(maps, p) == []
    assert maps["stats"]["torso"]["max_cm"] == pytest.approx(3.0)


def test_fit_colours_pin_and_cap_by_the_ease():
    v = tee()
    cols = []
    for x, y, zz in v:
        if zz >= 145:
            cols.append((0.2, 1.0, 0, 1))            # collar band pinned
        elif zz <= 100:
            cols.append((0.2, 0.0, 0, 1))            # hem with 1 cm of ease: capped at ease + thickness
        else:
            cols.append((1.0, 0.0, 0, 1))            # no body under it measured
    _, z, maps, p = painted(colours=cols)
    md = dict(zip(v, maps["max_distance"]))
    assert md[(16.0, 0.0, 150.0)] == 0.0
    # R (ease) is NOT used: it arrives sRGB-decoded through UE's FBX vertex colours (round 5); G pins
    assert md[(16.0, 0.0, 95.0)] == pytest.approx(3.0)
    i = v.index((16.0, 0.0, 95.0))
    assert maps["backstop_distance"][i] == 0.0
    assert maps["pinned"][v.index((16.0, 0.0, 150.0))]


def test_check_maps_calls_an_all_pinned_garment_armour():
    v, z, maps, p = painted()
    flat = dict(maps, max_distance=[0.0] * len(v), stats={k: dict(s, max_cm=0.0) for k, s in maps["stats"].items()})
    probs = paint.check_maps(flat, p)
    assert any("armour" in s for s in probs) and any("cannot move" in s for s in probs)


def test_assign_refuses_a_foreign_skeleton():
    with pytest.raises(ValueError, match="MetaHuman"):
        paint.assign([(0, 0, 0)], {"Bip01": ((0, 0, 0), (0, 0, 1))}, presets.get("cotton_tee"))


# --- qa.cloth's judge -----------------------------------------------------------------------------------------------

def run(n=48, cloth=lambda f, i, p: (0.0, 0.0, 0.0), body=lambda f: (f * 0.5, 0.0, 0.0), **kw):
    """A garment of the tee's vertices: skinned = rest + the body's motion; sim = skinned + cloth(f, i, rest)."""
    v, z, maps, p = painted()
    zones = [a for a, _ in z]
    frames = list(range(1000, 1000 + n))
    skin, sim = [], []
    for f in range(n):
        b = body(f)
        sk = [(x + b[0], y + b[1], zz + b[2]) for x, y, zz in v]
        skin.append(sk)
        sim.append([(s[0] + c[0], s[1] + c[1], s[2] + c[2]) for s, c in
                    ((s, cloth(f, i, v[i])) for i, s in enumerate(sk))])
    hem = qcloth.hem_mask(v, zones, p["free"], p["hem_band_cm"])
    return qcloth.judge(frames, sim, skin, zones, maps["max_distance"], fps=24, free=p["free"], pinned=p["pinned"],
                        hem=hem, subject="Host.Tee", **kw), maps


def swing(amp=1.0):
    """Cloth that lags the body in the free zone, proportional to how low the vertex hangs (the hem most)."""
    def c(f, i, p):
        w = max(0.0, (130 - p[2]) / 35.0) if abs(p[1]) < 18 else max(0.0, (abs(p[1]) - 20) / 16.0)
        return (amp * w * math.sin(f / 4.0), 0.0, -0.3 * w)
    return c


def test_a_swinging_hem_is_alive_and_passes():
    r, _ = run(cloth=swing(1.5))
    assert r["pass"], r["issues"]
    assert r["metrics"]["zones"]["hem"]["motion_cm"] > 0.3
    assert r["metrics"]["zones"]["collar"]["slip_cm"] < 0.05


def test_armour_cloth_that_never_moves_relative_to_the_body_fails_dead():
    r, _ = run(cloth=lambda f, i, p: (0.0, 0.0, -0.2) if p[2] < 120 else (0.0, 0.0, 0.0))
    codes = {i["code"] for i in r["issues"]}
    assert not r["pass"] and "cloth.dead" in codes
    dead = [i for i in r["issues"] if i["code"] == "cloth.dead"]
    assert all("armour" in i["message"] and i["fix"] for i in dead)


def test_a_still_body_is_not_judged_dead():
    r, _ = run(cloth=lambda f, i, p: (0.0, 0.0, 0.0001 * (p[2] < 100)), body=lambda f: (0, 0, 0))
    codes = {i["code"] for i in r["issues"]}
    assert "cloth.dead" not in codes and "cloth.alive_unjudged" in codes


def test_no_simulation_at_all_is_called_out():
    r, _ = run()
    assert "cloth.not_simulating" in {i["code"] for i in r["issues"]} and not r["pass"]


def test_explosion_and_velocity_spike():
    r, _ = run(cloth=lambda f, i, p: (40.0, 0, 0) if (f == 30 and i == 3) else swing(1.0)(f, i, p))
    codes = {i["code"] for i in r["issues"]}
    assert {"cloth.explosion", "cloth.velocity_spike"} <= codes
    sp = [i for i in r["issues"] if i["code"] == "cloth.velocity_spike"][0]
    assert sp["frame"] in (1030, 1031)


def test_nan_fails_at_once():
    r, _ = run(cloth=lambda f, i, p: (float("nan"), 0, 0) if f == 5 else (0, 0, 0))
    assert [i["code"] for i in r["issues"]] == ["cloth.nan"] and r["issues"][0]["frame"] == 1005


def test_cold_start_is_caught():
    def settle(f, i, p):          # the hem drops 4 cm into place over the first 4 frames, then sways gently
        w = max(0.0, (130 - p[2]) / 35.0) if abs(p[1]) < 18 else 0.0
        drop = -2.5 * w * (1 - min(f, 4) / 4.0)
        return (0.5 * w * math.sin(f / 4.0), 0.0, drop)
    r, _ = run(cloth=settle, body=lambda f: (f * 0.1, 0, 0))
    assert "cloth.cold_start" in {i["code"] for i in r["issues"]}
    r2, _ = run(cloth=swing(0.5), body=lambda f: (f * 0.1, 0, 0))
    assert "cloth.cold_start" not in {i["code"] for i in r2["issues"]}


def test_anchor_slip_and_jitter_warn():
    def slip(f, i, p):
        if p[2] >= 148:
            return (0.8, 0, 0)                                  # the collar off the neck
        return (0.3 * (-1) ** f if p[2] < 100 else 0.0, 0, 0)   # the hem buzzes
    r, _ = run(cloth=slip, body=lambda f: (0, 0, 0))
    codes = {i["code"] for i in r["issues"]}
    assert {"cloth.anchor_slip", "cloth.jitter"} <= codes


def test_max_distance_exceeded_warns():
    r, maps = run(cloth=lambda f, i, p: (4.0 + 0.5 * math.sin(f), 0, 0) if p[2] >= 145 else swing(1.0)(f, i, p))
    assert "cloth.max_distance_exceeded" in {i["code"] for i in r["issues"]}


def test_too_few_frames():
    r = qcloth.judge([1, 2], [[(0, 0, 0)]] * 2, [[(0, 0, 0)]] * 2, ["torso"], [1.0])
    assert r["issues"][0]["code"] == "cloth.no_data"


def test_sample_keeps_every_zone():
    zones = ["torso"] * 9000 + ["collar"] * 50
    idx = qcloth.sample(len(zones), 500, zones)
    assert len(idx) >= 500 and sum(1 for i in idx if zones[i] == "collar") >= 40
    assert qcloth.sample(10, 500) == list(range(10))


# --- fold detail and the gate file ----------------------------------------------------------------------------------

def _shirt(w=120, h=160, folds=0.0):
    """A garment mask (a rounded block) with luminance: smooth shading, plus horizontal folds of `folds` amplitude."""
    mask = [0] * (w * h)
    lum = [0.05] * (w * h)
    for y in range(20, 150):
        for x in range(20, 100):
            mask[y * w + x] = 1
            lum[y * w + x] = 0.3 + 0.001 * x + folds * math.sin(y / 2.5) * math.sin(x / 7.0)
    return lum, mask, w, h


def test_fold_detail_reads_folds_and_not_a_smooth_shell():
    smooth = qcloth.fold_detail(*_shirt(folds=0.0))
    folded = qcloth.fold_detail(*_shirt(folds=0.03))
    assert smooth["detail"] < 0.01 and folded["detail"] > 5 * max(smooth["detail"], 1e-4)
    assert folded["band"][1] > 20 and folded["band"][3] < 150
    assert qcloth.fold_detail([0.0] * 100, [0] * 100, 10, 10)["detail"] is None


def test_gate_numbers_round4_fails_and_a_good_round_passes():
    r4 = {"S13 f1000-1060": {"pass": False, "issues": [{"code": "cloth.no_clothing", "severity": "fail"}]}}
    g = qcloth.gate_numbers(r4, {"S13 f1030": (0.02, 0.02)})["gate"]
    assert g["garment.cloth_alive"]["value"] == 0.0 and g["garment.cloth_sound"]["value"] == 0
    assert g["garment.cloth_detail_ratio"]["value"] == 1.0
    good, _ = run(cloth=swing(1.5))
    g = qcloth.gate_numbers({"S13 f1000-1048": good}, {"S13 f1030": (0.05, 0.02)})["gate"]
    assert g["garment.cloth_alive"]["value"] >= 0.3 and g["garment.cloth_sound"]["value"] == 1
    assert g["garment.cloth_detail_ratio"]["value"] == 2.5
    g = qcloth.gate_numbers({}, {"S13": (None, 0.02)})["gate"]
    assert all("error" in v for v in g.values())


# --- topology: is a section simulatable? ------------------------------------------------------------------------------

def test_topology_open_strip_closed_box_and_pieces():
    strip = [(i, i + 1, i + 2) for i in range(20)]
    st = topology.analyze(strip)[0]
    assert st["islands"] == 1 and st["border_edges"] > 0 and topology.judge(st) == []
    v = [(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)]
    q = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    box = [t for a, b, c, d in q for t in ((a, b, c), (a, c, d))]
    st = topology.analyze(box)[0]
    assert st["border_edges"] == 0 and any("CLOSED" in w for w in topology.judge(st))
    pieces = strip + [(100, 101, 102), (110, 111, 112)]
    st = topology.analyze(pieces)[0]
    assert st["islands"] == 3 and any("separate pieces" in w for w in topology.judge(st))
    st = topology.analyze(strip + [(500, 501, 502)] * 1, [0] * 20 + [1])
    assert set(st) == {0, 1} and st[0]["islands"] == 1
    assert any("too many" in w for w in topology.judge({"verts": 50000, "border_edges": 10, "islands": 1,
                                                        "main_frac": 1.0}))
