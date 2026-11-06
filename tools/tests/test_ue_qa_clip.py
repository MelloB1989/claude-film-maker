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
    assert codes[0] == "garment.wpo_inflate" and "garment.armor_detail" in codes and "garment.armor_motion" in codes
    cloth = GL.look({"ease": GL.ease_stats([0.4 + 3.5 * (i / 399) ** 1.5 for i in range(400)]), "thickness_cm": 0.15,
                     "silhouette": 1.06, "detail": 0.05, "motion": 0.2, "wpo": {"FM_Inflate": 0.0}}, "Host tee")
    assert cloth["verdict"] == "cloth" and cloth["pass"] and cloth["index"] < 0.1 and not cloth["issues"]


def test_armor_without_wpo_still_fails_on_the_index():
    r = GL.look({"ease": GL.ease_stats([1.2] * 50), "thickness_cm": 0.9, "silhouette": 1.3, "detail": 0.005})
    assert r["verdict"] == "armor" and r["issues"][0]["code"] == "garment.armor" and "motion" in r["missing"]
    assert GL.look({})["pass"] is False
