"""B47 MetaHuman variations: the pure cast generator (deterministic, distinct, in range), the `cast` spec kind, and
mh.variants making a cast on the fake."""
import json
from pathlib import Path

import pytest
import yaml

from fakeunreal import run_op
from fakeunreal.ext_mh import add_presets, add_wardrobe
from filmtools.unreal import mh_cast, mh_spec

REPO = Path(__file__).resolve().parents[2]
EX = yaml.safe_load((REPO / "examples/unreal/cast/cafe-extras.yaml").read_text())
CAST_SCHEMA = json.loads((REPO / "tools/filmtools/unreal/schemas/cast.schema.json").read_text())
CHAR_SCHEMA = json.loads((REPO / "tools/filmtools/unreal/schemas/character.schema.json").read_text())
G = mh_cast.generator()


def test_same_seed_same_cast_and_count_keeps_prefix():
    a, b = G.generate(EX), G.generate(EX)
    assert a == b
    more = G.generate({**EX, "count": 9})
    assert more["members"][:6] == a["members"]
    other = G.generate({**EX, "seed": 8})
    assert other["members"] != a["members"]


def test_members_are_distinct_and_in_range():
    g = G.generate({**EX, "count": 12})
    assert all(d is None or d >= 0.2 for d in g["distances"]), g["distances"]
    for t, m in zip(g["traits"], g["members"]):
        lo, hi = EX["height_cm"][t["sex"]]
        assert lo <= m["body"]["Height"] <= hi
        assert 22 <= t["age"] <= 70
        assert 0.15 <= m["skin"]["u"] <= 0.85
        assert (m["body"]["Masculine/Feminine"] > 0) == (t["sex"] == "female")
        assert m["from"]["preset"] in EX["presets"][t["sex"]]
        if t["sex"] == "female":
            assert m["grooms"]["Beard"] == "none"
    assert {t["sex"] for t in g["traits"]} == {"female", "male"}


def test_age_greys_hair_and_wears_teeth():
    young, old = G.age_look(25), G.age_look(70)
    assert young["whiteness"] == 0 and old["whiteness"] > 0.5
    assert young["worn_down"] == 0 and old["worn_down"] > 0.2


def test_bad_casts_say_what_is_wrong():
    with pytest.raises(G.CastError, match="folder"):
        G.generate({k: v for k, v in EX.items() if k != "folder"})
    with pytest.raises(G.CastError, match="low <= high"):
        G.generate({**EX, "age": [70, 20]})
    with pytest.raises(G.CastError, match="sex"):
        G.generate({**EX, "sex": "other"})


def test_schemas():
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(EX, CAST_SCHEMA)
    for m in G.generate(EX)["members"]:
        jsonschema.validate(m, CHAR_SCHEMA)


def test_plan_offline_covers_every_member():
    steps = mh_cast.plan(EX, None)
    adds = [s for s in steps if s["op"] == "mh.add"]
    assert len(adds) == 6 and steps[0]["why"].startswith("Cafe01:")
    assert not any(s["op"] in ("mh.rig", "mh.build") for s in steps)  # rig: none


@pytest.fixture
def box(ue, fmb, tmp_path, monkeypatch):
    add_presets(ue)
    add_wardrobe(ue)
    monkeypatch.setenv("HOME", str(tmp_path))
    return ue


def test_cast_converges_on_the_fake(box):
    state = {m["asset"]: run_op("mh.describe", path=m["asset"]) for m in mh_cast.members(EX)}
    for s in mh_cast.plan(EX, state):
        run_op(s["op"], **s["args"])
    state = {m["asset"]: run_op("mh.describe", path=m["asset"]) for m in mh_cast.members(EX)}
    assert mh_cast.plan(EX, state) == []


def test_variants_op_makes_and_previews(box):
    r = run_op("mh.variants", cast=EX)
    assert len(r["members"]) == 6 and r["changed"] is False and not box.called(
        "MetaHumanCharacterEditorSubsystem.commit_body_state")
    r = run_op("mh.variants", cast=EX, make=True, preview=True)
    assert r["changed"] and len(r["previews"]) == 6
    assert box.assets.get("/Game/Characters/Extras/MH_Cafe03") is not None
    again = run_op("mh.variants", cast=EX, make=True)
    assert not any(m["changed"] for m in again["made"])
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("mh.variants", cast={**EX, "count": 0})
    assert e.value.code == "bad_args"
    assert mh_spec  # the character planner the cast kind reuses
