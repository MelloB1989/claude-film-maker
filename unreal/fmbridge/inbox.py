"""The fallback transport: each *.py dropped into Saved/Bridge/in (by SSM send-command, no tunnel needed) runs on the
game thread through the same runner as POST /exec; its output lands in Saved/Bridge/out/<name>.json."""
from __future__ import annotations

import glob
import json
import os
import time

import unreal

from . import server

ROOT = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "Bridge")
INBOX, OUTBOX = os.path.join(ROOT, "in"), os.path.join(ROOT, "out")
_state = {"tick": None, "last": 0.0}


def _tick(_dt):
    if time.time() - _state["last"] < 0.5:
        return
    _state["last"] = time.time()
    for path in sorted(glob.glob(os.path.join(INBOX, "*.py"))):
        name = os.path.basename(path)[:-3]
        with open(path, encoding="utf-8") as f:
            code = f.read()
        os.remove(path)
        res = server._run("exec", {"code": code, "name": name})
        with open(os.path.join(OUTBOX, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(res, f)


def start() -> None:
    os.makedirs(INBOX, exist_ok=True)
    os.makedirs(OUTBOX, exist_ok=True)
    if not _state["tick"]:
        _state["tick"] = unreal.register_slate_post_tick_callback(_tick)
