"""bake.py end to end on a synthetic film: no clips, no GPU, 1/10 scale."""
import json
import shutil

import cv2
import numpy as np
import pytest

from filmtools.amv import bake, layerfx as fx, plan as planmod

SCALE = 0.1


def make_film(tmp_path):
    return _build(tmp_path)


def _build(tmp_path):
    film = tmp_path / "films" / "syn"
    (film / "amv").mkdir(parents=True)
    (film / "film.json").write_text(json.dumps({"id": "syn", "amv": {"plan": "amv/plan.json"}}))
    n = 4
    shot = {"name": "S1", "a": 0, "b": n, "end": n, "src": "clip", "remap": [0.0] * n,
            "px": [960.0] * n, "py": [540.0] * n, "s": [100.0] * n, "rz": [0.0] * n,
            "tile": [120, 110], "ev": 0.5, "sat": -12,
            "rfb": [[0, 30, 960.0, 540.0], [3, 0, 960.0, 540.0]], "dblur": [[0, 20], [3, 0]], "bulge": [[0, 20], [3, 0]],
            "hole": [[960.0, 540.0, 200.0, 150.0]] * n, "hole_f0": 0,
            "titles": [{"style": "x", "f_in": 1, "spec": {"text": "T", "dur": 2}}],
            "matte": "assets/roto/S1/00000.png", "rim": True}
    plan = {"dur": n, "fps": 30, "footage": {"clip": "assets/clips/none.mp4"}, "shots": [shot]}
    (film / "amv" / "plan.json").write_text(json.dumps(plan))
    out = tmp_path / "out" / "syn" / "amv"
    for f in range(n):
        yy, xx = np.mgrid[0:1080, 0:1920]
        img = np.stack([xx / 1920, yy / 1080, np.full_like(xx, 0.4, float)], axis=2).astype(np.float32)
        bake.write_png(out / "src" / "S1" / f"{f:04d}.png", np.dstack([img, np.ones((1080, 1920, 1), np.float32)]))
    t = np.zeros((1080, 1920, 4), np.float32)
    t[500:580, 800:1100] = (1, 0, 0, 1)
    for k in range(2):
        bake.write_png(out / "titles" / "S1.0" / f"{k:04d}.png", t)
    (film / "assets" / "roto" / "S1").mkdir(parents=True)
    m = np.zeros((1080, 1920, 4), np.float32)
    m[:, :960] = 1
    m[..., 3] = 1
    for i in range(n):
        bake.write_png(film / "assets" / "roto" / "S1" / f"{i:05d}.png", m)
    return film, out


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    """One synthetic film shared by the tests (writing its 1080p PNGs is the slow part); tests copy what they mutate."""
    return _build(tmp_path_factory.mktemp("syn"))


def test_scaled_canvas_matches_plan_at_full_scale():
    for tile in ((110, 110), (135, 110), (155, 245)):
        shot = planmod.Shot(0, {"name": "x", "tile": list(tile)})
        assert bake.scaled_canvas(shot, 1.0) == shot.canvas
        cw, ch, ox, oy = bake.scaled_canvas(shot, 0.5)
        assert cw % 2 == 0 and ch % 2 == 0
        assert abs(cw - shot.canvas[0] / 2) <= 1 and abs(ch - shot.canvas[1] / 2) <= 1
        assert abs(ox - shot.canvas[2] / 2) <= 1 and abs(oy - shot.canvas[3] / 2) <= 1


def test_bake_cli_writes_contract(synth, tmp_path):
    film, out = synth
    assert bake.main(["--film", str(film), "--scale", str(SCALE), "--workers", "1", "--out", str(tmp_path / "layers")]) == 0
    plan = planmod.load(film)
    shot = plan.shots[0]
    meta = json.loads((tmp_path / "layers" / "S1" / "canvas.json").read_text())
    cw, ch, ox, oy = bake.scaled_canvas(shot, SCALE)
    assert meta == {"w": cw, "h": ch, "ox": ox, "oy": oy, "scale": SCALE}
    files = sorted(p.name for p in (tmp_path / "layers" / "S1").glob("*.png"))
    assert files == [f"{f:04d}.png" for f in range(4)]
    img = cv2.imread(str(tmp_path / "layers" / "S1" / "0001.png"), cv2.IMREAD_UNCHANGED)
    assert img.shape == (ch, cw, 4)


def test_frame_content(synth, tmp_path):
    film, out = synth
    plan = planmod.load(film)
    shot = plan.shots[0]
    matte = bake.Matte(plan, shot)
    assert matte.count == 4
    f = 3                                            # all effects at zero: the plain composite
    img = bake.bake_frame(plan, shot, f, SCALE, str(out / "src"), str(out / "titles"), matte)
    cw, ch, ox, oy = bake.scaled_canvas(shot, SCALE)
    assert img.shape == (ch, cw, 4)
    lw, lh = bake.layer_size(SCALE)
    # the hole (r 200 x 150 px, expansion 0 .. 4 .. 40 keyed up to b-1 = 3): transparent in the middle, opaque at the corners
    cx, cy = ox + lw // 2, oy + lh // 2
    assert img[cy, cx, 3] == 0
    assert img[oy + 2, ox + 2, 3] == 1
    # mirrored tile: pixel just left of the layer copies the layer's first column, everywhere alpha is 1
    assert img[oy + 2, ox - 1, 3] > 0.99
    # the title (red box, tile-centred at 960,540 -> inside the hole, so look at a frame without hole instead)
    shot.raw.pop("hole")
    img = bake.bake_frame(plan, shot, 2, SCALE, str(out / "src"), str(out / "titles"), matte)
    ty, tx = oy + int(540 * SCALE), ox + int(1050 * SCALE)
    assert img[ty, tx, 0] > 0.9 and img[ty, tx, 1] < 0.1                  # title over the right half of the matte...
    # ...and the cutout (matte = left half) sits over the title: the title's left part (x 800..960) is hidden
    tx_l = ox + int(850 * SCALE)
    assert img[ty, tx_l, 0] < 0.9 or img[ty, tx_l, 1] > 0.1
    # frame with no title: the plate's gradient shows (green grows with y)
    img0 = bake.bake_frame(plan, shot, 0, SCALE, str(out / "src"), str(out / "titles"), matte)
    assert img0[oy + int(900 * SCALE), cx, 1] > img0[oy + int(100 * SCALE), cx, 1]


def test_missing_titles_and_src_standin_fail_clearly(synth, tmp_path):
    film, out = synth
    plan = planmod.load(film)
    shot = plan.shots[0]
    assert bake.title_frames(plan, shot, 1, str(tmp_path / "nowhere"), SCALE) == []
    with pytest.raises(FileNotFoundError):                       # no src and no clip: say so, don't write black
        bake.bake_frame(plan, shot, 0, SCALE, str(tmp_path / "nosrc"), None, None)


def test_matte_outside_sequence_hides_cutout(synth, tmp_path):
    film, out = synth
    plan = planmod.load(film)
    m = bake.Matte(plan, plan.shots[0])
    assert m.frame(-1, SCALE) is None and m.frame(4, SCALE) is None
    assert m.frame(2, SCALE).shape == bake.layer_size(SCALE)[::-1]


def test_select_and_frames():
    assert bake.parse_frames("30-40") == (30, 40) and bake.parse_frames("7") == (7, 7) and bake.parse_frames(None) is None
