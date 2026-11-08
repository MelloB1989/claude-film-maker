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
        curves[f]["CTRL_expressions_browRaiseInL"] = 0.6
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


def test_desk_twitches_are_not_gestures():
    def path(i, h):  # quick 3 cm shifts on the desk every second: fast, but small
        k = i % 24
        return [0.0, (10.0 if h == "r" else -10.0) + (3.0 if 2 <= k < 4 else 0.0), 75.0]
    assert P.body_rows(samples(240, path), FPS, [[0, 240]], 71.0)["body.gesture_onsets_per_s"]["value"] == 0


def test_frown_is_reported():
    curves = {f: {"CTRL_expressions_browDownL": 0.5 if f < 60 else 0.0} for f in range(240)}
    assert P.face_rows_curves(curves, FPS, [[0, 240]])["face.curves_frown_frac"]["value"] == 0.25


def test_hands_in_frame_by_camera_kind():
    L = _limbs()
    assert L.cam_kind("CAM_MCU_L") == "MCU" and L.cam_kind("CAM_CU") == "CU" and L.cam_kind("CAM_WIDE") == "WIDE"
    assert L.hand_in([(100, 100, 50), (120, 90, 50)], 1920, 1080)
    assert not L.hand_in([(100, 100, 50), (120, 1100, 50)], 1920, 1080)  # a fingertip below the frame
    rows = {f: {"camera": "CAM_MCU", "in": f % 5 == 0} for f in range(20)}
    rows.update({f: {"camera": "CAM_WIDE", "in": True} for f in range(20, 30)})
    k = L.hands_fracs(rows)
    assert k["MCU"]["frac"] == 0.2 and k["MCU"]["frac"] < k["MCU"]["line"] and k["WIDE"]["frac"] == 1.0


def test_smooth_min_jerk_beats_count_and_two_hands_count_once():
    import math as m

    def path(i, h):  # both hands up at z 90, a smooth 0.3 s stroke every second (min-jerk ramp), rest between
        k = i % 24
        s = 0.0 if k >= 8 else 10 * (lambda t: 10 * t**3 - 15 * t**4 + 6 * t**5)(k / 7)
        return [s, 10.0 if h == "r" else -10.0, 90.0]
    r = P.body_rows(samples(240, path), FPS, [[0, 240]], 71.0)
    assert 0.8 <= r["body.gesture_onsets_per_s"]["value"] <= 1.3  # ~1/s, once for the two hands together


def test_a_hand_already_up_at_a_span_start_is_not_an_onset():
    still_up = samples(120, lambda i, h: [0.0, 10.0 if h == "r" else -10.0, 92.0 if h == "r" else 75.0])
    r = P.body_rows(still_up, FPS, [[0, 40], [60, 120]], 71.0)  # two spans, the right hand up and still
    assert r["body.gesture_onsets_per_s"]["value"] == 0


def test_rest_frames_and_hand_to_chest():
    s = samples(120, lambda i, h: [0.0, 10.0 if h == "r" else -10.0, 80.0 + (5.0 * (i // 3) if 30 <= i < 60 else
                                                                               (50.0 if i >= 60 else 0.0))])
    rf = P.rest_frames(s, FPS, every=1)
    assert rf and all(f < 30 or f >= 66 for f in rf)  # the moving stretch is not rest
    L = _limbs()
    torso = ([0, 0, 100], [0, 0, 150])
    body = cylinder(*torso, 14)  # the chest surface ~14 cm out from the spine
    cloud = L.torso_cloud(body, torso, [])
    near = L.nearest([[17, 0, 128]], cloud)["cm"]  # hands 3 cm off the chest: the rejected high rest
    far = L.nearest([[38, 0, 118]], cloud)["cm"]   # hands ~24 cm in front: the new rest
    assert near < 5 and far > 15


def test_torso_cloud_drops_the_other_hands_fingers_and_the_lap():
    L = _limbs()
    torso = ([0, 0, 100], [0, 0, 150])
    chest = cylinder(*torso, 14)
    lap = [[x, y, 92.0] for x in range(5, 40, 3) for y in range(-15, 16, 5)]  # thighs below the spine segment
    other_fingers = [[38.0, 2.0, 118.0], [40.0, 3.0, 118.0]]  # the left hand's fingers beside the right hand
    fingers = [([30.0, 3.0, 118.0], [42.0, 3.0, 118.0])]  # hand -> fingertip segment of the left hand
    cloud = L.torso_cloud(chest + lap + other_fingers, torso, [], fingers=fingers)
    assert all(p[2] >= 100 for p in cloud)  # no lap point
    assert L.nearest([[38.0, -2.0, 118.0]], cloud)["cm"] > 15  # the right hand ~24 cm off the chest, not 4 cm off a finger


def test_parity_absorbs_a_rigid_frame_change_and_catches_a_stale_layer():
    import math as m
    fr = list(range(48))
    def pos(i, b):
        k = P.PARITY_BONES.index(b)
        return [10 + k + 5 * m.sin(i / 6 + k), -20 + 3 * k, 90 + 4 * m.cos(i / 5 + k)]
    off = {"frames": fr, "bones": {b: [pos(i, b) for i in fr] for b in P.PARITY_BONES}}
    th = m.radians(-90)  # the editor in world coordinates: yawed -90 and moved
    def world(p):
        x, y, z = p
        return [x * m.cos(th) - y * m.sin(th) + 300, x * m.sin(th) + y * m.cos(th) - 120, z + 5]
    ed = {"frames": fr, "bones": {b: [world(p) for p in v] for b, v in off["bones"].items()}}
    assert P.parity(ed, off)["value"] < 0.01
    stale = {"frames": fr, "bones": {b: [list(p) for p in v] for b, v in ed["bones"].items()}}
    for i in range(20, 30):  # a stale layer moves the right hand 6 cm for 10 frames
        stale["bones"]["hand_r"][i][2] += 6
    r = P.parity(stale, off)
    assert r["value"] > 4 and r["at"].startswith("hand_r@")
