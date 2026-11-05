"""film-ue's platform commands (WP1): boxes, profiles, the editor service, sync, the Epic sign-in, provisioning, and a
shell on the box. cli.py finds this module (cli_<area>.py), calls register(sub) and then dispatch(a).

    film-ue box up NAME [--type g6.4xlarge] [--ttl 4h] [--idle 20m] [--stall 15m] [--spot] [--like PROFILE] [--ami ID]
    film-ue box ls | status NAME | extend NAME --ttl 2h | keepalive NAME | down NAME [--forget]
    film-ue box image NAME [--label L] [--wait] | images | image-rm AMI         (box up --ami latest uses the newest)
    film-ue profile ls | use NAME | show [NAME] | copy SRC DST | rm NAME
    film-ue editor status | start | stop | restart [--wait] [--once-args="..."] | log [N] [--journal] | crashes [N]
                   | mode default|offscreen|xvfb | enable      (editor_cli: hand-written verbs beside the generated
                                                                 op commands film-ue editor describe|cvar|...)
    film-ue sync project up|down [--delete] [--allow-dirty] [--stop-editor] | ddc save|restore [--version V]
                 | epic save|restore|status | engine restore --engine-s3 S3 --version V | status       [--dry-run]
    film-ue epic-login [--fab] [--exchange-code-cmd CMD]
    film-ue provision --engine-s3 S3 --version 5.8.4 --project-src s3://...|win:PATH --project NAME [--level L]
                      [--epic-s3 S3] [--watchdog-ttl 4h --idle 20m --stall 15m]
    film-ue desktop on|off
    film-ue first-run [--restart] [--from STEP] [--epic] [--voice FILE] [--status]   the new-box checklist (resumable)
    film-ue sh 'COMMAND' [--root] [--timeout S]      run it in the box's own shell (bash or PowerShell)

Every command prints JSON (or plain text for logs). A command another module already registered is left to it."""
from __future__ import annotations

import json
import sys

from . import workstation as ws

_MINE: set = set()


def _add(sub, name: str, **kw):
    if name in sub.choices:  # cli.py (or another hook) still has it: theirs stays, mine is skipped
        return None
    _MINE.add(name)
    return sub.add_parser(name, **kw)


def register(sub) -> None:
    p = _add(sub, "box", help="temporary GPU boxes: up, ls, status, extend, keepalive, down")
    if p:
        bs = p.add_subparsers(dest="box_cmd", required=True)
        u = bs.add_parser("up")
        u.add_argument("name")
        u.add_argument("--type", dest="instance_type", default="g6.4xlarge")
        u.add_argument("--ttl", default="4h")
        u.add_argument("--idle", default="20m")
        u.add_argument("--stall", default="15m")
        u.add_argument("--spot", action="store_true")
        u.add_argument("--like", default="", help="copy settings (project dir, bucket, epic_s3) from this profile")
        u.add_argument("--ami", default="")
        u.add_argument("--subnet", default="")
        u.add_argument("--security-group", default="")
        u.add_argument("--iam-profile", default="ue-workstation")
        u.add_argument("--volume-gb", type=int, default=300)
        u.add_argument("--key-name", default="")
        u.add_argument("--region", default="")
        u.add_argument("--no-wait", action="store_true")
        u.add_argument("--save-ddc-on-exit", action="store_true", help="the watchdog saves the DDC to S3 before an "
                                                                         "idle or TTL power-off (needs --like)")
        bs.add_parser("ls").add_argument("--region", default="")
        for n in ("status", "keepalive"):
            bs.add_parser(n).add_argument("name")
        e = bs.add_parser("extend")
        e.add_argument("name")
        e.add_argument("--ttl", required=True)
        d = bs.add_parser("down")
        d.add_argument("name")
        d.add_argument("--forget", action="store_true")
        im = bs.add_parser("image")
        im.add_argument("name")
        im.add_argument("--label", default="")
        im.add_argument("--wait", action="store_true")
        bs.add_parser("images").add_argument("--region", default="")
        bs.add_parser("image-rm").add_argument("ami")
    p = _add(sub, "profile", help="box profiles: ls, use, show, copy, rm")
    if p:
        ps = p.add_subparsers(dest="profile_cmd", required=True)
        ps.add_parser("ls")
        ps.add_parser("use").add_argument("name")
        ps.add_parser("show").add_argument("name", nargs="?")
        c = ps.add_parser("copy")
        c.add_argument("src")
        c.add_argument("dst")
        ps.add_parser("rm").add_argument("name")
    p = _add(sub, "sync", help="project / DDC / Epic sign-in / engine between the box and S3")
    if p:
        p.add_argument("what", choices=("project", "ddc", "epic", "engine", "status"))
        p.add_argument("direction", nargs="?", default="", help="project: up|down; ddc: save|restore; epic: "
                                                                 "save|restore|status; engine: restore")
        p.add_argument("--delete", action="store_true")
        p.add_argument("--allow-dirty", action="store_true")
        p.add_argument("--stop-editor", action="store_true")
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--version", default="")
        p.add_argument("--engine-s3", default="")
    p = _add(sub, "epic-login", help="sign the box's editor in to Epic (device code or exchange code)")
    if p:
        p.add_argument("--fab", action="store_true", help="Fab's own sign-in")
        p.add_argument("--exchange-code-cmd", default="", help="a command that prints a fresh exchange code")
    p = _add(sub, "provision", help="set up a fresh Linux box")
    if p:
        p.add_argument("--engine-s3", required=True, help="the build's S3 root (holds tools/ue-restore.sh)")
        p.add_argument("--version", required=True)
        p.add_argument("--project-src", required=True, help="s3://prefix or win:<path> on an attached Windows disk")
        p.add_argument("--project", required=True, help="the project's name (NAME.uproject)")
        p.add_argument("--level", default="")
        p.add_argument("--epic-s3", default="")
        p.add_argument("--watchdog-ttl", default="", help="also install the watchdog: time to live (e.g. 4h)")
        p.add_argument("--idle", default="20m")
        p.add_argument("--stall", default="15m")
    p = _add(sub, "desktop", help="a temporary desktop (VNC through SSM) for a one-off sign-in")
    if p:
        p.add_argument("state", choices=("on", "off"))
    p = _add(sub, "first-run", help="the resumable checklist for a new box (prints the next command on a failure)")
    if p:
        p.add_argument("--restart", action="store_true", help="from the first step again")
        p.add_argument("--from", dest="from_step", default="", help="from this step (settings, reach, editor, bridge, "
                                                                     "shaders, doctor, epic, selftest, demo0)")
        p.add_argument("--epic", action="store_true", help="run the Epic sign-in if there is none (prints a code)")
        p.add_argument("--voice", default="", help="the demo's voice line (a WAV) to put on the box")
        p.add_argument("--status", action="store_true", help="where it stopped last time")
        p.add_argument("--json", action="store_true")
    p = _add(sub, "sh", help="run a command in the box's own shell")
    if p:
        p.add_argument("command")
        p.add_argument("--root", action="store_true")
        p.add_argument("--timeout", type=int, default=600)


def _out(v) -> None:
    if isinstance(v, str):
        print(v)
    else:
        print(json.dumps(v, indent=1, default=str))


def _linux_only(cmd: str) -> None:
    if not ws.linux():
        raise SystemExit(f"film-ue {cmd} is for a Linux box: film-ue --box NAME set --os linux ...")


def dispatch(a) -> bool:
    cmd = getattr(a, "cmd", None)
    if cmd not in _MINE:
        return False
    if cmd == "box":
        from . import boxes
        b = a.box_cmd
        if b == "up":
            _out(boxes.up(a.name, instance_type=a.instance_type, ttl=a.ttl, idle=a.idle, stall=a.stall, spot=a.spot,
                          ami=a.ami, subnet=a.subnet, security_group=a.security_group, iam_profile=a.iam_profile,
                          volume_gb=a.volume_gb, key_name=a.key_name, like=a.like, region=a.region,
                          wait=not a.no_wait, save_ddc_on_exit=a.save_ddc_on_exit,
                          log=lambda m: print(m, file=sys.stderr)))
        elif b == "ls":
            _out(boxes.ls(a.region or None))
        elif b == "status":
            _out(boxes.status(a.name))
        elif b == "extend":
            _out(boxes.extend(a.name, a.ttl))
        elif b == "keepalive":
            _out(boxes.keepalive(a.name))
        elif b == "down":
            _out(boxes.down(a.name, forget=a.forget, log=lambda m: print(m, file=sys.stderr)))
        elif b == "image":
            _out(boxes.image(a.name, label=a.label, wait=a.wait, log=lambda m: print(m, file=sys.stderr)))
        elif b == "images":
            _out(boxes.images(a.region or None))
        elif b == "image-rm":
            _out(boxes.image_rm(a.ami))
    elif cmd == "profile":
        from . import profiles
        p = a.profile_cmd
        _out({"ls": lambda: profiles.listing(), "use": lambda: profiles.use(a.name),
              "show": lambda: profiles.show(a.name), "copy": lambda: profiles.copy(a.src, a.dst),
              "rm": lambda: profiles.remove(a.name)}[p]())
    elif cmd == "sync":
        from . import sync
        w, d = a.what, a.direction
        if w == "project":
            _out(sync.project(d, delete=a.delete, allow_dirty=a.allow_dirty, stop_editor=a.stop_editor,
                              dry_run=a.dry_run))
        elif w == "ddc":
            _out(sync.ddc(d, version=a.version, dry_run=a.dry_run))
        elif w == "epic":
            _out(sync.epic(d or "status"))
        elif w == "engine":
            if d != "restore" or not a.engine_s3 or not a.version:
                raise SystemExit("film-ue sync engine restore --engine-s3 S3 --version V")
            _out(sync.engine(a.engine_s3, a.version))
        else:
            _out(sync.status())
    elif cmd == "epic-login":
        _linux_only("epic-login")
        from . import linuxbox
        _out(linuxbox.epic_login(fab=a.fab, exchange_code_cmd=a.exchange_code_cmd))
    elif cmd == "provision":
        _linux_only("provision")
        from . import linuxbox
        res = linuxbox.provision(a.engine_s3, a.version, a.project_src, a.project, a.level, epic_s3=a.epic_s3)
        if a.watchdog_ttl:
            import time
            from .boxes import parse_duration
            until = int(time.time()) + parse_duration(a.watchdog_ttl)
            res["watchdog"] = linuxbox.step("watchdog", str(until), str(parse_duration(a.idle) // 60),
                                            str(parse_duration(a.stall) // 60), ws.conf()["project_dir"], timeout=300)
        _out(res)
    elif cmd == "desktop":
        _linux_only("desktop")
        from . import linuxbox
        _out(linuxbox.desktop(a.state == "on"))
    elif cmd == "first-run":
        from . import firstrun
        code = firstrun.main_args(a)
        if code:
            raise SystemExit(code)
    elif cmd == "sh":
        _out(ws.transport().run(a.command, a.timeout, root=a.root))
    return True


EDITOR_VERBS = ("status", "start", "stop", "restart", "log", "crashes", "mode", "enable")


def editor_cli(argv: list) -> int:
    """`film-ue editor <verb>` for the service verbs (opcli.EXTENSIONS["editor"]); the editor.* ops keep their own
    generated commands (film-ue editor describe, film-ue editor cvar --name ...)."""
    import argparse
    ap = argparse.ArgumentParser(prog="film-ue editor", description="the editor as a service on its box")
    ap.add_argument("action", choices=EDITOR_VERBS)
    ap.add_argument("arg", nargs="?", default="", help="log/crashes: how many; mode: default|offscreen|xvfb")
    ap.add_argument("--wait", action="store_true", help="start/restart: until the bridge answers")
    ap.add_argument("--once-args", default="", help="start/restart: extra editor arguments for this start only "
                                                    "(write --once-args=\"-A -B\": they start with a dash)")
    ap.add_argument("--journal", action="store_true", help="log: the unit's journal instead of the editor's log")
    a = ap.parse_args(argv)
    from . import editorsvc
    act = a.action
    if act == "status":
        _out(editorsvc.status())
    elif act in ("start", "stop", "restart"):
        _out(editorsvc.control(act, wait=a.wait, once_args=a.once_args))
    elif act == "log":
        _out(editorsvc.log(int(a.arg or 200), journal=a.journal))
    elif act == "crashes":
        _out(editorsvc.crashes(int(a.arg or 5)))
    elif act == "enable":
        _linux_only("editor enable")
        _out(ws.editor("enable"))
    elif act == "mode":
        _linux_only("editor mode")
        from . import linuxbox
        linuxbox.upload_kit()
        _out(linuxbox.step("mode", a.arg or "default", timeout=300))
    return 0
