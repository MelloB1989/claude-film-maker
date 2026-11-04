"""`film-ue <area> <verb> --arg value ...`: every bridge op as a command, generated from the op schema (so a new op is
a new command with no CLI code).

    film-ue level spawn --label Key --cls RectLight --loc 0,0,300
    film-ue level move --label Key --loc '[150,118,228]' --look-at 8,0,172 --json
    film-ue seq new --path /Game/Demo/Seq --end 96 --dry-run       # check the call offline, send nothing
    film-ue render mrq --sequence ... --async                        # a job id; film-ue job ID --wait
    film-ue look light --args @light.json                            # arguments from a JSON/YAML file

Values: numbers and strings as typed; lists as JSON or comma-separated (`0,0,300`); dicts as JSON or `k=v,k=v`
(`--rot pitch=-10,yaw=90`); `@file` reads a JSON (or YAML) file, `-` reads stdin; `null` for none. A bool flag alone is
true (`--replace`), `--no-replace` false. A flag is the argument's name with `-` for `_` (`--look-at` for look_at;
a trailing `_` dropped: `--rot` for rot_).

--json prints one JSON document on stdout whatever happens: {"ok", "op", "result", "stdout", "ms"} or {"ok": false,
"op", "error": {"code", "message", "hint", "candidates"}}. Exit codes: 0 ok, 1 the op failed, 2 a bad call (caught
offline), 3 no bridge.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import errors, schema as _schema

EXIT_OK, EXIT_OP, EXIT_USAGE, EXIT_BRIDGE = 0, 1, 2, 3


class Usage(Exception):
    def __init__(self, problem: errors.Problem):
        super().__init__(problem.message)
        self.problem = problem


class _Parser(argparse.ArgumentParser):
    """argparse that raises (with candidates) instead of printing and exiting, so --json callers get JSON."""

    def __init__(self, *a, op: str = "", flags: list | None = None, **kw):
        super().__init__(*a, **kw)
        self._op, self._flags = op, flags or []

    def error(self, message):
        cands = []
        if "unrecognized arguments" in message:
            bad = [w for w in message.split(":", 1)[1].split() if w.startswith("--")]
            if bad:
                cands = errors.close(bad[0].lstrip("-"), [f.lstrip("-") for f in self._flags])
                cands = ["--" + c for c in cands]
        elif "invalid choice" in message:
            import re
            m = re.search(r"invalid choice: '([^']+)'.*choose from (.*)\)", message)
            if m:
                cands = errors.close(m.group(1), [c.strip(" '") for c in m.group(2).split(",")])
        raise Usage(errors.Problem("bad_args", message, f"film-ue describe {self._op}".strip() if self._op else
                                   "film-ue describe", cands))


# ---------------------------------------------------------------------------------------------------------- values

_TRUE, _FALSE = {"true", "yes", "on", "1", "y"}, {"false", "no", "off", "0", "n"}


def _read_ref(raw: str):
    """@file (JSON or YAML) or - (stdin): the parsed value; None when raw is neither."""
    if raw == "-":
        text = sys.stdin.read()
    elif raw.startswith("@") and len(raw) > 1:
        p = Path(raw[1:])
        if not p.exists():
            raise ValueError(f"no file {p}")
        text = p.read_text()
        if p.suffix in (".yaml", ".yml"):
            import yaml
            return True, yaml.safe_load(text)
    else:
        return False, None
    try:
        return True, json.loads(text)
    except ValueError:
        return True, text.rstrip("\n")


def _json_or(raw: str):
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def parse_value(raw: str, kind: str, nullable: bool = True):
    """A command-line string to the value an op takes, by its kind (int, float, bool, str, list, dict, any)."""
    is_ref, v = _read_ref(raw)
    if is_ref:
        return v
    if raw == "null" and (nullable or kind == "any"):
        return None
    if kind == "int":
        f = float(raw)
        if f != int(f):
            raise ValueError(f"{raw!r} is not a whole number")
        return int(f)
    if kind == "float":
        return float(raw)
    if kind == "bool":
        if raw.lower() in _TRUE:
            return True
        if raw.lower() in _FALSE:
            return False
        raise ValueError(f"{raw!r} is not true/false")
    if kind == "str":
        return raw
    if kind == "list":
        s = raw.strip()
        if s.startswith("["):
            v = json.loads(s)
            if not isinstance(v, list):
                raise ValueError("not a list")
            return v
        return [] if not s else [_json_or(x.strip()) for x in s.split(",")]
    if kind == "dict":
        s = raw.strip()
        if s.startswith("{"):
            v = json.loads(s)
            if not isinstance(v, dict):
                raise ValueError("not an object")
            return v
        out = {}
        for part in filter(None, (x.strip() for x in s.split(","))):
            if "=" not in part:
                raise ValueError(f"{part!r}: write k=v,k=v or JSON")
            k, val = part.split("=", 1)
            out[k.strip()] = _json_or(val.strip())
        return out
    v = _json_or(raw)  # any: JSON, else the shapes the ops' conventions use (a k=v dict, a comma list), else text
    if isinstance(v, str) and raw.strip():
        parts = [x.strip() for x in raw.split(",")]
        if all(re.fullmatch(r"[A-Za-z_]\w*=.*", x) for x in parts):
            return parse_value(raw, "dict")
        if len(parts) > 1 and all(isinstance(_json_or(x), (int, float)) for x in parts):
            return parse_value(raw, "list")
    return v


# ---------------------------------------------------------------------------------------------------------- parser

COMMON = [  # (flag, argparse keywords); an op's own argument of the same name wins and this one becomes --call-<flag>
    ("--json", dict(action="store_true", help="one JSON document on stdout, also on failure")),
    ("--dry-run", dict(action="store_true", help="validate and print the request; send nothing")),
    ("--async", dict(dest="async_", action="store_true", help="start it and print the job id")),
    ("--timeout", dict(dest="call_timeout", type=float, default=900, help="seconds to wait for the answer (900)")),
    ("--args", dict(dest="args_json", metavar="JSON|@FILE", help="arguments as one JSON/YAML object (flags win)")),
    ("--verbose", dict(action="store_true", help="the bridge's traceback with an error")),
    ("--live", dict(action="store_true", help="the running bridge's schema (an op this checkout lacks)")),
]


def _add_common(p: argparse.ArgumentParser, taken: set) -> list:
    g = p.add_argument_group("film-ue")
    used = []
    for flag, kw in COMMON:
        f = flag if flag not in taken else "--call-" + flag[2:]
        kw = dict(kw)
        kw.setdefault("dest", flag[2:].replace("-", "_"))
        g.add_argument(f, **kw)
        used.append(f)
    return used


def build(ix: dict, prog: str = "film-ue") -> _Parser:
    ap = _Parser(prog=prog, description="the bridge's ops (film-ue describe for more)",
                 formatter_class=argparse.RawDescriptionHelpFormatter)
    areas = ap.add_subparsers(dest="area", metavar="AREA", parser_class=_Parser)
    areas.required = True
    for area, a in ix["areas"].items():
        ap_area = areas.add_parser(area, help=a["doc"][:80], description=a["doc"],
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
        verbs = ap_area.add_subparsers(dest="verb", metavar="VERB", parser_class=_Parser)
        verbs.required = True
        for name in a["ops"]:
            o = ix["ops"][name]
            flags = ["--" + p["flag"] for p in o["params"]]
            epi = (o.get("doc") or "") + (("\n\nexamples:\n  " + "\n  ".join(o["examples"])) if o.get("examples") else "")
            vp = verbs.add_parser(o["verb"], help=o["summary"][:100], description=o["summary"], epilog=epi,
                                  formatter_class=argparse.RawDescriptionHelpFormatter, op=name, flags=flags)
            g = vp.add_argument_group("arguments")
            for p in o["params"]:
                h = f"{p.get('type') or p['value']}; " + ("required" if p["required"] else
                                                          f"default {json.dumps(p['default'])}")
                if p.get("choices"):
                    h += "; one of " + ", ".join(p["choices"])
                if p.get("help"):
                    h += ". " + p["help"]
                h = h.replace("%", "%%")
                dest = "p__" + p["name"]
                if p["value"] == "bool":
                    g.add_argument("--" + p["flag"], dest=dest, nargs="?", const="true", default=None,
                                   metavar="BOOL", help=h)
                    g.add_argument("--no-" + p["flag"], dest=dest, action="store_const", const="false",
                                   help=argparse.SUPPRESS)
                else:
                    g.add_argument("--" + p["flag"], dest=dest, default=None, metavar=p["value"].upper(), help=h)
                if p["flag"].replace("-", "_") != p["flag"]:  # --look_at too, as Python spells it
                    g.add_argument("--" + p["flag"].replace("-", "_"), dest=dest, default=None, help=argparse.SUPPRESS)
            taken = set(flags) | {"--" + p["flag"].replace("-", "_") for p in o["params"]}
            vp._flags += _add_common(vp, taken)
    return ap


def args_of(ns: argparse.Namespace, o: dict) -> dict:
    """The op's keyword arguments from the parsed command line: --args first, flags over it; values by kind."""
    out = {}
    if ns.args_json:
        is_ref, v = _read_ref(ns.args_json)
        v = v if is_ref else json.loads(ns.args_json)
        if not isinstance(v, dict):
            raise Usage(errors.Problem("bad_args", "--args must be a JSON object", f"film-ue describe {o['name']}"))
        out.update(v)
    for p in o["params"]:
        raw = getattr(ns, "p__" + p["name"], None)
        if raw is None:
            continue
        try:
            out[p["name"]] = parse_value(raw, p["value"], p["nullable"])
        except (ValueError, json.JSONDecodeError) as e:
            raise Usage(errors.Problem("bad_value", f"--{p['flag']} {raw!r}: {e}",
                                       f"--{p['flag']} takes {p['value']} ({p.get('type') or 'see film-ue describe '+o['name']})"))
        if p.get("choices") and out[p["name"]] not in p["choices"]:
            raise Usage(errors.Problem("bad_value", f"--{p['flag']} {raw!r} is not one of {', '.join(p['choices'])}",
                                       f"film-ue describe {o['name']}", errors.close(str(raw), p["choices"])))
    return out


# ------------------------------------------------------------------------------------------------------------ run

def _emit(as_json: bool, doc: dict, human: str | None = None, err: bool = False):
    if as_json:
        print(json.dumps(doc, indent=1, default=str))
    elif human is not None:
        (sys.stderr if err else sys.stdout).write(human.rstrip("\n") + "\n")


def _human_result(v) -> str:
    return v if isinstance(v, str) else json.dumps(v, indent=1, default=str)


def run(argv: list, ix: dict | None = None, transport=None) -> int:
    """Parse and run one `<area> <verb> ...` command; returns the exit code. `transport(kind, payload, timeout)` is the
    SDK's wire (tests pass a fake)."""
    as_json = "--json" in argv or "--call-json" in argv
    try:
        if ix is None:
            ix = _schema.index(_schema.load())
            if "--live" in argv:
                from .describe import live_index
                ix = live_index()
        ext = extension(argv, ix)
        if ext:
            return int(ext(argv[1:]) or 0)
        ns, extra = build(ix).parse_known_args(argv)
        name = f"{ns.area}.{ns.verb}"
        o = ix["ops"][name]
        if extra:
            flags = ["--" + p["flag"] for p in o["params"]] + [f for f, _ in COMMON]
            bad = next((w for w in extra if w.startswith("-")), extra[0])
            raise Usage(errors.Problem("bad_args", f"{name} has no {bad}" if bad.startswith("-") else
                                       f"unexpected {bad!r} (every argument is a --flag)",
                                       f"film-ue describe {name}", errors.close(bad, flags)))
        args = args_of(ns, o)
        p = errors.check_args(name, args, ix)
        if p:
            raise Usage(p)
    except Usage as u:
        _emit(as_json, {"ok": False, "op": " ".join(argv[:2]), "error": u.problem.as_dict()}, u.problem.text(), err=True)
        return EXIT_USAGE
    req = {"op": name, "args": args, "async": ns.async_, "timeout": ns.call_timeout}
    if ns.dry_run:
        _emit(as_json or True, {"ok": True, "dry_run": True, **req, "multi_tick": o.get("multi_tick"),
                                "mutates": o.get("mutates")})
        return EXIT_OK
    from .sdk import Unreal, OpError, Job
    ue = Unreal(transport=transport, check=False)
    ue._index = ix
    stdout = []
    ue._log = stdout.append
    try:
        res = ue.call(name, wait=not ns.async_, timeout=ns.call_timeout, **args)
    except OpError as e:
        doc = {"ok": False, "op": name, "error": e.problem.as_dict() if ns.verbose else
               {k: v for k, v in e.problem.as_dict().items() if k != "detail"}, "stdout": e.stdout}
        if e.stdout and not as_json:
            sys.stdout.write(e.stdout)
        _emit(as_json, doc, e.problem.text(ns.verbose), err=True)
        return EXIT_OP
    except SystemExit as e:  # the transport: no tunnel, no token, no bridge
        p = errors.Problem("bridge_down", str(e.code or e), "film-ue health; film-ue status (is the box up?); "
                           "film-ue editor status (Linux)")
        _emit(as_json, {"ok": False, "op": name, "error": p.as_dict()}, p.text(), err=True)
        return EXIT_BRIDGE
    if isinstance(res, Job):
        _emit(as_json, {"ok": True, "op": name, "job": res.id, "hint": f"film-ue job {res.id} --wait"},
              f"started job {res.id}: film-ue job {res.id} --wait")
        return EXIT_OK
    if stdout and not as_json:
        sys.stderr.write("".join(stdout))
    _emit(as_json, {"ok": True, "op": name, "result": res, "stdout": "".join(stdout)}, _human_result(res))
    return EXIT_OK


# An area's own hand-written commands beside its generated ones: `film-ue render plan spec.yaml` runs
# filmtools.unreal.render.main(["plan", "spec.yaml"]), while `film-ue render mrq --sequence ...` stays the op.
# A WP adds its line here (module:function taking argv, returning an exit code); the op verbs always win.
EXTENSIONS = {
    "render": "filmtools.unreal.render:main",
}


def extension(argv: list, ix: dict):
    """The extension's main when argv[0] is an area with one and argv[1] is not one of its op verbs, else None."""
    if len(argv) < 2 or argv[0] not in EXTENSIONS or argv[1].startswith("-"):
        return None
    if argv[0] in ix["areas"] and f"{argv[0]}.{argv[1]}" in ix["ops"]:
        return None
    mod, fn = EXTENSIONS[argv[0]].split(":")
    import importlib
    try:
        return getattr(importlib.import_module(mod), fn)
    except (ImportError, AttributeError):
        return None


def wants(argv: list, builtin: set, ix: dict | None = None) -> bool:
    """Is this command line an op command (its first word an area, not one of film-ue's own commands)?"""
    words = [w for w in argv if not w.startswith("-")]
    if not words or words[0] in builtin:
        return False
    ix = ix or _schema.index(_schema.load())
    return words[0] in ix["areas"] or (words[0] in EXTENSIONS and extension(argv, ix) is not None)


def job(job_id: str, wait: bool = False, as_json: bool = False, timeout: float = 3600, transport=None) -> int:
    """`film-ue job ID [--wait]`: a job's state, or its result once done."""
    from .sdk import Unreal, OpError
    ue = Unreal(transport=transport, check=False)
    try:
        if wait:
            res = ue.job(job_id).wait(timeout)
            _emit(as_json, {"ok": True, "job": job_id, "result": res}, _human_result(res))
        else:
            r = ue.job(job_id).poll()
            _emit(True, r)
        return EXIT_OK
    except OpError as e:
        _emit(as_json, {"ok": False, "job": job_id, "error": e.problem.as_dict()}, e.problem.text(), err=True)
        return EXIT_OP
