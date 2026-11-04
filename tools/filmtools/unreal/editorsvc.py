"""The editor as a service on its box: is it up, start/stop/restart it, its logs, its crashes.

    film-ue editor status            unit state, restarts, the bridge's health, the last crash, the watchdog's view
    film-ue editor start|stop|restart [--wait]     (Linux: systemd; the first start compiles shaders for a while)
    film-ue editor restart --once-args "-AUTH_TYPE=exchangecode -AUTH_PASSWORD=..."   extra arguments for one start
    film-ue editor log [N] [--journal]             the editor's own log, or the unit's journal
    film-ue editor crashes [N]                     crash reports: when, the exception, the fatal line

On Linux the editor runs under systemd (ue-editor.service, Restart=on-failure), and the box's watchdog restarts an
editor that stopped answering (ue_watchdog.py). On Windows it runs in the logged-in desktop session (DCV), so it can
be inspected and stopped from here but only started from that session."""
from __future__ import annotations

import json
import shlex
import time

from . import workstation as ws

ONCE_ARGS = ".film-ue/ue-args-once"  # in the editor user's home: read and deleted by ue-editor.sh at the next start


def _svc() -> str:
    return shlex.quote(ws.conf().get("service") or "ue-editor")


def unit() -> dict:
    """The systemd unit's state (Linux)."""
    props = "ActiveState,SubState,Result,NRestarts,MainPID,ExecMainStartTimestamp,ExecMainStatus"
    out = ws.sh(f"systemctl show {_svc()} -p {props}", 60, root=True)
    kv = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return {"active": kv.get("ActiveState"), "sub": kv.get("SubState"), "result": kv.get("Result"),
            "restarts": int(kv.get("NRestarts") or 0), "pid": int(kv.get("MainPID") or 0) or None,
            "since": kv.get("ExecMainStartTimestamp") or None, "exit_status": kv.get("ExecMainStatus")}


def _windows_process() -> dict:
    out = ws.ps("$p = Get-Process UnrealEditor -ErrorAction SilentlyContinue | Select-Object -First 1; "
                "if ($p) { @{pid=$p.Id; started=$p.StartTime.ToString('o'); rss_mb=[int]($p.WorkingSet64/1MB); "
                "responding=$p.Responding} | ConvertTo-Json -Compress } else { '{}' }", 60)
    try:
        p = json.loads(out.strip().splitlines()[-1]) if out.strip() else {}
    except ValueError:
        p = {}
    return {"active": "active" if p.get("pid") else "inactive", **p}


def _health():
    from . import client
    try:
        return client.health()
    except SystemExit as e:
        return {"ok": False, "error": str(e)}


def status() -> dict:
    """Everything about the editor in one answer: the process/unit, the bridge, the last crash, the watchdog."""
    out = {"os": ws.conf()["os"]}
    out["unit"] = unit() if ws.linux() else _windows_process()
    out["bridge"] = _health()
    c = crashes(1)
    out["last_crash"] = c[0] if c else None
    if ws.linux():
        data = ws.transport().get("/var/lib/film-ue/watchdog.json")
        if data:
            try:
                out["watchdog"] = json.loads(data).get("last_decision")
            except ValueError:
                pass
    return out


def control(action: str, wait: bool = False, wait_s: int = 3600, once_args: str = "") -> dict:
    """start, stop or restart the editor (Linux), optionally waiting for its bridge to answer. `once_args`: extra
    command-line arguments for this one start only (they are not kept: a secret in them is not reused)."""
    if action not in ("start", "stop", "restart"):
        raise SystemExit(f"editor {action}: start, stop or restart")
    if not ws.linux():
        if action == "stop":
            ws.ps("Stop-Process -Name UnrealEditor -ErrorAction SilentlyContinue", 120)
            return {"action": "stop", "unit": _windows_process()}
        raise SystemExit("on Windows the editor starts in the logged-in desktop session (DCV): start it there")
    if once_args:
        if action == "stop":
            raise SystemExit("--once-args only applies to a start or restart")
        ws.sh(f"umask 077 && mkdir -p \"$HOME/.film-ue\" && printf '%s\\n' {shlex.quote(once_args)} > \"$HOME/{ONCE_ARGS}\"",
              60)  # as the editor's user, mode 600
    ws.sh(f"systemctl reset-failed {_svc()} 2>/dev/null || true; systemctl {action} {_svc()}", 300, root=True)
    out = {"action": action, "unit": unit()}
    if wait and action != "stop":
        out["bridge"] = wait_bridge(wait_s)
    return out


def wait_bridge(seconds: int = 3600, poll_s: float = 10, sleep=time.sleep) -> dict:
    """Until the editor's bridge answers /health (the first start on a box compiles every shader first). Fails fast
    with the reason when the unit itself died."""
    from . import client
    end = time.time() + seconds
    last = ""
    while time.time() < end:
        try:
            if ws.conf().get("bridge") != "ssm" and ws.conf().get("transport") != "local":
                client.token(refresh=True)  # a restarted editor writes a new token
            return client.health()
        except SystemExit as e:
            last = str(e)
        if ws.linux():
            u = unit()
            if u["active"] == "failed":
                c = crashes(1)
                raise SystemExit(f"the editor's unit failed ({u['result']}, {u['restarts']} restarts)"
                                 + (f"; last crash: {c[0].get('exception') or c[0].get('fatal')}" if c else "")
                                 + ": film-ue editor log / film-ue editor crashes")
        sleep(poll_s)
    raise SystemExit(f"the bridge did not answer in {seconds}s ({last}): film-ue editor status / film-ue editor log")


def log(lines: int = 200, journal: bool = False) -> str:
    """The editor's own log (the newest Saved/Logs/*.log), or the unit's journal (Linux)."""
    n = int(lines)
    if journal:
        if not ws.linux():
            raise SystemExit("no journal on Windows: film-ue editor log (the editor's own log)")
        return ws.sh(f"journalctl -u {_svc()} -n {n} --no-pager", 120, root=True)
    logs = ws.project("Saved", "Logs")
    if ws.linux():
        return ws.sh(f"f=$(ls -t {shlex.quote(logs)}/*.log 2>/dev/null | grep -v backup | head -1); "
                     f"[ -n \"$f\" ] && tail -n {n} \"$f\" || echo 'no editor log yet'", 120)
    return ws.ps(f"$f = Get-ChildItem '{logs}\\*.log' | Where-Object {{ $_.Name -notmatch 'backup' }} | "
                 f"Sort-Object LastWriteTime -Descending | Select-Object -First 1; "
                 f"if ($f) {{ Get-Content $f.FullName -Tail {n} }} else {{ 'no editor log yet' }}", 120)


CRASH_SCRIPT = r'''
d="$1"; n="$2"
[ -d "$d" ] || exit 0
for c in $(ls -td "$d"/crashinfo-* 2>/dev/null | head -n "$n"); do
  t=$(stat -c %Y "$c")
  ex=$(grep -h -m1 -o 'Exception was "[^"]*"' "$c"/Diagnostics.txt 2>/dev/null | head -1)
  fatal=$(grep -h -m1 -E 'Fatal error|Assertion failed|appError called' "$c"/*.log 2>/dev/null | head -1 | cut -c1-300)
  oom=$(grep -h -m1 -E 'Out Of Memory|OutOfMemory|out of video memory' "$c"/*.log 2>/dev/null | head -1 | cut -c1-200)
  printf '%s\t%s\t%s\t%s\t%s\n' "$(basename "$c")" "$t" "$ex" "$fatal" "$oom"
done
'''


def crashes(limit: int = 5) -> list[dict]:
    """The newest crash reports (Saved/Crashes): when, the exception, the first fatal line, an out-of-memory line."""
    d = ws.project("Saved", "Crashes")
    if ws.linux():
        out = ws.sh(f"bash -s -- {shlex.quote(d)} {int(limit)} <<'FMEOF'\n{CRASH_SCRIPT}\nFMEOF", 120)
        rows = []
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) < 5:
                continue
            name, t, ex, fatal, oom = parts[:5]
            rows.append({"report": name, "time": int(t) if t.isdigit() else None,
                         "exception": ex.replace("Exception was ", "").strip('"') or None,
                         "fatal": fatal or None, "out_of_memory": oom or None})
        return rows
    out = ws.ps(f"Get-ChildItem '{d}' -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTime "
                f"-Descending | Select-Object -First {int(limit)} | ForEach-Object {{ $x = Select-String -Path "
                f"(Join-Path $_.FullName '*.log') -Pattern 'Fatal error|Assertion failed' -List | Select-Object "
                f"-First 1; @{{report=$_.Name; time=[int][double]::Parse((Get-Date $_.LastWriteTime -UFormat %s)); "
                f"fatal=$(if ($x) {{ $x.Line }} else {{ $null }})}} }} | ConvertTo-Json -Compress", 120)
    try:
        data = json.loads(out) if out.strip() else []
    except ValueError:
        return []
    return data if isinstance(data, list) else [data]
