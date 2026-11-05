"""B49 film-ue first-run: steps in order, fixes it makes itself, a stop with the exact next command, progress kept in
the profile so a rerun continues, --from and --restart."""
from __future__ import annotations

import pytest

from filmtools.unreal import firstrun
from filmtools.unreal import workstation as ws


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setattr(ws, "CONF_DIR", tmp_path)
    monkeypatch.setenv("FILM_UE_BOX", "gpu1")
    ws.save(os="linux", instance="i-1", project_dir="/srv/ue/projects/Demo")
    calls = []

    def fake(name, result="ok"):
        def step(opts, log):
            calls.append(name)
            if isinstance(result, Exception):
                raise result
            return f"{name} {result}"
        return step
    for n in firstrun.STEPS:
        monkeypatch.setitem(firstrun.RUN, n, fake(n))
    return calls, fake, monkeypatch


def test_all_steps_pass_in_order_and_are_remembered(box):
    calls, fake, mp = box
    r = firstrun.run(log=lambda m: None)
    assert r["ok"] and calls == list(firstrun.STEPS) and "10-character.yaml" in r["next"]
    assert ws.conf()["first_run"]["done"] == list(firstrun.STEPS)
    calls.clear()
    firstrun.run(log=lambda m: None)
    assert calls == ["reach"]  # everything done before is skipped; reaching the box is always checked


def test_a_stop_saves_where_and_the_next_command_and_a_rerun_continues(box):
    calls, fake, mp = box
    mp.setitem(firstrun.RUN, "epic", fake("epic", firstrun.Stop("no sign-in", "film-ue --box gpu1 epic-login", True)))
    out = []
    r = firstrun.run(log=out.append)
    assert not r["ok"] and r["next"] == "film-ue --box gpu1 epic-login" and r["steps"]["epic"]["needs_you"]
    assert "selftest" not in calls and any("next: film-ue --box gpu1 epic-login" in m for m in out)
    st = firstrun.status()
    assert st["stopped_at"] == "epic" and st["done"] == ["settings", "reach", "editor", "bridge", "shaders", "doctor"]
    calls.clear()
    mp.setitem(firstrun.RUN, "epic", fake("epic"))
    assert firstrun.run(log=lambda m: None)["ok"] and calls == ["reach", "epic", "selftest", "demo0"]


def test_from_and_restart(box):
    calls, fake, mp = box
    firstrun.run(log=lambda m: None)
    calls.clear()
    firstrun.run(start="doctor", log=lambda m: None)
    assert calls == ["reach", "doctor", "epic", "selftest", "demo0"]
    calls.clear()
    firstrun.run(restart=True, log=lambda m: None)
    assert calls == list(firstrun.STEPS)
    with pytest.raises(SystemExit, match="no step 'nope'"):
        firstrun.run(start="nope")


def test_settings_step_names_what_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(ws, "CONF_DIR", tmp_path)
    monkeypatch.setenv("FILM_UE_BOX", "fresh")
    ws.save(os="linux")
    with pytest.raises(firstrun.Stop) as e:
        firstrun.step_settings({}, print)
    assert "instance" in e.value.message and "box up" in e.value.next_cmd


def test_the_editor_step_starts_a_stopped_editor(box, monkeypatch):
    from filmtools.unreal import editorsvc, linuxbox
    monkeypatch.setattr(linuxbox, "upload_kit", lambda: "")
    monkeypatch.setattr(linuxbox, "step", lambda *a, **k: "rhi=ok")
    state = {"active": "inactive"}
    monkeypatch.setattr(editorsvc, "unit", lambda: {"active": state["active"], "result": "success", "restarts": 0})
    monkeypatch.setattr(editorsvc, "control", lambda act, **kw: state.update(active="active"))
    assert "active" in firstrun.step_editor({}, lambda m: None)


def test_the_bridge_step_installs_an_old_bridge(box, monkeypatch):
    from filmtools.unreal import cli, client, editorsvc
    answers = iter([{"ok": True, "bridge": 1}, ])
    monkeypatch.setattr(client, "health", lambda retry_s=0: next(answers))
    installed = []
    monkeypatch.setattr(cli, "install", lambda: installed.append(1) or "installed")
    monkeypatch.setattr(editorsvc, "wait_bridge", lambda s=3600: {"bridge": 2, "engine": "5.8.4", "platform": "linux"})
    assert "bridge 2" in firstrun.step_bridge({}, lambda m: None) and installed == [1]


def test_epic_step_asks_for_the_sign_in_unless_told_to_run_it(box, monkeypatch):
    from filmtools.unreal import linuxbox
    monkeypatch.setattr(linuxbox, "upload_kit", lambda: "")
    monkeypatch.setattr(linuxbox, "step", lambda *a, **k: "signed_in=no\nsign_ins=0\n")
    with pytest.raises(firstrun.Stop) as e:
        firstrun.step_epic({}, lambda m: None)
    assert e.value.needs_you and "epic-login" in e.value.next_cmd
    monkeypatch.setattr(linuxbox, "epic_login", lambda log=print: "signed in")
    assert firstrun.step_epic({"epic": True}, lambda m: None) == "signed in"


def test_the_editor_step_sets_sm6_and_restarts_a_running_editor_once(box, monkeypatch):
    from filmtools.unreal import editorsvc, linuxbox
    ws.save(project_dir="/srv/ue/projects/P")
    monkeypatch.setattr(linuxbox, "upload_kit", lambda: "")
    answers, steps, acts = ["rhi=set", "rhi=ok"], [], []
    monkeypatch.setattr(linuxbox, "step", lambda *a, **k: steps.append(a) or answers.pop(0))
    monkeypatch.setattr(editorsvc, "unit", lambda: {"active": "active", "result": "success", "restarts": 0})
    monkeypatch.setattr(editorsvc, "control", lambda act, **kw: acts.append(act))
    firstrun.step_editor({}, lambda m: None)
    firstrun.step_editor({}, lambda m: None)
    assert steps == [("rhi", "/srv/ue/projects/P")] * 2 and acts == ["restart"]
