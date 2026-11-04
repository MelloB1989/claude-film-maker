"""WP2's pure helpers (unreal/fmbridge/ops/_assetlib.py): paths, texture roles and sets, the PNG probe, the
catalog query. No fake engine: the module never imports unreal."""
from __future__ import annotations

import importlib.util
import struct
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("_assetlib", ROOT / "unreal/fmbridge/ops/_assetlib.py")
L = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(L)


@pytest.mark.parametrize("given,want", [
    ("/Game/A/B", "/Game/A/B"), ("/Game/A/B.B", "/Game/A/B"), ("/Game/A/B.B:Sub", "/Game/A/B"),
    ("StaticMesh'/Game/A/B.B'", "/Game/A/B"), ("/Game/A/B/", "/Game/A/B")])
def test_package_path(given, want):
    assert L.package_path(given) == want
    assert L.object_path(given) == want + "." + want.rsplit("/", 1)[-1]


def test_valid_path_explains():
    assert L.valid_path("/Game/Props/SM_Chair") == ""
    assert "mount point" in L.valid_path("Game/Props")
    assert "mount point" in L.valid_path("/Game")
    assert "characters" in L.valid_path("/Game/My Props/SM Chair")
    assert L.safe_name("3d chair (v2)") == "A_3d_chair_v2"


@pytest.mark.parametrize("name,role,set_,srgb,comp", [
    ("T_Wood_Normal_4K.png", "normal", "t_wood", False, "TC_NORMALMAP"),
    ("T_Rock_BaseColor.png", "base_color", "t_rock", True, "TC_DEFAULT"),
    ("T_Rock_Base_Color.png", "base_color", "t_rock", True, "TC_DEFAULT"),
    ("rock_ORM.png", "orm", "rock", False, "TC_MASKS"),
    ("Chair_N.tga", "normal", "chair", False, "TC_NORMALMAP"),
    ("Aset_rock_4K_Roughness.jpg", "roughness", "aset_rock", False, "TC_MASKS"),
    ("T_Bark_D.png", "base_color", "t_bark", True, "TC_DEFAULT"),
    ("T_Leaf_Opacity.png", "opacity", "t_leaf", False, "TC_MASKS"),
    ("Metal_Metalness_2K.png", "metallic", "metal", False, "TC_MASKS"),
    ("T_X_AmbientOcclusion.png", "ao", "t_x", False, "TC_MASKS"),
    ("Normal.png", "normal", "Normal", False, "TC_NORMALMAP"),
    ("wood.png", "", "wood", True, "TC_DEFAULT"),
    ("sky_4k.exr", "hdr", "sky_4k", False, "TC_HDR"),
])
def test_texture_role(name, role, set_, srgb, comp):
    r = L.texture_role(name)
    assert (r["role"], r["set"], r["srgb"], r["compression"]) == (role, set_, srgb, comp)


def test_data_maps_use_the_masks_sampler():
    # a TC_MASKS map sampled as Color does not compile: role, compression and sampler always agree
    for name, (_, srgb, comp, sampler) in L.ROLES.items():
        assert (comp == "TC_MASKS") == (sampler == "SAMPLERTYPE_MASKS"), name
        assert srgb == (sampler == "SAMPLERTYPE_COLOR"), name


def test_one_letter_tokens_only_at_the_end():
    assert L.texture_role("T_N_Thing.png")["role"] == ""  # N not last
    assert L.texture_role("tex_N_1001.png")["role"] == "normal"  # a UDIM after it is not the role
    assert L.texture_role("N.png")["role"] == ""


def test_opengl_normals_flip_green():
    assert L.texture_role("floor_nor_gl_2k.png")["flip_green"] is True
    assert L.texture_role("T_Y_Normal_GL.png")["flip_green"] is True
    assert L.texture_role("T_Y_Normal.png")["flip_green"] is False


def test_packing():
    assert L.texture_role("rock_ORM.png")["packing"] == ["ao", "roughness", "metallic"]
    assert L.texture_role("rock_MRA.png")["packing"] == ["metallic", "roughness", "ao"]


def test_texture_set_groups_and_pbr_inputs():
    sets = L.texture_set(["T_Rock_BaseColor.png", "T_Rock_Normal.png", "T_Rock_ORM.png", "readme.txt", "wood.png",
                          "T_Moss_Albedo.jpg", "T_Moss_Gloss.jpg"])
    assert sets["t_rock"] == {"base_color": "T_Rock_BaseColor.png", "normal": "T_Rock_Normal.png",
                              "orm": "T_Rock_ORM.png"}
    assert sets["_unknown"] == ["wood.png"]
    inp = L.pbr_inputs(sets["t_rock"])
    assert inp["roughness"] == ("orm", "G") and inp["metallic"] == ("orm", "B") and inp["ao"] == ("orm", "R")
    assert L.pbr_inputs(sets["t_moss"])["roughness"] == ("gloss", "R", "invert")


def _png(path, w, h, rgb, filt=0):
    raw = b"".join(bytes([filt]) + bytes(rgb) * w for _ in range(h))
    if filt == 1:  # Sub: first pixel raw, then deltas of 0
        raw = b"".join(bytes([1]) + bytes(rgb) + bytes(3 * (w - 1)) for _ in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    return str(path)


def test_probe_png_tells_a_normal_map(tmp_path):
    n = L.probe_png(_png(tmp_path / "a.png", 16, 8, (128, 128, 255)))
    assert n["normal_like"] and n["width"] == 16 and n["mean"][2] == 1.0
    assert L.probe_png(_png(tmp_path / "b.png", 16, 8, (128, 128, 255), filt=1))["normal_like"]
    assert not L.probe_png(_png(tmp_path / "c.png", 16, 8, (200, 120, 60)))["normal_like"]
    (tmp_path / "d.png").write_bytes(b"not a png")
    assert L.probe_png(str(tmp_path / "d.png")) == {}
    assert L.probe_png(str(tmp_path / "missing.png")) == {}


@pytest.mark.parametrize("q,words,sizes,axis", [
    ("a 45 cm chair", ["chair"], [45.0], None),
    ("table 120x80 cm", ["table"], [120.0, 80.0], None),
    ("lamp 1.5m tall", ["lamp"], [150.0], "z"),
    ("mug ~10cm", ["mug"], [10.0], None),
    ("sofas", ["sofa"], [], None),
    ("2 ft stool", ["stool"], [60.96], None),
    ("a 30 inch wide shelf", ["shelf"], [76.2], "y"),
])
def test_parse_query(q, words, sizes, axis):
    p = L.parse_query(q)
    assert (p["words"], p["sizes_cm"], p["axis"]) == (words, sizes, axis)


CAT = [{"path": "/Game/P/SM_Chair_A", "name": "SM_Chair_A", "class": "StaticMesh", "size_cm": [50, 48, 90]},
       {"path": "/Game/P/SM_Chair_Kid", "name": "SM_Chair_Kid", "class": "StaticMesh", "size_cm": [32, 30, 46]},
       {"path": "/Game/P/SM_Table", "name": "SM_Table", "class": "StaticMesh", "size_cm": [120, 80, 75]},
       {"path": "/Game/P/SM_Lamp", "name": "SM_Lamp", "class": "StaticMesh", "size_cm": [30, 30, 160],
        "tags": ["lighting", "floor"]}]


def test_search_ranks_by_words_and_size():
    r = L.search(CAT, "a 45 cm chair")
    assert [x["path"] for x in r][:2] == ["/Game/P/SM_Chair_Kid", "/Game/P/SM_Chair_A"]
    assert r[0]["scale"] == pytest.approx(45 / 46, abs=1e-3)
    assert L.search(CAT, "table 120x80")[0]["size_error"] == 0
    assert L.search(CAT, "lamp 1.5 m tall")[0]["path"] == "/Game/P/SM_Lamp"
    assert L.search(CAT, "lighting")[0]["path"] == "/Game/P/SM_Lamp"  # tags count
    assert L.search(CAT, "piano") == []
    assert L.search(CAT, "chair", cls="SkeletalMesh") == []


def test_search_without_size_needs_no_bounds():
    assert L.search([{"path": "/Game/M/MI_Oak", "name": "MI_Oak"}], "oak")[0]["score"] == 1.0
    assert L.search([{"path": "/Game/M/MI_Oak", "name": "MI_Oak"}], "oak 40cm") == []
