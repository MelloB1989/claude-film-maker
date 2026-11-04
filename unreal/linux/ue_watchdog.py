#!/usr/bin/env python3
"""The GPU box's own watchdog, run every minute by ue-watchdog.timer (as root). It keeps a temporary box from costing
money when nobody is using it, and an editor from staying stuck:

  ttl      past its time-to-live (box up --ttl, box extend): power off
  idle     nothing has happened for `idle_min` minutes: power off. Something happens when the bridge was called
           recently or has jobs, the GPU is busy, the CPU is busy (a shader compile, a restore), someone is logged
           in (ssh), or something touched /run/film-ue/keepalive (film-ue box keepalive). An open tunnel alone does
           not count
  stall    the editor answered once and then stopped answering (or its game thread stopped ticking) for
           `stall_min` minutes: restart it; more than `max_restarts` restarts in an hour: power off (a crash loop)
  dead     the editor's unit failed (systemd gave up restarting it): start it again, counted like a stall restart

On EC2 the box is launched with "shutdown behaviour: terminate" (film-ue box up), so power off ends it for good;
before that the editor is stopped cleanly so its unit saves the Epic sign-in to S3 (ue-epic save).

Config: /etc/film-ue/watchdog.json {"ttl_until": epoch|null, "idle_min": 20, "stall_min": 15, "max_restarts": 3,
"grace_min": 30, "service": "ue-editor", "port": 18765, "token": path, "dry_run": false}. State and the last decision:
/var/lib/film-ue/watchdog.json (film-ue box status shows it). Everything decided is logged to the journal.

`decide()` is a pure function of the config, the state and what was measured, so it is unit-tested
(tools/tests/test_ue_platform_watchdog.py); this file runs on the box's own python3 (3.10 on Ubuntu 22.04)."""
import json
import os
import subprocess
import sys
import time
import urllib.request

CONF = "/etc/film-ue/watchdog.json"
STATE = "/var/lib/film-ue/watchdog.json"
KEEPALIVE = "/run/film-ue/keepalive"
DEFAULTS = {"ttl_until": None, "idle_min": 20, "stall_min": 15, "max_restarts": 3, "grace_min": 30,
            "service": "ue-editor", "port": 18765, "token": "", "dry_run": False,
            "gpu_busy_pct": 15, "load_busy": 2.0}


# ------------------------------------------------------------------------------------------------- deciding
def decide(cfg, state, m):
    """What to do now. cfg: the config. state: what the last runs remembered. m: what was just measured:
    {"now", "uptime_s", "health": dict|None, "gpu_pct": int|None, "load1": float, "sessions": int,
     "keepalive_age_s": float|None, "service": "active"|"failed"|"inactive"|..., "service_since": epoch|None}.
    Returns (actions, new_state, reasons): actions are ("poweroff", why) | ("restart", why) | ("start", why)."""
    now = m["now"]
    st = dict(state)
    st.setdefault("last_active", now)
    st.setdefault("restarts", [])
    st["restarts"] = [t for t in st["restarts"] if now - t < 3600]
    actions, reasons = [], []
    h = m.get("health")

    # time to live
    ttl = cfg.get("ttl_until")
    if ttl and now >= ttl:
        return [("poweroff", f"ttl: the box's time ran out {int(now - ttl)} s ago")], st, ["ttl"]

    # activity
    busy = []
    if m.get("uptime_s", 1e9) < cfg["grace_min"] * 60:
        busy.append("booting")
    if h:
        jobs = h.get("jobs") or {}
        if jobs.get("running") or jobs.get("queued"):
            busy.append("bridge jobs")
        if h.get("idle_s") is not None and h["idle_s"] < cfg["idle_min"] * 60:
            busy.append("bridge calls")
    if m.get("gpu_pct") is not None and m["gpu_pct"] >= cfg["gpu_busy_pct"]:
        busy.append(f"gpu {m['gpu_pct']}%")
    if m.get("load1", 0) >= cfg["load_busy"]:
        busy.append(f"load {m['load1']:.1f}")
    if m.get("sessions"):
        busy.append(f"{m['sessions']} sessions")
    if m.get("keepalive_age_s") is not None and m["keepalive_age_s"] < cfg["idle_min"] * 60:
        busy.append("keepalive")
    if busy:
        st["last_active"] = now
    reasons += busy
    idle_s = now - st["last_active"]
    st["idle_s"] = int(idle_s)
    if idle_s >= cfg["idle_min"] * 60:
        return [("poweroff", f"idle: nothing for {int(idle_s // 60)} min")], st, reasons + ["idle"]

    # the editor: stalled or dead
    svc, since = m.get("service"), m.get("service_since")
    if since and st.get("service_since") != since:  # a new start of the unit: it must answer once before a stall counts
        st.update(service_since=since, answered=False, stall_since=None)
    alive = bool(h) and (h.get("last_tick_s") is None or h["last_tick_s"] < cfg["stall_min"] * 60)
    if svc == "active":
        if alive:
            st.update(answered=True, stall_since=None)
        elif st.get("answered"):
            st["stall_since"] = st.get("stall_since") or now
            if now - st["stall_since"] >= cfg["stall_min"] * 60:
                if len(st["restarts"]) >= cfg["max_restarts"]:
                    return [("poweroff", f"crash loop: {len(st['restarts'])} editor restarts in the last hour")], st, \
                        reasons + ["stall-loop"]
                stalled_min = int((now - st["stall_since"]) // 60)
                st["restarts"].append(now)
                st.update(stall_since=None, answered=False)
                actions.append(("restart", f"stall: the editor has not answered (or ticked) for {stalled_min} min"))
    elif svc == "failed":
        if len(st["restarts"]) >= cfg["max_restarts"]:
            return [("poweroff", f"crash loop: the editor keeps failing ({len(st['restarts'])} restarts in an hour)")], \
                st, reasons + ["dead-loop"]
        st["restarts"].append(now)
        actions.append(("start", "dead: systemd gave up on the editor"))
    return actions, st, reasons


# ----------------------------------------------------------------------------------------------- measuring
def _run(cmd, timeout=20):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def measure(cfg):
    now = time.time()
    m = {"now": now}
    try:
        with open("/proc/uptime") as f:
            m["uptime_s"] = float(f.read().split()[0])
    except OSError:
        m["uptime_s"] = 1e9
    m["health"] = None
    try:
        tok = open(cfg["token"]).read().strip() if cfg.get("token") else ""
        req = urllib.request.Request(f"http://127.0.0.1:{cfg['port']}/health", headers={"X-FM-Token": tok})
        with urllib.request.urlopen(req, timeout=10) as r:
            m["health"] = json.loads(r.read())
    except Exception:
        pass
    out = _run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"])
    m["gpu_pct"] = max((int(x) for x in out.split() if x.strip().isdigit()), default=None)
    m["load1"] = os.getloadavg()[0]
    # logins only (ssh, a console): an SSM port-forward is also an ssm-session-worker, and the bridge's own tunnel
    # left open must not keep an idle box alive (its calls count through the bridge's idle_s instead)
    m["sessions"] = len([x for x in _run(["who"]).splitlines() if x.strip()])
    try:
        m["keepalive_age_s"] = now - os.path.getmtime(KEEPALIVE)
    except OSError:
        m["keepalive_age_s"] = None
    m["service"] = _run(["systemctl", "is-active", cfg["service"]]).strip() or "unknown"
    since = _run(["systemctl", "show", "-p", "ExecMainStartTimestampMonotonic", "--value", cfg["service"]]).strip()
    m["service_since"] = int(since) if since.isdigit() and int(since) > 0 else None
    return m


# ------------------------------------------------------------------------------------------------- acting
def act(cfg, actions):
    for kind, why in actions:
        print(f"film-ue watchdog: {kind}: {why}", flush=True)
        if cfg.get("dry_run"):
            continue
        if kind == "poweroff":
            _run(["systemctl", "stop", cfg["service"]], timeout=180)  # its ExecStopPost saves the Epic sign-in
            _run(["systemctl", "poweroff"])
        elif kind == "restart":
            _run(["systemctl", "restart", cfg["service"]], timeout=180)
        elif kind == "start":
            _run(["systemctl", "reset-failed", cfg["service"]])
            _run(["systemctl", "start", cfg["service"]], timeout=180)


def _load(path, default):
    try:
        with open(path) as f:
            return {**default, **json.load(f)}
    except (OSError, ValueError):
        return dict(default)


def main(argv=None):
    cfg = _load(CONF, DEFAULTS)
    state = _load(STATE, {})
    m = measure(cfg)
    actions, state, reasons = decide(cfg, state, m)
    state["last_run"] = m["now"]
    state["last_decision"] = {"actions": actions, "busy": reasons, "ttl_left_s":
                              int(cfg["ttl_until"] - m["now"]) if cfg.get("ttl_until") else None,
                              "editor": m["service"], "gpu_pct": m["gpu_pct"], "load1": round(m["load1"], 2)}
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE)
    act(cfg, actions)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
