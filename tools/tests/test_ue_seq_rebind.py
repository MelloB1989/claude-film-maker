"""seq.rebind and a binding's converge (seqcore bind) point a binding at the level's actor of ITS label, never at
another actor that took its object name. A possessable keeps its actor by object name, not label (the fake models it
with bind_by_name): when a reel camera is deleted and another script's camera is spawned first, that camera takes the
freed name (CineCameraActor_0) and the old binding finds it. Day-1 r3 on the box: after build.py cameras(), Reel_V02's
keys drove perf.py's Test_agent-10_S13 and Reel_V02 stood still."""
import pytest

from fakeunreal import run_op

SEQ = "/Game/L/SEQ_Rebind"


@pytest.fixture
def reused(ue):
    """Two reel cameras keyed in SEQ, both deleted, then a test camera and the respawned reel cameras: the test
    camera has Reel_A's old object name, the new Reel_A has Reel_B's."""
    ue.bind_by_name = True
    a, b = ue.spawn("CineCameraActor", "Reel_A"), ue.spawn("CineCameraActor", "Reel_B")
    run_op("seq.new", path=SEQ, start=0, end=48, fps=24)
    for lab in ("Reel_A", "Reel_B"):
        run_op("seq.key_transform", path=SEQ, label=lab, keys=[[0, [0, 0, 100], {"yaw": 0}], [24, [50, 0, 100], {}]])
    names = a.get_name(), b.get_name()
    a.destroy_actor()
    b.destroy_actor()
    test = ue.spawn("CineCameraActor", "Test_agent-10_S13")
    a2, b2 = ue.spawn("CineCameraActor", "Reel_A"), ue.spawn("CineCameraActor", "Reel_B")
    assert (test.get_name(), a2.get_name()) == names  # the freed names were taken: the case under test
    return {"Reel_A": a2, "Reel_B": b2, "test": test}


def located(label: str) -> list:
    from fmbridge.ops.seqcore import _engine as E
    seq = E.load(SEQ)
    return seq.locate_bound_objects(E.bindings(seq)[(label, "")], E.world())


def test_a_binding_found_on_another_actor_is_not_bound(reused):
    from fmbridge.ops.seqcore import _engine as E
    seq = E.load(SEQ)
    b = E.bindings(seq)[("Reel_A", "")]
    assert located("Reel_A") == [reused["test"]]  # the stale binding finds the test camera
    assert E.is_bound(seq, b) is True              # something is found...
    assert E.is_bound(seq, b, "Reel_A") is False   # ...but not its own actor


def test_rebind_points_each_binding_at_its_own_label(reused):
    assert run_op("seq.rebind", path=SEQ, labels=["Reel_A", "Reel_B"]) == {"Reel_A": "ok", "Reel_B": "ok"}
    assert located("Reel_A") == [reused["Reel_A"]]
    assert located("Reel_B") == [reused["Reel_B"]]
    from fmbridge.ops.seqcore import _engine as E
    seq = E.load(SEQ)
    assert all(E.is_bound(seq, E.bindings(seq)[(lab, "")], lab) for lab in ("Reel_A", "Reel_B"))
    assert len(E.bindings(seq)[("Reel_A", "")].get_tracks()) == 1  # its keys kept


def test_keys_after_the_converge_drive_the_right_camera(reused):
    from fmbridge.ops.seqcore import _engine as E
    seq = E.load(SEQ)
    E.bind(seq, "Reel_A")
    E.bind(seq, "Reel_B")
    assert located("Reel_A") == [reused["Reel_A"]] and located("Reel_B") == [reused["Reel_B"]]
    assert reused["test"] not in located("Reel_A") + located("Reel_B")


def test_a_correct_binding_is_left_alone(ue):
    ue.bind_by_name = True
    ue.spawn("CineCameraActor", "Reel_A")
    run_op("seq.new", path=SEQ, start=0, end=48, fps=24)
    run_op("seq.key_transform", path=SEQ, label="Reel_A", keys=[[0, [0, 0, 100], {"yaw": 0}]])
    from fmbridge.ops.seqcore import _engine as E
    seq = E.load(SEQ)
    have = E.bindings(seq)[("Reel_A", "")]
    assert E.bind(seq, "Reel_A") == (have, False)


def test_a_binding_named_apart_from_its_actor_is_judged_as_before(ue):
    """A binding whose name is no actor's label (renamed, or its actor relabelled): bound means it finds something,
    as before, so describe never reports it unbound (a plan would emit seq.rebind for it forever) and bind() is not
    sent to actor(name)."""
    ue.bind_by_name = True
    cam = ue.spawn("CineCameraActor", "Reel_A")
    run_op("seq.new", path=SEQ, start=0, end=48, fps=24)
    run_op("seq.key_transform", path=SEQ, label="Reel_A", keys=[[0, [0, 0, 100], {"yaw": 0}]])
    cam.set_actor_label("Reel_A_renamed")
    from fmbridge.ops.seqcore import _engine as E
    seq = E.load(SEQ)
    b = E.bindings(seq)[("Reel_A", "")]
    assert E.is_bound(seq, b, "Reel_A") is True
    assert run_op("seq.rebind", path=SEQ) == {}
    assert located("Reel_A") == [cam]
