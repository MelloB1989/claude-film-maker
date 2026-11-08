import json

from gate_film import merge, scoped


def test_merge_aliases_and_job_minimum(tmp_path):
    (tmp_path / "grain.json").write_text(json.dumps({"gate": {"shot.grain_sigma_close": {"value": 0.7}}}))
    (tmp_path / "box.json").write_text(json.dumps({"jobs": [{"garment.leaders_ok": 1}, {"garment.leaders_ok": 0}]}))
    n = merge([str(tmp_path / "grain.json"), str(tmp_path / "box.json")], {"shot.grain_sigma_close": "shot.grain_sigma"})
    assert n["shot.grain_sigma"]["value"] == 0.7 and n["garment.leaders_ok"]["value"] == 0


def test_scoped_drops_the_other_films_items():
    sp = scoped({"items": {"a": {"films": ["whatsapp"]}, "b": {}}}, "netflix")
    assert list(sp["items"]) == ["b"]


def test_info_films_makes_an_item_info_for_that_film_only():
    spec = {"items": {"hair.cut_pop_ratio": {"info_films": ["netflix"], "info_reason": "no held cut"}}}
    assert scoped(spec, "netflix")["items"]["hair.cut_pop_ratio"]["info"] is True
    assert "info" not in scoped(spec, "whatsapp")["items"]["hair.cut_pop_ratio"]


def test_every_new_spec_item_has_a_line():
    import json
    import sys
    from pathlib import Path
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here.parents[2] / "tools"))
    from filmtools.unreal import qa_local
    qa_local.qa()
    core = sys.modules["fmqa.gate"].ITEMS
    spec = json.loads((here / "gate_spec.json").read_text())
    bad = [k for k, v in spec["items"].items() if k not in core and v.get("line") is None and not v.get("info")]
    assert not bad, f"spec items without a line (an override replaced the whole item?): {bad}"


def test_line_by_film():
    spec = {"items": {"body.hands_in_frame_mcu_frac": {"line": 0.6, "line_by_film": {"netflix": 0.5}}}}
    assert scoped(spec, "netflix")["items"]["body.hands_in_frame_mcu_frac"]["line"] == 0.5
    assert scoped(spec, "whatsapp")["items"]["body.hands_in_frame_mcu_frac"]["line"] == 0.6
