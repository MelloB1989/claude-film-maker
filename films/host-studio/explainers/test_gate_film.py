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
