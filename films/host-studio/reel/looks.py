"""The presenters' looks at each other, computed from the stage (round 4, agent-01), and the check that they read.

The operator on preview2: "he turns head in wrong directions". The looks in perf.py were hand-signed angles, and the
signs were wrong: its notes called world -Y "his own right". The presenters face +X (the camera side), and Unreal is
left-handed (X forward, Y right, Z up), so a presenter's own left is -Y: she (y -55) is on HIS left, he (y +40) on
HER right. perfkit's frame is right (yaw + = the character's own left, perf.calibrate: left = forward x up), so the
fix is here: every "look at the partner" is now the partner's face seen from the looker's eyes, in the looker's frame.

Where the presenters are comes from the level when it has been read (`perf.py looks` samples SEQ_Reel on the box into
OUT/looks_stage.json: each presenter's eyes, head, and facing at the look frames, and the shot's camera), else from
shots.py (the marks, the eyes' heights, facing +X, the cameras' keys). Whoever HOST is (Trey, Host_Op), his eyes are
where the level puts them.

    uv run python ../films/host-studio/reel/looks.py            # the table from shots.py (no box)
    uv run python ../films/host-studio/reel/looks.py --stage F  # from a sampled stage (perf.py looks writes it)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "unreal" / "fmbridge"))
from shots import EYES_HER, EYES_HIM, FULL_FRAME, MARK_HER, MARK_HIM, SHOTS  # noqa: E402

UP = (0.0, 0.0, 1.0)
OTHER = {"him": "her", "her": "him"}
# A look the neck and eyes cannot reach (she is ~130 deg round from his front in S15) is carried as far as they go: the
# head no further than HEAD_MAX, the eyes no further than EYE_MAX past the head (perfkit's gaze.EYE_RANGE).
HEAD_MAX, EYE_MAX = 65.0, 35.0
ERR_MAX = 15.0  # degrees: a look within this of the partner's face reads as on them
STAGE = HERE.parents[2] / "out" / "host-studio" / "reel" / "perf" / "looks_stage.json"


# ------------------------------------------------------------------------------------------------- vectors

def sub(a, b):
    return [x - y for x, y in zip(a, b)]


def add(a, b):
    return [x + y for x, y in zip(a, b)]


def mul(a, k):
    return [x * k for x in a]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def unit(a):
    n = math.sqrt(dot(a, a)) or 1.0
    return [x / n for x in a]


def angle(a, b) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(unit(a), unit(b))))))


def facing(yaw_deg: float) -> list:
    """The horizontal forward of an actor turned `yaw_deg` (Unreal: 0 = +X, 90 = +Y)."""
    r = math.radians(yaw_deg)
    return [math.cos(r), math.sin(r), 0.0]


def left_of(fwd) -> list:
    """The character's own left: forward x up (left-handed Unreal; perf.calibrate's `left`). +X forward -> -Y."""
    return unit(cross(unit([fwd[0], fwd[1], 0.0]), UP))


# ------------------------------------------------------------------------------------------------- the stage

def offline_pose(who: str) -> dict:
    """A presenter on their mark from shots.py: facing +X, the eyes 9 cm forward of the feet at their height."""
    m, z = (MARK_HIM, EYES_HIM) if who == "him" else (MARK_HER, EYES_HER)
    eyes = [m[0] + 9.0, m[1], z]
    return {"eyes": eyes, "head": [m[0], m[1], z - 8.0], "yaw": 0.0}


def camera_at(sid: str, frame: int) -> dict:
    """A reel camera at a master frame from shots.py's keys (what build.py keys on Reel_<sid>)."""
    s = next(x for x in SHOTS if x.id == sid)
    loc, at = s.at((frame - s.start) / s.frames)
    return {"loc": list(loc), "at": list(at), "focal": float(s.lens), "film_w": float(FULL_FRAME[0])}


def shot_of(frame: int):
    return next(s for s in SHOTS if s.start <= frame < s.end)


class Stage:
    """Where the presenters' eyes are and which way their bodies face, and the cameras, at master frames: from a
    sampled stage (perf.py looks) where it has the frame, else from shots.py."""

    def __init__(self, sampled: dict | None = None):
        self.sampled = sampled or {}
        self.source = "level" if self.sampled else "shots.py"

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Stage":
        p = Path(path) if path else STAGE
        return cls(json.loads(p.read_text())) if p.exists() else cls()

    def _frame(self, frame: int) -> dict | None:
        fr = self.sampled.get("frames", {})
        if not fr:
            return None
        k = min(fr, key=lambda x: abs(int(x) - frame))
        return fr[k] if abs(int(k) - frame) <= 2 else None

    def pose(self, who: str, frame: int) -> dict:
        got = self._frame(frame)
        if got and who in got:
            return got[who]
        if self.sampled and self.sampled.get("rest", {}).get(who):  # the level's presenter, held still
            return self.sampled["rest"][who]
        return offline_pose(who)

    def camera(self, sid: str, frame: int) -> dict:
        got = self._frame(frame)
        if got and got.get("cameras", {}).get(sid):
            return got["cameras"][sid]
        return camera_at(sid, frame)


# ------------------------------------------------------------------------------------------------- looks

def local(pose: dict, point) -> tuple:
    """`point` seen from `pose`'s eyes in its own frame: (yaw + = own left, pitch + = up, distance cm)."""
    f = facing(pose["yaw"])
    v = sub(point, pose["eyes"])
    y = math.degrees(math.atan2(dot(v, left_of(f)), dot(v, f)))
    h = math.hypot(dot(v, f), dot(v, left_of(f)))
    return y, math.degrees(math.atan2(v[2], h)), math.sqrt(dot(v, v))


def world_dir(pose: dict, yaw: float, pitch: float) -> list:
    """The world direction of (yaw, pitch) in `pose`'s frame."""
    f, l_ = facing(pose["yaw"]), left_of(facing(pose["yaw"]))
    cy, sy, cp, sp = math.cos(math.radians(yaw)), math.sin(math.radians(yaw)), math.cos(math.radians(pitch)), \
        math.sin(math.radians(pitch))
    return unit(add(add(mul(f, cp * cy), mul(l_, cp * sy)), mul(list(UP), sp)))


def reach(share: float) -> float:
    """The farthest gaze yaw a look with this head share can carry: the head to HEAD_MAX, the eyes to EYE_MAX."""
    return min(HEAD_MAX / max(share, 1e-3), EYE_MAX / max(1.0 - share, 1e-3))


def look(who: str, frame: int, share: float = 1.0, stage: Stage | None = None) -> dict:
    """`who`'s look at the partner's face at `frame`: perf.face's gaze (yaw, pitch, dist_cm), in `who`'s frame. The
    yaw is the true one, cut to what the head share can reach (`reach`) when the partner is further round."""
    st = stage or Stage.load()
    me, them = st.pose(who, frame), st.pose(OTHER[who], frame)
    y, p, d = local(me, them["eyes"])
    r = reach(share)
    cmd = max(-r, min(r, y))
    return {"yaw": round(cmd, 1), "pitch": round(p, 1), "dist_cm": round(d, 1), "true_yaw": round(y, 1),
            "reach": round(r, 1), "source": st.source}


# ------------------------------------------------------------------------------------------------- the check

def screen_x(cam: dict, p) -> float:
    """`p`'s horizontal place in the frame: -1 the left edge, +1 the right (Unreal: right = up x forward)."""
    fwd = unit(sub(cam["at"], cam["loc"]))
    right = unit(cross(list(UP), fwd))
    v = sub(p, cam["loc"])
    z = dot(v, fwd)
    return dot(v, right) / max(z, 1e-3) * cam["focal"] / (cam["film_w"] / 2.0)


def head_plan(gaze: list, start_gaze, t: float) -> tuple:
    """perfkit's planned head (yaw, pitch) and gaze at `t` s for perf.face's gaze list (what perf.face composes)."""
    from perfkit import gaze as G
    shifts = [G.Shift(g["t"], g.get("yaw", 0.0), g.get("pitch", 0.0), g.get("dist_cm", 200.0), g.get("scan"),
                      g.get("head")) for g in gaze]
    plan = G.GazePlan(shifts, start=tuple(start_gaze or (0.0, 0.0)))
    return plan.head_base(t), plan.gaze(t)


def check(who: str, frame: int, sid: str, head, gaze_, stage: Stage | None = None, rest_frame: int | None = None):
    """One look beat in one camera: where the head points (perfkit's head (yaw, pitch), or a measured world forward)
    against the partner's face. screen_dir: which way across the frame the head's turn goes (from where it points at
    rest), partner_dir: which side of the head the partner is on screen; err_deg: the gaze's 3D angle off the
    partner's face, head_err_deg the head's. OK: the turn goes the partner's way and the gaze is within ERR_MAX (or,
    for a partner beyond reach, the head is turned the right way at least half its reach)."""
    st = stage or Stage.load()
    me, them = st.pose(who, frame), st.pose(OTHER[who], frame)
    cam = st.camera(sid, frame)
    hd = head if len(head) == 3 else world_dir(me, *head)
    gz = gaze_ if len(gaze_) == 3 else world_dir(me, *gaze_)
    rest = world_dir(me, 0.0, 0.0)
    to = sub(them["eyes"], me["eyes"])
    L = 30.0
    turn = screen_x(cam, add(me["eyes"], mul(hd, L))) - screen_x(cam, add(me["eyes"], mul(rest, L)))
    side = screen_x(cam, them["eyes"]) - screen_x(cam, me["eyes"])
    sd = "right" if turn > 0 else "left"
    pd = "right" if side > 0 else "left"
    err, herr = angle(gz, to), angle(hd, to)
    y_true, _, _ = local(me, them["eyes"])
    y_head, _, _ = local(me, add(me["eyes"], hd))
    beyond = abs(y_true) > HEAD_MAX + EYE_MAX
    ok_ = sd == pd and (err <= ERR_MAX or (beyond and y_head * y_true > 0 and abs(y_head) >= 0.5 * HEAD_MAX))
    return {"shot": sid, "frame": frame, "who": who, "screen_dir": sd, "partner_dir": pd,
            "err_deg": round(err, 1), "head_err_deg": round(herr, 1), "true_yaw": round(y_true, 1),
            "head_yaw": round(y_head, 1), "beyond_reach": beyond, "ok": ok_}


def table(rows: list) -> str:
    cols = ["shot", "beat", "who", "frames", "yaw_cmd", "true_yaw", "head_yaw", "screen_dir", "partner_dir", "err_deg",
            "head_err_deg", "ok"]
    out = ["  ".join(f"{c:>12}" if c != "beat" else f"{c:<26}" for c in cols)]
    for r in rows:
        out.append("  ".join(f"{str(r.get(c, '')):<26}" if c == "beat" else f"{str(r.get(c, '')):>12}" for c in cols))
    return "\n".join(out)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stage", help="a sampled stage JSON (perf.py looks); default OUT/looks_stage.json if present")
    ap.add_argument("--json", help="also write the rows here")
    a = ap.parse_args()
    import perf
    rows = perf.look_table(Stage.load(a.stage))
    print(table(rows))
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1))
    sys.exit(0 if all(r["ok"] for r in rows) else 1)


if __name__ == "__main__":
    main()
