"""`film-ue describe [area | area.verb | prefix]`: what the ops are and how to call them, from the schema (offline: no
box needed). With --json the same as data (the schema's entries). For the state of a running editor (the level's
actors, a sequence's tracks) see `film-ue describe --live level|seq PATH|actor LABEL`."""
from __future__ import annotations

import json
import textwrap

from . import schema as _schema


def _default(p: dict) -> str:
    return "required" if p["required"] else "= " + json.dumps(p["default"])


def op_text(o: dict) -> str:
    flags = " ".join(f"--{p['flag']} {p['value'].upper()}" for p in o["params"] if p["required"])
    out = [f"{o['name']}  —  {o['summary']}", "",
           f"  film-ue {o['area']} {o['verb']} {flags}".rstrip() + (" [options]" if any(not p["required"] for p in o["params"]) else ""),
           f"  ue.{o['area']}.{o['verb'] if o['verb'] != 'import' else 'import_'}(" +
           ", ".join(f"{p['name']}=..." for p in o["params"] if p["required"]) + ")", ""]
    if o["params"]:
        out.append("  arguments:")
        w = max(len(p["flag"]) for p in o["params"]) + 2
        for p in o["params"]:
            line = f"    --{p['flag']:<{w}} {p.get('type') or p['value']:<14} {_default(p)}"
            if p.get("choices"):
                line += "  one of " + ", ".join(p["choices"])
            out.append(line)
            if p.get("help"):
                out.append(textwrap.fill(p["help"], 110, initial_indent=" " * 8, subsequent_indent=" " * 8))
        out.append("")
    traits = [t for t, on in (("multi-tick (runs over editor ticks; --async for a job id)", o.get("multi_tick")),
                              ("changes the project", o.get("mutates")),
                              ("idempotent (re-running converges)", o.get("idempotent"))) if on]
    if o.get("tags"):
        traits.append("tags: " + ", ".join(o["tags"]))
    if traits:
        out += ["  " + "; ".join(traits), ""]
    if o.get("returns"):
        out.append(f"  returns: {o['returns']}")
    out += ["", textwrap.indent((o.get("doc") or "(no docstring)").strip(), "  ")]
    if o.get("examples"):
        out += ["", "  examples:"] + [f"    {e}" for e in o["examples"]]
    if o.get("file"):
        out += ["", f"  source: {o['file']}:{o['line']}"]
    return "\n".join(out)


def area_text(ix: dict, area: str) -> str:
    a = ix["areas"][area]
    out = [f"{area}: {a['doc']}".rstrip(": "), ""]
    w = max(len(ix["ops"][n]["verb"]) for n in a["ops"]) + 2
    for n in a["ops"]:
        o = ix["ops"][n]
        mark = "~" if o.get("multi_tick") else " "
        out.append(f"  {mark}{o['verb']:<{w}} {o['summary']}")
    out += ["", f"  film-ue describe {area}.<verb> for one op's arguments; ~ = multi-tick"]
    return "\n".join(out)


def overview(ix: dict) -> str:
    out = ["The bridge's op areas (film-ue <area> <verb> --arg value; ue.<area>.<verb>(arg=value) in Python):", ""]
    w = max((len(a) for a in ix["areas"]), default=4) + 2
    for area, a in ix["areas"].items():
        out.append(f"  {area:<{w}} {len(a['ops']):>3} ops  {a['doc']}"[:150])
    if ix.get("broken"):
        out += ["", "  BROKEN modules (their ops are missing):"] + [f"    {m}: {e}" for m, e in ix["broken"].items()]
    out += ["", "  film-ue describe <area> lists its ops; film-ue describe <area.verb> shows one; --json for data.",
            "  Start with docs/unreal/GUIDE.md."]
    return "\n".join(out)


def resolve(ix: dict, name: str):
    """('op', op) | ('area', area) | ('prefix', [ops]) | ('none', candidates)."""
    if not name:
        return "all", None
    if name in ix["ops"]:
        return "op", ix["ops"][name]
    if name in ix["areas"]:
        return "area", name
    if " " in name:  # "seq new"
        return resolve(ix, name.replace(" ", ".", 1))
    hits = [n for n in ix["ops"] if n.startswith(name)] or [n for n in ix["ops"] if name in n]
    if hits:
        return "prefix", hits
    from .errors import close
    return "none", close(name, list(ix["ops"]) + list(ix["areas"]))


def text(ix: dict, name: str = "") -> str:
    kind, v = resolve(ix, name)
    if kind == "all":
        return overview(ix)
    if kind == "op":
        return op_text(v)
    if kind == "area":
        return area_text(ix, v)
    if kind == "prefix":
        if len(v) == 1:
            return op_text(ix["ops"][v[0]])
        return "\n".join(f"  {n:<28} {ix['ops'][n]['summary']}" for n in v)
    return f"nothing called {name!r}" + (f"; did you mean: {', '.join(v)}" if v else "") + "\n(film-ue describe lists the areas)"


def data(ix: dict, name: str = ""):
    kind, v = resolve(ix, name)
    if kind == "all":
        return {"areas": ix["areas"], "broken": ix["broken"], "fingerprint": ix["fingerprint"]}
    if kind == "op":
        return v
    if kind == "area":
        return [ix["ops"][n] for n in ix["areas"][v]["ops"]]
    if kind == "prefix":
        return [ix["ops"][n] for n in v]
    return {"error": f"nothing called {name!r}", "candidates": v}


# what --live asks the running editor: the state Claude reads before changing it
LIVE = {
    "level": ("level.actors", lambda rest: {}),
    "actors": ("level.actors", lambda rest: {"contains": rest[0] if rest else ""}),
    "seq": ("seq.tracks", lambda rest: {"path": rest[0]}),
    "cuts": ("seq.cuts", lambda rest: {"path": rest[0]}),
    "actor": ("mh.components", lambda rest: {"label": rest[0]}),
    "assets": ("assets.list", lambda rest: {"path": rest[0] if rest else "/Game"}),
}


def live_index() -> dict:
    """The schema of the running bridge (ops.schema, else the older `list`)."""
    from . import client
    r = client.op("ops.schema")
    if r.get("ok"):
        return _schema.index(r["result"])
    r = client.op("list", full=True)
    if not r.get("ok"):
        raise SystemExit(r.get("error", "the bridge did not answer list"))
    return _schema.index(_schema.from_list(r["result"]))
