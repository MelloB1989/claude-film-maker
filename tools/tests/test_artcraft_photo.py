"""ArtCraft stills (LightCraft + PhotoCraft): looks, targets, crops and the steps each app gets, always; a real grade
through both engines when `lightcraft-cli` and `photocraft-cli` are installed (python -m filmtools.artcraft install
lightcraft photocraft, or $LIGHTCRAFT_CLI / $PHOTOCRAFT_CLI)."""
import json
from pathlib import Path

import numpy as np
import pytest
from conftest import make_film

from filmtools.artcraft import install
from filmtools.artcraft import lightcraft as LC
from filmtools.artcraft import photo as PH
from filmtools.artcraft import photocraft as PC

LC_CLI, PC_CLI = LC.find_cli(), PC.find_cli()
needs_cli = pytest.mark.skipif(not LC_CLI or not PC_CLI, reason="lightcraft-cli / photocraft-cli not installed")


# ---------------------------------------------------------------------------------------------- targets, crops

def test_targets():
    assert PH.parse_target("instagram-portrait") == (1440, 1800)
    assert PH.parse_target("1080x1350") == (1080, 1350)
    assert PH.parse_target("4:5@1800") == (1440, 1800)
    assert PH.parse_target("16:9@1920") == (1920, 1080)
    assert PH.parse_target("film", (1080, 1920)) == (1080, 1920)
    assert PH.parse_target([600, 400]) == (600, 400)
    for bad in ("nope", "4:x"):
        with pytest.raises(SystemExit):
            PH.parse_target(bad)
    with pytest.raises(SystemExit, match="--film"):
        PH.parse_target("film")


@pytest.mark.parametrize("crop,focus,zoom", [(None, None, 1), ([0.21, 0.14, 0.83], None, 1), ([0.1, 0.1, 0.9, 0.5], None, 1),
                                             (None, [0.95, 0.02], 2.0), ([0.5, 0.9, 1.6], None, 1)])
def test_crop_is_the_target_aspect_and_inside_the_photo(crop, focus, zoom):
    x, y, w, h = PH.crop_rect((3024, 4032), (1440, 1800), crop, focus, zoom)
    assert abs(w / h - 0.8) < 1e-3
    assert 0 <= x and 0 <= y and x + w <= 3024 and y + h <= 4032


def test_crop_values():
    assert PH.crop_rect((3024, 4032), (1440, 1800)) == (0, 126, 3024, 3780)              # largest 4:5, centred
    assert PH.crop_rect((3024, 4032), (1440, 1800), [0.21, 0.14, 0.83]) == (635, 564, 1875, 2344)
    x, y, w, h = PH.crop_rect((4000, 3000), (1000, 1000), focus=[1.0, 0.5], zoom=2)       # pushed back inside
    assert (w, h) == (1500, 1500) and x + w == 4000


# --------------------------------------------------------------------------------------------------------- looks

def test_builtin_looks_resolve_complete():
    for name in PH.LOOKS:
        lo = PH.resolve_look(name)
        assert set(lo) >= {"develop", "sky", "person", "face", "finish"}
        assert set(lo["finish"]) == set(PH.FINISH)


def test_look_inherits_from_base():
    extra = {"warm-fresh": {"base": "fresh", "develop": {"wb.temp": 6700}, "finish": {"leak": 10}}}
    lo = PH.resolve_look("warm-fresh", extra)
    assert lo["develop"]["wb.temp"] == 6700
    assert lo["develop"]["mixer.blue.sat"] == PH.LOOKS["fresh"]["develop"]["mixer.blue.sat"]
    assert lo["finish"]["leak"] == 10 and lo["finish"]["sharpen"] == 35


@pytest.mark.parametrize("extra,msg", [({"x": {"devlop": {}}}, "unknown key"), ({"x": {"base": "x"}}, "circular"),
                                       ({"x": {"base": "nope"}}, "not a look"), ({"x": {"finish": {"blur": 1}}}, "finish key")])
def test_bad_looks_are_errors(extra, msg):
    with pytest.raises(SystemExit, match=msg):
        PH.resolve_look("x", extra)


# ------------------------------------------------------------------------------------------------------- steps

def shot(**kw):
    return PH.Shot(src=Path("/p/IMG_1.HEIC"), name="one", **kw)


def test_lightcraft_steps_masks_and_overrides():
    s = shot(sky=True, develop={"light.exposure": -0.15}, soften=0.5,
             spots=[{"kind": "person", "at": [0.5, 0.4], "r": [0.1, 0.2]}, {"kind": "face", "at": [0.5, 0.3], "r": 0.03}],
             looks={"golden-hour": {"face": {"exposure": 0.0}}})
    steps = PH.lc_steps(s, PH.resolve_look("golden-hour"), "golden-hour")
    assert steps[0]["command"] == "develop.set"
    assert steps[0]["params"]["values"]["light.exposure"] == -0.15                   # the photo's own value wins
    assert steps[0]["params"]["values"]["wb.temp"] == 7200
    assert [x["params"].get("kind") for x in steps[1:3]] == ["sky", None]
    rad = [x for x in steps if x["command"] == "mask.add" and x["params"]["kind"] == "radial"]
    assert [(r["params"]["rx"], r["params"]["ry"]) for r in rad] == [(0.1, 0.2), (0.03, 0.03)]
    lum = [x["params"]["hi"] for x in steps if x["command"] == "mask.addComponent"]
    assert lum == [0.55, 0.55]                                                         # sky in frame: keep spots off it
    face = [x for x in steps if x["command"] == "mask.adjust"][-1]["params"]["values"]
    assert face["texture"] == -15 and face["clarity"] == -5 and face["exposure"] == 0.0


def test_raw_files_drop_the_relative_white_balance():
    s = PH.Shot(src=Path("/p/a.dng"), name="a")
    vals = PH.lc_steps(s, PH.resolve_look("fresh"), "fresh")[0]["params"]["values"]
    assert not any(k.startswith("wb.") for k in vals)
    s = PH.Shot(src=Path("/p/a.dng"), name="a", develop={"wb.temp": 5200})
    assert PH.lc_steps(s, PH.resolve_look("fresh"), "fresh")[0]["params"]["values"]["wb.temp"] == 5200


def test_bad_spot_kind():
    with pytest.raises(SystemExit, match="spot kind"):
        PH.lc_steps(shot(spots=[{"kind": "hat", "at": [0, 0], "r": 0.1}]), PH.resolve_look("clean"), "clean")


def test_photocraft_steps_per_look():
    g, rect = PH.pc_steps(shot(), PH.resolve_look("golden-hour"), "golden-hour", (3024, 4032), (1440, 1800))
    ids = [c for c, _ in g]
    assert ids == ["image.crop", "layer.duplicate", "filter.blur.gaussianBlur", "layer.layerStyle.blendingOptions",
                   "layer.newFillLayer.gradient", "layer.layerStyle.blendingOptions", "layer.flattenImage",
                   "filter.sharpen.unsharpMask"]
    crop = g[0][1]
    assert (crop["x"], crop["y"], crop["width"], crop["height"]) == rect
    assert (crop["targetWidth"], crop["targetHeight"], crop["resample"]) == (1440, 1800, "lanczos")
    assert g[4][1]["angle"] == -45                                                      # the leak from the top-left
    f, _ = PH.pc_steps(shot(looks={"fresh": {"finish": {"sharpen": 0}}}), PH.resolve_look("fresh"), "fresh",
                       (3024, 4032), (720, 900))
    assert [c for c, _ in f] == ["image.crop"]


def test_spec_shot_validation(tmp_path):
    s = PH.Shot.from_dict({"src": "a.jpg", "spots": [{"kind": "face", "at": [0.5, 0.5], "r": 0.1}]}, tmp_path)
    assert s.name == "a" and s.src == (tmp_path / "a.jpg").resolve()
    with pytest.raises(SystemExit, match="unknown key"):
        PH.Shot.from_dict({"src": "a.jpg", "exposure": 1}, tmp_path)
    with pytest.raises(SystemExit, match="a spot is"):
        PH.Shot.from_dict({"src": "a.jpg", "spots": [{"at": [0.5, 0.5]}]}, tmp_path)


def test_detail_falls_with_blur_not_with_contrast():
    rng = np.random.default_rng(1)
    img = rng.normal(128, 30, (400, 320)).cumsum(axis=1) % 255           # streaky texture with fine detail
    blur = (img + np.roll(img, 1, 0) + np.roll(img, 1, 1) + np.roll(img, (1, 1), (0, 1))) / 4
    base = PH.detail(img)
    assert PH.detail(blur) < 0.7 * base
    assert abs(PH.detail(img * 0.5 + 40) / base - 1) < 1e-3


# ---------------------------------------------------------------------------------------------- install, cli

def test_install_knows_the_photo_apps(tmp_path):
    assert {"lightcraft", "photocraft"} <= set(install.APPS)
    assert install.ENV["photocraft"] == "PHOTOCRAFT_CLI"
    for v in ("0.9.0", "0.10.0"):
        b = tmp_path / f"photocraft-{v}-linux-x86_64" / "bin" / "photocraft-cli"
        b.parent.mkdir(parents=True)
        b.write_text("")
    assert install.find_cli("photocraft", home=tmp_path).endswith("photocraft-0.10.0-linux-x86_64/bin/photocraft-cli")


def test_cli_looks_and_spec_errors(tmp_path, capsys):
    assert PH.main(["looks"]) == 0
    assert "golden-hour" in capsys.readouterr().out
    spec = tmp_path / "photos.json"
    spec.write_text(json.dumps({"photos": [], "colour": "x"}))
    with pytest.raises(SystemExit, match="unknown key"):
        PH.main(["spec", str(spec), "--out", str(tmp_path)])
    spec.write_text(json.dumps({"photos": [{"src": "a.jpg"}]}))
    with pytest.raises(SystemExit, match="--out DIR or --film"):
        PH.main(["spec", str(spec)])


def test_film_target_and_out(tmp_path):
    fp = make_film(tmp_path, "vert", format="vertical")
    out, size = PH._film(str(fp.dir))
    assert out == tmp_path / "out" / "vert" / "stills" and size == (1080, 1920)


# --------------------------------------------------------------------------------------------- the engines

def photo_file(path: Path, w=900, h=1200):
    """A synthetic photo: a blue sky gradient over a textured, green-brown ground, with a light 'shirt' block."""
    from PIL import Image
    rng = np.random.default_rng(7)
    y = np.linspace(0, 1, h)[:, None, None]
    sky = np.concatenate([110 + 60 * y, 150 + 50 * y, 230 - 20 * y], axis=2) * np.ones((1, w, 1))
    ground = np.stack([90 + rng.normal(0, 25, (h, w)), 110 + rng.normal(0, 25, (h, w)), 60 + rng.normal(0, 20, (h, w))], 2)
    img = np.where(y < 0.55, sky, ground)
    img[int(h * .4):int(h * .62), int(w * .42):int(w * .58)] = 235 + rng.normal(0, 6, (int(h * .62) - int(h * .4), int(w * .58) - int(w * .42), 1))
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(path, quality=95)
    return path


@needs_cli
def test_grade_both_looks_end_to_end(tmp_path):
    src = photo_file(tmp_path / "IMG_9.jpg")
    s = PH.Shot(src=src, name="hero", crop=[0.2, 0.15, 0.8], sky=True,
                spots=[{"kind": "person", "at": [0.5, 0.5], "r": [0.1, 0.12]}, {"kind": "face", "at": [0.5, 0.42], "r": 0.04}])
    done = PH.run_all([s], ["fresh", "golden-hour"], "4:5@500", tmp_path / "out", LC_CLI, PC_CLI, do_check=True,
                      do_sheet=True, log=lambda *a: None)
    from PIL import Image
    for look, recs in done.items():
        r = recs[0]
        assert Image.open(r["out"]).size == (400, 500)
        assert r["crop"] == list(PH.crop_rect((900, 1200), (400, 500), s.crop))
        assert r["detail"] >= PH.DETAIL_MIN, r                                          # as sharp as a plain resize
        assert json.loads((tmp_path / "out" / look / "grade.json").read_text())[0]["name"] == "hero"
    assert (tmp_path / "out" / "sheet.jpg").exists()


@needs_cli
def test_spec_cli_end_to_end(tmp_path):
    photo_file(tmp_path / "a.jpg")
    spec = tmp_path / "photos.json"
    spec.write_text(json.dumps({"look": "clean", "target": "300x300", "looks": {"cool": {"base": "clean", "develop": {"wb.temp": 6000}}},
                                "photos": [{"src": "a.jpg", "name": "sq", "focus": [0.5, 0.5], "zoom": 1.5}]}))
    assert PH.main(["spec", str(spec), "--look", "clean,cool", "--out", str(tmp_path / "o")]) == 0
    assert (tmp_path / "o" / "clean" / "sq.jpg").exists() and (tmp_path / "o" / "cool" / "sq.jpg").exists()


@needs_cli
def test_engine_errors_name_the_step(tmp_path):
    src = photo_file(tmp_path / "b.jpg", 200, 200)
    with pytest.raises(LC.RunError, match="lightcraft-cli run on b.jpg failed"):
        LC.run(LC_CLI, src, [LC.step("no.such.command")], tmp_path)
    with pytest.raises(PC.RunError, match="photocraft-cli run on b.jpg failed"):
        PC.run(PC_CLI, src, [["no.such.command", {}]], tmp_path / "x.jpg")
