"""The GPU box's watchdog (unreal/linux/ue_watchdog.py): time to live, idle power-off, a stalled or dead editor
restarted, a crash loop ended. decide() is pure; main() is run with its measurements faked and dry_run on."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("ue_watchdog", ROOT / "unreal" / "linux" / "ue_watchdog.py")
wd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wd)

CFG = {**wd.DEFAULTS, "idle_min": 20, "stall_min": 10, "max_restarts": 2, "grace_min": 30}
T0 = 1_000_000.0


def m(now, **kw):
    base = {"now": now, "uptime_s": 7200, "health": None, "gpu_pct": 0, "load1": 0.1, "sessions": 0,
            "keepalive_age_s": None, "service": "active", "service_since": 111}
    base.update(kw)
    return base


def H(**kw):
    return {"ok": True, "jobs": {"queued": 0, "running": 0}, "idle_s": 10_000, "last_tick_s": 0.1, **kw}


def test_ttl_ends_the_box_whatever_else_happens():
    acts, _, why = wd.decide({**CFG, "ttl_until": T0}, {}, m(T0 + 5, gpu_pct=99, health=H(idle_s=1)))
    assert acts == [("poweroff", "ttl: the box's time ran out 5 s ago")] and why == ["ttl"]


def test_idle_counts_from_the_last_activity_of_any_kind():
    st = {}
    for busy in (dict(gpu_pct=80), dict(load1=6.0), dict(sessions=1), dict(keepalive_age_s=60),
                 dict(health=H(idle_s=30)), dict(health=H(jobs={"running": 1, "queued": 0})), dict(uptime_s=60)):
        acts, st, why = wd.decide(CFG, st, m(T0, **busy))
        assert acts == [] and why and st["last_active"] == T0
    acts, st, _ = wd.decide(CFG, st, m(T0 + 19 * 60, health=H()))
    assert acts == [] and st["idle_s"] == 19 * 60
    acts, st, why = wd.decide(CFG, st, m(T0 + 20 * 60, health=H()))
    assert acts == [("poweroff", "idle: nothing for 20 min")] and "idle" in why


def test_a_stalled_editor_is_restarted_only_after_it_answered_once():
    st = {}
    # starting up (first open compiles for ~20 min): no answer yet is not a stall
    for t in range(0, 40 * 60, 60):
        acts, st, _ = wd.decide(CFG, st, m(T0 + t, gpu_pct=50))
        assert acts == []
    acts, st, _ = wd.decide(CFG, st, m(T0 + 41 * 60, gpu_pct=50, health=H(idle_s=5)))
    assert st["answered"] is True
    acts, st, _ = wd.decide(CFG, st, m(T0 + 42 * 60, gpu_pct=50))                      # silent now
    acts, st, _ = wd.decide(CFG, st, m(T0 + 51 * 60, gpu_pct=50))
    assert acts == []
    acts, st, _ = wd.decide(CFG, st, m(T0 + 52 * 60, gpu_pct=50))
    assert acts and acts[0][0] == "restart" and "10 min" in acts[0][1] and len(st["restarts"]) == 1


def test_a_stuck_game_thread_is_a_stall_even_if_http_answers():
    st = {"answered": True, "service_since": 111}
    acts, st, _ = wd.decide(CFG, st, m(T0, gpu_pct=50, health=H(idle_s=5, last_tick_s=11 * 60)))
    assert st["stall_since"] == T0
    acts, st, _ = wd.decide(CFG, st, m(T0 + 10 * 60, gpu_pct=50, health=H(idle_s=5, last_tick_s=21 * 60)))
    assert acts[0][0] == "restart"


def test_a_new_unit_start_resets_the_stall_clock():
    st = {"answered": True, "service_since": 111, "stall_since": T0}
    acts, st, _ = wd.decide(CFG, st, m(T0 + 11 * 60, gpu_pct=50, service_since=222))
    assert acts == [] and st["answered"] is False and st["stall_since"] is None


def test_a_crash_loop_powers_off_instead_of_restarting_forever():
    st = {"restarts": [T0 - 100, T0 - 50], "answered": True, "service_since": 111, "stall_since": T0 - 11 * 60}
    acts, _, why = wd.decide(CFG, st, m(T0, gpu_pct=50))
    assert acts[0][0] == "poweroff" and "crash loop" in acts[0][1] and "stall-loop" in why
    acts, st2, _ = wd.decide(CFG, {"restarts": [T0 - 4000]}, m(T0, gpu_pct=50, service="failed"))
    assert acts == [("start", "dead: systemd gave up on the editor")] and len(st2["restarts"]) == 1  # old one aged out
    acts, _, _ = wd.decide(CFG, {"restarts": [T0 - 10, T0 - 5]}, m(T0, gpu_pct=50, service="failed"))
    assert acts[0][0] == "poweroff"


def test_main_writes_its_decision_and_acts_in_dry_run(tmp_path, monkeypatch, capsys):
    conf, state = tmp_path / "w.json", tmp_path / "state" / "w.json"
    conf.write_text(json.dumps({"ttl_until": T0, "dry_run": True}))
    monkeypatch.setattr(wd, "CONF", str(conf))
    monkeypatch.setattr(wd, "STATE", str(state))
    monkeypatch.setattr(wd, "measure", lambda cfg: m(T0 + 1))
    ran = []
    monkeypatch.setattr(wd, "_run", lambda cmd, timeout=20: ran.append(cmd) or "")
    assert wd.main([]) == 0
    s = json.loads(state.read_text())
    assert s["last_decision"]["actions"][0][0] == "poweroff" and s["last_decision"]["ttl_left_s"] == -1
    assert "film-ue watchdog: poweroff: ttl" in capsys.readouterr().out and ran == []  # dry run: nothing executed


def test_poweroff_stops_the_editor_first_so_it_saves_the_sign_in(monkeypatch):
    ran = []
    monkeypatch.setattr(wd, "_run", lambda cmd, timeout=20: ran.append(cmd) or "")
    wd.act({**CFG, "dry_run": False}, [("poweroff", "idle")])
    assert ran == [["systemctl", "stop", "ue-editor"], ["systemctl", "poweroff"]]


def test_the_box_python_can_run_it():
    import ast
    src = (ROOT / "unreal" / "linux" / "ue_watchdog.py").read_text()
    ast.parse(src, feature_version=(3, 8))  # Ubuntu 22.04's python3 is 3.10; stay well under it
