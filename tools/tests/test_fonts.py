import json

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation

from filmtools import fonts
from filmtools.fonts import build_all, make_instance, width_class


def advance(path, ch="M"):
    f = TTFont(path)
    return f["hmtx"][f.getBestCmap()[ord(ch)]][0]


def box(w, h):
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0))
    pen.lineTo((0, h))
    pen.lineTo((w, h))
    pen.lineTo((w, 0))
    pen.closePath()
    return pen.glyph()


def variable_font(path, axes=(("wght", 100, 400, 900), ("wdth", 75, 100, 100))):
    """A one-glyph variable font: M widens (and its advance grows) with weight, narrows with width, and is kerned."""
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "M"])
    fb.setupCharacterMap({ord("M"): "M"})
    fb.setupGlyf({".notdef": box(400, 600), "M": box(500, 700)})
    fb.setupHorizontalMetrics({".notdef": (500, 0), "M": (600, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Probe", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    fb.setupFvar(axes=[(tag, lo, d, hi, tag) for tag, lo, d, hi in axes], instances=[])
    # 4 outline points, then the phantom points (left, right = the advance, top, bottom)
    heavier = TupleVariation({"wght": (0, 1.0, 1.0)}, [(0, 0), (0, 0), (200, 0), (200, 0), (0, 0), (200, 0), (0, 0),
                                                       (0, 0)])
    narrower = TupleVariation({"wdth": (-1.0, -1.0, 0)}, [(0, 0), (0, 0), (-150, 0), (-150, 0), (0, 0), (-150, 0),
                                                          (0, 0), (0, 0)])
    fb.setupGvar({"M": [heavier, narrower], ".notdef": []})
    fb.addOpenTypeFeatures("feature kern { pos M M -50; } kern;")
    fb.save(str(path))
    return path


@pytest.fixture
def vf(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "OFL-Probe.txt").write_text("licence")
    return variable_font(tmp_path / "src" / "Probe[wdth,wght].ttf")


def test_instances_are_static_weighted_and_kerned(vf, tmp_path):
    light = make_instance(vf, {"wght": 300, "wdth": 75}, tmp_path / "Probe-75-300.ttf", 300, 3)
    heavy = make_instance(vf, {"wght": 900, "wdth": 100}, tmp_path / "Probe-100-900.ttf", 900, 5)
    for p, wt, wc in ((light, 300, 3), (heavy, 900, 5)):
        f = TTFont(p)
        assert "fvar" not in f and "GPOS" in f
        assert (f["OS/2"].usWeightClass, f["OS/2"].usWidthClass) == (wt, wc)
    assert advance(light) < advance(heavy)


def test_width_classes_follow_the_wdth_axis():
    assert [width_class(w) for w in (50, 75, 87.5, 100, 125, 200)] == [1, 3, 4, 5, 7, 9]
    assert width_class(80) == 3


def test_the_films_list_is_cut_into_its_fonts_folder_with_the_licences(vf, film):
    film.config.write_text(json.dumps({"id": "demo", "pipeline": {"fonts": [
        {"src": str(vf), "axes": {"wght": 600}, "out": "Probe-600.ttf"},
        {"src": str(vf), "axes": {"wght": 400, "wdth": 75}, "out": "Probe-75-400.ttf"}]}}))
    fonts.main([])
    out = film.dir / "fonts"
    assert sorted(p.name for p in out.iterdir()) == ["OFL-Probe.txt", "Probe-600.ttf", "Probe-75-400.ttf"]
    f = TTFont(out / "Probe-75-400.ttf")
    assert (f["OS/2"].usWeightClass, f["OS/2"].usWidthClass) == (400, 3)


def test_a_source_is_found_beside_the_film_first(vf, tmp_path):
    assert build_all([{"src": "src/Probe[wdth,wght].ttf", "axes": {"wght": 500}, "out": "P.ttf"}], tmp_path / "o",
                     film_dir=tmp_path)[0].name == "P.ttf"
    with pytest.raises(SystemExit, match="not found"):
        build_all([{"src": "src/Missing.ttf", "axes": {}, "out": "M.ttf"}], tmp_path / "o", film_dir=tmp_path)


def test_one_instance_needs_no_film(vf, tmp_path, capsys):
    fonts.main(["--src", str(vf), "--axis", "wght=700", "--out", str(tmp_path / "one.ttf")])
    assert TTFont(tmp_path / "one.ttf")["OS/2"].usWeightClass == 700


def test_a_film_with_no_fonts_says_where_to_list_them(film):
    with pytest.raises(SystemExit, match="pipeline.fonts"):
        fonts.main([])
