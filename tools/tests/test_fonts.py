from fontTools.ttLib import TTFont

from gitloom_film.fonts import SRC, bricolage_name, make_instance


def advance(path, ch="M"):
    f = TTFont(path)
    return f["hmtx"][f.getBestCmap()[ord(ch)]][0]


def test_bricolage_instances_are_static_weighted_and_kerned(tmp_path):
    src = SRC / "BricolageGrotesque[opsz,wdth,wght].ttf"
    narrow = make_instance(src, {"opsz": 96, "wdth": 75, "wght": 300}, tmp_path / bricolage_name(75, 300), 300, 3)
    wide = make_instance(src, {"opsz": 96, "wdth": 100, "wght": 800}, tmp_path / bricolage_name(100, 800), 800, 5)
    assert (narrow.name, wide.name) == ("Bricolage-w750-300.ttf", "Bricolage-w1000-800.ttf")
    assert bricolage_name(87.5, 600) == "Bricolage-w875-600.ttf"
    for p, wt, wc in ((narrow, 300, 3), (wide, 800, 5)):
        f = TTFont(p)
        assert "fvar" not in f and "GPOS" in f
        assert (f["OS/2"].usWeightClass, f["OS/2"].usWidthClass) == (wt, wc)
    assert advance(narrow) < advance(wide)


def test_mono_instance_stays_monospaced(tmp_path):
    p = make_instance(SRC / "JetBrainsMono[wght].ttf", {"wght": 500}, tmp_path / "JetBrainsMono-500.ttf", 500)
    f = TTFont(p)
    assert "fvar" not in f and f["OS/2"].usWeightClass == 500
    assert len({advance(p, c) for c in "iMW0"}) == 1
