"""The MetaHuman face's animation curves: names, groups and the head pose curves.

Verified on the UE 5.8.4 source: the 251 raw control curve names are the list in
Engine/Plugins/MetaHuman/MetaHumanCoreTechLib/Source/MetaHumanCoreTech/Private/GuiToRawControlsUtils.cpp:202-447
(each `CTRL_expressions_<name>`); the head curves HeadYaw/HeadPitch/HeadRoll (degrees, the head's rotation relative to
its neutral frame), HeadTranslationX/Y/Z (cm) and HeadControlSwitch (0/1, 1 = the face rig turns the head from
these curves) are written by MetaHumanPerformanceExportUtils.cpp:99-109,2684-2702.

Sign conventions of the head curves on a real face rig are measured, not assumed: `perf.calibrate` turns the head by
each curve and records which way it went; `HeadSigns` carries the result. perfkit itself works in the CHARACTER's
frame: yaw + = the character turns to their own left, pitch + = looks up, roll + = the top of the head tilts to the
character's left.
"""
from __future__ import annotations

PREFIX = "CTRL_expressions_"

# every raw expression control, without the prefix (GuiToRawControlsUtils.cpp:202-447)
RAW = (
    "browDownL", "browDownR", "browLateralL", "browLateralR", "browRaiseInL", "browRaiseInR", "browRaiseOuterL",
    "browRaiseOuterR", "earUpL", "earUpR", "eyeBlinkL", "eyeBlinkR", "eyeCheekRaiseL", "eyeCheekRaiseR",
    "eyeFaceScrunchL", "eyeFaceScrunchR", "eyeLidPressL", "eyeLidPressR", "eyeLookDownL", "eyeLookDownR",
    "eyeLookLeftL", "eyeLookLeftR", "eyeLookRightL", "eyeLookRightR", "eyeLookUpL", "eyeLookUpR", "eyeLowerLidDownL",
    "eyeLowerLidDownR", "eyeLowerLidUpL", "eyeLowerLidUpR", "eyeParallelLookDirection", "eyePupilNarrowL",
    "eyePupilNarrowR", "eyePupilWideL", "eyePupilWideR", "eyeRelaxL", "eyeRelaxR", "eyeSquintInnerL",
    "eyeSquintInnerR", "eyeUpperLidUpL", "eyeUpperLidUpR", "eyeWidenL", "eyeWidenR", "eyelashesDownINL",
    "eyelashesDownINR", "eyelashesDownOUTL", "eyelashesDownOUTR", "eyelashesUpINL", "eyelashesUpINR",
    "eyelashesUpOUTL", "eyelashesUpOUTR", "jawBack", "jawChinCompressL", "jawChinCompressR", "jawChinRaiseDL",
    "jawChinRaiseDR", "jawChinRaiseUL", "jawChinRaiseUR", "jawClenchL", "jawClenchR", "jawFwd", "jawLeft", "jawOpen",
    "jawOpenExtreme", "jawRight", "mouthCheekBlowL", "mouthCheekBlowR", "mouthCheekSuckL", "mouthCheekSuckR",
    "mouthCornerDepressL", "mouthCornerDepressR", "mouthCornerDownL", "mouthCornerDownR", "mouthCornerNarrowL",
    "mouthCornerNarrowR", "mouthCornerPullL", "mouthCornerPullR", "mouthCornerRounderDL", "mouthCornerRounderDR",
    "mouthCornerRounderUL", "mouthCornerRounderUR", "mouthCornerSharpenDL", "mouthCornerSharpenDR",
    "mouthCornerSharpenUL", "mouthCornerSharpenUR", "mouthCornerUpL", "mouthCornerUpR", "mouthCornerWideL",
    "mouthCornerWideR", "mouthDimpleL", "mouthDimpleR", "mouthDown", "mouthFunnelDL", "mouthFunnelDR",
    "mouthFunnelUL", "mouthFunnelUR", "mouthLeft", "mouthLipsBlowL", "mouthLipsBlowR", "mouthLipsPressL",
    "mouthLipsPressR", "mouthLipsPullDL", "mouthLipsPullDR", "mouthLipsPullUL", "mouthLipsPullUR",
    "mouthLipsPurseDL", "mouthLipsPurseDR", "mouthLipsPurseUL", "mouthLipsPurseUR", "mouthLipsPushDL",
    "mouthLipsPushDR", "mouthLipsPushUL", "mouthLipsPushUR", "mouthLipsStickyLPh1", "mouthLipsStickyLPh2",
    "mouthLipsStickyLPh3", "mouthLipsStickyRPh1", "mouthLipsStickyRPh2", "mouthLipsStickyRPh3", "mouthLipsThickDL",
    "mouthLipsThickDR", "mouthLipsThickInwardDL", "mouthLipsThickInwardDR", "mouthLipsThickInwardUL",
    "mouthLipsThickInwardUR", "mouthLipsThickUL", "mouthLipsThickUR", "mouthLipsThinDL", "mouthLipsThinDR",
    "mouthLipsThinInwardDL", "mouthLipsThinInwardDR", "mouthLipsThinInwardUL", "mouthLipsThinInwardUR",
    "mouthLipsThinUL", "mouthLipsThinUR", "mouthLipsTightenDL", "mouthLipsTightenDR", "mouthLipsTightenUL",
    "mouthLipsTightenUR", "mouthLipsTogetherDL", "mouthLipsTogetherDR", "mouthLipsTogetherUL", "mouthLipsTogetherUR",
    "mouthLipsTowardsDL", "mouthLipsTowardsDR", "mouthLipsTowardsUL", "mouthLipsTowardsUR", "mouthLowerLipBiteL",
    "mouthLowerLipBiteR", "mouthLowerLipDepressL", "mouthLowerLipDepressR", "mouthLowerLipRollInL",
    "mouthLowerLipRollInR", "mouthLowerLipRollOutL", "mouthLowerLipRollOutR", "mouthLowerLipShiftLeft",
    "mouthLowerLipShiftRight", "mouthLowerLipTowardsTeethL", "mouthLowerLipTowardsTeethR", "mouthPressDL",
    "mouthPressDR", "mouthPressUL", "mouthPressUR", "mouthRight", "mouthSharpCornerPullL", "mouthSharpCornerPullR",
    "mouthStickyDC", "mouthStickyDINL", "mouthStickyDINR", "mouthStickyDOUTL", "mouthStickyDOUTR", "mouthStickyUC",
    "mouthStickyUINL", "mouthStickyUINR", "mouthStickyUOUTL", "mouthStickyUOUTR", "mouthStretchL",
    "mouthStretchLipsCloseL", "mouthStretchLipsCloseR", "mouthStretchR", "mouthUp", "mouthUpperLipBiteL",
    "mouthUpperLipBiteR", "mouthUpperLipRaiseL", "mouthUpperLipRaiseR", "mouthUpperLipRollInL",
    "mouthUpperLipRollInR", "mouthUpperLipRollOutL", "mouthUpperLipRollOutR", "mouthUpperLipShiftLeft",
    "mouthUpperLipShiftRight", "mouthUpperLipTowardsTeethL", "mouthUpperLipTowardsTeethR", "neckDigastricDown",
    "neckDigastricUp", "neckMastoidContractL", "neckMastoidContractR", "neckStretchL", "neckStretchR",
    "neckSwallowPh1", "neckSwallowPh2", "neckSwallowPh3", "neckSwallowPh4", "neckThroatDown", "neckThroatExhale",
    "neckThroatInhale", "neckThroatUp", "noseNasolabialDeepenL", "noseNasolabialDeepenR", "noseNostrilCompressL",
    "noseNostrilCompressR", "noseNostrilDepressL", "noseNostrilDepressR", "noseNostrilDilateL", "noseNostrilDilateR",
    "noseWrinkleL", "noseWrinkleR", "noseWrinkleUpperL", "noseWrinkleUpperR", "teethBackD", "teethBackU",
    "teethDownD", "teethDownU", "teethFwdD", "teethFwdU", "teethLeftD", "teethLeftU", "teethRightD", "teethRightU",
    "teethUpD", "teethUpU", "tongueBendDown", "tongueBendUp", "tongueDown", "tongueIn", "tongueLeft", "tongueNarrow",
    "tongueOut", "tonguePress", "tongueRight", "tongueRoll", "tongueThick", "tongueThin", "tongueTipDown",
    "tongueTipLeft", "tongueTipRight", "tongueTipUp", "tongueTwistLeft", "tongueTwistRight", "tongueUp",
    "tongueWide",
)
CURVES = frozenset(PREFIX + n for n in RAW)

HEAD_ROT = ("HeadYaw", "HeadPitch", "HeadRoll")
HEAD_POS = ("HeadTranslationX", "HeadTranslationY", "HeadTranslationZ")
HEAD_SWITCH = "HeadControlSwitch"
HEAD = HEAD_ROT + HEAD_POS + (HEAD_SWITCH,)

SIDES = ("L", "R")
LOOK = ("Left", "Right", "Up", "Down")


def c(name: str) -> str:
    """The full curve name: "eyeBlinkL" -> "CTRL_expressions_eyeBlinkL" (full names pass through)."""
    return name if name.startswith(PREFIX) or name in HEAD else PREFIX + name


_CANON = {n.lower(): n for n in CURVES | set(HEAD)}


def canon(name: str) -> str:
    """A curve name as the engine listed it, in this module's spelling. Curve names are FNames (case-insensitive):
    5.8's MetaHuman face loops list "ctrl_expressions_eyeblinkl" for CTRL_expressions_eyeBlinkL (day 1). Names this
    module does not know pass through."""
    return _CANON.get(str(name).lower(), str(name))


def is_face_curve(name: str) -> bool:
    return name in CURVES or name in HEAD


def unknown(names) -> list:
    """The names in `names` that are not MetaHuman face curves (typos), each with its nearest valid name."""
    import difflib
    pool = sorted(CURVES | set(HEAD))
    bad = []
    for n in names:
        full = c(n)
        if full not in CURVES and full not in HEAD:
            near = difflib.get_close_matches(full, pool, n=3, cutoff=0.6)
            bad.append({"name": n, "did_you_mean": near})
    return bad


def group(prefix: str) -> list:
    """Every full curve name whose raw name starts with `prefix` ("eyeLook", "mouthCorner", "brow")."""
    return sorted(PREFIX + n for n in RAW if n.startswith(prefix))


def eye_look(direction: str, side: str) -> str:
    """CTRL_expressions_eyeLook{Left,Right,Up,Down}{L,R}."""
    return f"{PREFIX}eyeLook{direction}{side}"


def blink(side: str) -> str:
    return f"{PREFIX}eyeBlink{side}"


BLINKS = (blink("L"), blink("R"))
EYE_LOOK = tuple(eye_look(d, s) for s in SIDES for d in LOOK)
# the mouth region: lowered under a talking mouth so an expression does not fight the lip-sync
MOUTH = frozenset(n for n in CURVES if n[len(PREFIX):].startswith(("mouth", "jaw", "tongue", "teeth")))


class HeadSigns:
    """How the rig's head curves map to the character's frame: +1 or -1 per curve (see the module docstring), and
    the eye-look gains in degrees at full curve (1.0), and whether eyeLookLeft means the character's left. Defaults are a best guess until `perf.calibrate` measures the
    real rig; `measured` says which."""

    AXES = ("yaw", "pitch", "roll")

    def __init__(self, yaw: float = 1.0, pitch: float = 1.0, roll: float = 1.0, eye_deg: dict | None = None,
                 measured: bool = False, eye_flip: bool = False, curves: dict | None = None,
                 dead: list | None = None, yaw_bone: dict | None = None, turn_on: str = "Face",
                 yaw_gain: float = 1.0, yaw_table: list | None = None):
        self.yaw, self.pitch, self.roll = yaw, pitch, roll
        # how far the turn curve turns the head per unit, as a fraction of a degree (perf.calibrate's turn_strength):
        # r4 (box), HeadRoll turns the 5.8 faces ~0.35 deg per unit, so to_rig writes the turn at 1/gain
        self.yaw_gain = yaw_gain
        # the turn curve's measured response [[units, deg (+ = the character's left)], ...] at several amplitudes
        # (perf.calibrate, r4): the box's HeadRoll is not linear (his turned 50 deg at 140 units and 11 at 185; hers
        # 95 at 70 where a 10-unit probe said 0.46 deg per unit), so a turn is written through this table
        self.yaw_table = sorted([float(u), float(d)] for u, d in yaw_table) if yaw_table else None
        # which head curve turns the head about each of the character's axes. The names need not say it: on the
        # reel's MetaHumans HeadYaw nods, HeadRoll turns and HeadPitch tilts (REEL_PERF.md, measured on the head bone)
        self.curves = {"yaw": "HeadYaw", "pitch": "HeadPitch", "roll": "HeadRoll", **(curves or {})}
        if sorted(self.curves.values()) != sorted(HEAD_ROT) or set(self.curves) != set(self.AXES):
            raise ValueError(f"head curves {self.curves}: each of yaw, pitch, roll needs one of {list(HEAD_ROT)}")
        self.dead = list(dead or [])  # head curves that move nothing on this rig (perf.calibrate)
        # when no curve turns the head (5.8's MetaHuman face: HeadRoll is dead), each neck/head bone's local axis and
        # sign that turn it to the character's left {bone: [axis, sign]}: perf.face writes the turn on those bones
        self.yaw_bone = {b: list(v) for b, v in yaw_bone.items()} if yaw_bone else None
        # whose bones those are: "Face", or "Body" when the face takes its neck and head from the body (5.8's
        # MetaHuman: the face's own neck tracks move nothing, round 3); a Body turn is written by perf.turn_head
        self.turn_on = turn_on
        self.eye_flip = eye_flip  # True when eyeLookLeft turns the eye to the character's right
        # degrees an eye turns at eyeLook* = 1.0: a guess (MetaHuman's eyes reach roughly 30-40 deg); gaze_lock and
        # perf.calibrate measure it per rig
        self.eye_deg = {"Left": 35.0, "Right": 35.0, "Up": 25.0, "Down": 30.0, **(eye_deg or {})}
        self.measured = measured

    def turns_by_bone(self) -> bool:
        """No head curve turns this head: the turn goes on the neck and head bones (yaw_bone)."""
        return self.curves["yaw"] in self.dead and bool(self.yaw_bone)

    def to_json(self) -> dict:
        return {"yaw": self.yaw, "pitch": self.pitch, "roll": self.roll, "eye_deg": dict(self.eye_deg),
                "measured": self.measured, "eye_flip": self.eye_flip, "curves": dict(self.curves), "dead": list(self.dead),
                "yaw_bone": self.yaw_bone, "turn_on": self.turn_on, "yaw_gain": self.yaw_gain,
                "yaw_table": self.yaw_table}

    def axes(self):
        """(curve name, axis, sign) for the three head curves."""
        return [(self.curves[k], k, getattr(self, k)) for k in self.AXES]

    def _branch(self, side: float) -> list:
        """The table from 0 out to one side while the turn keeps growing that way: [(units, deg)], |deg| rising."""
        pts = [p for p in self.yaw_table if p[0] * side > 0]
        pts.sort(key=lambda p: abs(p[0]))
        out = [(0.0, 0.0)]
        for u, d in pts:
            if d * side <= out[-1][1] * side:
                break
            out.append((u, d))
        return out

    def turn_units(self, deg: float) -> float:
        """The turn curve's value for a head turn of `deg` (+ = left): through yaw_table (clamped to the most it
        reached), else sign / gain."""
        if not self.yaw_table:
            return self.yaw * deg / self.gain("yaw")
        for side in (1.0, -1.0):
            br = self._branch(side)
            if deg * side >= 0 and len(br) > 1 and br[-1][1] * side > 0:
                if deg * side >= br[-1][1] * side:
                    return br[-1][0]
                for (u0, d0), (u1, d1) in zip(br, br[1:]):
                    if deg * side <= d1 * side:
                        return u0 + (u1 - u0) * (deg - d0) / (d1 - d0)
        return 0.0

    def turn_deg(self, units: float) -> float:
        """The head turn (deg, + = left) a turn curve value gives: the inverse of turn_units."""
        if not self.yaw_table:
            return self.yaw * self.gain("yaw") * units
        side = 1.0 if units >= 0 else -1.0
        br = sorted(self._all_side(side), key=lambda p: abs(p[0]))
        if abs(units) >= abs(br[-1][0]):
            return br[-1][1]
        for (u0, d0), (u1, d1) in zip(br, br[1:]):
            if abs(units) <= abs(u1):
                return d0 + (d1 - d0) * (units - u0) / (u1 - u0)
        return 0.0

    def _all_side(self, side: float) -> list:
        return [(0.0, 0.0)] + [tuple(p) for p in self.yaw_table if p[0] * side > 0]

    def gain(self, key: str) -> float:
        """Degrees the head turns per unit of `key`'s curve (only the turn is measured; the others 1)."""
        return self.yaw_gain if key == "yaw" and self.curves["yaw"] not in self.dead else 1.0

    @classmethod
    def from_json(cls, d: dict | None) -> "HeadSigns":
        d = d or {}
        return cls(d.get("yaw", 1.0), d.get("pitch", 1.0), d.get("roll", 1.0), d.get("eye_deg"), d.get("measured", False),
                   d.get("eye_flip", False), d.get("curves"), d.get("dead"), d.get("yaw_bone"), d.get("turn_on", "Face"),
                   d.get("yaw_gain", 1.0), d.get("yaw_table"))


LIVE_CM = 0.05  # 10 degrees of head turn moves the eyes over a centimetre: under this a curve does nothing


def head_axes(resp: dict) -> dict:
    """{axis: curve} from each head curve's measured response {curve: {"yaw", "pitch", "roll"}} (cm at the eyes). A tilt
    (roll) is the one curve that changes the eyes' height difference; it also moves them sideways, so sideways motion
    alone cannot name the turn. Of the other two, the one that moves the eyes up or down more nods (pitch).

    A curve that moves nothing (round 3, the box: HeadRoll on her 5.8 face) gets the axis left over, so writing it is
    harmless; the live ones are named by what they do. Raises ValueError when fewer than two curves move, or when two
    live curves do the same thing."""
    live = [c for c in resp if max(abs(v) for v in resp[c].values()) >= LIVE_CM]
    dead = [c for c in resp if c not in live]
    if len(live) < 2:
        raise ValueError(f"only {live} of the head curves move the head")
    if not dead:
        roll = max(resp, key=lambda c: abs(resp[c]["roll"]))
        rest = [c for c in resp if c != roll]
        pitch = max(rest, key=lambda c: abs(resp[c]["pitch"]))
        yaw = next(c for c in rest if c != pitch)
        return {"yaw": yaw, "pitch": pitch, "roll": roll}

    def kind(c):
        r = {k: abs(v) for k, v in resp[c].items()}
        if r["roll"] >= 0.3 * max(r["yaw"], r["pitch"]):  # turns and nods leave the eyes level
            return "roll"
        return "pitch" if r["pitch"] > r["yaw"] else "yaw"
    out = {}
    for c in live:
        k = kind(c)
        if k in out:
            raise ValueError(f"{out[k]} and {c} both {k} the head: {resp}")
        out[k] = c
    for k, c in zip([k for k in ("roll", "pitch", "yaw") if k not in out], dead):
        out[k] = c
    return {k: out[k] for k in ("yaw", "pitch", "roll")}
