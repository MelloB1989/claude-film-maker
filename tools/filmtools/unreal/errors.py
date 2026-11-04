"""Actionable errors: turn what the bridge answers when an op fails into a message, a hint (the next command to run)
and candidates (names it may have meant), so an agent can fix the call instead of reading a traceback.

The bridge's own OpError (fmbridge/errors.py) already answers {"ok": false, "code", "message", "hint", "candidates"};
older ops raise plain exceptions, whose traceback's last line is matched here against the usual failures.

    explain(response, op="level.move", args={...}, index=schema.index(...)) -> Problem
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field


@dataclass
class Problem:
    code: str                     # a stable kind: unknown_op, bad_args, not_found, timeout, bridge_down, op_failed, ...
    message: str                  # one line: what went wrong
    hint: str = ""                # what to do next (a command when there is one)
    candidates: list = field(default_factory=list)
    detail: str = ""              # the traceback or the raw error, for when the hint is not enough
    job: str = ""                 # a job still running after a timeout

    def as_dict(self) -> dict:
        d = {"code": self.code, "message": self.message, "hint": self.hint, "candidates": self.candidates}
        if self.job:
            d["job"] = self.job
        if self.detail:
            d["detail"] = self.detail
        return d

    def text(self, verbose: bool = False) -> str:
        out = [f"error [{self.code}]: {self.message}"]
        if self.candidates:
            out.append("  did you mean: " + ", ".join(map(str, self.candidates[:6])))
        if self.hint:
            out.append("  hint: " + self.hint)
        if verbose and self.detail:
            out.append(self.detail.rstrip())
        elif self.detail and self.detail.strip() != self.message:
            out.append("  (--verbose for the traceback)")
        return "\n".join(out)


def close(word: str, names, n: int = 5) -> list:
    names = list(names)
    hits = difflib.get_close_matches(word, names, n=n, cutoff=0.55)
    return hits or [x for x in names if word and (word in x or x in word)][:n]


def _last_line(tb: str) -> str:
    lines = [line for line in (tb or "").strip().splitlines() if line.strip()]
    return lines[-1].strip() if lines else ""


# (pattern on the exception's last line, code, message template, hint template); groups name the parts
_RULES = [
    (r"no op '(?P<x>[^']+)'", "unknown_op", "no op {x!r} on the bridge",
     "film-ue describe lists every op; `film-ue ops <prefix>` asks the running bridge"),
    (r"got an unexpected keyword argument '(?P<x>\w+)'", "bad_args", "{op} takes no argument {x!r}",
     "film-ue describe {op} shows its arguments"),
    (r"missing (?P<n>\d+) required (?:keyword-only |positional )?arguments?: (?P<x>.+)$", "bad_args",
     "{op} needs {x}", "film-ue describe {op} shows its arguments"),
    (r"no actor labell?ed '(?P<x>[^']+)'", "not_found", "no actor labelled {x!r} in the open level",
     "film-ue level actors --contains {short} (labels are exact; the level may not be the one you think: "
     "film-ue describe level)"),
    (r"(?:no asset|asset .* (?:not found|does not exist)|could not load|failed to load)\s*'?(?P<x>/[\w/.\-]+)?",
     "not_found", "asset not found{xs}", "film-ue assets list --path {folder} (paths are /Game/..., no extension)"),
    (r"no sequence|LevelSequence.*None|not a LevelSequence", "not_found", "the sequence does not exist or is not a "
     "LevelSequence", "film-ue assets list --cls LevelSequence; create one with film-ue seq new --path ..."),
    (r"no such job", "not_found", "no such job (finished jobs are kept an hour, and none survive a bridge restart)",
     "start the op again"),
    (r"timeout after (?P<s>[\d.]+)s \(still running as job (?P<x>\w+)\)", "timeout",
     "still running after {s}s (job {x})", "film-ue job {x} --wait follows it; raise --timeout for next time"),
    (r"the bridge restarted", "bridge_restarted", "the bridge restarted before or while this ran",
     "send it again (film-ue health first)"),
    (r"no desktop on", "no_desktop", "no desktop on this box", "use look.still / seq.still for pictures"),
    (r"KeyError: '(?P<x>[^']+)'", "bad_value", "unknown key {x!r}", "film-ue describe {op} lists the accepted values"),
    (r"(?P<t>TypeError|ValueError): (?P<x>.+)$", "bad_value", "{x}", "film-ue describe {op} shows what it takes"),
]


def from_bridge_text(text: str, op: str = "", index: dict | None = None, args: dict | None = None) -> Problem:
    line = _last_line(text)
    for pat, code, msg, hint in _RULES:
        m = re.search(pat, line) or (re.search(pat, text) if code in ("timeout", "bridge_restarted") else None)
        if not m:
            continue
        g = {k: (v or "") for k, v in m.groupdict().items()}
        x = g.get("x", "")
        fmt = {"op": op or "the op", "short": x.split("_")[0] if x else "", "folder": x.rsplit("/", 1)[0] if x else "/Game",
               "xs": f": {x}" if x else "", **g}
        p = Problem(code, msg.format(**fmt), hint.format(**fmt), detail=text if "Traceback" in text else "")
        if code == "timeout":
            p.job = x
        if code == "unknown_op" and index:
            p.candidates = close(x, index["ops"])
        if code == "bad_args" and index and op in index["ops"] and "unexpected" in pat:
            p.candidates = close(x, [q["name"] for q in index["ops"][op]["params"]])
        return p
    return Problem("op_failed", line or "the op failed", f"film-ue describe {op}" if op else "",
                   detail=text if text != line else "")


def explain(res: dict, op: str = "", args: dict | None = None, index: dict | None = None) -> Problem | None:
    """A bridge answer to a Problem, or None when it succeeded."""
    if res.get("ok", True) and "error" not in res:
        return None
    if res.get("message") or res.get("code"):  # the bridge's OpError: already actionable
        return Problem(res.get("code") or "op_failed", res.get("message") or _last_line(res.get("error", "")),
                       res.get("hint") or "", list(res.get("candidates") or []), detail=res.get("error", ""),
                       job=res.get("job", ""))
    return from_bridge_text(res.get("error", ""), op, index, args)


def check_args(op: str, args: dict, index: dict) -> Problem | None:
    """Before sending: is it a known op, are the names right and the required ones there? (offline, from the schema)"""
    if op not in index["ops"]:
        return Problem("unknown_op", f"no op {op!r} in the schema", "film-ue describe lists every op",
                       close(op, index["ops"]))
    o = index["ops"][op]
    names = {p["name"] for p in o["params"]}
    flags = {p["flag"].replace("-", "_"): p["name"] for p in o["params"]}
    for k in args:
        if k not in names and k not in flags and not o.get("varkw"):
            return Problem("bad_args", f"{op} takes no argument {k!r}", f"film-ue describe {op}",
                           close(k, sorted(names)))
    given = {flags.get(k, k) for k in args}
    missing = [p["name"] for p in o["params"] if p["required"] and p["name"] not in given]
    if missing:
        return Problem("bad_args", f"{op} needs {', '.join(missing)}", f"film-ue describe {op}")
    return None
