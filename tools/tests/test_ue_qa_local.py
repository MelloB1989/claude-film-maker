"""film-qa (filmtools.unreal.qa_local): the QA core on local stills, no editor."""
import json

import pytest

from filmtools.unreal import qa_local


def _still(path, color, w=64, h=36):
    q = qa_local.qa()
    im = __import__("fmqa.image", fromlist=["image"])
    img = im.Image(w, h, 3)
    for y in range(h):
        for x in range(w):
            img.put(x, y, tuple(min(255, c + (x * 3 + y * 5) % 40) for c in color))
    return im.write(img, str(path))


def test_image_compare_sheet_overlay(tmp_path, capsys):
    a = _still(tmp_path / "00010.png", (90, 80, 70))
    b = _still(tmp_path / "00020.png", (10, 10, 10))
    r = qa_local.image(a)
    assert r["pass"] and "exposure" in r["metrics"]
    c = qa_local.compare(a, a, diff=str(tmp_path / "d.png"))
    assert c["metrics"]["ssim"] == pytest.approx(1.0) and (tmp_path / "d.png").is_file()
    s = qa_local.sheet(str(tmp_path / "s.png"), [a, b], title="t")
    assert s["cells"] == 2 and (tmp_path / "s.png").is_file()
    o = qa_local.overlay(a, str(tmp_path / "o.png"), ["thirds", "safe"], [{"box": [0.1, 0.1, 0.5, 0.5], "label": "x"}])
    assert o["width"] == 64
    qa_local.main(["sheet", str(tmp_path / "s2.png"), a, b, "--labels", "one,two"])
    assert json.loads(capsys.readouterr().out)["cells"] == 2


def test_review_folder_and_exit_code(tmp_path, capsys):
    d = tmp_path / "frames"
    d.mkdir()
    _still(d / "00010.png", (120, 110, 100))
    _still(d / "00011.png", (0, 0, 0), w=64, h=36)  # nearly black: underexposed, exposure jump
    r = qa_local.review(str(d))
    assert (d / "review.json").is_file() and (d / "review.png").is_file()
    assert any(i["code"].startswith("exposure.") for i in r["issues"])
    with pytest.raises(SystemExit):  # a flat black frame is a fail: exit 1
        flat = d / "flat"
        flat.mkdir()
        q = qa_local.qa()
        im = __import__("fmqa.image", fromlist=["image"])
        im.write(im.solid(32, 18, (0, 0, 0)), str(flat / "00001.png"))
        qa_local.main(["review", str(flat)])


def test_framing_from_numbers(tmp_path):
    cam = {"loc": [600, 0, 100], "look_at": [0, 0, 90], "fov": 40, "name": "Cam"}
    bones = {"head": [0, 0, 162], "pelvis": [0, 0, 98], "calf_l": [0, 10, 50], "foot_l": [0, 10, 9], "ball_l": [0, 10, 3]}
    r = qa_local.framing(cam, bones, "ada")
    assert r["metrics"]["size"]["size"] in ("LS", "MLS")
