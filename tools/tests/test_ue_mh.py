"""WP3 MetaHuman ops against the fake engine (fakeunreal/ext_mh.py): creation, appearance, wardrobe, the cloud rig and
textures as multi-tick jobs, build, the character spec (apply converges, export round-trips)."""
import os

import pytest

from fakeunreal import drive, run_op
from fakeunreal.ext_mh import add_presets, add_wardrobe

P = "/Game/Chars/Ava/MH_Ava"


@pytest.fixture
def mh(ue, fmb, tmp_path, monkeypatch):
    """A fake engine with presets and wardrobe items, and an Epic sign-in saved on this 'machine'."""
    add_presets(ue)
    add_wardrobe(ue)
    monkeypatch.setenv("HOME", str(tmp_path))
    cred = tmp_path / ".local/share/.eos_sdk/keychain/abc/persistent_auth/credential"
    cred.parent.mkdir(parents=True)
    cred.write_text("x")
    return ue


def err(fn, *a, **k):
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        fn(*a, **k)
    return e.value


def test_presets_and_add_converges(mh):
    assert run_op("mh.presets") == ["Ada", "Jorge", "Vivian"]
    r = run_op("mh.add", path=P, preset="ada")
    assert r == {"path": P, "changed": True, "from": "/MetaHumanCharacter/Optional/Presets/Ada"}
    assert run_op("mh.add", path=P, preset="Ada")["changed"] is False
    assert mh.dialogs == []


def test_add_errors_are_actionable(mh):
    e = err(run_op, "mh.add", path=P, preset="Adda")
    assert e.code == "not_found" and "Ada" in e.candidates
    e = err(run_op, "mh.add", path=P)
    assert e.code == "not_found" and "preset" in e.hint
    e = err(run_op, "mh.add", path=P, preset="Ada", blank=True)
    assert e.code == "bad_args"


def test_blank_and_duplicate(mh):
    assert run_op("mh.add", path=P, blank=True)["from"] == "blank"
    v = run_op("mh.duplicate", source=P, path=P + "_B")
    assert v["changed"] and mh.assets[P + "_B"] is not mh.assets[P]
    mh.assets[P + "_B"]._props["__fm_body"]["Height"] = [True, 190.0]
    assert mh.assets[P]._props["__fm_body"]["Height"][1] != 190.0  # the copy owns its state


def test_body_constraint_copies_and_convergence(mh):
    run_op("mh.add", path=P, preset="Ada")
    r = run_op("mh.body", character=P, measurements={"height": 168, "Waist": 61})
    assert r["changed"] and r["body"] == {"Height": 168.0, "Waist": 61.0}
    assert run_op("mh.body", character=P, measurements={"Height": 168, "Waist": 61})["changed"] is False
    r = run_op("mh.body", character=P, measurements={"Waist": 300})
    assert r["warnings"] and "outside" in r["warnings"][0]
    e = err(run_op, "mh.body", character=P, measurements={"Wasit": 60})
    assert e.code == "bad_args" and "Waist" in e.candidates
    assert run_op("mh.body", character=P, measurements={"Waist": None})["body"] == {"Waist": None}


def test_body_from_character(mh):
    run_op("mh.add", path=P, preset="Ada")
    run_op("mh.body", character="/MetaHumanCharacter/Optional/Presets/Vivian", measurements={"Chest": 99})
    r = run_op("mh.body", character=P, from_character="/MetaHumanCharacter/Optional/Presets/Vivian")
    assert r["body"]["Height"] == 180.0 and r["body"]["Chest"] == 99.0


def test_face_blend_unrigs_a_rigged_face(mh):
    run_op("mh.add", path=P, preset="Ada")
    mh.assets[P]._props["__fm_rigged"] = True
    mh.assets[P]._props["has_face_dna_blendshapes"] = True
    r = run_op("mh.face", path=P, blend={"Ada": 1, "Jorge": 1})
    assert r["changed"] and r["unrigged"]
    assert mh.assets[P]._props["__fm_face"] == [1.5] * 8
    assert run_op("mh.face", path=P, blend={"Ada": 1, "Jorge": 1})["changed"] is False
    e = err(run_op, "mh.face", path=P, coefficients=[0.0])
    assert e.code == "bad_args"


def test_skin_commits_only_on_change(mh):
    run_op("mh.add", path=P, preset="Ada")
    mh.assets[P]._props["has_high_resolution_textures"] = True
    r = run_op("mh.skin", character=P, u=0.6, v=0.4, settings={"freckles": {"density": 0.3, "mask": "Type1"}},
               texture_resolution="4k")
    assert r["changed"] and r["u"] == 0.6
    s = mh.assets[P]._props["skin_settings"]
    assert s.freckles.mask == "TYPE1" and s.desired_texture_sources_resolutions.face_albedo == "RES4K"
    assert mh.assets[P]._props["has_high_resolution_textures"] is False  # the engine discards them on commit
    n = len(mh.called("MetaHumanCharacterEditorSubsystem.commit_skin_settings"))
    assert run_op("mh.skin", character=P, u=0.6)["changed"] is False
    assert len(mh.called("MetaHumanCharacterEditorSubsystem.commit_skin_settings")) == n
    e = err(run_op, "mh.skin", character=P, settings={"freckels": {}})
    assert e.code == "bad_args" and "freckles" in e.candidates


def test_eyes_teeth_lashes_makeup(mh):
    run_op("mh.add", path=P, preset="Ada")
    r = run_op("mh.eyes", path=P, both={"iris": {"iris_pattern": "Iris003", "primary_color_u": 0.2}},
               right={"iris": {"primary_color_u": 0.3}})
    assert r["changed"]
    e = mh.assets[P]._props["eyes_settings"]
    assert e.eye_left.iris.iris_pattern == "IRIS003" and e.eye_right.iris.primary_color_u == 0.3
    assert run_op("mh.eyelashes", path=P, settings={"type": "LongCurl", "melanin": 0.9})["changed"]
    assert mh.assets[P]._props["head_model_settings"].eyelashes.type == "LONG_CURL"
    assert run_op("mh.teeth", path=P, settings={"overbite": 0.3})["teeth"]["overbite"] == 0.3
    r = run_op("mh.makeup", path=P, settings={"lips": {"type": "Natural", "color": [0.3, 0.05, 0.05]}})
    assert r["makeup_settings"]["lips"]["color"] == [0.3, 0.05, 0.05, 1.0]
    e = err(run_op, "mh.makeup", path=P, settings={"lips": {"type": "Glossy"}})
    assert e.code == "bad_args" and "NATURAL" in e.hint


def test_groom_add_is_idempotent_and_colours(mh):
    run_op("mh.add", path=P, preset="Ada")
    r = run_op("mh.groom", character=P, slot="Hair", item="WI_Hair_L_Straight", melanin=1.0, redness=0.05)
    assert r["changed"] and r["params"]["Melanin"] == 1.0
    r2 = run_op("mh.groom", character=P, slot="Hair", item="WI_Hair_L_Straight", melanin=1.0, redness=0.05)
    assert r2["changed"] is False
    coll = mh.assets[P]._props["internal_collection"]
    assert list(coll._items) == ["WI_Hair_L_Straight"]  # no second palette entry
    assert run_op("mh.item_params", character=P, slot="Hair")["params"]["Redness"] == 0.05
    assert run_op("mh.groom", character=P, slot="Beard", item="none")["changed"] is False
    e = err(run_op, "mh.item_set", character=P, slot="Hair", params={"Melanine": 0.5})
    assert e.code == "bad_args" and "Melanin" in e.candidates
    e = err(run_op, "mh.groom", character=P, slot="Hat")
    assert e.code == "bad_args"


def test_rig_fails_fast_without_sign_in(mh, monkeypatch, tmp_path):
    run_op("mh.add", path=P, preset="Ada")
    monkeypatch.setenv("HOME", str(tmp_path / "nobody"))
    e = err(run_op, "mh.rig", character=P)
    assert e.code == "unsupported" and "epic-login" in e.hint
    assert not mh.called("MetaHumanCharacterEditorSubsystem.request_auto_rigging")


def test_rig_textures_build_then_up_to_date(fmb, mh):
    run_op("mh.add", path=P, preset="Ada")
    r = run_op("mh.rig", character=P)
    assert r["changed"] and "finished" in r["log"]
    req = mh.called("MetaHumanCharacterEditorSubsystem.request_auto_rigging")[0][0][1]
    assert req.blocking is False and req.rig_type == "JOINTS_AND_BLEND_SHAPES"
    assert run_op("mh.rig", character=P)["changed"] is False
    e = err(run_op, "mh.build", character=P, name="Ava")
    assert e.code == "conflict" and "mh.textures" in e.hint
    assert run_op("mh.textures", character=P)["has_high_res_textures"]
    b = run_op("mh.build", character=P, name="Ava")
    assert b["changed"] and b["bp"] == "/Game/Chars/Ava/Unpacked/Ava/BP_Ava"
    assert run_op("mh.build", character=P, name="Ava")["changed"] is False
    d = run_op("mh.describe", path=P)
    assert d["build"]["stale"] is False and d["rig_stale"] is False
    run_op("mh.body", character=P, measurements={"Height": 175})
    d = run_op("mh.describe", path=P)
    assert d["rig_stale"] and d["build"]["stale"]
    assert run_op("mh.rig", character=P)["changed"]  # the body moved: re-rig


def test_rig_failure_comes_from_the_log(mh):
    run_op("mh.add", path=P, preset="Ada")
    mh.mh_fail_rig = True
    e = err(run_op, "mh.rig", character=P)
    assert e.code == "engine" and "failed with code" in e.message


def test_rig_times_out(mh):
    run_op("mh.add", path=P, preset="Ada")
    mh.mh_rig_ticks = 10 ** 6
    import fmbridge.ops.mh.cloud as cl
    import time
    t = [1000.0]
    real = time.time
    cl.time.time = lambda: t.__setitem__(0, t[0] + 60) or t[0]
    try:
        e = err(run_op, "mh.rig", character=P, timeout_s=300)
    finally:
        cl.time.time = real
    assert e.code == "timeout"


def test_rig_is_multi_tick(fmb, mh):
    run_op("mh.add", path=P, preset="Ada")
    gen = fmb.call("mh.rig", character=P)
    res, ticks = drive(gen)
    assert res["changed"] and ticks >= mh.mh_rig_ticks


SPEC = {"kind": "character", "version": 1, "name": "Ava", "asset": P, "from": {"preset": "Ada"},
        "body": {"Height": 168, "Waist": 61}, "face": {"blend": {"Ada": 0.7, "Vivian": 0.3}},
        "skin": {"u": 0.55, "v": 0.45, "freckles": {"density": 0.2}}, "eyes": {"both": {"iris": {"primary_color_u": 0.2}}},
        "eyelashes": {"type": "LongCurl"}, "makeup": {"lips": {"type": "Natural"}},
        "grooms": {"Hair": {"item": "WI_Hair_L_Straight", "melanin": 1.0}, "Beard": "none"},
        "outfit": {"item": "WI_Outfit_Casual"}, "build": {"name": "Ava"}}


def test_apply_converges(mh):
    r = run_op("mh.apply", spec=SPEC)
    assert r["changed"] and [s["op"] for s in r["steps"]][-1] == "mh.build"
    assert r["describe"]["build"]["bp"].endswith("BP_Ava")
    r2 = run_op("mh.apply", spec=SPEC)
    assert r2["changed"] is False, [s for s in r2["steps"] if s["changed"]]


def test_apply_dry_run_and_bad_keys(mh):
    r = run_op("mh.apply", spec=SPEC, dry_run=True)
    assert [s["op"] for s in r["steps"]][:3] == ["mh.add", "mh.body", "mh.face"]
    assert not mh.called("MetaHumanCharacterEditorSubsystem.commit_body_state")
    e = err(run_op, "mh.apply", spec={**SPEC, "hair": {}})
    assert e.code == "bad_args"


def test_export_round_trip(mh):
    run_op("mh.apply", spec=SPEC)
    out = run_op("mh.export", path=P)
    assert out["kind"] == "character" and out["body"]["measurements"]["Height"] == 168.0
    assert out["grooms"]["Hair"]["item"] == "WI_Hair_L_Straight"
    twin = {**out, "asset": "/Game/Chars/Twin/MH_Twin", "from": {"preset": "Jorge"}, "build": {"name": "Twin"}}
    run_op("mh.apply", spec=twin)
    a, b = run_op("mh.describe", path=P), run_op("mh.describe", path="/Game/Chars/Twin/MH_Twin")
    for k in ("body", "face", "skin", "eyes", "makeup", "eyelashes", "teeth"):
        assert a[k] == b[k], k
    assert a["wardrobe"]["Hair"]["params"] == b["wardrobe"]["Hair"]["params"]


def test_remove(mh):
    run_op("mh.apply", spec=SPEC)
    r = run_op("mh.remove", path=P, built=True)
    assert r["changed"] and len(r["removed"]) == 2
    assert run_op("mh.remove", path=P)["changed"] is False
    assert run_op("mh.describe", path=P) == {"path": P, "exists": False}


def test_auth_status_and_exchange_code(mh):
    assert run_op("mh.auth_status")["signed_in"] in (True, None)
    r = run_op("mh.login", exchange_code="abc123")
    assert r["exchange_code_set"] and mh.console[-1].endswith("MetaHuman.Cloud.Config.ExchangeCode abc123")


def test_package_keeps_legacy_names(fmb):
    from fmbridge.ops import mh as M
    for n in ("presets", "wardrobe", "from_preset", "login", "rig", "textures", "palette", "add_item", "clear_slot",
              "skin", "body", "build", "components", "drive_face", "cloth_inflate", "garment"):
        assert callable(getattr(M, n)), n
    assert os.path.basename(M.__file__) == "__init__.py"
