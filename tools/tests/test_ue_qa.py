"""fmbridge.qa (WP10): the pure-Python QA core, with numpy and without (the editor usually has none)."""
import json
import math
import random

import pytest

from _qa_load import load

qa = load()
from fmqa import compare, continuity, draw, framing, geometry, image, metrics, overlay, review, sheet  # noqa: E402

HAS_NP = image.np is not None


@pytest.fixture(params=["numpy", "pure"] if HAS_NP else ["pure"])
def backend(request, monkeypatch):
    """Run a test on both code paths; they must agree."""
    if request.param == "pure":
        monkeypatch.setattr(image, "NP", None)
    yield request.param


def noisy(w=64, h=36, seed=1):
    rnd = random.Random(seed)
    img = image.Image(w, h, 3)
    for y in range(h):
        for x in range(w):
            img.put(x, y, (rnd.randrange(256), (x * 4) % 256, (y * 7) % 256))
    return img


# --- image --------------------------------------------------------------------------------------------------------

def test_png_roundtrip(tmp_path, backend):
    img = noisy()
    p = image.write(img, str(tmp_path / "a.png"))
    back = image.decode_png(open(p, "rb").read())
    assert (back.w, back.h, back.c) == (64, 36, 3) and back.data == img.data


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "L", "LA", "P", "I;16"])
def test_png_decode_matches_pil_for_every_filter(tmp_path, backend, mode):
    PIL = pytest.importorskip("PIL.Image")
    rnd = random.Random(3)
    base = PIL.new("RGB", (37, 23))
    base.putdata([(rnd.randrange(256), (i * 3) % 256, (i // 7) % 256) for i in range(37 * 23)])
    im = base.convert(mode) if mode != "I;16" else base.convert("L").convert("I;16")
    p = tmp_path / "f.png"
    im.save(p, optimize=False)  # libpng picks adaptive filters: Sub, Up, Average and Paeth all occur
    got = image.decode_png(p.read_bytes())
    want = {"RGB": im, "RGBA": im, "L": im, "LA": im.convert("RGBA"), "P": im.convert("RGB"),
            "I;16": None}[mode]
    if mode == "I;16":  # 16-bit samples keep their high byte
        import numpy as np
        assert got.c == 1 and got.data == bytearray((np.array(im).astype(np.uint32) >> 8).astype(np.uint8).tobytes())
    else:
        assert got.data == bytearray(want.tobytes())


def test_resize_area_average(backend):
    img = image.Image(4, 2, 1, bytearray([0, 100, 200, 50, 10, 110, 210, 70]))
    small = image.resize(img, 2, 1)
    assert list(small.data) == [55, 133]  # (0+100+10+110)/4, (200+50+210+70)/4 rounded
    big = image.resize(image.Image(1, 1, 3, bytearray([1, 2, 3])), 3, 2)
    assert big.data == bytearray([1, 2, 3] * 6)


def test_resize_backends_agree(monkeypatch):
    if not HAS_NP:
        pytest.skip("numpy")
    img = noisy(97, 61)
    a = image.resize(img, 40, 25)
    monkeypatch.setattr(image, "NP", None)
    b = image.resize(img, 40, 25)
    assert max(abs(x - y) for x, y in zip(a.data, b.data)) <= 1


def test_crop_fit_rgb_paste():
    img = noisy(20, 10)
    c = image.crop(img, 5, 2, 9, 6)
    assert (c.w, c.h) == (4, 4) and c.px(0, 0) == img.px(5, 2)
    assert image.fit(img, 10).size == (10, 5)
    assert image.fit(img, 50) is img
    rgba = image.Image(2, 1, 4, bytearray([1, 2, 3, 9, 4, 5, 6, 9]))
    assert image.rgb(rgba).data == bytearray([1, 2, 3, 4, 5, 6])
    dst = image.Image(4, 4, 3)
    image.paste(dst, image.solid(2, 2, (9, 9, 9)), 3, 3)  # clipped to one pixel
    assert dst.px(3, 3) == (9, 9, 9) and dst.px(2, 2) == (0, 0, 0)
    with pytest.raises(ValueError):
        image.crop(img, 5, 5, 5, 9)


def test_srgb_roundtrip_and_luma(backend):
    for v in (0.0, 0.01, 0.2, 0.5, 1.0):
        assert image.linear_to_srgb(image.srgb_to_linear(v)) == pytest.approx(v, abs=1e-9)
    grey = image.solid(4, 4, (119, 119, 119))
    assert set(image.luma8(grey)) == {119}
    lum = list(image.luminance(grey))
    assert lum[0] == pytest.approx(0.1845, abs=0.002)  # sRGB 119 is ~18% grey


def test_read_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        image.read(str(tmp_path / "missing.png"))
    with pytest.raises(ValueError):
        image.decode_png(b"nope")


# --- draw / overlay / sheet ------------------------------------------------------------------------------------------

def test_text_and_shapes(backend):
    img = image.Image(80, 20, 3)
    box = draw.text(img, 2, 2, "OK 42", "white", 1)
    assert box[2] > box[0]
    lit = sum(1 for i in range(0, len(img.data), 3) if img.data[i] == 255)
    assert lit > 20  # glyphs drawn
    draw.fill(img, 0, 0, 10, 10, (255, 0, 0), 0.5)
    assert img.px(9, 9)[0] in (127, 128)
    draw.line(img, 0, 19, 79, 19, "fail", 1, dash=4)
    assert img.px(0, 19) == (240, 60, 50) and img.px(5, 19) != (240, 60, 50)
    assert draw.wrap("one two three four", 6 * 8, 1).split("\n") == ["one two", "three", "four"]


def test_overlay_guides_boxes_caption(backend):
    base = image.solid(300, 169, (40, 40, 40))
    out = overlay.overlay(base, guides=["thirds", "safe", "center", "grid:4x3", "aspect:2.39", "headroom", "golden"],
                          boxes=[{"box": [0.1, 0.2, 0.4, 0.8], "label": "ADA", "color": "warn", "fill": 0.2}],
                          points=[{"at": [0.5, 0.5], "label": "eye"}], caption="frame 12 CamA")
    assert out.size == base.size and out.data != base.data
    assert out.px(0, 0)[0] < 40  # letterboxed by the 2.39 mask
    with pytest.raises(ValueError):
        overlay.overlay(base, guides=["nope"])


def test_contact_sheet(tmp_path):
    cells = [{"image": image.solid(160, 90, (k * 40, 50, 50)), "label": f"F{k}", "status": s, "note": "n"}
             for k, s in enumerate(["ok", "warn", "fail", "info", None])]
    p = image.write(image.solid(80, 45, (200, 200, 200)), str(tmp_path / "x.png"))
    cells.append(p)
    sh = sheet.contact_sheet(cells, cell_width=160, title="T")
    assert sh.w > 160 * 2 and sh.h > 90 * 2
    sbs = sheet.side_by_side(image.solid(160, 90, (0, 0, 0)), image.solid(320, 180, (255, 255, 255)))
    assert sbs.w > 2 * 160


# --- metrics -------------------------------------------------------------------------------------------------------

def test_exposure_verdicts(backend):
    assert metrics.exposure(image.solid(32, 18, (0, 0, 0)))["verdict"] == "flat"
    g = image.gradient(64, 36)
    e = metrics.exposure(g)
    assert e["verdict"] in ("ok", "clipped") and e["p1"] < e["median"] < e["p99"]
    dark = image.Image(64, 36, 3)
    for i in range(len(dark.data)):
        dark.data[i] = (i * 7) % 20
    assert metrics.exposure(dark)["verdict"] == "under"
    bright = image.Image(64, 36, 3)
    for i in range(len(bright.data)):
        bright.data[i] = 175 + (i * 7) % 81
    assert metrics.exposure(bright)["verdict"] == "over"
    mid = image.solid(10, 10, (119, 119, 119))
    mid.put(0, 0, (0, 0, 0))  # not flat
    assert abs(metrics.exposure(mid)["stops"]) < 0.1


def test_histogram_bins(backend):
    img = image.solid(4, 4, (255, 255, 255))
    h = metrics.histogram(img)
    assert h[255] == 16 and sum(h) == 16
    assert metrics.histogram(img, "r", bins=4) == [0, 0, 0, 16]


def test_color_cast_and_name(backend):
    warm = image.solid(16, 16, (150, 120, 100))
    c = metrics.color(warm)
    assert c["cast"]["r"] > 0.1 and c["cast"]["b"] < -0.1 and c["cast_toward"] == "red/warm"
    blue = metrics.color(image.solid(8, 8, (20, 40, 220)))
    assert blue["name"] == "blue" and blue["saturation"] > 0.8


def test_sharpness_and_regions(backend):
    sharp = noisy(48, 27)
    soft = image.resize(image.resize(sharp, 12, 7), 48, 27)
    assert metrics.sharpness(sharp) > 5 * metrics.sharpness(soft)
    r = metrics.regions(sharp)
    assert set(r) == set(metrics.GRID3) and "color" in r["center"]
    with pytest.raises(ValueError):
        metrics.region_box([0.5, 0.5, 0.2, 0.9])


def test_analyze_issues(backend):
    flat = metrics.analyze(image.solid(64, 36, (0, 0, 0)))
    assert [i["code"] for i in flat["issues"]] == ["image.flat"]
    img = noisy(96, 54)
    # a blurred subject on a sharp frame is a focus miss
    sub = image.resize(image.resize(image.crop(img, 30, 10, 60, 40), 6, 6), 30, 30)
    image.paste(img, sub, 30, 10)
    res = metrics.analyze(img, subjects={"ada": [30 / 96, 10 / 54, 60 / 96, 40 / 54]})
    assert any(i["code"] == "focus.subject_soft" for i in res["issues"])
    dark = image.Image(64, 36, 3)
    for i in range(len(dark.data)):
        dark.data[i] = (i * 7) % 20
    assert any(i["code"] == "exposure.under" for i in metrics.analyze(dark)["issues"])
    assert not any(i["code"] == "exposure.under" for i in metrics.analyze(dark, expect={"stops": [-9, 0]})["issues"])


# --- compare -------------------------------------------------------------------------------------------------------

def test_compare_identical_and_changed(backend):
    a = noisy(80, 45)
    same = compare.compare(a, a.copy())
    assert same["ssim"] == pytest.approx(1.0) and same["psnr"] == float("inf") and same["verdict"] == "same"
    b = a.copy()
    draw.fill(b, 60, 0, 80, 15, (255, 255, 255))  # top-right changed
    r = compare.compare(a, b, cols=4, rows=3)
    assert r["ssim"] < 0.99 and r["psnr"] < 30
    assert any(c["cell"] == [3, 0] for c in r["changed"]) and not any(c["cell"] == [0, 2] for c in r["changed"])
    assert compare.diff_image(a, b).size == a.size


def test_compare_backends_agree(monkeypatch):
    if not HAS_NP:
        pytest.skip("numpy")
    a = noisy(40, 24, 1)
    b = noisy(40, 24, 2)
    s1, p1 = compare.ssim(a, b), compare.psnr(a, b)
    monkeypatch.setattr(image, "NP", None)
    assert compare.ssim(a, b) == pytest.approx(s1, abs=1e-3) and compare.psnr(a, b) == pytest.approx(p1, abs=1e-3)


def test_compare_aspect_mismatch_and_reference():
    with pytest.raises(ValueError):
        compare.compare(image.solid(40, 20, 0), image.solid(20, 20, 0))
    a = noisy(64, 36)
    ok = compare.against_reference(image.resize(a, 128, 72), a)  # same picture at another size
    assert ok["issues"] == [] or all(i["severity"] == "info" for i in ok["issues"])
    bad = compare.against_reference(image.solid(64, 36, (250, 250, 250)), a, name="f12")
    assert any(i["code"] == "compare.differs" for i in bad["issues"])


# --- framing -------------------------------------------------------------------------------------------------------

def body(at=(0.0, 0.0, 0.0), facing_x=-1):
    """A standing figure 180 cm tall at `at`, facing -X (toward a camera on +X) by default: bone -> location."""
    x0, y0, z0 = at
    side = -1 if facing_x < 0 else 1  # facing -X: the body's left is at +Y (Unreal: Y right of +X)
    b = {"head": 162, "neck_01": 150, "spine_05": 138, "spine_03": 120, "spine_01": 105, "pelvis": 98,
         "thigh_l": 92, "thigh_r": 92, "calf_l": 50, "calf_r": 50, "foot_l": 9, "foot_r": 9, "ball_l": 3, "ball_r": 3,
         "upperarm_l": 142, "upperarm_r": 142, "lowerarm_l": 112, "lowerarm_r": 112, "hand_l": 86, "hand_r": 86}
    out = {}
    for name, z in b.items():
        y = 0.0
        if name.endswith("_l"):
            y = 18.0 * side if "arm" in name or "hand" in name else 10.0 * side
        elif name.endswith("_r"):
            y = -18.0 * side if "arm" in name or "hand" in name else -10.0 * side
        out[name] = [x0, y0 + y, z0 + z]
    return out


def cam_at(x, z, look_z, fov=40.0, y=0.0, aspect=16 / 9):
    return framing.Camera([x, y, z], framing.look_at([x, y, z], [0, y, look_z]), fov=fov, aspect=aspect, name="Cam")


def test_axes_and_projection():
    f, r, u = framing.axes({"yaw": 90})
    assert f == pytest.approx((0, 1, 0), abs=1e-9) and r == pytest.approx((-1, 0, 0), abs=1e-9) and u == pytest.approx((0, 0, 1))
    cam = framing.Camera([0, 0, 0], {"pitch": 0, "yaw": 0, "roll": 0}, fov=90, aspect=2.0)
    assert cam.project([100, 0, 0]) == pytest.approx((0.5, 0.5, 100))
    assert cam.project([100, 100, 0])[:2] == pytest.approx((1.0, 0.5))      # right edge at 45 degrees
    assert cam.project([100, 0, 50])[:2] == pytest.approx((0.5, 0.0))        # top edge: vertical half-angle tan = 0.5
    assert cam.project([-10, 0, 0])[2] < 0
    rolled = framing.Camera([0, 0, 0], {"roll": 90}, fov=90, aspect=1.0)
    u_, v_, _ = rolled.project([100, 0, 50])  # rolled 90 degrees: world up appears on a side of the frame
    assert v_ == pytest.approx(0.5) and abs(u_ - 0.5) == pytest.approx(0.25)
    d = cam.ray(*cam.project([100, 40, -20])[:2])
    n = math.sqrt(100 ** 2 + 40 ** 2 + 20 ** 2)
    assert d == pytest.approx((100 / n, 40 / n, -20 / n))
    fov = framing.Camera([0, 0, 0], {}, focal=35, sensor_width=36).fov
    assert fov == pytest.approx(54.43, abs=0.01)
    with pytest.raises(ValueError):
        framing.Camera([0, 0, 0], {})


def test_camera_from_dict_and_screen_box():
    cam = framing.Camera.from_dict({"loc": [500, 0, 100], "look_at": [0, 0, 100], "fov": 60})
    sb = framing.screen_box(cam, framing.bounds_corners([0, 0, 100], [20, 20, 20]))
    assert sb["in_frame"] == 1.0 and 0.4 < sb["box"][0] < 0.5 < sb["box"][2] < 0.6
    behind = framing.screen_box(cam, [[900, 0, 100]])
    assert behind["box"] is None and behind["behind"] == 1


def test_shot_sizes_from_distance():
    b = body()
    sizes = {}
    for x in (90, 160, 260, 380, 700, 2500):
        cam = cam_at(x, 160, 150 if x < 300 else 95, fov=40)
        sizes[x] = framing.shot_size(cam, framing.derive_landmarks(b))["size"]
    order = ["ECU", "CU", "MCU", "MS", "MLS", "LS", "ELS"]
    seq = [order.index(sizes[x]) for x in sorted(sizes)]
    assert seq == sorted(seq) and sizes[2500] in ("LS", "ELS") and sizes[90] in ("ECU", "CU")


def test_check_long_shot_clean_and_suggest():
    b = body()
    cam = cam_at(600, 100, 90, fov=40)
    r = framing.check(cam, "ada", bones=b, frame=10)
    assert r["size"]["size"] in ("LS", "MLS")
    codes = {i["code"] for i in r["issues"]}
    assert "framing.out_of_frame" not in codes and "framing.feet_cut" not in codes
    s = framing.suggest(cam, b, "MCU")
    cam2 = framing.Camera(s["loc"], framing.look_at(s["loc"], s["look_at"]), fov=40)
    r2 = framing.check(cam2, "ada", bones=b, expect={"size": "MCU"})
    assert r2["size"]["size"] == "MCU"
    assert not any(i["code"] in ("framing.size", "framing.headroom_low", "framing.headroom_high") for i in r2["issues"])


def test_check_feet_cut_and_headroom():
    b = body()
    # aim so the frame bottom lands just above the ankles: feet cut
    cam = cam_at(420, 100, 96, fov=40)
    tz = cam.ty * 420  # half the frame height at the body
    # move the camera up so the bottom edge sits at z ~ 16 (between ankle 9 and calf 50... above the ankles)
    shift = (96 - tz) - 14
    cam = cam_at(420, 100 + shift, 96 + shift, fov=40)
    r = framing.check(cam, "ada", bones=b)
    codes = [i["code"] for i in r["issues"]]
    assert "framing.feet_cut" in codes
    # too much headroom: subject small at the bottom of a tight vertical frame
    cam3 = cam_at(400, 260, 220, fov=40)
    r3 = framing.check(cam3, "ada", bones=b)
    assert any(i["code"] in ("framing.headroom_high", "framing.head_out") for i in r3["issues"]) or r3["size"]["size"] == "OUT"


def test_check_head_cut_and_out_of_frame():
    b = body()
    cam = cam_at(120, 140, 140, fov=40)  # tight on the chest: the crown is above the frame
    r = framing.check(cam, "ada", bones=b)
    assert any(i["code"] in ("framing.headroom_low", "framing.head_out") for i in r["issues"])
    away = framing.Camera([300, 0, 100], {"yaw": 0}, fov=40)  # looking away from the body
    r2 = framing.check(away, "ada", bones=b)
    assert r2["issues"][0]["code"] == "framing.out_of_frame" and r2["issues"][0]["severity"] == "fail"


def test_check_joint_cut_at_knees():
    b = body()
    for x in range(250, 460, 4):  # find a camera height where the bottom edge sits on the knees (z 50)
        cam = cam_at(x, 120, 110, fov=40)
        u, v, d = cam.project(b["calf_l"])
        if abs(1 - v) < 0.015:
            break
    r = framing.check(cam, "ada", bones=b)
    assert any(i["code"] == "framing.joint_cut" and "knee" in i["message"] for i in r["issues"])


def test_look_room():
    b = body()
    # the figure faces +Y (screen left for a camera on +X looking -X)... place it frame-left so it looks off the edge
    turned = {k: [v[0], v[1], v[2]] for k, v in b.items()}
    cam = cam_at(250, 150, 150, fov=40, y=0)
    facing = (0.0, -1.0, 0.0)  # world -Y: for this camera (right vector -Y... computed) check both ways
    r1 = framing.check(cam, "ada", bones=turned, facing=facing)
    r2 = framing.check(cam, "ada", bones=turned, facing=(0.0, 1.0, 0.0))
    assert {r1.get("looks"), r2.get("looks")} == {"left", "right"}
    # move the subject to the side it looks toward: little room -> issue
    side = 1 if r1["looks"] == "right" else -1
    cam_r = framing.Camera(cam.loc, framing.look_at(cam.loc, [0, 0, 150]), fov=40)
    shift = [0, 0, 0]
    # shift the body along the camera's right vector so it sits at u ~ 0.8 (looking right) or 0.2 (left)
    off = 0.3 * 2 * cam_r.tx * 250 * side
    moved = {k: [v[0] + cam_r.right[0] * off, v[1] + cam_r.right[1] * off, v[2]] for k, v in turned.items()}
    r3 = framing.check(cam_r, "ada", bones=moved, facing=facing)
    assert any(i["code"] == "framing.look_room" for i in r3["issues"]), (r3.get("eyes"), r3.get("looks"), shift)


def test_framing_bounds_only_and_expect():
    cam = framing.Camera.from_dict({"loc": [300, 0, 50], "look_at": [0, 0, 50], "fov": 40})
    r = framing.check(cam, "lamp", bounds=([0, 120, 50], [30, 30, 50]))
    assert r["issues"] and r["issues"][0]["code"] == "framing.cut"
    ok = framing.check(cam, "lamp", bounds=([0, 0, 50], [10, 10, 20]))
    assert ok["issues"] == []
    with pytest.raises(ValueError):
        framing.check(cam, "x")
    r2 = framing.check(cam_at(600, 100, 90), "ada", bones=body(), expect={"size": "CU"})
    assert any(i["code"] == "framing.size" and "tighten" in i["fix"] for i in r2["issues"])


# --- geometry ------------------------------------------------------------------------------------------------------

def test_overlaps():
    items = {"table": ([0, 0, 40], [60, 40, 40]), "cup": ([0, 0, 85], [4, 4, 5]),
             "chair": ([50, 0, 40], [25, 25, 40]), "far": ([500, 0, 0], [10, 10, 10])}
    r = geometry.overlaps(items)
    pairs = {frozenset(p[:2]) for p in r["pairs"]}
    assert frozenset(("table", "chair")) in pairs and frozenset(("table", "cup")) not in pairs
    assert not any("far" in p for p in pairs)
    assert geometry.overlaps(items, ignore_pairs=[("table", "chair")])["pairs"] == []
    assert r["issues"][0]["code"] == "mesh.overlap"


def test_floating():
    items = {"vase": ([0, 0, 105], [5, 5, 5]), "box": ([50, 0, 10], [10, 10, 10]), "lamp": ([0, 0, 300], [5, 5, 5]),
             "rug": ([0, 0, -2], [100, 100, 1])}
    r = geometry.floating(items, {"vase": 4.0, "box": 0.2, "lamp": None, "rug": -6})
    codes = {i["subject"]: i["code"] for i in r["issues"]}
    assert codes == {"vase": "mesh.floating", "lamp": "mesh.unsupported", "rug": "mesh.sunk"}
    assert "loc=[0.0, 0.0, 101.0]" in next(i["fix"] for i in r["issues"] if i["subject"] == "vase")


def test_penetration_from_depth_layers():
    w, h = 20, 10
    inf = float("inf")
    garment = [inf] * (w * h)
    body_ = [inf] * (w * h)
    for y in range(2, 9):
        for x in range(4, 16):
            garment[y * w + x] = 100.0
            body_[y * w + x] = 101.5  # under the cloth
    for y, x in ((4, 6), (4, 7), (5, 6), (5, 7), (6, 12)):  # skin pokes through in two places
        body_[y * w + x] = 98.0
    r = geometry.penetration(body_, garment, w, h)
    assert r["pixels"] == 5 and r["garment_pixels"] == 84 and r["worst_cm"] == 2.0
    assert [c["pixels"] for c in r["clusters"]] == [4, 1]
    assert r["clusters"][0]["box"] == [0.3, 0.4, 0.4, 0.6]
    iss = geometry.penetration_issues(r, "ada", view="front", min_pixels=2)
    assert iss and iss[0]["code"] == "mesh.penetration" and iss[0]["severity"] == "fail"
    clean = geometry.penetration(body_, garment, w, h, tolerance_cm=5)
    assert clean["pixels"] == 0 and geometry.penetration_issues(clean, "ada") == []
    out = geometry.mask_overlay(image.solid(w, h, (0, 0, 0)), r["mask"])
    assert out.px(6, 4) != (0, 0, 0) and out.px(0, 0) == (0, 0, 0)
    with pytest.raises(ValueError):
        geometry.penetration([1.0], [1.0, 2.0], 1, 1)


# --- continuity ----------------------------------------------------------------------------------------------------

def test_snapshot_diff():
    a = {"actors": {"Chair": {"class": "StaticMeshActor", "loc": [0, 0, 0], "rot": {"yaw": 0}, "scale": [1, 1, 1],
                              "materials": ["/Game/M_Wood"], "props": {"intensity": 10.0}},
                    "Lamp": {"class": "PointLight", "loc": [100, 0, 200], "props": {"intensity": 5000.0,
                                                                                      "light_color": [1, 0.9, 0.8]}},
                    "FMQA_Rig": {"class": "SceneCapture2D", "loc": [0, 0, 0]}}}
    b = json.loads(json.dumps(a))
    b["actors"]["Chair"]["loc"] = [12, 0, 0]
    b["actors"]["Chair"]["rot"] = {"yaw": 359.8}  # wraps: no change
    b["actors"]["Lamp"]["props"]["intensity"] = 2500.0
    del b["actors"]["FMQA_Rig"]
    b["actors"]["Cup"] = {"class": "StaticMeshActor", "loc": [0, 0, 80]}
    d = continuity.diff(a, b, ignore=["FMQA_*"])
    assert d["added"] == ["Cup"] and d["removed"] == []
    assert set(d["changed"]) == {"Chair", "Lamp"} and "rot" not in d["changed"]["Chair"]
    assert d["changed"]["Lamp"] == {"props.intensity": [5000.0, 2500.0]}
    assert all(i["severity"] == "info" for i in d["issues"])
    assert continuity.diff(a, a)["changed"] == {}


def test_frame_continuity(backend):
    a = metrics.analyze(image.solid(32, 18, (120, 110, 100)) if False else noisy(32, 18))
    dark = image.Image(32, 18, 3, bytearray(v // 4 for v in noisy(32, 18).data))
    b = metrics.analyze(dark)
    iss = continuity.frames(a, b, name="cut 3->4:")
    assert any(i["code"] == "continuity.exposure_jump" for i in iss)


# --- review --------------------------------------------------------------------------------------------------------

def test_review_build(tmp_path):
    p1 = image.write(noisy(160, 90), str(tmp_path / "0001.png"))
    panels = [
        {"image": p1, "frame": 1, "camera": "CamA", "issues": [
            qa.issue("framing.feet_cut", "warn", "feet cut", "widen", box=[0.4, 0.9, 0.6, 1.0])]},
        {"image": image.solid(160, 90, (0, 0, 0)), "frame": 2, "camera": "CamB",
         "issues": [qa.issue("image.flat", "fail", "black frame")]},
        {"image": str(tmp_path / "missing.png"), "frame": 3},
    ]
    rep = review.build(panels, str(tmp_path / "rev"), title="shot 010",
                       scene_issues=[qa.issue("mesh.floating", "warn", "vase floats", subject="vase")])
    assert rep["verdict"] == "fail" and rep["counts"] == {"fail": 1, "warn": 3, "info": 0}
    assert rep["summary"][0].startswith("[fail] frame 2 CamB: black frame")
    js = json.loads(open(rep["json"]).read())
    assert js["panels"][0]["status"] == "warn" and js["panels"][1]["status"] == "fail"
    img = image.read(rep["image"])
    assert img.w > 300 and img.h > 200
    empty = review.build([], str(tmp_path / "rev2"))
    assert empty["verdict"] == "ok" and qa.worst([]) == "ok"


def test_issue_validation():
    with pytest.raises(ValueError):
        qa.issue("x", "bad", "m")
    i = qa.issue("a.b", "warn", "m", frame=None, value=0)
    assert "frame" not in i and i["value"] == 0
