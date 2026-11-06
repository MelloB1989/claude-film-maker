"""cast_gate.py's offline parts (round 4): lips per spoken line on synthetic frames, the watch's seat, the lod0 judge
and the sign verdict. No Unreal.

    cd tools && uv run --with pillow --with numpy --with pytest pytest ../films/host-studio/reel/test_cast_gate.py
"""
import json
import sys
from argparse import Namespace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cast_gate as g  # noqa: E402

BOX = [0.45, 0.45, 0.55, 0.55]  # a 54 px tall box at 960x540


def _frames(tmp, shot_range, talk, w=960, h=540):
    """Grey frames; inside BOX, noise that changes every frame on `talk` frames and stays put otherwise."""
    rng = np.random.default_rng(1)
    still = rng.integers(0, 255, (54, 96, 3), dtype=np.uint8)
    for f in range(*shot_range):
        a = np.full((h, w, 3), 90, np.uint8)
        a[243:297, 432:528] = rng.integers(0, 255, (54, 96, 3), dtype=np.uint8) if f in talk else still
        Image.fromarray(a).save(tmp / f"{f:04d}.png")


def test_speakers_cover_every_line():
    got = g.speakers()
    assert got == [("S13", "him"), ("S15", "him"), ("S15", "her"), ("S16", "her"), ("S17", "him"), ("S17", "her")]


def test_lips_per_line(tmp_path):
    # S13 (960-1080): L1 1020-1065 moves; S15 (1080-1200): his L2 1095-1133 moves, her L3a 1158-1185 does NOT
    talk = set(range(1020, 1065)) | set(range(1095, 1133))
    _frames(tmp_path, (960, 1200), talk)
    mouths = {k: {"box": BOX} for k in ("S13:him", "S15:him", "S15:her")}
    r = g.frames(str(tmp_path), None, str(tmp_path / "out"), mouths)
    assert r["lips"]["S13:him"]["lines"]["L1"]["pass"] is True
    assert r["lips"]["S15:him"]["lines"]["L2"]["pass"] is True
    assert r["lips"]["S15:her"]["lines"]["L3a"]["pass"] is False
    # his L2 is her silence in S15, so her off-frames move too: her ratio is under 1
    assert r["lips"]["S15:her"]["lines"]["L3a"]["ratio"] < 1
    lips = g._lips(r, None)
    assert not lips["pass"]
    assert any(b.startswith("S15:her L3a") for b in lips["failed"])
    assert any(b.startswith("L3b") for b in lips["failed"])  # S16 was not measured: refused, not skipped


def test_small_box_defers_to_engine(tmp_path):
    _frames(tmp_path, (1320, 1440), set())
    tiny = [0.5, 0.5, 0.505, 0.505]  # ~3 px
    r = g.frames(str(tmp_path), None, str(tmp_path / "out"), {"S17:him": {"box": tiny}})
    line = r["lips"]["S17:him"]["lines"]["L4a"]
    assert line["pass"] is None and "engine" in line["why"]
    eng = {"people": {"him": {"lips": {"pass": True, "lines": {"L4a": {"jaw_max": 0.3, "activity": 0.02}}}}}}
    assert g._lips(r, eng)["lines"]["S17:him L4a"]["pass"] is True
    eng["people"]["him"]["lips"]["lines"]["L4a"]["jaw_max"] = 0.02
    assert g._lips(r, eng)["lines"]["S17:him L4a"]["pass"] is False


@pytest.mark.parametrize("cms,ok", [([3.6, 3.7, 3.5], True), ([3.6, 8.2], False), ([7.9], False), ([3.0], False)])
def test_watch_seat(cms, ok):
    eng = {"shots": {"S16": {1202 + i: {"watch_cm": c} for i, c in enumerate(cms)}}}
    assert g._watch(eng)["pass"] is ok
    assert g.summary({"people": {}, "shots": eng["shots"]})["b.watch"] is ok


def _comp(name, cls, **kw):
    return {"name": name, "class": cls, "trash": name.startswith("TRASH_"), **kw}


def test_lod0_judge():
    good = {"Host": {"components": [_comp("LODSync", "LODSyncComponent", forced_lod=0),
                                    _comp("Body", "SkeletalMeshComponent", forced_lod_model=1)]},
            "Presenter": {"components": [_comp("LODSync", "LODSyncComponent", forced_lod=0),
                                         _comp("Hair", "GroomComponent", groom=True)]}}
    assert g.lod0_judge(good)["pass"]
    bad = json.loads(json.dumps(good))
    bad["Host"]["components"].append(_comp("TRASH_SkeletalMeshComponent_57", "SkeletalMeshComponent",
                                           forced_lod_model=1))
    bad["Presenter"]["components"][0]["forced_lod"] = -1
    r = g.lod0_judge(bad)
    assert not r["pass"] and len(r["failed"]) == 2


def test_cams_need_13_ok():
    txt = "\n".join(f"{s} OK" for s in g.SHOTS_13)
    assert g._cams(txt, "S13 35mm him: ...\n")["pass"]
    r = g._cams(txt.replace("S17 OK", "S17 OFF: loc 3.1 cm"), "")
    assert not r["pass"] and r["cameras_ok"] == "12/13"
    assert not g._cams(txt, "PROBLEM S17 knee in frame\n")["pass"]


def test_sign_refuses_and_waives(tmp_path):
    def w(name, obj):
        p = tmp_path / name
        p.write_text(obj if isinstance(obj, str) else json.dumps(obj))
        return str(p)
    eng = {"people": {}, "shots": {"S16": {1202: {"watch_cm": 3.6, "her": {"pass": True, "worst_fraction": 0.3}}},
                                   "S13": {962: {"him": {"pass": True, "worst_fraction": 0.0004}}}}}
    lines = {k: {"frames": [a, b], "ratio": 3.0, "pass": True} for k, _, a, b, _ in g.LINES}
    fr = {"lips": {"all": {"lines": lines}}}
    hue = {"images": {"f1236": {"crown": {"a": 2, "b": 7, "C": 7, "green_px": 0.01},
                                "ends_screen_left": {"a": 0.0, "b": 2.4, "C": 2.4, "green_px": 0.24}},
                      "f1300": {"crown": {"a": 2, "b": 7, "C": 7, "green_px": 0.01}}}}
    lod = {"pass": True, "failed": []}
    a = Namespace(name="t", engine=w("e.json", eng), frames=w("f.json", fr), hue=w("h.json", hue),
                  turns=w("t.json", [{"shot": "S15", "who": "him", "f0": 1128, "f1": 1316, "ok": True}]), clip=[], clip_before="",
                  cams=w("c.txt", "\n".join(f"{s} OK" for s in g.SHOTS_13)), framing=w("fr.txt", ""),
                  lod0=w("l.json", lod), waive=[], out=str(tmp_path / "gate.json"))
    rep = g.sign(a)
    assert rep["verdict"] == "REFUSE" and rep["blocking"] == ["c.hair_hue"]
    assert "f1236 ends_screen_left: green_px 0.24" in rep["items"]["c.hair_hue"]["failed"][0]
    a.waive = ["c.hair_hue=time-boxed, dropped on the orchestrator's word"]
    rep = g.sign(a)
    assert rep["verdict"] == "SIGN" and "WAIVED" in g.sign_text(rep)


def test_turns_agent01_rule():
    row = {"shot": "S15", "who": "him", "beat": "over his shoulder", "f0": 1128, "f1": 1316, "frame": 1150,
           "true_yaw": 130.1, "head_yaw": 65.0, "screen_dir": "right", "partner_dir": "right", "err_deg": 44.4,
           "stage": "level", "ok": True}
    her = {"shot": "S15", "who": "her", "f0": 1080, "f1": 1146, "frame": 1100, "true_yaw": -49.9, "head_yaw": -32.2,
           "screen_dir": "left", "partner_dir": "left", "err_deg": 0.0, "stage": "level", "ok": True}
    assert g._turns([row, her])["pass"]
    assert not g._turns([{**row, "screen_dir": "left"}])["pass"]          # preview2's wrong way, even if ok says so
    assert not g._turns([{**her, "err_deg": 40.0}])["pass"]               # within reach but missing her face
    assert not g._turns([{**row, "head_yaw": 20.0}])["pass"]              # beyond reach, the head barely turns
    assert not g._turns([{**row, "stage": "shots.py"}])["pass"]           # the plan, not the level


def test_clip_pass_json():
    def him_shots(**over):
        return {"label": "Host", "shots": {sid: {"962": {"Body>tee": {"fraction": 0.0, "clusters": []},
                                                          "Face>tee": {"fraction": 0.03},
                                                          "neck": {"n": 400, "out": 0, "max_out_cm": 0.0}}}
                                           for sid in ("S13", "S15", "S17", "S18")}}
    her_b = {"label": "Presenter", "shots": {sid: {"1210": {"Body>Top": {"fraction": 0.15}}}
                                             for sid in ("S15", "S16", "S17", "S18")}}
    her = json.loads(json.dumps(her_b))
    him = him_shots()
    r = g._clip([him, her], None, her_b)
    assert r["pass"], r["failed"]
    assert r["info_only"]["Host Face>tee"] == 0.03          # reported, not gated
    him["shots"]["S17"]["1330"] = {"Trousers>tee": {"fraction": 0.0047, "clusters": [{"px": 21, "worst_cm": 1.2}]}}
    him["shots"]["S15"]["962"]["neck"] = {"out": 227, "max_out_cm": 2.46}
    her["shots"]["S16"]["1210"]["Body>Top"]["fraction"] = 0.155
    her["shots"]["S17"]["1210"]["Body>Top"]["fraction"] = 0.30
    r = g._clip([him, her], None, her_b)
    assert [f.split(":")[0] for f in r["failed"]] == ["Host S15 f962 neck", "Host S17 f1330 Trousers>tee",
                                                      "Presenter S17 f1210 Body>Top"]
    assert not g._clip([her], None, None)["pass"]           # her needs her before pass
    del her_b["shots"]["S16"]
    her["shots"]["S18"] = {"error": "no camera cut S18"}
    assert len(g._clip([her], None, her_b)["failed"]) == 3   # S18 errored, S16 has no before, S17 0.30
