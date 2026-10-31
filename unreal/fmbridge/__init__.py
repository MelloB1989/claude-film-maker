"""fmbridge: claude-film-maker's bridge into the Unreal editor.

Inside the editor it serves an HTTP endpoint on 127.0.0.1 (fmbridge.server) that runs Python and named operations
(fmbridge.ops: assets, levels, looks, MetaHumans, speech to face, curves, sequences, renders) on the game thread, sends
desktop input and grabs the screen (fmbridge.gui), and moves files. A file inbox (fmbridge.inbox) is the fallback when
no tunnel is up. tools/filmtools/unreal is the operator's side (`film-ue`). Started by init_unreal.py at editor start.
"""
from . import gui, inbox, server  # noqa: F401


def start() -> str:
    msg = server.start()
    inbox.start()
    return msg
