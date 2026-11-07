"""Round 7 performance rows (filmtools.unreal.qa_perf): pure parts, no MediaPipe, no editor."""
from filmtools.unreal import qa_perf as P

FPS = 24.0
ZERO = {c: 0.05 for c in P.CHANNELS}


def face(n, events=()):
    """n frames of a neutral face with (start, length, {channel: value}) events on top."""
    s = {f: dict(ZERO) for f in range(n)}
    for a, ln, ch in events:
        for f in range(a, a + ln):
            s[f].update(ch)
    return s


def test_mouth_only_face_fails_every_face_row():
    r = P.face_rows(face(240), FPS, [[0, 240]])  # 10 s, nothing but the resting offsets
    assert r["face.expr_active_frac"]["value"] == 0.0
    assert r["face.smile_events_per_min"]["value"] == 0 and r["face.brow_flash_per_min"]["value"] == 0
    assert r["face.neutral_hold_max_s"]["value"] == 10.0


def test_lively_face_counts_smiles_brows_and_short_holds():
    up = {"browInnerUp": 0.6}
    duch = {"mouthSmileLeft": 0.6, "mouthSmileRight": 0.6, "cheekSquintLeft": 0.4, "cheekSquintRight": 0.4}
    ev = [(a, 8, up) for a in range(0, 240, 30)] + [(a + 12, 10, duch) for a in range(0, 240, 60)]
    r = P.face_rows(face(240, ev), FPS, [[0, 240]])
    assert r["face.brow_flash_per_min"]["value"] >= 40  # 8 flashes in 10 s
    assert r["face.smile_events_per_min"]["value"] >= 20  # 4 Duchenne smiles in 10 s
    assert r["face.neutral_hold_max_s"]["value"] < 1.5
    # a smile without the cheeks/eyes is not a Duchenne smile
    social = [(12, 10, {"mouthSmileLeft": 0.6, "mouthSmileRight": 0.6})]
    assert P.face_rows(face(240, social), FPS, [[0, 240]])["face.smile_events_per_min"]["value"] == 0


def test_long_brow_hold_is_not_a_flash_and_speaking_spans_scope_it():
    r = P.face_rows(face(240, [(10, 60, {"browInnerUp": 0.6})]), FPS, [[0, 240]])  # 2.5 s up: not a flash
    assert r["face.brow_flash_per_min"]["value"] == 0
    assert P.face_rows(face(48), FPS, [[100, 200]])["face.expr_active_frac"]["value"] is None


def samples(n, path):
    return {"frames": list(range(n)), "bones": {"hand_l": [path(i, "l") for i in range(n)],
                                                 "hand_r": [path(i, "r") for i in range(n)]}}


def test_pinned_hands_on_the_desk_fail_the_body_rows():
    s = samples(120, lambda i, h: [0.0, 10.0 if h == "r" else -10.0, 75.0])  # still, wrists 4 cm over a 71 cm desk
    r = P.body_rows(s, FPS, [[0, 120]], 71.0)
    assert r["body.gesture_onsets_per_s"]["value"] == 0 and r["body.hands_above_desk_frac"]["value"] == 0
    assert r["body.wrist_travel_cm_per_s"]["value"] == 0


def test_gesturing_hand_counts_onsets_and_height():
    def path(i, h):
        if h == "l":
            return [0.0, -10.0, 75.0]
        k = i % 24  # one gesture a second: 6 frames moving fast up and out, then rest
        z = 75.0 + (min(k, 6) * 3.0 if k < 12 else 18.0 - (min(k - 12, 6) * 3.0))
        return [0.0, 10.0, z]
    r = P.body_rows(samples(240, path), FPS, [[0, 240]], 71.0)
    assert 0.8 <= r["body.gesture_onsets_per_s"]["value"] <= 2.2
    assert r["body.hands_above_desk_frac"]["value"] > 0.3


def _limbs():
    from _qa_load import load
    load()
    return __import__("fmqa.limbs", fromlist=["limbs"])


def cylinder(a, b, r, n=24, rings=12):
    import math
    pts = []
    for i in range(rings + 1):
        t = i / rings
        c = [a[k] + t * (b[k] - a[k]) for k in range(3)]
        for j in range(n):
            ang = 2 * math.pi * j / n
            pts.append([c[0] + r * math.cos(ang), c[1] + r * math.sin(ang), c[2]])
    return pts


def test_arm_clear_of_the_torso_and_arm_inside_it():
    L = _limbs()
    torso = ([0, 0, 100], [0, 0, 150])
    body = cylinder(*torso, 15)  # a 15 cm-radius torso
    arm_out = ([22, 0, 148], [26, 0, 118])  # upper arm hanging 22-26 cm from the spine axis: clear
    a, t = L.classify(body + cylinder(*arm_out, 4), arm_out, torso)
    r = L.clearance(a, t, torso)
    assert r["cm"] is not None and r["cm"] > 1.0
    arm_in = ([16, 0, 148], [14, 0, 118])  # pinned: its inner side sinks into the torso's volume
    a, t = L.classify(body + cylinder(*arm_in, 4), arm_in, torso)
    assert L.clearance(a, t, torso)["cm"] < 0
    assert L.clearance([], t, torso)["cm"] is None


def test_curve_precheck_on_metahuman_controls():
    curves = {f: {"CTRL_expressions_browRaiseInL": 0.0, "CTRL_expressions_mouthCornerPullL": 0.0,
                  "CTRL_expressions_eyeCheekRaiseL": 0.0} for f in range(240)}
    assert P.face_rows_curves(curves, FPS, [[0, 240]])["face.curves_expr_active_frac"]["value"] == 0.0
    for f in range(20, 30):
        curves[f]["CTRL_expressions_browRaiseInL"] = 0.5
    for f in range(60, 70):
        curves[f].update({"CTRL_expressions_mouthCornerPullL": 0.4, "CTRL_expressions_eyeCheekRaiseL": 0.3})
    r = P.face_rows_curves(curves, FPS, [[0, 240]])
    assert r["face.curves_brow_flash_per_min"]["value"] == 6 and r["face.curves_smile_events_per_min"]["value"] == 6


def test_a_held_smile_drifting_around_the_line_is_one_event():
    s = face(240)
    for f in range(20, 120):  # 4 s held smile whose level wobbles 0.22-0.30 around the 0.25 line (rig scale)
        lvl = 0.30 if (f // 3) % 2 else 0.22
        s[f].update({"mouthSmileLeft": lvl + 0.05, "mouthSmileRight": lvl + 0.05,
                     "cheekSquintLeft": 0.35, "cheekSquintRight": 0.35})
    r = P.face_rows(s, FPS, [[0, 240]], lines={"smile": 0.25, "squint": 0.2}, neutral=False)
    assert r["face.smile_events_per_min"]["value"] == 6  # one smile in 10 s
