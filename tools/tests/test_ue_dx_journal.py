"""B32: the op journal on the fake engine: mutating ops recorded with args/ms/result, reads skipped, tail, clear,
replay rebuilding a level, a job's outcome folded into its start line."""
import json

import pytest

from fakeunreal import drive, run_op


@pytest.fixture
def jr(fmb, tmp_path, monkeypatch):
    from fmbridge.ops import journal
    monkeypatch.setitem(journal._state, "path", str(tmp_path / "journal.jsonl"))
    monkeypatch.setitem(journal._state, "on", True)
    assert journal.HOOKED
    return journal


def test_mutating_ops_are_recorded(jr, fmb):
    run_op("level.spawn", label="A", shape="cube", loc=[0, 0, 50])
    run_op("level.move", label="A", loc=[10, 0, 50])
    run_op("ops.schema")                       # not mutating
    run_op("journal.tail")                     # the journal itself
    es = run_op("journal.tail")["entries"]
    assert [e["op"] for e in es] == ["level.spawn", "level.move"]
    assert es[0]["args"] == {"label": "A", "shape": "cube", "loc": [0, 0, 50]} and "ms" in es[0] and es[0]["result"] == "A"


def test_tail_prefix_and_clear(jr):
    run_op("level.spawn", label="A", shape="cube")
    assert run_op("journal.tail", prefix="look.")["entries"] == []
    assert run_op("journal.clear")["changed"] is True
    assert run_op("journal.tail")["entries"] == []


def test_replay_rebuilds(jr, ue, fmb):
    run_op("level.spawn", label="A", shape="cube", loc=[0, 0, 50])
    run_op("level.move", label="A", loc=[30, 0, 50])
    entries = run_op("journal.tail")["entries"]
    run_op("level.delete", labels=["A"])
    run_op("journal.record", on=False)
    res = run_op("journal.replay", entries=entries)
    assert res["ran"] == 2 and res["failed"] == []
    assert ue.actor("A").get_actor_location().x == 30
    dry = run_op("journal.replay", entries=entries, dry_run=True)
    assert dry["count"] == 2


def test_job_outcome_is_folded_in(jr, fmb, monkeypatch):
    def slow(*, n: int = 2):
        """A multi-tick op."""
        for _ in range(n):
            yield
        return {"done": n}
    monkeypatch.setitem(fmb._OPS, "zz.slow", slow)
    gen = fmb.call("zz.slow", n=2)
    res, _ = drive(gen)
    jr.finished(gen, {"name": "zz.slow", "state": "done", "result": res, "ms": 5})
    (e,) = run_op("journal.tail")["entries"]
    assert e["op"] == "zz.slow" and e["job"] and e["state"] == "done" and e["result"] == {"done": 2}


def test_big_arguments_are_cut(jr, fmb):
    run_op("level.spawn", label="B" * 5000, shape="cube")
    (e,) = run_op("journal.tail")["entries"]
    assert "truncated" in e["args"]
    res = run_op("journal.replay", entries=[e], keep_going=True)
    assert res["failed"] and "too big" in res["failed"][0]["error"]
