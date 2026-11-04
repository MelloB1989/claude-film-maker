"""film-ue: drive Unreal on the cloud workstation through the bridge (unreal/fmbridge).

    film-ue [--box NAME] ...                    one of several workstations (settings in film-ue.NAME.json)
    film-ue set --instance i-... [--region ap-south-1] [--os windows|linux] [--project-dir DIR] [--bucket B]
                [--user ubuntu] [--local-port N] [--transport ssm|ssh --ssh ubuntu@HOST --ssh-key PATH]
                [--bridge tunnel|ssm]   ssm: each bridge call is one SSM command (curl on the box), no tunnel
    film-ue up | down | status | password       the workstation (password: Windows only, to the clipboard)
    film-ue provision --engine-s3 S3 --version 5.8.4 --project-src s3://...|win:UEProjects/NAME --project NAME
                      [--level /Game/...]
                                                a fresh Linux box: volume, driver, engine, project, editor unit
    film-ue editor start|stop|restart|status|enable|log [N]|mode default|offscreen|xvfb   the editor's unit (Linux)
    film-ue epic-login                          Linux: sign the editor in to Epic if it is not (prints a code for
                                                epicgames.com/activate); kept in S3 (set --epic-s3) for the next box
    film-ue desktop on|off                      Linux: a temporary desktop (VNC through SSM) for a one-off sign-in
    film-ue install                             copy unreal/fmbridge + init_unreal.py into the project, start the bridge
    film-ue health                              bridge up? engine, project, queue
    film-ue ops [prefix]                        the bridge's operations with their signatures
    film-ue op NAME [key=json ...]              call one: film-ue op level.move label=Key 'loc=[0,0,300]'
    film-ue exec FILE.py | -c CODE              run Python in the editor; `result = ...` is returned
    film-ue screen OUT.png                      the workstation's desktop
    film-ue gui click X Y [W H] | type TEXT | key ctrl+s | drag X1 Y1 X2 Y2 [W H] | wait MS
    film-ue push LOCAL REMOTE | pull REMOTE LOCAL | pull-dir REMOTE_DIR LOCAL_DIR (through S3, for renders)
    film-ue log [N]                             the editor log's tail
    film-ue tunnel | close                      open/close the SSM tunnel (opened on demand anyway)
    film-ue poc N [...]                         the Linux proof-of-concept checks (filmtools.unreal.poc)
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

from . import client, workstation as ws

ROOT = Path(__file__).resolve().parents[3]


def _print(res):
    if isinstance(res, dict) and "stdout" in res:
        if res.get("stdout"):
            sys.stdout.write(res["stdout"])
        if not res.get("ok"):
            sys.stderr.write(res.get("error", "") + "\n")
            raise SystemExit(1)
        if res.get("result") is not None:
            print(json.dumps(res["result"], indent=1))
    else:
        print(json.dumps(res, indent=1))


def _kv(pairs):
    out = {}
    for p in pairs:
        k, v = p.split("=", 1)
        try:
            out[k] = json.loads(v)
        except ValueError:
            out[k] = v
    return out


BOOT = """import sys
h = getattr(unreal, "_bridge_handle", None)  # the first scratch bridge, if it is still ticking
if h:
    unreal.unregister_slate_post_tick_callback(h)
    unreal._bridge_handle = None
old_server, old_inbox = sys.modules.get("fmbridge.server"), sys.modules.get("fmbridge.inbox")
if old_server:
    try:
        old_server.stop()
    except Exception as e:
        print("old server:", e)
if old_inbox and old_inbox._state.get("tick"):
    unreal.unregister_slate_post_tick_callback(old_inbox._state["tick"])
    old_inbox._state["tick"] = None
import gc, socketserver
for o in gc.get_objects():  # any orphaned bridge server still holding the port (an older install's)
    if isinstance(o, socketserver.BaseServer) and getattr(o, "server_address", ("", 0))[1] == 18765:
        try:
            o.shutdown()
            o.server_close()
        except Exception as e:
            print("orphan:", e)
for m in [k for k in sys.modules if k == "fmbridge" or k.startswith("fmbridge.")]:
    del sys.modules[m]
import fmbridge
print(fmbridge.start())
"""  # run by the editor's file inbox: retire the running bridge, load the new one


def _bridge_up() -> bool:
    try:
        return bool(client.health().get("ok"))
    except (SystemExit, OSError):
        return False


def install() -> str:
    """Copy the bridge into the project's Content/Python and (re)start it in the running editor through the file
    inbox: through the bridge itself when it is up (seconds), else over SSM (the first time; a minute)."""
    files = [ROOT / "unreal" / "init_unreal.py"] + sorted((ROOT / "unreal" / "fmbridge").rglob("*.py"))
    via_bridge = _bridge_up()
    if ws.linux() and not via_bridge:
        return _install_linux(files)

    def put(path: str, data: bytes):
        if via_bridge:
            client.request("PUT", "/file?path=" + urllib.parse.quote(path), data, 120)
        else:
            ws.put_text(path, data)

    def get(path: str) -> str:
        if not via_bridge:
            return ws.read_text(path).strip()
        try:
            return client.request("GET", "/file?path=" + urllib.parse.quote(path), timeout=10).decode()
        except (SystemExit, OSError):
            return ""  # between the old server and the new one

    for f in files:
        put(ws.project("Content", "Python", *f.relative_to(ROOT / "unreal").parts), f.read_bytes())
    out = ws.project("Saved", "Bridge", "out", "install.json")
    put(out, b"")
    put(ws.project("Saved", "Bridge", "in", "install.py"), BOOT.encode())
    for _ in range(60):  # until the editor has run it: a call sent sooner could still reach the old server
        res = get(out).strip()
        if res:
            r = json.loads(res)
            if not r.get("ok"):
                raise SystemExit("the bridge did not start:\n" + r.get("error", ""))
            if ws.conf().get("bridge") != "ssm":
                client.token(refresh=True)
            return f"installed {len(files)} files (via {'bridge' if via_bridge else 'ssm'}); bridge {r.get('stdout', '').strip()}"
        time.sleep(0.5 if via_bridge else 0)
    raise SystemExit("the editor did not pick up the install (is it running? film-ue screen)")


def _install_linux(files: list) -> str:
    """No bridge to talk to (the first install, or a broken one that cannot run the inbox): unpack the files over SSM in
    one command and restart the editor through systemd; init_unreal.py starts the new bridge."""
    import base64
    import io
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for f in files:
            t.add(f, arcname=str(f.relative_to(ROOT / "unreal")))
    b64 = base64.b64encode(buf.getvalue()).decode()
    if len(b64) > 90_000:
        raise SystemExit("the bridge is too big for one SSM command; install it over the bridge or S3")
    dest = shlex.quote(ws.project("Content", "Python"))
    ws.sh(f"mkdir -p {dest} && echo {b64} | base64 -d | tar -xz -C {dest}")
    ws.editor("restart")
    health = wait_bridge(3600)  # the first start on a box compiles every shader before the editor settles
    return f"installed {len(files)} files (via ssm + editor restart); bridge up on {health.get('engine')}"


def wait_bridge(seconds: int = 900) -> dict:
    """Until the editor (started by systemd at boot) answers /health; the first start compiles shaders for a while."""
    end = time.time() + seconds
    while time.time() < end:
        try:
            if ws.conf().get("bridge") != "ssm":  # on the box the token is read fresh each call
                client.token(refresh=True)  # a restarted editor writes a new token
            return client.health()
        except (SystemExit, OSError):
            time.sleep(10)
    raise SystemExit(f"the bridge did not answer in {seconds}s: film-ue editor status / film-ue editor log")


SETTINGS = ("instance", "region", "os", "project_dir", "key", "bucket", "user", "service", "local_port", "transport",
            "ssh", "ssh_key", "bridge", "epic_s3")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--box", help="which workstation (default: FILM_UE_BOX, else the one in film-ue.json)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set")
    for k in SETTINGS:
        s.add_argument("--" + k.replace("_", "-"), type=int if k == "local_port" else str,
                       choices={"os": ("windows", "linux"), "transport": ("ssm", "ssh"), "bridge": ("tunnel", "ssm")}.get(k))
    u = sub.add_parser("up")
    u.add_argument("--no-wait", action="store_true", help="Linux: do not wait for the bridge")
    for n in ("down", "status", "password", "install", "health", "tunnel", "close"):
        sub.add_parser(n)
    pv = sub.add_parser("provision")
    pv.add_argument("--engine-s3", required=True, help="the build's S3 root (holds tools/ue-restore.sh)")
    pv.add_argument("--version", required=True)
    pv.add_argument("--project-src", required=True,
                    help="s3://prefix (the .uproject at its top) or win:<path> on an attached Windows disk")
    pv.add_argument("--project", required=True, help="the project's name (NAME.uproject)")
    pv.add_argument("--level", default="", help="a level to open at start, e.g. /Game/Maps/Main")
    ed = sub.add_parser("editor")
    ed.add_argument("action", choices=("start", "stop", "restart", "status", "enable", "log", "mode"))
    ed.add_argument("arg", nargs="?", default="", help="log: lines (80); mode: default|offscreen|xvfb")
    sub.add_parser("desktop").add_argument("state", choices=("on", "off"))
    sub.add_parser("epic-login")
    sub.add_parser("poc", add_help=False)  # its own arguments: filmtools.unreal.poc
    sub.add_parser("ops").add_argument("prefix", nargs="?", default="")
    o = sub.add_parser("op")
    o.add_argument("name")
    o.add_argument("args", nargs="*")
    o.add_argument("--timeout", type=float, default=900)
    e = sub.add_parser("exec")
    e.add_argument("file", nargs="?")
    e.add_argument("-c", dest="code")
    e.add_argument("--timeout", type=float, default=900)
    sub.add_parser("screen").add_argument("out")
    g = sub.add_parser("gui")
    g.add_argument("action")
    g.add_argument("rest", nargs="*")
    for n in ("push", "pull", "pull-dir"):
        p = sub.add_parser(n)
        p.add_argument("src")
        p.add_argument("dst")
    sub.add_parser("log").add_argument("lines", nargs="?", type=int, default=80)
    a, extra = ap.parse_known_args()
    if extra and a.cmd != "poc":
        ap.error("unrecognized arguments: " + " ".join(extra))
    if a.box:
        os.environ["FILM_UE_BOX"] = a.box

    if a.cmd in ("provision", "editor", "desktop", "epic-login") and not ws.linux():
        raise SystemExit(f"film-ue {a.cmd} is for a Linux box: film-ue --box NAME set --os linux ...")

    if a.cmd == "set":
        print(json.dumps(ws.save(**{k: getattr(a, k) for k in SETTINGS if getattr(a, k) is not None}), indent=1))
    elif a.cmd == "up":
        print(json.dumps(ws.start(), indent=1, default=str))
        if ws.linux() and not a.no_wait:
            print(json.dumps(wait_bridge(), indent=1))
    elif a.cmd == "provision":
        from . import linuxbox
        print(json.dumps(linuxbox.provision(a.engine_s3, a.version, a.project_src, a.project, a.level), indent=1))
    elif a.cmd == "editor":
        if a.action == "log":
            print(ws.sh(f"journalctl -u {shlex.quote(ws.conf()['service'])} -n {int(a.arg or 80)} --no-pager", root=True))
        elif a.action == "mode":
            from . import linuxbox
            linuxbox.upload_kit()
            print(linuxbox.step("mode", a.arg or "default", timeout=300))
        else:
            print(ws.editor(a.action))
    elif a.cmd == "epic-login":
        from . import linuxbox
        print(linuxbox.epic_login())
    elif a.cmd == "desktop":
        from . import linuxbox
        print(linuxbox.desktop(a.state == "on"))
    elif a.cmd == "poc":
        from . import poc
        poc.main(extra)
    elif a.cmd == "down":
        client.close_tunnel()
        print(json.dumps(ws.stop(), indent=1, default=str))
    elif a.cmd == "status":
        print(json.dumps(ws.state(), indent=1, default=str))
    elif a.cmd == "password":
        subprocess.run("pbcopy", input=ws.password().encode(), check=True)
        print("the Administrator password is on the clipboard")
    elif a.cmd == "install":
        print(install())
    elif a.cmd == "health":
        print(json.dumps(client.health(), indent=1))
    elif a.cmd == "tunnel":
        print(f"tunnel on 127.0.0.1:{client.tunnel()}")
    elif a.cmd == "close":
        client.close_tunnel()
    elif a.cmd == "ops":
        _print(client.op("list", prefix=a.prefix))
    elif a.cmd == "op":
        _print(client.op(a.name, timeout=a.timeout, **_kv(a.args)))
    elif a.cmd == "exec":
        code = a.code if a.code is not None else Path(a.file).read_text()
        _print(client.exec_code(code, a.timeout))
    elif a.cmd == "screen":
        print(client.screen(a.out))
    elif a.cmd == "gui":
        r = [float(x) if x.replace(".", "", 1).lstrip("-").isdigit() else x for x in a.rest]
        act = {"click": lambda: {"click": r[:2], **({"ref": r[2:4]} if len(r) >= 4 else {})},
               "dclick": lambda: {"dclick": r[:2], **({"ref": r[2:4]} if len(r) >= 4 else {})},
               "rclick": lambda: {"rclick": r[:2], **({"ref": r[2:4]} if len(r) >= 4 else {})},
               "drag": lambda: {"drag": r[:4], **({"ref": r[4:6]} if len(r) >= 6 else {})},
               "scroll": lambda: {"scroll": r[:3], **({"ref": r[3:5]} if len(r) >= 5 else {})},
               "type": lambda: {"type": " ".join(a.rest)}, "key": lambda: {"key": a.rest[0]},
               "wait": lambda: {"wait": r[0]}}[a.action]()
        _print(client.gui([act]))
    elif a.cmd == "push":
        print(json.dumps(client.push(a.src, a.dst)))
    elif a.cmd == "pull":
        print(client.pull(a.src, a.dst))
    elif a.cmd == "pull-dir":
        print(ws.pull_dir(a.src, a.dst), "files")
    elif a.cmd == "log":
        print(json.loads(client.request("GET", f"/log?lines={a.lines}"))["log"])


if __name__ == "__main__":
    main()
