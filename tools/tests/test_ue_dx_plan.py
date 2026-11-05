"""B46: film-ue selftest plan (offline run order from the selftest modules) and the gates in film-ue selftest."""
import json

from filmtools.unreal import selftest as client_selftest, selftest_plan as sp


def test_durations_are_read_from_docstrings():
    assert sp._seconds("Takes ~10 s. Needs: nothing.") == 10
    assert sp._seconds("Takes about 1.5 min (two stills)") == 90
    assert sp._seconds("Takes ~2 min on the L4") == 120
    assert sp._seconds("no estimate here") is None
    assert sp._needs("x. Needs: GPU (a real RHI). Takes 1 s.") == "GPU (a real RHI)"


def test_plan_orders_gates_first_and_every_module_is_there():
    p = sp.plan()
    names = {m["name"] for m in sp.modules()}
    assert set(p["order"]) == names
    assert p["order"][:2] == ["platform", "dx"] or p["order"][0] == "dx"
    pos = {n: i for i, n in enumerate(p["order"])}
    for a, b in (("layout", "seq"), ("seq", "cam"), ("cam", "render"), ("render", "qa"), ("qa", "audio")):
        if a in pos and b in pos:
            assert pos[a] < pos[b], (a, b)
    assert p["estimate_s"] > 0 and p["worst_case_s"] >= p["estimate_s"]


def test_every_selftest_states_its_duration():
    """CONVENTIONS §10: a selftest's docstring says how long it takes (the plan's estimate)."""
    assert sp.plan()["unknown_estimates"] == []


def test_markdown_table_is_one_row_per_selftest():
    p = sp.plan()
    md = sp.markdown(p)
    rows = [line for line in md.splitlines() if line.startswith("| ") and line[2].isdigit()]
    assert len(rows) == len(p["order"]) and "Estimated total" in md


def test_a_failed_gate_stops_the_run(fmb, tmp_path, monkeypatch):
    from test_ue_dx_e2e import FakeBridge
    from filmtools.unreal.sdk import Unreal
    bridge = FakeBridge(fmb)
    calls = []

    def transport(kind, payload, timeout):
        if kind == "op" and payload["name"] == "selftest.run":
            calls.append(payload["args"]["area"])
            rep = {"area": payload["args"]["area"], "ok": payload["args"]["area"] != "dx", "status": "done",
                   "passed": 1, "failed": int(payload["args"]["area"] == "dx"), "checks": []}
            return {"ok": True, "job": "j" + payload["args"]["area"]} if payload.get("async") else {"ok": True, "result": rep}
        if kind == "job":
            area = payload["id"][1:]
            return {"done": True, "state": "done", "ok": True,
                    "result": {"area": area, "ok": area != "dx", "status": "done", "passed": 1,
                               "failed": int(area == "dx"), "checks": [{"name": "x", "ok": area != "dx"}]}}
        return bridge(kind, payload, timeout)
    monkeypatch.setattr(client_selftest, "client_phase", lambda area, ue: None)
    s = client_selftest.run_all(Unreal(transport=transport), ["all"], tmp_path / "r", pull=False, log=lambda m: None)
    assert calls[-1] == "dx" and s["stopped"]["after"] == "dx" and s["stopped"]["not_run"]
    assert "Stopped after the gate `dx` failed" in (tmp_path / "r" / "summary.md").read_text()
    calls.clear()
    s = client_selftest.run_all(Unreal(transport=transport), ["all"], tmp_path / "r2", pull=False, log=lambda m: None,
                                keep_going=True)
    assert "stopped" not in s and len(calls) > 2
