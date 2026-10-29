"""film-anime-render and film-anime-review (filmtools.anime.plates, render, review): which shot makes each scene, when a
plate is up to date, the review's grade and its sheet. Nothing here runs Blender or the app."""
import json
from pathlib import Path

import numpy as np
import pytest

from filmtools.anime import plates as P
from filmtools.anime import render as Rn
from filmtools.anime import review as R

from conftest import make_film


@pytest.fixture
def repo(tmp_path):
    """A repo with a film of three scenes, a render.py importing the core, and two shot files."""
    f = make_film(tmp_path, "demo", fps=24)
    (f.data / "timeline.json").write_text(json.dumps({"fps": 24, "format": [1920, 1080], "scenes": [
        {"id": "a", "start": 0, "end": 2}, {"id": "b", "start": 2, "end": 3.3}, {"id": "c", "start": 3.3, "end": 5}]}))
    (f.data / "plates.json").write_text(json.dumps({"plates": {"b": "b_alt"}}))
    (f.data / "look.json").write_text(json.dumps({"shots": {"a": {"rain": 1}, "b": {"rain": 0.5}}}))
    lib = tmp_path / "blender" / "lib"
    lib.mkdir(parents=True)
    (lib / "__init__.py").write_text("")
    (lib / "core.py").write_text("from .util import x\n")
    (lib / "util.py").write_text("x = 1\n")
    (lib / "unused.py").write_text("")
    (tmp_path / "blender" / "render.py").write_text("from lib import core\n")
    rf = f.dir / "blender" / "rf"
    rf.mkdir(parents=True)
    (rf / "__init__.py").write_text("")
    (rf / "sets.py").write_text("import lib.util\n")
    shots = f.dir / "blender" / "shots"
    shots.mkdir()
    (shots / "base.py").write_text("SHOT = {}\n")
    (shots / "a.py").write_text("from rf import sets\nimport importlib\nP = 'base.py'\n")
    (shots / "b_alt.py").write_text("from lib import core, util\n")
    (f.dir / "assets" / "vroid").mkdir(parents=True)
    (f.dir / "assets" / "vroid" / "m.vrm").write_bytes(b"model")
    (f.dir / "assets" / "ref").mkdir()
    (f.dir / "assets" / "ref" / "a.jpg").write_bytes(b"ref")
    return tmp_path, f


def test_scenes_take_their_plate_from_plates_json_and_their_frames_as_the_engine(repo):
    _, f = repo
    s = {x.id: x for x in P.scenes(f)}
    assert s["a"].plate == "a" and s["b"].plate == "b_alt" and s["c"].plate == "c"
    assert (s["a"].f0, s["a"].f1) == (0, 48) and (s["b"].f0, s["b"].f1) == (48, 80) and s["c"].f0 == 80
    assert s["a"].exists and s["b"].exists and not s["c"].exists


def test_the_module_graph_follows_imports_through_the_core_and_the_film_and_files_named_beside(repo):
    root, f = repo
    roots = [root / "blender", f.dir / "blender"]
    g = {str(p.relative_to(root)) for p in P.module_graph([f.dir / "blender/shots/a.py", root / "blender/render.py"], roots)}
    assert g == {"films/demo/blender/shots/a.py", "films/demo/blender/shots/base.py", "films/demo/blender/rf/__init__.py",
                 "films/demo/blender/rf/sets.py", "blender/lib/__init__.py", "blender/lib/util.py", "blender/lib/core.py",
                 "blender/render.py"}


def test_a_plates_hash_moves_with_its_code_its_models_and_its_own_look_entry_only(repo):
    root, f = repo
    a = next(s for s in P.scenes(f) if s.id == "a")
    fp = lambda: P.fingerprint(f, a, P.FINAL, root)["hash"]  # noqa: E731
    h0 = fp()
    assert "assets/ref" not in " ".join(P.fingerprint(f, a, P.FINAL, root)["files"])
    (root / "blender/lib/unused.py").write_text("y = 2\n")
    assert fp() == h0  # not imported
    d = json.loads((f.data / "look.json").read_text())
    d["shots"]["b"]["rain"] = 0.1
    (f.data / "look.json").write_text(json.dumps(d))
    assert fp() == h0  # another shot's entry
    for change in (lambda: (root / "blender/lib/util.py").write_text("x = 2\n"),
                   lambda: (f.dir / "assets/vroid/m.vrm").write_bytes(b"model 2"),
                   lambda: (f.data / "look.json").write_text(json.dumps({"shots": {"a": {"rain": 0.2}}})),
                   lambda: (f.dir / "blender/shots/base.py").write_text("SHOT = {'scene': 'a'}\n")):
        change()
        h1 = fp()
        assert h1 != h0
        h0 = h1
    assert P.fingerprint(f, a, P.PREVIEW, root)["hash"] != h0


def test_the_plan_renders_what_is_stale_skips_what_is_stamped_and_slates_what_has_no_shot(repo, monkeypatch):
    root, f = repo
    monkeypatch.setattr(P.paths, "ROOT", root)
    steps = {s["scene"]: s for s in Rn.plan(f, P.FINAL, None, False)}
    assert steps["a"]["action"] == "render" and steps["b"]["action"] == "render" and steps["c"]["action"] == "no shot"
    P.write_stamp(f, "a", steps["a"]["fingerprint"], P.FINAL)
    steps = {s["scene"]: s for s in Rn.plan(f, P.FINAL, None, False)}
    assert steps["a"]["action"] == "up to date" and steps["b"]["action"] == "render"
    assert {s["scene"]: s["action"] for s in Rn.plan(f, P.FINAL, ["a"], True)} == {"a": "render"}


def test_a_failed_plate_is_set_aside_so_the_film_slates_it(repo):
    _, f = repo
    d = P.plates_dir(f, "a")
    (d / "proxy").mkdir(parents=True)
    (d / "0000.exr").write_bytes(b"x")
    Rn.set_aside(f, "a")
    assert not d.exists() and (d.parent / "a.failed" / "0000.exr").exists()


def test_the_plate_size_is_the_modes(repo):
    _, f = repo
    assert P.mode_res(f, P.FINAL) == "1920x1080" and P.mode_res(f, P.PREVIEW) == "960x540"
    assert P.mode_res(f, {**P.PREVIEW, "res": "480x270"}) == "480x270"


def test_the_review_grade_is_neutral_by_default_and_keeps_luma_when_it_warms():
    img = np.random.default_rng(1).uniform(0.05, 0.95, (8, 12, 3))
    assert np.allclose(R.grade(img, {}), img, atol=1e-9)
    warm = R.grade(img, {"warmth": 0.3})
    lin = lambda s: R._srgb_to_lin(s)  # noqa: E731
    assert np.allclose(R._luma(lin(warm)), R._luma(lin(img)), atol=1e-6)
    assert (warm[..., 0] - warm[..., 2]).mean() > (img[..., 0] - img[..., 2]).mean()
    grey = R.grade(img, {"saturation": 0})
    assert np.allclose(grey[..., 0], grey[..., 1]) and np.allclose(grey[..., 1], grey[..., 2])


def test_review_frames_and_labels():
    sc = P.Scene("b", 2, 3.3, "b_alt", Path("x.py"), 48, 80)
    assert R.frames_of(sc, 1) == [63] and R.frames_of(sc, 2) == [58, 69] and R.frames_of(sc, 3) == [48, 63, 79]
    assert R.label(3, sc, 63, 24) == "03 b [b_alt]  2.62s  f63"


def test_the_sheet_tiles_pictures_and_slates_with_labels(tmp_path):
    from PIL import Image

    p = tmp_path / "x.png"
    Image.new("RGB", (96, 54), (200, 10, 10)).save(p)
    out = R.tile([{"label": "01 a", "image": p}, {"label": "02 b", "slate": ["b", "not rendered"]}] * 4,
                 tmp_path / "s.png", cols=3, size=(96, 54), title="t")
    im = Image.open(out)
    assert im.size == (3 * 102 + 6, 30 + 3 * (54 + R.TILE_LABEL + 6) + 6)
    assert im.getpixel((6 + 48, 30 + 6 + R.TILE_LABEL + 27))[0] > 150  # the first tile's red


def test_cuts_pair_the_last_frame_out_with_the_first_frame_in():
    a = P.Scene("a", 0, 2, "a", Path("a.py"), 0, 48)
    b = P.Scene("b", 2, 3.3, "b_alt", Path("b.py"), 48, 80)
    c = P.Scene("c", 3.3, 5, "c", Path("c.py"), 80, 120)
    cuts = R.cut_order([a, b, c])
    assert [(n, s.id, f) for n, s, f, _ in cuts] == [(1, "a", 47), (2, "b", 48), (2, "b", 79), (3, "c", 80)]
    assert cuts[0][3].startswith("cut 01 out") and cuts[1][3].startswith("cut 01 in")
    assert [(s.id, f) for _, s, f, _ in R.cut_order([a, b, c], ["c"])] == [("b", 79), ("c", 80)]
