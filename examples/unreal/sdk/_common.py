"""Shared by the SDK examples: the command line (--box, --out), the SDK handle, and printing each step's result and
each check, so a run reads as a log Claude can follow. Every example is `main(ue, args) -> dict` (tests pass a fake)."""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = "/Game/_SDK"           # everything the examples make lives here
LEVEL = ROOT + "/L_SDK"
SEQ = ROOT + "/SEQ_SDK"


def parse(doc: str, argv=None, options=()):
    ap = argparse.ArgumentParser(description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)
    for flag, kw in options:
        ap.add_argument(flag, **kw)
    ap.add_argument("--box", help="the workstation (film-ue --box NAME)")
    ap.add_argument("--out", default="/srv/film/sdk", help="a folder ON THE BOX for stills and renders")
    ap.add_argument("--json", action="store_true", help="print only the final result as JSON")
    return ap.parse_args(argv)


def connect(args):
    if args.box:
        os.environ["FILM_UE_BOX"] = args.box
    from filmtools.unreal.sdk import Unreal
    return Unreal()


class Log:
    def __init__(self, quiet: bool = False):
        self.quiet, self.failed = quiet, []

    def step(self, what: str, result):
        if not self.quiet:
            text = json.dumps(result, default=str)
            print(f"-> {what}: {text[:400]}{' ...' if len(text) > 400 else ''}")
        return result

    def check(self, what: str, ok: bool, detail=""):
        if not ok:
            self.failed.append(what)
        if not self.quiet:
            print(f"   {'PASS' if ok else 'FAIL'} {what}" + (f"  ({detail})" if detail else ""))
        return ok


def run(main, doc: str, options=()):
    from filmtools.unreal.sdk import OpError
    args = parse(doc, options=options)
    log = Log(args.json)
    try:
        res = main(connect(args), args, log)
    except OpError as e:
        print(e.problem.text(), file=sys.stderr)
        sys.exit(1)
    if args.json:
        print(json.dumps({"ok": not log.failed, "failed": log.failed, "result": res}, indent=1, default=str))
    else:
        print("OK" if not log.failed else f"FAILED: {', '.join(log.failed)}")
    sys.exit(1 if log.failed else 0)
