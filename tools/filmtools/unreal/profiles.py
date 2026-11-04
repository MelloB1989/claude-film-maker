"""Box profiles: the settings of each box film-ue can drive (a Windows workstation, a temporary Linux GPU box, this
machine), one file each, and which one is current.

    film-ue profile ls                     every profile, the current one marked
    film-ue profile use gpu1               make it current (FILM_UE_BOX or --box still win for one command)
    film-ue profile show [NAME]            its settings (nothing secret is stored)
    film-ue profile copy gpu1 gpu2         start a new one from another (instance and port cleared)
    film-ue profile rm gpu2                forget it (its settings, token and tunnel; the box itself is untouched)

Files live beside each other in CONF_DIR (~/.config): film-ue.json is the unnamed default profile, film-ue.NAME.json
a named one, film-ue.current names the current one."""
from __future__ import annotations

import json
import os
import re

from . import workstation as ws

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,40}$")
DEFAULT = "default"
PER_BOX = ("json", "token", "tunnel.json", "tunnel.log", "vnc.json")
FRESH = ("instance", "local_port", "ssh")  # what a copy must not share with its source


def _current_file():
    return ws.CONF_DIR / "film-ue.current"


def _check(name: str) -> str:
    if not NAME.match(name or ""):
        raise SystemExit(f"profile name {name!r}: letters, digits, - and _ (up to 41), starting with a letter or digit")
    return name


def _path(name: str):
    return ws.CONF_DIR / ("film-ue.json" if name == DEFAULT else f"film-ue.{name}.json")


def current() -> str:
    """The profile commands use: FILM_UE_BOX, else the one `use` chose, else the default."""
    env = os.environ.get("FILM_UE_BOX")
    if env:
        return env
    f = _current_file()
    return f.read_text().strip() if f.exists() and f.read_text().strip() else DEFAULT


def names() -> list[str]:
    out = []
    if (ws.CONF_DIR / "film-ue.json").exists():
        out.append(DEFAULT)
    for p in sorted(ws.CONF_DIR.glob("film-ue.*.json")):
        n = p.name[len("film-ue."):-len(".json")]
        if NAME.match(n) and n != DEFAULT and not n.endswith((".tunnel", ".vnc")):
            out.append(n)
    return out


def listing() -> list[dict]:
    cur = current()
    rows = []
    for n in names():
        c = json.loads(_path(n).read_text())
        rows.append({"name": n, "current": n == cur, "os": c.get("os", "windows"), "transport": c.get("transport", "ssm"),
                     "instance": c.get("instance", ""), "ssh": c.get("ssh", ""), "project_dir": c.get("project_dir", ""),
                     "temporary": bool(c.get("ttl_until"))})
    return rows


def use(name: str) -> dict:
    name = _check(name)
    if not _path(name).exists():
        raise SystemExit(f"no profile {name!r}: film-ue profile ls (or make it: film-ue --box {name} set ...)")
    ws.CONF_DIR.mkdir(parents=True, exist_ok=True)
    _current_file().write_text("" if name == DEFAULT else name)
    return show(name)


def show(name: str | None = None) -> dict:
    name = name or current()
    p = _path(_check(name))
    if not p.exists():
        raise SystemExit(f"no profile {name!r}: film-ue profile ls")
    return {"name": name, **json.loads(p.read_text())}


def copy(src: str, dst: str) -> dict:
    s, d = _path(_check(src)), _path(_check(dst))
    if not s.exists():
        raise SystemExit(f"no profile {src!r}: film-ue profile ls")
    if d.exists():
        raise SystemExit(f"profile {dst!r} exists: film-ue profile rm {dst} first")
    c = {k: v for k, v in json.loads(s.read_text()).items() if k not in FRESH}
    d.write_text(json.dumps(c, indent=1))
    return {"name": dst, **c}


def remove(name: str) -> list[str]:
    """Forget a profile: its settings, cached token and tunnel record (the box itself is not touched)."""
    name = _check(name)
    gone = []
    for kind in PER_BOX:
        p = ws.CONF_DIR / (f"film-ue.{kind}" if name == DEFAULT else f"film-ue.{name}.{kind}")
        if p.exists():
            p.unlink()
            gone.append(p.name)
    if current() == name and _current_file().exists():
        _current_file().unlink()
    if not gone:
        raise SystemExit(f"no profile {name!r}: film-ue profile ls")
    return gone
