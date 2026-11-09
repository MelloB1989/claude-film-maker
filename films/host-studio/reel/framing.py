"""Where the presenters land in each presenter shot's frame, from shots.py and motion.py: pure Python (no Unreal), so
a re-frame for a new body is checked before it costs box time.

A point is projected through the shot's camera at every keyed frame of the cut (no handles): u across (-1 left edge,
+1 right), v up (-1 bottom edge, +1 top), the full-frame 16:9 back and the shot's lens. The rules (the operator's):
presenter shots are cut above the knee (no shoes are made), and a presenter a shot is about keeps the whole head in
frame. `python framing.py` prints a table; test_framing.py holds the rules.

His measured body (studio.py's measure stage on the box) goes into shots.py with --him, then the table and the rules
are printed for it (exit 1 when one breaks):

    python3 framing.py --him eyes=168.3 top=180.1 knee=51.2
"""
from __future__ import annotations

import math

import motion as M
from shots import SIGN, EYES_HER, EYES_HIM, FULL_FRAME, KNEE_HER, KNEE_HIM, MARK_HER, MARK_HIM, SHOTS, TOP_HER, TOP_HIM

FWD = M.EYE_FWD  # the eyes (and the head) are this far ahead of the mark; the knees about half of it
BODY = {"him": (MARK_HIM, EYES_HIM, TOP_HIM, KNEE_HIM), "her": (MARK_HER, EYES_HER, TOP_HER, KNEE_HER)}


def points(body=None) -> dict:
    """{who: {"eyes", "top", "knee": [x, y, z]}} for {who: (mark, eyes, top of the head, knee)} (default BODY)."""
    out = {}
    for who, (m, eyes, top, knee) in (body or BODY).items():
        out[who] = {"eyes": (m[0] + FWD, m[1], eyes), "top": (m[0] + 2, m[1], top), "knee": (m[0] + FWD / 2, m[1], knee)}
    return out


# The sign's lower edge (120 cm across, about 36 cm tall), its two corners: in these shots the whole word reads above
# his head, never behind it.
SIGN_FEET = ((SIGN[0], SIGN[1] - 60, SIGN[2] - 18), (SIGN[0], SIGN[1] + 60, SIGN[2] - 18))
UNDER_SIGN = ("S13", "S17", "S18")
# who each presenter shot is about (their whole head in frame); S15 frames him as a foreground shoulder, his crown
# just out of the top (v2), so only she is held there
ABOUT = {"S13": ("him",), "S15": ("her",), "S16": ("her",), "S17": ("him", "her"), "S18": ("him", "her")}


def project(loc, pitch: float, yaw: float, lens: float, p) -> tuple:
    """(u, v, depth): p on the frame of a camera at loc looking (pitch, yaw), roll 0. Unreal axes: X forward at yaw 0,
    Y right, Z up; u, v are -1..1 at the frame's edges."""
    cp, sp, cy, sy = math.cos(math.radians(pitch)), math.sin(math.radians(pitch)), math.cos(math.radians(yaw)), \
        math.sin(math.radians(yaw))
    fw, right, up = (cp * cy, cp * sy, sp), (-sy, cy, 0.0), (-sp * cy, -sp * sy, cp)
    d = [q - c for c, q in zip(loc, p)]
    z = sum(a * b for a, b in zip(d, fw))
    x, y = sum(a * b for a, b in zip(d, right)), sum(a * b for a, b in zip(d, up))
    return x / z * lens / (FULL_FRAME[0] / 2), y / z * lens / (FULL_FRAME[1] / 2), z


def track(shot, body=None) -> dict:
    """{who: {point: [(u, v), ...]}} over the cut's frames, for everyone in the shot's cast."""
    sm, pts = M.samples(shot, 0), points(body)
    return {who: {k: [project(loc, pitch, yaw, shot.lens, p)[:2] for _, loc, pitch, yaw, _ in sm]
                  for k, p in pts[who].items()} for who in shot.cast}


def worst(shot, body=None) -> dict:
    """{who: {"eyes": (lowest v, highest v), "top": highest v, "knee": highest v, "u": (min u, max u) of the eyes}}."""
    out = {}
    for who, pts in track(shot, body).items():
        ev = [v for _, v in pts["eyes"]]
        out[who] = {"eyes": (min(ev), max(ev)), "top": max(v for _, v in pts["top"]),
                    "knee": max(v for _, v in pts["knee"]), "u": (min(u for u, _ in pts["eyes"]),
                                                                  max(u for u, _ in pts["eyes"]))}
    return out


def sign(shot) -> list:
    """[(u from, u to, v)] of the sign's lower edge over the cut's frames (v the lower of its two corners)."""
    out = []
    for _, loc, pitch, yaw, _ in M.samples(shot, 0):
        (u0, v0, _), (u1, v1, _) = (project(loc, pitch, yaw, shot.lens, p) for p in SIGN_FEET)
        out.append((min(u0, u1), max(u0, u1), min(v0, v1)))
    return out


def under_sign(shot, body=None) -> float:
    """The least gap (v) between the top of his head and the sign's lower edge over the frames where his head is
    under the sign (within 0.05 of its width); 9.0 when it never is."""
    gaps = [sv - hv for (a, b, sv), (hu, hv) in zip(sign(shot), track(shot, body)["him"]["top"])
            if a - 0.05 <= hu <= b + 0.05]
    return min(gaps, default=9.0)


def problems(shots=SHOTS, body=None) -> list:
    """Every broken rule: [shot, who, what]."""
    bad = []
    for s in shots:
        for who, w in worst(s, body).items():
            if w["knee"] > -1.0:
                bad.append([s.id, who, f"knee in frame (v {w['knee']:+.2f})"])
            if who in ABOUT.get(s.id, ()) and w["top"] > 1.0:
                bad.append([s.id, who, f"top of the head cut (v {w['top']:+.2f})"])
        if s.id in UNDER_SIGN and "him" in s.cast:
            gap = under_sign(s, body)
            if gap < 0.05:
                bad.append([s.id, "him", f"his head reaches the sign (gap {gap:+.2f})"])
    return bad


def set_him(eyes: float, top: float, knee: float, path=None) -> None:
    """Write his measured eye, head-top and knee heights (cm) into shots.py."""
    import re
    from pathlib import Path
    p = Path(path or Path(__file__).with_name("shots.py"))
    src = p.read_text()
    for pat, new in ((r"^EYES_HIM, EYES_HER = [\d.]+,", f"EYES_HIM, EYES_HER = {eyes:.1f},"),
                     (r"^TOP_HIM, TOP_HER = [\d.]+,", f"TOP_HIM, TOP_HER = {top:.1f},"),
                     (r"^KNEE_HIM, KNEE_HER = [^,]+,", f"KNEE_HIM, KNEE_HER = {knee:.1f},")):
        src, n = re.subn(pat, new, src, count=1, flags=re.M)
        if n != 1:
            raise SystemExit(f"shots.py: no line matches {pat}")
    p.write_text(src)


if __name__ == "__main__":
    import sys
    if "--him" in sys.argv:
        kv = dict(a.split("=", 1) for a in sys.argv[sys.argv.index("--him") + 1:])
        set_him(float(kv["eyes"]), float(kv["top"]), float(kv["knee"]))
        import subprocess
        raise SystemExit(subprocess.call([sys.executable, __file__]))
    for s in SHOTS:
        for who, w in worst(s).items():
            print(f"{s.id} {s.lens:>3g}mm {who}: eyes v {w['eyes'][0]:+.2f}..{w['eyes'][1]:+.2f} u {w['u'][0]:+.2f}.."
                  f"{w['u'][1]:+.2f}  top {w['top']:+.2f}  knee {w['knee']:+.2f}"
                  + (f"  under the sign by {under_sign(s):+.2f}" if s.id in UNDER_SIGN and who == "him" else ""))
    for p in problems():
        print("PROBLEM", *p)
    raise SystemExit(1 if problems() else 0)
