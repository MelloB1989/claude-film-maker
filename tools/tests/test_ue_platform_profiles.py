"""Box profiles: several boxes' settings side by side, one current, copies that do not share a box."""
from __future__ import annotations

import pytest

from filmtools.unreal import profiles
from filmtools.unreal import workstation as ws


@pytest.fixture
def conf(tmp_path, monkeypatch):
    monkeypatch.setattr(ws, "CONF_DIR", tmp_path)
    monkeypatch.delenv("FILM_UE_BOX", raising=False)
    return tmp_path


def test_profiles_list_use_show_copy_remove(conf, monkeypatch):
    ws.save(os="windows", instance="i-win")                 # the default profile
    monkeypatch.setenv("FILM_UE_BOX", "gpu1")
    ws.save(os="linux", instance="i-gpu1", project_dir="/srv/ue/projects/Demo", local_port=18766)
    monkeypatch.delenv("FILM_UE_BOX")
    assert profiles.names() == ["default", "gpu1"] and profiles.current() == "default"
    assert ws.conf()["instance"] == "i-win"
    profiles.use("gpu1")
    assert profiles.current() == "gpu1" and ws.box() == "gpu1" and ws.conf()["instance"] == "i-gpu1"
    assert [r["current"] for r in profiles.listing()] == [False, True]
    c = profiles.copy("gpu1", "gpu2")
    assert "instance" not in c and "local_port" not in c and c["project_dir"] == "/srv/ue/projects/Demo"
    monkeypatch.setenv("FILM_UE_BOX", "default")             # one command on another box
    assert ws.conf()["instance"] == "i-win"
    monkeypatch.delenv("FILM_UE_BOX")
    (conf / "film-ue.gpu1.token").write_text("t")
    assert sorted(profiles.remove("gpu1")) == ["film-ue.gpu1.json", "film-ue.gpu1.token"]
    assert profiles.current() == "default" and profiles.names() == ["default", "gpu2"]


def test_bad_or_missing_names_are_explained(conf):
    with pytest.raises(SystemExit, match="letters, digits"):
        profiles.use("../etc")
    with pytest.raises(SystemExit, match="no profile 'nope'"):
        profiles.use("nope")
    with pytest.raises(SystemExit, match="no profile"):
        profiles.remove("nope")
    ws.save(os="linux")
    with pytest.raises(SystemExit, match="exists"):
        profiles.copy("default", "default")
