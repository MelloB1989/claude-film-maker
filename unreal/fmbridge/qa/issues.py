"""The one shape every QA check reports a problem in, so a review can merge them and Claude can act on them."""
from __future__ import annotations

SEVERITIES = ("fail", "warn", "info")  # fail: the shot is wrong; warn: probably wrong, look; info: worth knowing


def issue(code: str, severity: str, message: str, fix: str = "", **where) -> dict:
    """A problem found by a check. `code` is dotted and stable ("framing.headroom_low"), `message` says what is wrong
    with numbers, `fix` says what to do about it (an op to call where there is one), `where` locates it: frame,
    camera, subject, region, box ([x0, y0, x1, y1] as fractions of the frame), value, expected."""
    if severity not in SEVERITIES:
        raise ValueError(f"severity {severity!r}: one of {SEVERITIES}")
    out = {"code": code, "severity": severity, "message": message}
    if fix:
        out["fix"] = fix
    out.update({k: v for k, v in where.items() if v is not None})
    return out


def worst(issues: list) -> str:
    """The worst severity among issues: "fail", "warn", "info", or "ok" with none."""
    found = {i.get("severity") for i in issues}
    for s in SEVERITIES:
        if s in found:
            return s
    return "ok"


def count(issues: list) -> dict:
    return {s: sum(1 for i in issues if i.get("severity") == s) for s in SEVERITIES}
