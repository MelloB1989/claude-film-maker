"""B12: editor.plugins (.uproject), editor.cvars (sets, snapshots), editor.project_setting (Default*.ini), and the pure
file editors behind them (ops/_ini.py)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fakeunreal import pure, run_op

ini = pure("ops/_ini.py")

INI = """; a comment
[/Script/EngineSettings.GameMapsSettings]
EditorStartupMap=/Game/Maps/Studio

[/Script/Engine.RendererSettings]
r.RayTracing=False
+r.SomeArray=a
r.Lumen.HardwareRayTracing=True

[/Script/LinuxTargetPlatform.LinuxTargetSettings]
-TargetedRHIs=SF_VULKAN_SM5
+TargetedRHIs=SF_VULKAN_SM6
"""


def test_ini_get_and_set_keep_everything_else():
    assert ini.ini_get(INI, "/Script/Engine.RendererSettings", "r.RayTracing") == "False"
    assert ini.ini_get(INI, "/Script/Engine.RendererSettings", "r.SomeArray") is None  # array lines are not values
    new, ch = ini.ini_set(INI, "/Script/Engine.RendererSettings", "r.RayTracing", True)
    assert ch and "r.RayTracing=True" in new and "; a comment" in new and "+TargetedRHIs=SF_VULKAN_SM6" in new
    assert ini.ini_set(new, "/Script/Engine.RendererSettings", "r.RayTracing", True) == (new, False)
    new2, _ = ini.ini_set(new, "/Script/Engine.RendererSettings", "r.Nanite", 1)
    sec = new2.split("[/Script/Engine.RendererSettings]")[1].split("[")[0]
    assert "r.Nanite=1" in sec and sec.rstrip().endswith("r.Nanite=1")   # inside its section, before the blank line
    new3, _ = ini.ini_set(new2, "/Script/New.Section", "k", "v")
    assert new3.rstrip().endswith("[/Script/New.Section]\nk=v")
    new4, _ = ini.ini_set(INI, "/Script/LinuxTargetPlatform.LinuxTargetSettings", "bX", False)
    assert new4.rstrip().endswith("bX=False")                            # a section that runs to the end of the file


def test_uproject_plugins_on_and_off():
    up = json.dumps({"FileVersion": 3, "Plugins": [{"Name": "A", "Enabled": True}, {"Name": "B", "Enabled": False}]})
    assert ini.uproject_plugins(up) == {"A": True, "B": False}
    new, ch = ini.uproject_set_plugins(up, enable=["B", "C"], disable=["A"])
    assert sorted(ch) == ["A", "B", "C"] and ini.uproject_plugins(new) == {"A": False, "B": True, "C": True}
    assert json.loads(new)["FileVersion"] == 3
    assert ini.uproject_set_plugins(new, enable=["B"]) == (new, [])


@pytest.fixture
def project(ue):
    root = Path(ue.root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "Fake.uproject").write_text(json.dumps({"FileVersion": 3, "Plugins": [{"Name": "MetaHuman", "Enabled": True}]}))
    (root / "Config").mkdir(exist_ok=True)
    (root / "Config" / "DefaultEngine.ini").write_text(INI)
    ue.stub("PluginBlueprintLibrary.get_enabled_plugin_names", ["MetaHuman", "PythonScriptPlugin", "MovieRenderPipeline"])
    ue.stub("PluginBlueprintLibrary.get_plugin_descriptor_file_path",
            lambda name: f"/engine/Plugins/{name}/{name}.uplugin" if name != "NoSuchPlugin" else None)
    return root


def test_plugins_lists_and_edits_the_uproject(fmb, ue, project):
    r = run_op("editor.plugins", prefix="M")
    assert r["enabled"] == ["MetaHuman", "MovieRenderPipeline"] and r["project"] == {"MetaHuman": True}
    r = run_op("editor.plugins", enable=["MovieRenderPipeline"])
    assert r["changed"] == ["MovieRenderPipeline"] and r["restart_required"]
    assert ini.uproject_plugins((project / "Fake.uproject").read_text())["MovieRenderPipeline"] is True
    assert run_op("editor.plugins", enable=["MovieRenderPipeline"])["changed"] == []
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("editor.plugins", enable=["NoSuchPlugin"])
    assert e.value.code == "not_found"


def test_cvars_set_snapshot_restore(fmb, ue, project):
    ue.cvars.update({"r.RayTracing": "1", "r.ScreenPercentage": "100"})
    r = run_op("editor.cvars", values={"r.RayTracing": 0, "r.ScreenPercentage": 50}, snapshot="pre")
    assert r["values"] == {"r.RayTracing": "0", "r.ScreenPercentage": "50"} and sorted(r["changed"]) == \
        ["r.RayTracing", "r.ScreenPercentage"]
    r = run_op("editor.cvars", restore="pre")
    assert r["values"] == {"r.RayTracing": "1", "r.ScreenPercentage": "100"} and r["restored"] == "pre"
    from fmbridge.ops import editor_config
    editor_config._SNAPSHOTS.clear()                                    # a new bridge: the file still has it
    assert run_op("editor.cvars", restore="pre")["values"]["r.RayTracing"] == "1"
    assert run_op("editor.cvars", names=["r.RayTracing"])["changed"] == []
    from fmbridge.errors import OpError
    for bad in ({"names": ["r.Nope"]}, {"restore": "never"}):
        with pytest.raises(OpError) as e:
            run_op("editor.cvars", **bad)
        assert e.value.code == "not_found"


def test_project_setting_reads_and_writes_default_ini(fmb, ue, project):
    r = run_op("editor.project_setting", section="/Script/Engine.RendererSettings", key="r.RayTracing")
    assert r["value"] == "False" and r["changed"] is False
    r = run_op("editor.project_setting", section="/Script/Engine.RendererSettings", key="r.RayTracing", value=True)
    assert r["changed"] and r["restart_required"] and r["before"] == "False" and r["value"] == "True"
    assert "r.RayTracing=True" in (project / "Config" / "DefaultEngine.ini").read_text()
    r = run_op("editor.project_setting", file="Game", section="/Script/X", key="k", value="v")
    assert r["changed"] and (project / "Config" / "DefaultGame.ini").read_text() == "[/Script/X]\nk=v\n"
    from fmbridge.errors import OpError
    with pytest.raises(OpError) as e:
        run_op("editor.project_setting", file="Engin", section="s", key="k")
    assert e.value.code == "bad_args" and "Engine" in e.value.candidates
