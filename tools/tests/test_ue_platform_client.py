"""The client against the real bridge server (unreal/fmbridge/server.py on the fake engine), over HTTP on this machine
(transport "local"): calls, jobs with progress, cancel, listing, a timeout that leaves the job running, a job the
bridge does not know, and retries through a dropped connection."""
from __future__ import annotations

import socket
import sys
import threading
import time
import urllib.error

import pytest

from filmtools.unreal import client
from filmtools.unreal import workstation as ws

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="posix paths for the local box")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def bridge(ue, tmp_path, monkeypatch):
    """The real server on a free port, ticked by a thread standing in for the game thread; the client set up for a
    local box pointing at it."""
    from fakeunreal import load_fmbridge
    load_fmbridge()
    from fmbridge import server
    port = _free_port()
    monkeypatch.setattr(ws, "CONF_DIR", tmp_path / "conf")
    monkeypatch.setenv("FILM_UE_BOX", "here")
    project = ue.project_dir if hasattr(ue, "project_dir") else str(tmp_path / "project")
    server._state.update(registry=None, server=None, tick=None)
    monkeypatch.setattr(server, "JOURNAL", str(tmp_path / "journal"))
    server.start(port)
    stop = threading.Event()

    def ticker():
        while not stop.is_set():
            server._tick(0.016)
            time.sleep(0.005)
    th = threading.Thread(target=ticker, daemon=True)
    th.start()
    import os
    saved = os.path.dirname(server.TOKEN_PATH)
    ws.save(os="linux", transport="local", port=port, local_port=port, project_dir=os.path.dirname(saved))
    yield server
    stop.set()
    th.join(2)
    server.stop()


def test_health_and_a_plain_op(bridge):
    h = client.health()
    assert h["ok"] and h["bridge"] == 2 and h["jobs"] == {"queued": 0, "running": 0} and "engine" in h
    r = client.op("list", prefix="bridge")
    assert r["ok"] and r["state"] == "done" and isinstance(r["result"], (list, dict))


def test_a_long_exec_reports_progress_and_finishes(bridge):
    code = ("def job():\n    for i in range(5):\n        yield {'progress': i / 5, 'message': f'step {i}', 'wait': 0.01}\n"
            "    return 'done'\nresult = job()")
    seen = []
    jid = client.submit_exec(code)
    r = client.wait(jid, timeout=10, on_progress=lambda j: seen.append(j.get("message")))
    assert r["ok"] and r["result"] == "done" and r["state"] == "done"
    assert any(m and m.startswith("step") for m in seen)
    assert client.exec_code("result = 6 * 7")["result"] == 42


def test_wait_false_list_and_cancel(bridge):
    code = "def job():\n    while True:\n        yield 0.05\nresult = job()"
    started = client.exec_code(code, wait=False)
    jid = started["job"]
    deadline = time.time() + 5
    while client.job(jid)["state"] != "running" and time.time() < deadline:
        time.sleep(0.02)
    assert any(j["id"] == jid for j in client.jobs(state="running"))
    assert client.cancel(jid)["state"] in ("cancelling", "cancelled")
    r = client.wait(jid, timeout=5)
    assert r["state"] == "cancelled" and r["ok"] is False


def test_a_timeout_leaves_the_job_running_and_says_how_to_find_it(bridge):
    code = "def job():\n    while True:\n        yield 0.05\nresult = job()"
    r = client.exec_code(code, timeout=0.3)
    assert r["ok"] is False and "timeout after 0.3s" in r["error"] and "film-ue job" in r["error"]
    assert client.job(r["job"])["state"] == "running"
    client.cancel(r["job"])


def test_a_failed_op_carries_code_and_hint(bridge):
    r = client.op("bridge.nope")
    assert r["ok"] is False and r["code"] == "not_found" and "Traceback" in r["error"]


def test_an_unknown_job_is_gone_with_what_to_do(bridge):
    with pytest.raises(client.JobGone, match="editor restarted"):
        client.wait("feedfacecafe", timeout=2)


def test_a_dropped_connection_is_retried_for_reads(bridge, monkeypatch):
    real = client._http
    fails = {"n": 2}

    def flaky(*a, **k):
        if fails["n"]:
            fails["n"] -= 1
            raise urllib.error.URLError("connection reset")
        return real(*a, **k)
    monkeypatch.setattr(client, "_http", flaky)
    monkeypatch.setattr(client.time, "sleep", lambda s: None)
    assert client.health(retry_s=5)["ok"]
    fails["n"] = 1
    with pytest.raises(client.BridgeDown, match="no answer"):
        client.health(retry_s=0)


def test_no_editor_is_an_actionable_error(tmp_path, monkeypatch):
    monkeypatch.setattr(ws, "CONF_DIR", tmp_path)
    monkeypatch.setenv("FILM_UE_BOX", "none")
    ws.save(os="linux", transport="local", port=_free_port(), project_dir=str(tmp_path / "p"))
    with pytest.raises(client.BridgeDown, match="no bridge token"):
        client.health()
