"""film-ue: drive Unreal on the cloud workstation through the bridge (unreal/fmbridge).

    film-ue set --instance i-... [--region ap-south-1] [--project-dir C:\\UEProjects\\HostStudio]
    film-ue up | down | status | password       the workstation (password goes to the clipboard, never the screen)
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
"""
from __future__ import annotations

import argparse
import json
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
    pd = ws.conf()["project_dir"]
    files = [ROOT / "unreal" / "init_unreal.py"] + sorted((ROOT / "unreal" / "fmbridge").rglob("*.py"))
    via_bridge = _bridge_up()

    def put(path: str, data: bytes):
        if via_bridge:
            client.request("PUT", "/file?path=" + urllib.parse.quote(path), data, 120)
        else:
            ws.put_text(path, data)

    def get(path: str) -> str:
        if not via_bridge:
            return ws.ps(f"if (Test-Path '{path}') {{ Get-Content '{path}' -Raw }}").strip()
        try:
            return client.request("GET", "/file?path=" + urllib.parse.quote(path), timeout=10).decode()
        except (SystemExit, OSError):
            return ""  # between the old server and the new one

    for f in files:
        put(pd + "\\Content\\Python\\" + str(f.relative_to(ROOT / "unreal")).replace("/", "\\"), f.read_bytes())
    out = pd + r"\Saved\Bridge\out\install.json"
    put(out, b"")
    put(pd + r"\Saved\Bridge\in\install.py", BOOT.encode())
    for _ in range(60):  # until the editor has run it: a call sent sooner could still reach the old server
        res = get(out).strip()
        if res:
            r = json.loads(res)
            if not r.get("ok"):
                raise SystemExit("the bridge did not start:\n" + r.get("error", ""))
            client.token(refresh=True)
            return f"installed {len(files)} files (via {'bridge' if via_bridge else 'ssm'}); bridge {r.get('stdout', '').strip()}"
        time.sleep(0.5 if via_bridge else 0)
    raise SystemExit("the editor did not pick up the install (is it running? film-ue screen)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set")
    s.add_argument("--instance")
    s.add_argument("--region")
    s.add_argument("--project-dir")
    s.add_argument("--key")
    s.add_argument("--bucket")
    for n in ("up", "down", "status", "password", "install", "health", "tunnel", "close"):
        sub.add_parser(n)
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
    a = ap.parse_args()

    if a.cmd == "set":
        print(json.dumps(ws.save(**{k: v for k, v in (("instance", a.instance), ("region", a.region),
                                                       ("project_dir", a.project_dir), ("key", a.key), ("bucket", a.bucket)) if v}),
                         indent=1))
    elif a.cmd == "up":
        print(json.dumps(ws.start(), indent=1, default=str))
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
