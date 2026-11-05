"""film-ue first-run: the checklist for the first morning on a new GPU box, resumable. Each step checks one thing,
fixes it when it safely can (start the editor, install the bridge, wait out the shader compile), and on a failure
stops and prints the exact command to run next. Progress lives in the box's profile (`first_run`), so running it
again continues where it stopped.

    film-ue [--box NAME] first-run [--restart] [--from STEP] [--epic] [--voice demo_line.wav] [--json]

Steps, in order:
  settings      the profile has what a box needs (os, instance or ssh, project dir)
  reach         a command runs on the box
  editor        the editor service is up (Linux: started if it is not; the project made to target Vulkan SM6)
  bridge        the bridge answers; installed (or updated to this checkout's protocol) if not
  shaders       no shader compiling (waits; the first open of a project takes ~20 min)
  doctor        film-ue doctor passes (the editor's own check: plugins, RHI, GPU, disk, broken ops)
  epic          a saved Epic sign-in (MetaHuman cloud services); --epic runs the sign-in (prints a code)
  selftest      film-ue selftest platform dx passes
  demo0         the demo's stage 0: the voice line on the box (--voice FILE), the scratch folders ready
"""
from __future__ import annotations

import json
import time

from . import workstation as ws

STEPS = ("settings", "reach", "editor", "bridge", "shaders", "doctor", "epic", "selftest", "demo0")
DEMO_VOICE = "/srv/film/demo/demo_line.wav"


class Stop(Exception):
    """A step that could not pass: what is wrong and the exact next command."""

    def __init__(self, message: str, next_cmd: str, needs_you: bool = False):
        super().__init__(message)
        self.message, self.next_cmd, self.needs_you = message, next_cmd, needs_you


def _box_flag() -> str:
    b = ws.box()
    return f"--box {b} " if b else ""


def _cmd(rest: str) -> str:
    return f"film-ue {_box_flag()}{rest}"


# ---------------------------------------------------------------------------------------------------------- steps
def step_settings(opts, log) -> str:
    c = ws.conf()
    missing = []
    if c.get("transport") in (None, "", "ssm") and not c.get("instance"):
        missing.append("instance")
    if c.get("transport") == "ssh" and not c.get("ssh"):
        missing.append("ssh")
    if not c.get("project_dir"):
        missing.append("project_dir")
    if missing:
        hint = "film-ue box up NAME --like linux" if "instance" in missing else \
            _cmd("set " + " ".join(f"--{m.replace('_', '-')} ..." for m in missing))
        raise Stop(f"the profile lacks {', '.join(missing)}", hint)
    return f"{c.get('os')} box over {c.get('transport') or 'ssm'}, project {c['project_dir']}"


def step_reach(opts, log) -> str:
    try:
        root = ws.linux() and ws.conf().get("transport") != "local"  # as root on a remote box (what provision needs)
        out = ws.transport().run("echo film-ue-ok" if ws.linux() else "'film-ue-ok'", 120, root=root)
    except SystemExit as e:
        raise Stop(f"no command reaches the box: {e}",
                   _cmd("status") + "   (is it running? film-ue box ls / film-ue up)")
    if "film-ue-ok" not in out:
        raise Stop(f"the box answered oddly: {out[-200:]!r}", _cmd("sh 'uptime'"))
    return "commands run on the box"


def step_editor(opts, log) -> str:
    from . import editorsvc
    if not ws.linux():
        u = editorsvc._windows_process()
        if u.get("active") != "active":
            raise Stop("the editor is not running in the desktop session", "log in over DCV and start the editor",
                       needs_you=True)
        return f"editor pid {u.get('pid')}"
    from . import linuxbox
    linuxbox.upload_kit()
    rhi = linuxbox.step("rhi", ws.conf()["project_dir"], timeout=120)
    u = editorsvc.unit()
    if "rhi=set" in rhi and u["active"] in ("active", "activating"):
        log("the project did not target Vulkan SM6 (now set in Config/DefaultEngine.ini): restarting the editor")
        editorsvc.control("restart")
        u = editorsvc.unit()
    if u["active"] != "active":
        log(f"the editor's unit is {u['active']} ({u['result']}): starting it")
        editorsvc.control("start")
        u = editorsvc.unit()
        if u["active"] not in ("active", "activating"):
            c = editorsvc.crashes(1)
            raise Stop(f"the editor's unit did not start ({u['active']}, {u['result']})"
                       + (f"; last crash: {c[0].get('exception') or c[0].get('fatal')}" if c else ""),
                       _cmd("editor log 200 --journal"))
    return f"unit {u['active']}, {u['restarts']} restarts"


def step_bridge(opts, log) -> str:
    from . import client
    try:
        h = client.health(retry_s=10)
    except SystemExit:
        h = None
    if not h or int(h.get("bridge") or 1) < 2:
        log("the bridge is " + ("not answering" if not h else f"protocol {h.get('bridge') or 1}") + ": installing it")
        from .cli import install
        try:
            log(install())
        except SystemExit as e:
            raise Stop(f"install failed: {e}", _cmd("editor log 200"))
        from . import editorsvc
        h = editorsvc.wait_bridge(3600) if ws.linux() else client.health(retry_s=120)
    return f"bridge {h.get('bridge')} on {h.get('engine')}, {h.get('platform')}"


def step_shaders(opts, log) -> str:
    from . import client
    t0 = time.time()
    r = client.op("editor.wait_compile", timeout=3700, timeout_s=3600, settle_s=float(opts.get("settle_s", 6)))
    if not r.get("ok"):
        raise Stop(f"shaders still compiling or the wait failed: {r.get('message') or r.get('error', '')[-300:]}",
                   _cmd("first-run") + "   (it waits again; ~20 min on a first open)")
    return f"compiled (waited {round(time.time() - t0)} s, up to {r['result'].get('workers_max')} workers)"


def step_doctor(opts, log) -> str:
    from . import cli_doctor
    d = cli_doctor.run()
    fails = [i for i in d.get("issues", []) if i.get("severity") == "fail"]
    if fails:
        first = fails[0]
        raise Stop("doctor: " + "; ".join(i.get("message", i.get("code", "")) for i in fails)[:600],
                   first.get("fix") or _cmd("doctor"))
    warns = [i for i in d.get("issues", []) if i.get("severity") == "warn"]
    return "doctor passes" + (f" ({len(warns)} warnings: film-ue doctor)" if warns else "")


def step_epic(opts, log) -> str:
    if not ws.linux():
        return "skipped: the Windows editor signs in on its desktop"
    from . import linuxbox
    linuxbox.upload_kit()
    st = linuxbox.step("epic", "status", timeout=120)
    if "signed_in=yes" in st:
        return "a saved Epic sign-in is on the box"
    if opts.get("epic"):
        log(linuxbox.epic_login(log=log))
        return "signed in"
    raise Stop("no Epic sign-in on the box: the MetaHuman cloud services (rig, textures) need one",
               _cmd("epic-login") + "   (prints a code for epicgames.com/activate; or rerun first-run with --epic)",
               needs_you=True)


def step_selftest(opts, log) -> str:
    from . import selftest
    from .sdk import Unreal
    import tempfile
    from pathlib import Path
    out = Path(tempfile.mkdtemp(prefix="film-ue-first-run-"))
    summary = selftest.run_all(Unreal(), list(opts.get("selftest_areas") or ["platform", "dx"]), out, log=log)
    if not summary.get("ok"):
        bad = [k for k, a in (summary.get("areas") or {}).items() if not a.get("ok")]
        first = (summary.get("failures") or [{}])[0]
        raise Stop(f"selftest: {', '.join(bad) or '?'} failed; first: {first.get('area')}: {first.get('name')} "
                   f"{str(first.get('detail') or '')[:200]} (report: {out}/summary.md)",
                   "film-ue selftest platform dx   (then read the report's summary.md)")
    return f"selftest platform + dx pass (report: {out})"


def step_demo0(opts, log) -> str:
    from . import client
    voice = opts.get("voice")
    if voice:
        client.push(voice, DEMO_VOICE)
        return f"voice line on the box at {DEMO_VOICE}"
    have = ws.transport().exists(DEMO_VOICE) if ws.linux() else False
    if not have:
        raise Stop("the demo's voice line is not on the box", _cmd("first-run --voice path/to/demo_line.wav") +
                   f"   (or film-ue push FILE {DEMO_VOICE})", needs_you=True)
    return "the demo's stage 0 is done: next, film-ue apply ../examples/unreal/demo/10-character.yaml (from tools/)"


RUN = {"settings": step_settings, "reach": step_reach, "editor": step_editor, "bridge": step_bridge,
       "shaders": step_shaders, "doctor": step_doctor, "epic": step_epic, "selftest": step_selftest,
       "demo0": step_demo0}


# ---------------------------------------------------------------------------------------------------------- driving
def _progress() -> dict:
    return dict(ws.conf().get("first_run") or {})


def _save(p: dict) -> None:
    ws.save(first_run=p)


def run(restart: bool = False, start: str = "", opts: dict | None = None, log=print) -> dict:
    """Run the checklist from the first step not yet done (or from `start`, or all with `restart`). Returns
    {"ok", "done": [...], "steps": {name: {"ok", "detail"|"error", "next"}}, "next"}."""
    opts = dict(opts or {})
    if start and start not in STEPS:
        raise SystemExit(f"no step {start!r}: {', '.join(STEPS)}")
    p = {} if restart else _progress()
    done = [s for s in p.get("done", []) if s in STEPS]
    if start:
        done = [s for s in done if STEPS.index(s) < STEPS.index(start)]
    report = {"ok": False, "done": list(done), "steps": {}, "next": None}
    for name in STEPS:
        if name in done and name not in ("reach",):  # a reach check is cheap: always re-run it
            report["steps"][name] = {"ok": True, "detail": "done before"}
            continue
        log(f"[{STEPS.index(name) + 1}/{len(STEPS)}] {name} ...")
        t0 = time.time()
        try:
            detail = RUN[name](opts, log)
        except Stop as s:
            report["steps"][name] = {"ok": False, "error": s.message, "next": s.next_cmd, "needs_you": s.needs_you,
                                     "s": round(time.time() - t0, 1)}
            report["next"] = s.next_cmd
            _save({"done": report["done"], "at": time.time(), "stopped_at": name, "error": s.message,
                   "next": s.next_cmd})
            log(f"    STOP: {s.message}\n    next: {s.next_cmd}")
            return report
        report["steps"][name] = {"ok": True, "detail": detail, "s": round(time.time() - t0, 1)}
        if name not in report["done"]:
            report["done"].append(name)
        _save({"done": report["done"], "at": time.time()})
        log(f"    ok: {detail}")
    report["ok"] = True
    report["next"] = "film-ue apply ../examples/unreal/demo/10-character.yaml   (from tools/: the demo's stage 1)"
    log("first-run complete. next: " + report["next"])
    return report


def status() -> dict:
    p = _progress()
    return {"steps": list(STEPS), "done": p.get("done", []), "stopped_at": p.get("stopped_at"),
            "error": p.get("error"), "next": p.get("next"), "at": p.get("at")}


def main_args(a, log=print) -> int:
    if getattr(a, "status", False):
        print(json.dumps(status(), indent=1))
        return 0
    r = run(restart=a.restart, start=a.from_step, opts={"epic": a.epic, "voice": a.voice}, log=log)
    if a.json:
        print(json.dumps(r, indent=1, default=str))
    return 0 if r["ok"] else 1
