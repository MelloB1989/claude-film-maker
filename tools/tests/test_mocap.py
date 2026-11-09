"""filmtools.mocap: the clip prep's checks and command, the rows on a synthetic solved take (no engine, no video)."""
from __future__ import annotations

import math

from filmtools.mocap import prep, rows


def _info(**kw):
    s = {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "r_frame_rate": "60/1",
         "avg_frame_rate": "60/1", "pix_fmt": "yuv420p"}
    s.update(kw)
    return {"streams": [s]}


def test_prep_clean_clip_has_no_issues():
    assert prep.issues(_info()) == []


def test_prep_flags_phone_footage():
    got = " | ".join(prep.issues(_info(codec_name="hevc", width=1280, height=720, r_frame_rate="30000/1001",
                                       avg_frame_rate="2953/100", pix_fmt="yuv420p10le",
                                       side_data_list=[{"rotation": -90}])))
    for want in ("under HD", "variable frame rate", "want 60", "NTSC", "codec hevc", "rotation flag 270",
                 "8-bit"):
        assert want in got, want


def test_prep_make_cmd():
    c = prep.make_cmd("in.mov", "out.mp4", start=1.5, dur=10)
    assert c[c.index("-ss") + 1] == "1.500" and c.index("-ss") < c.index("-i")
    assert "fps=60,format=yuv420p" in c and "-an" in c and c[c.index("-crf") + 1] == "18" and c[-1] == "out.mp4"


def test_prep_keeps_a_whole_rate_and_upscales_on_ask():
    assert prep.whole_fps(_info(avg_frame_rate="24/1")) == 24
    assert prep.whole_fps(_info(avg_frame_rate="30000/1001")) == 30
    c = prep.make_cmd("in.mp4", "out.mp4", fps=24, height=1080)
    assert "fps=24,scale=-2:1080:flags=lanczos,format=yuv420p" in c


def _take(n=60, fps=24.0, wiggle=True):
    """A seated take: the head at 120 cm, the hands at desk height + 20 swinging, fingers curling on a sine."""
    bones = {b: [] for b in rows.ROWS_BONES}
    for k in range(n):
        t = k / fps
        bones["head"].append([0.0, 0.0, 120.0])
        bones["neck_01"].append([0.0, 0.0, 110.0])
        bones["spine_05"].append([0.0, 0.0, 100.0])
        for s, y in (("l", -20.0), ("r", 20.0)):
            hz = 91.0 + 10.0 * math.sin(2 * math.pi * 0.5 * t)
            bones["hand_" + s].append([30.0, y, hz])
            bones["lowerarm_" + s].append([10.0, y, hz - 5.0])
            c = math.radians(30.0 + (20.0 * math.sin(2 * math.pi * 1.0 * t) if wiggle else 0.0))
            for fi, f in enumerate(rows.FINGERS):
                x0, yy = 33.0, y + (fi - 2) * 1.5
                p1 = [x0, yy, hz]
                p2 = [p1[0] + 3.0, yy, hz]  # 01 -> 02 straight on, then the bend
                p3 = [p2[0] + 2.5 * math.cos(c), yy, hz - 2.5 * math.sin(c)]
                bones[f"{f}_01_{s}"].append(p1)
                bones[f"{f}_02_{s}"].append(p2)
                bones[f"{f}_03_{s}"].append(p3)
    return {"frames": list(range(n)), "bones": bones}


def test_rows_alive_fingers_pass():
    r = rows.rows(_take(), 24.0, desk_z=71.0)
    assert r["fingers.curl_range_deg_p50"] > 30 and r["fingers.moving_frac"] > 0.5
    assert r["verdict"]["fingers.curl_range_deg_p50"] == "ok" and r["verdict"]["fingers.moving_frac"] == "ok"
    assert r["wrist.below_desk_top_frac"] == 0.0
    assert r["face.fingertip_clear_cm_min"] > 0
    assert "body.hands_above_desk_frac" in r


def test_rows_frozen_fingers_flagged():
    r = rows.rows(_take(wiggle=False), 24.0, desk_z=71.0)
    assert r["fingers.curl_range_deg_p50"] < 1 and r["fingers.moving_frac"] == 0.0
    assert r["verdict"]["fingers.curl_range_deg_p50"].startswith("look")


def test_rows_hands_under_a_missing_desk():
    r = rows.rows(_take(), 24.0, desk_z=95.0)
    assert 0.2 < r["wrist.below_desk_top_frac"] < 0.8


def test_curl_straight_and_bent():
    P = {"hand_l": [[0, 0, 0]], "index_01_l": [[1, 0, 0]], "index_02_l": [[2, 0, 0]], "index_03_l": [[2, 0, -1]]}
    assert abs(rows.curl(P, "index", "l", 0) - 90.0) < 1e-6
