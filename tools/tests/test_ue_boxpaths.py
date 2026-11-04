"""B42: box paths for Windows and Linux (filmtools.unreal.boxpaths), pure."""
import pytest

from filmtools.unreal.boxpaths import BoxPaths

LIN = BoxPaths("linux", "/srv/ue/projects/HostStudio")
WIN = BoxPaths("windows", r"C:\UEProjects\HostStudio")


def test_named_locations_on_both():
    assert LIN.renders("SQ_Main", "0001.png") == "/srv/ue/projects/HostStudio/Saved/Renders/SQ_Main/0001.png"
    assert WIN.renders("SQ_Main") == r"C:\UEProjects\HostStudio\Saved\Renders\SQ_Main"
    assert LIN.token() == "/srv/ue/projects/HostStudio/Saved/fmbridge.token"
    assert WIN.bridge_in("install.py") == r"C:\UEProjects\HostStudio\Saved\Bridge\in\install.py"
    assert WIN.content_python("fmbridge", "ops", "audio.py").endswith(r"Content\Python\fmbridge\ops\audio.py")
    assert LIN.uproject() == "/srv/ue/projects/HostStudio/HostStudio.uproject"
    assert WIN.name() == "HostStudio" and LIN.selftest("audio") == "/srv/ue/projects/HostStudio/Saved/Selftest/audio"
    assert LIN.scratch("PoC", "renders") == "/srv/ue/projects/HostStudio/Saved/PoC/renders"


def test_mixed_separators_and_helpers():
    assert LIN.join("/srv/x", "a\\b.wav") == "/srv/x/a/b.wav"
    assert WIN.join(r"C:\x", "a/b.wav") == r"C:\x\a\b.wav"
    assert WIN.basename(r"C:\x\L1.wav") == "L1.wav" and LIN.parent("/a/b/c") == "/a/b"
    assert WIN.is_abs(r"D:\renders") and not LIN.is_abs("renders/x")


def test_errors():
    with pytest.raises(ValueError, match="box os"):
        BoxPaths("mac", "/x")
    with pytest.raises(SystemExit, match="film-ue set --project-dir"):
        BoxPaths("linux", "").saved()


def test_to_dict_lists_every_location():
    d = LIN.to_dict()
    assert d["os"] == "linux" and all(v.startswith("/srv/ue/projects/HostStudio") for k, v in d.items() if k != "os")


def test_style_of_and_users():
    from filmtools.unreal import audio_timing
    assert BoxPaths.style_of(r"D:\vo").join(r"D:\vo", "L1.wav") == r"D:\vo\L1.wav"
    assert BoxPaths.style_of("/srv/vo").os == "linux"
    doc = audio_timing.from_lines([{"id": "L1", "wav": "L1.wav", "start_frame": 0, "duration_s": 1, "speaker": "h"}], 24)
    h = audio_timing.performance_handoff(doc, {"h": {"face_mesh": "/Game/F", "label": "H"}}, wav_root=r"C:\P\Saved\Audio")
    assert h[0]["wav"] == r"C:\P\Saved\Audio\L1.wav"
