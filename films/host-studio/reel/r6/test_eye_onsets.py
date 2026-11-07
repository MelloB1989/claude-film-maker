from eye_onsets import LINES, judge


def strip(**over):
    lines = {ln: {"lead_f": 1, "verdict": "pass"} for ln in LINES}
    lines.update(over)
    return {"by": "cc-64d05f6e", "lines": lines}


def test_all_pass():
    assert judge(strip())["value"] == 1


def test_occluded_needs_a_note():
    assert judge(strip(L3a={"verdict": "occluded", "lead_f": None}))["value"] == 0
    assert judge(strip(L3a={"verdict": "occluded", "lead_f": None, "note": "her hair"}))["value"] == 1


def test_lead_outside_window_or_missing_line_fails():
    assert judge(strip(L1={"lead_f": 3, "verdict": "pass"}))["value"] == 0
    assert judge(strip(L1={"lead_f": -1, "verdict": "pass"}))["value"] == 0
    s = strip()
    del s["lines"]["L4b"]
    assert "L4b: not judged" in judge(s)["where"]


def test_wrong_signer_is_an_error():
    s = strip()
    s["by"] = "agent-09"
    assert judge(s)["value"] is None and "error" in judge(s)
