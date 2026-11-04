"""film-ue's commands for driving Unreal as an agent (WP11): describe, job, plan, apply, selftest, dx. Registered into
cli.py's parser by register(sub); dispatch(a) runs one and returns True when it was one of these."""
from __future__ import annotations

import json
import sys

NAMES = ("describe", "job", "plan", "apply", "selftest", "dx")


def register(sub) -> None:
    d = sub.add_parser("describe", help="the ops: areas, one area, one op (offline); --live: the editor's state")
    d.add_argument("name", nargs="*", help="area | area.verb | a prefix; with --live: level | actors TEXT | seq PATH | "
                                           "cuts PATH | components LABEL | assets PATH | <spec kind> NAME (its state: actor Box, scene office, ...)")
    d.add_argument("--json", action="store_true")
    d.add_argument("--live", action="store_true", help="ask the running bridge (its schema, or the editor's state)")
    j = sub.add_parser("job", help="an --async op's state, or its result with --wait")
    j.add_argument("id")
    j.add_argument("--wait", action="store_true")
    j.add_argument("--timeout", type=float, default=3600)
    j.add_argument("--json", action="store_true")
    for n in ("plan", "apply"):
        p = sub.add_parser(n, help="a declarative spec (YAML/JSON): " + ("the steps apply would run" if n == "plan" else
                                                                        "run them, then check it converged"))
        p.add_argument("spec", nargs="*", help="spec file(s), in order")
        p.add_argument("--kinds", nargs="?", const="", default=None, metavar="KIND",
                       help="list the kinds (or one kind's fields) and exit")
        p.add_argument("--only", default="", help="kinds to touch, comma-separated (default: all in the spec)")
        p.add_argument("--set", action="append", default=[], metavar="NAME=VALUE", help="override a spec variable")
        p.add_argument("--json", action="store_true")
        if n == "plan":
            p.add_argument("--state", default="", metavar="FILE",
                           help="plan offline against this state ({kind: {name: state}}) instead of the editor")
        else:
            p.add_argument("--dry-run", action="store_true", help="plan only (same as film-ue plan)")
            p.add_argument("--stop", action="store_true", help="stop at the first failing document")
    s = sub.add_parser("selftest", help="each area's acceptance test on the box; one report")
    s.add_argument("areas", nargs="*", default=["all"], help="areas (default all); `film-ue selftest --list`")
    s.add_argument("--list", action="store_true", help="the areas with a selftest, and what each needs")
    s.add_argument("--out", default="", help="local folder for the report (default selftest-reports/<time>)")
    s.add_argument("--keep", action="store_true", help="keep the scratch level and assets afterwards")
    s.add_argument("--json", action="store_true")
    s.add_argument("--timeout", type=float, default=3600, help="per area")
    s.add_argument("--no-pull", action="store_true", help="leave stills on the box")
    s.add_argument("--baseline", default="auto", choices=("auto", "compare", "update", "off"),
                   help="stills against stored baselines (WP10): auto stores the first and compares after")
    x = sub.add_parser("dx", help="the generated layers: gen (schema snapshot + SDK), check (stale?), lint (op docs)")
    x.add_argument("action", choices=("gen", "check", "lint", "docs", "sdk", "coverage"))
    x.add_argument("paths", nargs="*", help="dx sdk: Python files to check (default examples/ and films/*/unreal/)")
    x.add_argument("--json", action="store_true")


def _print(doc, as_json: bool, human: str | None = None):
    if as_json or human is None:
        print(json.dumps(doc, indent=1, default=str))
    else:
        print(human)


def dispatch(a) -> bool:
    if a.cmd not in NAMES:
        return False
    if a.cmd == "describe":
        from . import describe, schema
        name = " ".join(a.name)
        if a.live and a.name and a.name[0] in describe.LIVE:
            from . import opcli
            op, mk = describe.LIVE[a.name[0]]
            argv = [op.split(".")[0], op.split(".")[1]]
            for k, v in mk(a.name[1:]).items():
                argv += ["--" + k.replace("_", "-"), str(v)]
            raise SystemExit(opcli.run(argv + (["--json"] if a.json else [])))
        if a.live and a.name:
            from . import spec
            kd = spec.kinds().get(a.name[0])
            if kd and (kd.describe or kd.describe_many):  # film-ue describe --live <kind> NAME: its state, as plan sees it
                from .sdk import Unreal
                if len(a.name) < 2:
                    raise SystemExit(f"film-ue describe --live {kd.name} <{kd.key}>: which one?")
                doc = {"kind": kd.name, kd.key: a.name[1], "name": a.name[1]}
                ue = Unreal()
                own = ue.index["ops"].get(f"{kd.name}.describe")
                own_args = {p["name"] for p in own["params"]} if own else set()
                if own and (kd.key in own_args or "name" in own_args):  # the area's describe by name (scene.describe)
                    st = ue.call(own["name"], **{(kd.key if kd.key in own_args else "name"): a.name[1]})
                elif kd.describe:
                    st = kd.describe(ue, doc)
                else:
                    st = (kd.describe_many(ue, [doc]) or {}).get(a.name[1])
                print(json.dumps({"kind": kd.name, kd.key: a.name[1], "state": st}, indent=1, default=str))
                return True
        ix = describe.live_index() if a.live else schema.index(schema.load())
        if a.json:
            _print(describe.data(ix, name), True)
        else:
            print(describe.text(ix, name))
    elif a.cmd == "job":
        from . import opcli
        raise SystemExit(opcli.job(a.id, a.wait, a.json, a.timeout))
    elif a.cmd in ("plan", "apply"):
        from . import spec
        raise SystemExit(spec.main(a))
    elif a.cmd == "selftest":
        from . import selftest
        raise SystemExit(selftest.main(a))
    elif a.cmd == "dx":
        raise SystemExit(dx(a.action, a.json, a.paths))
    return True


def dx(action: str, as_json: bool = False, paths: list | None = None) -> int:
    from . import schema
    from .sdk import gen
    if action == "gen":
        p1 = schema.write_snapshot()
        p2 = gen.write()
        _print({"ok": True, "wrote": [str(p1), str(p2)]}, as_json, f"wrote {p1}\nwrote {p2}")
        return 0
    if action == "check":
        problems = stale()
        _print({"ok": not problems, "stale": problems}, as_json,
               "up to date" if not problems else "STALE: " + "; ".join(problems) + "\n  fix: film-ue dx gen")
        return 1 if problems else 0
    if action == "coverage":
        from . import coverage
        r = coverage.report()
        _print(r, as_json, coverage.text(r))
        return 0
    if action == "sdk":
        from . import sdkcheck
        probs = sdkcheck.check(paths or sdkcheck.default_paths())
        _print({"ok": not probs, "problems": [{"file": f, "line": n, "op": o, "problem": p} for f, n, o, p in probs]},
               as_json, "\n".join(f"{f}:{n}: {p}" for f, n, o, p in probs) or "every SDK call matches the op schema")
        return 1 if probs else 0
    if action == "docs":
        from . import doccheck
        probs = doccheck.check()
        _print({"ok": not probs, "problems": [{"file": f, "line": n, "command": c, "problem": p} for f, n, c, p in probs]},
               as_json, "\n".join(f"{f}:{n}: film-ue {c}\n    {p}" for f, n, c, p in probs) or "every film-ue command in the docs parses")
        return 1 if probs else 0
    found = schema.lint(schema.extract())
    _print({"ok": not found, "problems": [{"op": o, "problem": p} for o, p in found]}, as_json,
           "\n".join(f"{o}: {p}" for o, p in found) or "no problems")
    return 0


def stale() -> list:
    """What the generated files miss of the ops in this checkout (empty when current)."""
    from . import schema
    from .sdk import gen
    out = []
    live = schema.extract()
    if not schema.SNAPSHOT.exists() or json.loads(schema.SNAPSHOT.read_text()) != json.loads(json.dumps(live)):
        out.append(f"{schema.SNAPSHOT.name} differs from the ops")
    return out


if __name__ == "__main__":
    sys.exit(dx(sys.argv[1] if len(sys.argv) > 1 else "check"))
