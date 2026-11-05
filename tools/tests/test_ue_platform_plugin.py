"""setup.sh plugin (day 1: FabScript): the real bash step in a sandbox, with a fake Build.sh. The engine counts as
installed only while UBT runs, the built plugin lands in the project without Intermediate, and a failed build leaves
the project and the engine as they were."""
import io
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

SETUP = Path(__file__).resolve().parents[2] / "unreal" / "linux" / "setup.sh"

BUILD_OK = """#!/bin/bash
[ -f "$(dirname "$0")/../../InstalledBuild.txt" ] || { echo "not installed: would rebuild the engine"; exit 9; }
proj="${4#-Project=}"; d="$(dirname "$proj")/Plugins/Demo"
mkdir -p "$d/Binaries/Linux" "$d/Intermediate/Build" && touch "$d/Binaries/Linux/libUnrealEditor-Demo.so"
echo "[1/2] Compile Demo.cpp"; echo "[2/2] Link libUnrealEditor-Demo.so"
"""


def sandbox(tmp_path, build_sh):
    shims = tmp_path / "shims"
    shims.mkdir()
    (shims / "runuser").write_text('#!/bin/bash\nshift 3\nexec "$@"\n')  # runuser -u USER -- CMD...
    (shims / "chown").write_text("#!/bin/sh\nexit 0\n")
    for f in shims.iterdir():
        f.chmod(0o755)
    engine = tmp_path / "engine"
    b = engine / "Engine" / "Build" / "BatchFiles" / "Linux"
    b.mkdir(parents=True)
    (b / "Build.sh").write_text(build_sh)
    (b / "Build.sh").chmod(0o755)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data in (("Demo/Demo.uplugin", b"{}"), ("Demo/Source/Demo/Demo.Build.cs", b"//")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    tgz = tmp_path / "plugin-Demo.tgz"
    tgz.write_bytes(buf.getvalue())
    project = tmp_path / "project"
    project.mkdir()
    env = {**os.environ, "PATH": f"{shims}:{os.environ['PATH']}", "UE_USER": "me",
           "PLUGIN_BUILD_DIR": str(tmp_path / "pluginbuild")}

    def run():
        return subprocess.run(["bash", str(SETUP), "plugin", str(tgz), str(engine), str(project)], env=env,
                              capture_output=True, text=True)
    return run, engine, project


def test_builds_only_the_plugin_and_installs_it(tmp_path):
    run, engine, project = sandbox(tmp_path, BUILD_OK)
    r = run()
    assert r.returncode == 0, r.stderr + r.stdout
    assert "plugin: Demo built (2 actions)" in r.stdout
    assert (project / "Plugins/Demo/Binaries/Linux/libUnrealEditor-Demo.so").exists()
    assert not (project / "Plugins/Demo/Intermediate").exists()
    assert not (engine / "Engine/Build/InstalledBuild.txt").exists()
    assert run().returncode == 0  # again: replaces it


def test_a_failed_build_leaves_project_and_engine_alone(tmp_path):
    run, engine, project = sandbox(tmp_path, "#!/bin/bash\necho 'error: FabScriptLibrary.cpp: no such header'\nexit 6\n")
    r = run()
    assert r.returncode != 0 and "Demo did not build" in r.stderr and "no such header" in r.stderr
    assert not (project / "Plugins").exists()
    assert not (engine / "Engine/Build/InstalledBuild.txt").exists()


def test_an_engine_already_installed_keeps_its_marker(tmp_path):
    run, engine, project = sandbox(tmp_path, BUILD_OK)
    (engine / "Engine/Build/InstalledBuild.txt").write_text("")
    assert run().returncode == 0
    assert (engine / "Engine/Build/InstalledBuild.txt").exists()


@pytest.mark.parametrize("name", ["FabScript"])
def test_build_plugin_sends_the_source_without_binaries(monkeypatch, name):
    from filmtools.unreal import linuxbox
    from filmtools.unreal import workstation as ws
    put, steps = {}, []
    monkeypatch.setattr(ws, "conf", lambda: {"user": "ubuntu", "project_dir": "/srv/ue/projects/P"})
    monkeypatch.setattr(ws, "put_text", lambda path, data: put.__setitem__(path, data))
    monkeypatch.setattr(linuxbox, "step", lambda *a, **k: steps.append(a) or "plugin: built")
    assert linuxbox.build_plugin(name) == "plugin: built"
    tgz = put[f"/home/ubuntu/.film-ue/linux/plugin-{name}.tgz"]
    names = tarfile.open(fileobj=io.BytesIO(tgz)).getnames()
    assert f"{name}/{name}.uplugin" in names and not any("/Binaries" in n for n in names)
    assert steps[-1] == ("plugin", f"/home/ubuntu/.film-ue/linux/plugin-{name}.tgz", "/srv/ue/engine",
                         "/srv/ue/projects/P")
    with pytest.raises(SystemExit, match="no plugin Nope"):
        linuxbox.build_plugin("Nope")
