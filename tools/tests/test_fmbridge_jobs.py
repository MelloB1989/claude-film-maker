"""The bridge's job model (unreal/fmbridge/jobs.py) without the engine: states, multi-tick generators with waits and
progress, cancelling (queued, running, and a one-step job that cannot be), the journal a reloaded bridge reads back,
shutdown, pruning and structured failures."""
from __future__ import annotations

import importlib.util
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("fmbridge_jobs", ROOT / "unreal" / "fmbridge" / "jobs.py")
jobs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jobs)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def runner(table):
    """run(kind, payload): an op named in `table` is called with the payload's args."""
    def run(kind, payload):
        if kind == "exec":
            ns = {"result": None}
            exec(payload["code"], ns)
            return ns["result"]
        return table[payload["name"]](**(payload.get("args") or {}))
    return run


def drain(reg, clock, ticks=50, dt=0.1):
    for _ in range(ticks):
        reg.tick(budget=0)
        reg.tick()  # budget 0 starts nothing; the default budget starts queued jobs
        clock.t += dt


def test_a_plain_call_finishes_in_one_tick_with_its_output():
    def hello(who):
        print("hi", who)
        return {"who": who}
    reg = jobs.Registry(runner({"t.hello": hello}))
    j = reg.submit("op", {"name": "t.hello", "args": {"who": "x"}})
    assert j.view()["state"] == "queued" and not j.view()["done"]
    reg.tick()
    v = j.view()
    assert v["state"] == "done" and v["ok"] and v["result"] == {"who": "x"} and "hi x" in v["stdout"]
    assert j.event.is_set()


def test_exec_and_a_failure_carry_the_traceback():
    reg = jobs.Registry(runner({}))
    ok = reg.submit("exec", {"code": "result = 1 + 1"})
    bad = reg.submit("exec", {"code": "raise ValueError('nope')"})
    reg.tick()
    assert ok.view()["result"] == 2
    v = bad.view()
    assert v["state"] == "failed" and not v["ok"] and "ValueError: nope" in v["error"]


def test_a_generator_runs_across_ticks_honours_waits_and_reports_progress():
    clock = Clock()

    def count(n):
        for i in range(n):
            yield {"progress": i / n, "message": f"{i}/{n}", "wait": 1.0}
        return n

    reg = jobs.Registry(runner({"t.count": count}), clock=clock)
    j = reg.submit("op", {"name": "t.count", "args": {"n": 3}})
    reg.tick()  # starts: runs to the first yield
    assert j.state == "running" and j.progress == 0.0 and j.message == "0/3"
    reg.tick()  # the 1 s wait has not passed: no step
    assert j.message == "0/3"
    clock.t += 1.01
    reg.tick()
    assert j.message == "1/3"
    drain(reg, clock, ticks=30, dt=0.5)
    assert j.view()["state"] == "done" and j.view()["result"] == 3


def test_a_bare_yield_and_a_number_both_work():
    clock = Clock()

    def g():
        yield
        yield 0.5
        return "ok"

    reg = jobs.Registry(runner({"t.g": g}), clock=clock)
    j = reg.submit("op", {"name": "t.g"})
    drain(reg, clock)
    assert j.state == "done" and j.result == "ok"


def test_cancel_a_queued_job_and_a_running_generator_whose_finally_runs():
    clock = Clock()
    cleaned = []

    def long():
        try:
            while True:
                yield 1.0
        finally:
            cleaned.append(True)

    reg = jobs.Registry(runner({"t.long": long, "t.quick": lambda: 1}), clock=clock)
    running = reg.submit("op", {"name": "t.long"})
    reg.tick()
    queued = reg.submit("op", {"name": "t.quick"})
    assert reg.cancel(queued.id) == {"ok": True, "state": "cancelled"}
    assert queued.view()["state"] == "cancelled" and queued.event.is_set()
    assert reg.cancel(running.id)["state"] == "cancelling"
    reg.tick()
    assert running.state == "cancelled" and cleaned == [True]
    assert reg.cancel(running.id)["note"] == "already finished"
    assert reg.cancel("nope")["ok"] is False


def test_a_one_step_job_cannot_be_cancelled_while_it_runs():
    reg = jobs.Registry(runner({}))
    j = reg.submit("op", {"name": "x"})
    j.state = "running"  # as seen from another thread while the game thread runs it
    r = reg.cancel(j.id)
    assert r["ok"] is False and "cannot be stopped" in r["error"]


def test_wait_returns_when_done_from_another_thread_and_times_out_otherwise():
    reg = jobs.Registry(runner({"t.one": lambda: 1}))
    j = reg.submit("op", {"name": "t.one"})
    assert reg.wait(j, 0.05) is False
    threading.Timer(0.05, reg.tick).start()
    assert reg.wait(j, 5) is True and j.result == 1


def test_the_journal_answers_after_a_reload_and_running_jobs_become_lost(tmp_path):
    clock = Clock()

    def forever():
        while True:
            yield

    reg = jobs.Registry(runner({"t.one": lambda: {"a": 1}, "t.forever": forever}), journal=str(tmp_path), clock=clock)
    done = reg.submit("op", {"name": "t.one"})
    run = reg.submit("op", {"name": "t.forever"})
    reg.tick()
    assert (tmp_path / f"{done.id}.json").exists()
    reg.shutdown("the bridge restarted")
    assert run.view()["state"] == "lost" and "restarted while this ran" in run.view()["error"]
    again = jobs.Registry(runner({}), journal=str(tmp_path), clock=clock)
    v = again.get(done.id).view()
    assert v["state"] == "done" and v["ok"] and v["result"] == {"a": 1}
    assert again.get(run.id).view()["state"] == "lost"
    assert {x["id"] for x in again.list()} == {done.id, run.id}


def test_old_journal_entries_are_dropped_and_the_registry_is_pruned(tmp_path, monkeypatch):
    clock = Clock()
    reg = jobs.Registry(runner({"t.one": lambda: 1}), journal=str(tmp_path), clock=clock)
    old = reg.submit("op", {"name": "t.one"})
    reg.tick()
    clock.t += jobs.KEEP_SECONDS + 10
    fresh = jobs.Registry(runner({}), journal=str(tmp_path), clock=clock)
    assert fresh.get(old.id) is None and not (tmp_path / f"{old.id}.json").exists()
    monkeypatch.setattr(jobs, "KEEP_JOBS", 3)
    for _ in range(6):
        fresh.submit("op", {"name": "x"})
    assert len(fresh.list(limit=100)) <= 6  # queued jobs are never dropped
    reg2 = jobs.Registry(runner({"t.one": lambda: 1}), clock=clock)
    for _ in range(5):
        reg2.submit("op", {"name": "t.one"})
        reg2.tick()
    reg2.submit("op", {"name": "t.one"})
    assert len(reg2.list(limit=100)) <= 4


def test_list_filters_by_state_and_name():
    reg = jobs.Registry(runner({"mh.a": lambda: 1, "seq.b": lambda: 2}))
    reg.submit("op", {"name": "mh.a"})
    reg.submit("op", {"name": "seq.b"})
    reg.tick()
    reg.submit("op", {"name": "mh.a"})
    assert [j["name"] for j in reg.list(name="mh.")] == ["mh.a", "mh.a"]
    assert len(reg.list(state="queued")) == 1 and "result" not in reg.list()[0]


def test_a_structured_failure_comes_back_beside_the_traceback():
    class OpError(Exception):
        def __init__(self, code, hint):
            super().__init__(code)
            self.code, self.hint = code, hint

    def boom():
        raise OpError("not_found", "list with level.find")

    reg = jobs.Registry(runner({"t.boom": boom}), failure=lambda e: {"code": e.code, "hint": e.hint}
                        if isinstance(e, OpError) else None)
    j = reg.submit("op", {"name": "t.boom"})
    reg.tick()
    v = j.view()
    assert v["code"] == "not_found" and v["hint"] == "list with level.find" and "OpError" in v["error"]


def test_stdout_is_bounded(monkeypatch):
    monkeypatch.setattr(jobs, "STDOUT_MAX", 10)
    reg = jobs.Registry(runner({}))
    j = reg.submit("exec", {"code": "print('x' * 100)\nresult = 1"})
    reg.tick()
    assert len(j.view()["stdout"]) == 10


@pytest.mark.parametrize("state", jobs.FINISHED)
def test_every_finished_state_is_done(state):
    j = jobs.Job("op", {"name": "x"})
    j.state = state
    assert j.view()["done"] is True and j.view()["ok"] is (state == "done")


def test_finish_hooks_see_every_ending_with_the_generator(monkeypatch):
    seen = []
    monkeypatch.setattr(jobs, "_ON_FINISH", [])
    jobs.on_finish(lambda gen, view: seen.append((gen is not None, view["state"])))
    jobs.on_finish(lambda gen, view: 1 / 0)  # a broken hook changes nothing

    def g():
        yield
        return 1
    reg = jobs.Registry(runner({"t.g": g, "t.one": lambda: 1}))
    reg.submit("op", {"name": "t.one"})
    reg.submit("op", {"name": "t.g"})
    reg.tick()
    reg.tick()
    assert sorted(seen) == [(False, "done"), (True, "done")]
