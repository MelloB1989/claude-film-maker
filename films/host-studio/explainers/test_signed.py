from signed import EYE, rows


def test_signed_rows_and_refusals():
    s = {"by": "cc-64d05f6e", "film": "netflix", "gate": {k: 1 for k in EYE}, "notes": {"eye.light": "rim ok"}}
    r = rows(s)
    assert all(r[k]["value"] == 1 for k in EYE) and "rim ok" in r["eye.light"]["where"]
    del s["gate"]["eye.graphics"]
    assert rows(s)["eye.graphics"]["value"] is None
    s["by"] = "agent-09"
    assert all("error" in v for v in rows(s).values())
