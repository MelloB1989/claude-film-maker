"""B10: the scratch context (unreal/fmbridge/ops/_scratch.py) on the fake engine."""
import pytest


@pytest.fixture
def sc(fmb):
    from fmbridge.ops import _scratch
    return _scratch


def test_scratch_level_and_cleanup(sc, ue, fmb):
    fmb.call("level.new", path="/Game/Work/L_Main")
    with sc.scratch("/Game/_Scratch/t1") as s:
        assert sc.current_level() == "/Game/_Scratch/t1/L_t1" and s.previous == "/Game/Work/L_Main"
        fmb.call("level.spawn", label=s.prefix + "Box", shape="cube")
    assert sc.current_level() == "/Game/Work/L_Main"
    import unreal
    assert not unreal.EditorAssetLibrary.does_directory_exist("/Game/_Scratch/t1")
    assert ue.dialogs == []


def test_scratch_cleans_up_on_failure(sc, ue, fmb):
    import unreal
    fmb.call("level.new", path="/Game/Work/L_Main")
    with pytest.raises(RuntimeError):
        with sc.scratch("/Game/_Selftest/boom"):
            raise RuntimeError("kaput")
    assert sc.current_level() == "/Game/Work/L_Main"
    assert not unreal.EditorAssetLibrary.does_directory_exist("/Game/_Selftest/boom")


def test_scratch_in_the_open_level_removes_prefixed_actors(sc, ue, fmb):
    fmb.call("level.new", path="/Game/Work/L_Main")
    fmb.call("level.spawn", label="Keep", shape="cube")
    with sc.scratch("/Game/_Scratch/inplace", level=False) as s:
        fmb.call("level.spawn", label=s.prefix + "Tmp", shape="cube")
        assert sc.current_level() == "/Game/Work/L_Main"
    labels = [a.get_actor_label() for a in ue.world.actors()]
    assert "Keep" in labels and not any(x.startswith(s.prefix) for x in labels)


def test_scratch_keep(sc, ue, fmb):
    import unreal
    with sc.scratch("/Game/_Scratch/kept", keep=True):
        pass
    assert unreal.EditorAssetLibrary.does_asset_exist("/Game/_Scratch/kept/L_kept")


@pytest.mark.parametrize("bad", ["/Game/Characters", "/Game/_Scratch", "/Game/_Selftest/", "/Engine/_Scratch/x"])
def test_scratch_refuses_other_folders(sc, bad):
    with pytest.raises(ValueError):
        with sc.scratch(bad):
            pass


def test_scratch_in_a_generator_cleans_up_when_closed(sc, ue, fmb):
    import unreal

    def job():
        with sc.scratch("/Game/_Scratch/gen"):
            while True:
                yield
    g = job()
    next(g)
    assert unreal.EditorAssetLibrary.does_asset_exist("/Game/_Scratch/gen/L_gen")
    g.close()
    assert not unreal.EditorAssetLibrary.does_directory_exist("/Game/_Scratch/gen")
