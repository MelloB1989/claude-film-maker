"""film-ue texpack (client): separate AO/roughness/metallic packed into one ORM, gloss inverted into roughness,
an OpenGL normal flipped, a packed RMA reordered to ORM, files named nothing useful reported."""
from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
Image = pytest.importorskip("PIL.Image")

from filmtools.unreal import cli_texpack as T  # noqa: E402


def _img(path, value, mode="L", size=8):
    Image.new(mode, (size, size), value).save(path)
    return str(path)


def test_separate_maps_pack_into_orm(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _img(src / "Rock_BaseColor.png", (200, 100, 50), "RGB")
    _img(src / "Rock_AO.png", 200)
    _img(src / "Rock_Gloss.png", 50, size=16)  # another size: resized to the first's
    _img(src / "Rock_Normal_GL.png", (128, 100, 255), "RGB")
    _img(src / "notes.png", 3)
    r = T.pack([str(src)], str(tmp_path / "out"), flip_green=True)
    s = r["sets"]["T_rock"]
    orm = np.asarray(Image.open(s["files"]["orm"]))
    assert orm.shape == (8, 8, 3)
    assert (orm[0, 0] == [200, 205, 0]).all()  # AO, 255-gloss, no metallic -> 0
    assert np.asarray(Image.open(s["files"]["normal"]))[0, 0, 1] == 155  # green flipped
    assert any("gloss" in n for n in s["notes"]) and any("metallic" in n for n in s["notes"])
    assert [p.rsplit("/", 1)[-1] for p in r["ignored"]] == ["notes.png"]


def test_rma_reordered(tmp_path):
    src = tmp_path / "s"
    src.mkdir()
    Image.merge("RGB", [Image.new("L", (4, 4), v) for v in (10, 20, 30)]).save(src / "Metal_RMA.png")
    r = T.pack([str(src)], str(tmp_path / "o"))
    a = np.asarray(Image.open(r["sets"]["T_metal"]["files"]["orm"]))
    assert list(a[0, 0]) == [30, 10, 20]  # R rough, G metal, B AO -> R AO, G rough, B metal
