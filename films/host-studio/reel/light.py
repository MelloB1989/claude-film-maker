"""The reel's light timeline: the day-to-night states of PLAN.md section 3 as data, keyed onto the reel's sequence.

One shared set of light keys moves the room DAY -> GOLDEN -> DUSK -> BLUE -> IGNITION -> NIGHT -> NIGHT+KEY ->
NIGHT-DIM, so every shot sits at its true time of day and no cut jumps in light. The level stays as studio.py builds
it (day): everything here is a track in the sequence (closing the sequence restores the studio and the stills).
rig.py first adds what the day build lacks (the night's downlights at 0, the night garden card at 0, the halo's wipe
material); run it once after every studio.py.

Each channel of light is a Curve: points [frame, value, ease] where `ease` shapes the change *into* that point
(`hold`: a step on that frame; `lin`; `in`, `out`, `inout`: eased; `pop`: eased in with a small overshoot, the
"switched on" feel). Curves are baked to keys here (every frame through a change, two keys around a step, nothing in
a hold), so the sequence plays exactly what this file says whatever Sequencer's tangents do.

    cd tools && uv run python ../films/host-studio/reel/light.py --check            # offline: the states' values
    cd tools && uv run python ../films/host-studio/reel/light.py --seq /Game/Reel/SEQ_Reel
    cd tools && uv run python ../films/host-studio/reel/light.py --test [--states DAY,IGNITION]  # Test_ stills

--test builds its own Test_agent-05_Light sequence and cameras, takes viewport stills of each state into
light_test/, and deletes the cameras and the sequence afterwards.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from shots import BEAT, CR_C, EYES_HER, EYES_HIM, MARK_HER, MARK_HIM, SH_L, SLAT_Y, WALL, bar  # noqa: E402

END = bar(27)  # 1560: one past the last frame
SH_C = SH_L - 75.0

# ------------------------------------------------------------------------------------------------ the states
# Each state's first frame, and the frame a test still of it is taken at (where the state reads best).
STATES = {  # name: (start, still frame)
    "DAY": (0, bar(2)),              # PLAN v2: V01
    "GOLDEN": (bar(4), bar(8, 1)),   # V02, V03
    "DUSK": (bar(9), bar(10, 3)),    # V04
    "BLUE": (bar(11), bar(12, 3)),   # V05
    "IGNITION": (bar(13), bar(13, 4) + 3),     # mid-ignition: k a r lit, m igniting
    "NIGHT": (bar(14), bar(15)),
    "NIGHT+KEY": (bar(17), bar(18)),
    "NIGHT-DIM": (bar(25), bar(26, 4)),
}

# studio.py's day and night values (studio.py builds the day; its night is what BLUE/NIGHT match)
DAY_SUN = dict(elevation=28.0, azimuth=-28.0, lux=30000.0, temperature=5100.0, sky=0.6)
NIGHT_SUN = dict(elevation=-8.0, lux=2.0, temperature=7500.0, sky=0.04)
WINDOW_NIGHT = (0.35, 0.47, 0.85)  # WindowSky's night colour (sRGB 0-1, as look.light takes it)
SUN_LOC = (0.0, 0.0, 500.0)        # look.sky's FM_Sun

# the night's recessed downlights (studio.py night), added at 0 by rig.py: label, loc, aim, candelas, pop frame
DOWN = [("DownCredenza", (WALL + 55, CR_C, 296), (WALL + 25, CR_C, 72.0), 15.0, bar(14, 1)),
        ("DownSlats", (WALL + 32, SLAT_Y, 296), (WALL + 4, SLAT_Y, 90), 16.0, bar(14, 2)),
        ("DownOlive", (WALL + 75, 205, 296), (WALL + 62, 205, 120), 9.0, bar(14, 3)),
        ("DownShelves", (WALL + 60, SH_C, 296), (WALL + 15, SH_C, 140), 3.5, bar(14, 4))]

# The halo: the letters k a r m a ignite on bar 13 beats 1, 2, 3, 4 and 4& (PLAN.md section 2). The wipe edge runs
# between the gaps of the glyphs, measured on props/out/karma_halo.png (U across the halo card, 0 = screen-left):
# k 0.05-0.22, a 0.25-0.375, r 0.40-0.53, m 0.545-0.765, a 0.79-0.94.
IGNITE = [bar(13, 1), bar(13, 2), bar(13, 3), bar(13, 4), bar(13, 4) + BEAT // 2]
GAPS = [0.0, 0.235, 0.388, 0.537, 0.778, 1.0]
HALO_CARD, HALO_LIGHTS, HALO_LIGHT = 2.5, 1.2, 1.2  # studio.py: SignHalo intensity, Halo0-8 candelas
WIPE = 10          # frames for a letter to come up (shortened when the next letter comes sooner)
# studio.py's Halo0-8 run evenly from 6 cm inside the sign's screen-right end (min Y) to 6 cm inside its left end;
# the halo card spans the letters' 100 cm plus 6 cm each side: light k sits at U = (56 - (-44 + 11 k)) / 112
LIGHT_U = [(56 - (-44 + 11 * k)) / 112 for k in range(9)]
LETTER_OF_LIGHT = [next(i for i in range(5) if GAPS[i] <= u < GAPS[i + 1]) for u in LIGHT_U]  # a a m m r r a k k

# the presenters' lights (channel 1), studio.py's night values, placed around FACE for a host at the origin
FACE = (8.0, 0.0, 172.0)
HOST = {  # label: (loc, aimed at (relative to FACE), candelas at night)
    "Key": ((140, 130, 215), (0, 0, 0), 5.5),
    "Fill": ((190, -125, 160), (0, 0, 0), 1.0),
    "HairLight": ((-85, 25, 258), (-8, 0, 14), 5.0),
    "RimWarm": ((-90, -105, 180), (-8, 0, -12), 3.0),
    "RimWindow": ((-90, 110, 185), (-8, 0, -12), 3.5),
    "EyeLight": ((214, 6, 186), (0, 0, 0), 0.5),
}
KEY_UP = bar(17, 3)  # his key light ramps up over 12 frames: the reveal of S13 (PLAN v2: S13 is bars 17-18)
# where the presenters' lights point, shot by shot: one face, or the midpoint of both in the two-shots (each switch
# falls on a cut, where no camera sees it)
FACE_HIM = (MARK_HIM[0] + FACE[0], MARK_HIM[1], EYES_HIM - 2)
FACE_HER = (MARK_HER[0] + FACE[0], MARK_HER[1], EYES_HER - 2)
BOTH = tuple((a + b) / 2 for a, b in zip(FACE_HIM, FACE_HER))
AIMS = [(bar(17), FACE_HIM),   # S13: him
        (bar(19), FACE_HIM),   # S15: him sharp in front; her soft behind, in the practicals and rims
        (bar(21), FACE_HER),   # S16: her
        (bar(23), BOTH)]       # S17, S18: both
# S08's terminal: the cursor (baked into labels.py's T_Label_Terminal) holds solid through the typing on beats 1, 1&
# and 2 of bar 10, then blinks: off on each &, on with a tick on beats 3 and 4 (SOUND.md f570, f585), on again at the
# cut. rig.py puts the terminal on a ScreenBlink material; its rectangle in UV is the cursor's (labels.terminal: U
# 0.686-0.729, V 0.376-0.620) plus its 6 px glow.
CURSOR_UV = dict(CursorU0=0.677, CursorU1=0.738, CursorV0=0.335, CursorV1=0.661)
BLINK = [(bar(10, 2) + 8, 0.0), (bar(10, 3), 1.0), (bar(10, 3) + 8, 0.0), (bar(10, 4), 1.0), (bar(10, 4) + 8, 0.0),
         (bar(11), 1.0)]
DIM = 0.7  # NIGHT-DIM: the practicals ease down 30% over bars 25-26; the halo holds


# --------------------------------------------------------------------------------------------------- curves
def ease(kind: str, t: float) -> float:
    if kind == "lin":
        return t
    if kind == "in":
        return t * t
    if kind == "out":
        return 1 - (1 - t) ** 2
    if kind == "inout":
        return t * t * (3 - 2 * t)
    if kind == "pop":  # ease-out-back: a quick rise that overshoots ~6% and settles (a lamp striking)
        c = 1.2
        return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2
    raise ValueError(kind)


@dataclass
class Curve:
    points: list  # [frame, value, ease]; the first point's ease is ignored; values are floats or tuples

    def at(self, f: float):
        ps = self.points
        if f <= ps[0][0]:
            return ps[0][1]
        for (f0, v0, _), (f1, v1, e) in zip(ps, ps[1:]):
            if f < f1:
                if e == "hold":
                    return v0
                return _mix(v0, v1, ease(e, (f - f0) / (f1 - f0)))
        return ps[-1][1]

    def keys(self) -> list:
        """The baked keys, [frame, value]: every frame through a change, the ends of a hold, two keys at a step."""
        ps = self.points
        out = {ps[0][0]: ps[0][1]}
        for (f0, v0, _), (f1, v1, e) in zip(ps, ps[1:]):
            if v0 == v1:
                out[f1] = v1
            elif e == "hold":
                out[f1 - 1], out[f1] = v0, v1
            else:
                for f in range(f0 + 1, f1 + 1):
                    out[f] = self.at(f) if f < f1 else v1
        return [[f, _round(v)] for f, v in sorted(out.items())]


def _mix(a, b, t):
    if isinstance(a, (tuple, list)):
        return tuple(x + (y - x) * t for x, y in zip(a, b))
    return a + (b - a) * t


def _round(v):
    return [round(x, 5) for x in v] if isinstance(v, (tuple, list)) else round(v, 5)


def C(*points) -> Curve:
    return Curve([list(p) if len(p) == 3 else [p[0], p[1], "inout"] for p in points])


@dataclass
class Track:
    label: str             # the actor
    kind: str              # float | color | material | transform
    prop: str              # the property (float, color), the material parameter (material); "" for transform
    curve: Curve
    slot: object = None    # material: the slot (index or name)
    aim: Curve | None = None  # transform: what the actor looks at (location in `curve`)
    note: str = field(default="", compare=False)


# ---------------------------------------------------------------------------------------------- the timeline
def tracks() -> list:
    g, d, b, ig, n = (STATES[s][0] for s in ("GOLDEN", "DUSK", "BLUE", "IGNITION", "NIGHT"))
    dim0 = STATES["NIGHT-DIM"][0]
    T = []
    add = lambda *a, **k: T.append(Track(*a, **k))  # noqa: E731

    # the sun: 28 deg in the morning, low and warm through GOLDEN, under the horizon by BLUE. Below 0 deg a
    # directional light would shine up through the floor, so its lux is near zero before it gets there.
    elev = C((0, DAY_SUN["elevation"]), (g, DAY_SUN["elevation"]), (d, 8.0), (b, -3.0, "lin"),
             (ig, NIGHT_SUN["elevation"]))
    T.append(Track("FM_Sun", "transform", "", C((0, SUN_LOC), (END, SUN_LOC)), aim=elev,
                   note="pitch = -elevation, yaw = azimuth"))
    add("FM_Sun", "float", "Intensity", C((0, 30000.0), (g, 30000.0), (d, 8000.0), (d + 60, 1500.0, "out"),
                                          (d + 110, 40.0, "lin"), (b, 2.0, "out")))
    add("FM_Sun", "float", "Temperature", C((0, 5100.0), (g, 5100.0), (d, 3200.0), (d + 120, 2400.0),
                                            (ig, NIGHT_SUN["temperature"])))
    add("FM_SkyLight", "float", "Intensity", C((0, 0.6), (g, 0.6), (d, 0.35), (b, 0.08), (ig, NIGHT_SUN["sky"])))
    # the window: daylight 6200 K, warming in GOLDEN, cooling to the night's blue through DUSK and BLUE. Temperature
    # multiplies the colour (use_temperature stays on), so the night blue is the colour over a neutral 6500 K.
    add("WindowSky", "float", "Intensity", C((0, 8.0), (g, 8.0), (d, 5.0), (b, 1.4), (ig, 0.35)))
    add("WindowSky", "float", "Temperature", C((0, 6200.0), (g, 6200.0), (d, 4300.0), (d + 90, 5600.0),
                                               (b, 6500.0)))
    add("WindowSky", "color", "LightColor", C((0, (1.0, 1.0, 1.0)), (d, (1.0, 1.0, 1.0)), (d + 90, (0.75, 0.8, 0.95)),
                                              (b, WINDOW_NIGHT)))
    add("RoomBounce", "float", "Intensity", C((0, 1.5), (g, 1.5), (d, 1.0), (b, 0.45), (ig, 0.3)))
    add("RoomBounce", "float", "Temperature", C((0, 4500.0), (g, 4500.0), (d, 3600.0), (ig, 2800.0)))
    # the garden outside: the day card fades out as the night card (rig.py, additive in front of it) fades in
    add("Outside", "material", "Intensity", C((0, 40.0), (g, 40.0), (d, 22.0), (b, 4.0), (ig, 0.0, "out")), slot=0)
    add("OutsideNight", "material", "Intensity", C((0, 0.0), (d + 60, 0.0), (b, 1.0, "in"), (ig, 3.0)), slot=0)
    add("Curtains", "material", "Glow", C((0, 0.25), (g, 0.25), (d, 0.15), (b, 0.05), (ig, 0.02)), slot="M_Sheer")
    # the air thickens a little for the downlights' cones
    add("FM_Fog", "float", "FogDensity", C((0, 0.0002), (d, 0.0002), (n, 0.0006)))
    # exposure opens up as the light goes: studio.py's day 8.3, its night 9.6
    add("FM_Post", "float", "Settings.AutoExposureBias", C((0, 8.3), (g, 8.3), (d, 8.8), (b, 9.2), (ig, 9.6)))

    # practicals: the shelf LEDs come up in DUSK, everything eases down 30% in NIGHT-DIM
    end_dim = bar(27)  # two bars
    for k in range(4):
        add(f"ShelfLed{k}", "float", "Intensity", C((0, 1.3), (d, 1.3), (b, 1.5), (dim0, 1.5), (end_dim, 1.5 * DIM)))
    add("CandleLight", "float", "Intensity", C((0, 0.1), (dim0, 0.1), (end_dim, 0.1 * DIM)))
    add("Terminal", "material", "Blink", C((0, 1.0), *((f, v, "hold") for f, v in BLINK)), slot="M_Label_Terminal")

    # the halo: off all day; the card is wiped on letter by letter (Reveal) and each letter's LEDs strike in turn
    add("SignHalo", "material", "Intensity", C((0, 0.0), (ig, HALO_CARD, "hold")), slot=0)
    reveal = [(0, 0.0), (ig - 1, 0.0, "hold")]
    for k, f in enumerate(IGNITE):
        dur = min(WIPE, (IGNITE[k + 1] - f) if k + 1 < len(IGNITE) else WIPE)
        reveal += [(f, GAPS[k], "hold"), (f + dur, GAPS[k + 1], "out")]
    add("SignHalo", "material", "Reveal", C(*_dedupe(reveal)), slot=0)
    for k, letter in enumerate(LETTER_OF_LIGHT):
        f = IGNITE[letter]
        add(f"Halo{k}", "float", "Intensity", C((0, 0.0), (f, 0.0), (f + WIPE, HALO_LIGHT, "pop")))

    # the downlights pop on, one per beat of bar 14 (an LED driver: three frames)
    for label, _, _, cd, f in DOWN:
        add(label, "float", "Intensity", C((0, 0.0), (f, 0.0), (f + 3, cd, "out"), (dim0, cd), (end_dim, cd * DIM)))

    # the presenters' lights: off until S13; hair and rims first (him a silhouette against the halo), then the key,
    # fill and eye light come up together over 12 frames on bar 17 beat 3
    for label, (_, _, cd) in HOST.items():
        first = bar(17) if label in ("HairLight", "RimWarm", "RimWindow") else KEY_UP  # S13's first frame or KEY_UP
        ramp = "hold" if first < KEY_UP else "out"
        pts = [(0, 0.0), (first, cd, ramp)] if ramp == "hold" else [(0, 0.0), (first, 0.0), (first + 12, cd, ramp)]
        add(label, "float", "Intensity", C(*pts))
        add(label, "transform", "", *_aim_curves(label))
    add("Key", "float", "Temperature", C((0, 4300.0), (END, 4300.0)))
    return T


def _dedupe(points):
    """Points on the same frame: the first is kept (a hold onto the value a change just reached adds nothing)."""
    out = []
    for p in points:
        if out and out[-1][0] == p[0]:
            continue
        else:
            out.append(p)
    return out


def _aim_curves(label: str):
    """A host light's location and aim, shot by shot: moved with its subject (keeping its angle to the face), held,
    switched on the cut."""
    loc, at, _ = HOST[label]
    locs, aims = [], []
    for k, (f, face) in enumerate(AIMS):
        delta = [face[i] - FACE[i] for i in range(3)]
        p = tuple(loc[i] + delta[i] for i in range(3))
        a = tuple(face[i] + at[i] for i in range(3))
        locs.append((f if k else 0, p, "hold"))
        aims.append((f if k else 0, a, "hold"))
    locs.append((END, locs[-1][1], "hold"))
    aims.append((END, aims[-1][1], "hold"))
    return C(*locs), None, C(*aims)


# ------------------------------------------------------------------------------------------- to the sequence
def payload(t: Track) -> tuple:
    """The R1 op and its arguments for one track (without the sequence path)."""
    if t.kind == "float":
        return "seq.key_float", dict(label=t.label, prop=t.prop, keys=_lin(t.curve.keys()))
    if t.kind == "color":
        return "seq.key_color", dict(label=t.label, prop=t.prop, keys=_lin(t.curve.keys()))
    if t.kind == "material":
        return "seq.key_material", dict(label=t.label, param=t.prop, slot=t.slot, keys=_lin(t.curve.keys()))
    if t.kind == "transform":
        frames = sorted({k[0] for k in t.curve.keys()} | {k[0] for k in t.aim.keys()})
        keys = []
        for f in frames:
            loc, aim = t.curve.at(f), t.aim.at(f)
            if t.label == "FM_Sun":  # the sun's aim is its elevation
                keys.append([f, list(loc), {"pitch": -aim, "yaw": DAY_SUN["azimuth"], "roll": 0.0}, "linear"])
            else:
                keys.append([f, list(loc), list(aim), "linear"])
        return "seq.key_transform", dict(label=t.label, keys=keys)
    raise ValueError(t.kind)


def _lin(keys):
    """Baked keys play linearly between themselves (a hold's two ends are equal: flat)."""
    return [k + ["linear"] for k in keys]


def apply(seq: str, only: set | None = None) -> list:
    from filmtools.unreal import client
    done = []
    for t in tracks():
        if only and t.label not in only:
            continue
        name, args = payload(t)
        res = client.op(name, path=seq, **args)
        if not res.get("ok"):
            raise SystemExit(f"{name} {t.label} {t.prop}: {res.get('error', '')}{res.get('stdout', '')}")
        done.append((t.label, t.prop or "transform", len(args["keys"])))
    return done


# -------------------------------------------------------------------------------------------------- checking
def table(frames: dict) -> str:
    """The value of every channel at each of `frames` ({name: frame}): the states, offline."""
    rows, names = [], list(frames)
    for t in tracks():
        if t.kind == "transform":
            if t.label != "FM_Sun":
                continue
            vals = [f"{t.aim.at(f):.1f}deg" for f in frames.values()]
            name = "FM_Sun elevation"
        else:
            vals = [_fmt(t.curve.at(f)) for f in frames.values()]
            name = f"{t.label} {t.prop}"
        rows.append([name] + vals)
    w = [max(len(r[i]) for r in rows + [["channel"] + names]) for i in range(len(names) + 1)]
    line = lambda r: "  ".join(c.ljust(w[i]) for i, c in enumerate(r))  # noqa: E731
    return "\n".join([line(["channel"] + [f"{k}@{f}" for k, f in frames.items()])] + [line(r) for r in rows])


def _fmt(v):
    if isinstance(v, (tuple, list)):
        return "(" + ",".join(f"{x:.2f}" for x in v) + ")"
    return f"{v:.4g}"


def check() -> list:
    """Sanity: every curve inside the reel, frames ascending, keys finite, the sun dark before it sets."""
    bad = []
    for t in tracks():
        for c in (t.curve, t.aim):
            if c is None:
                continue
            fs = [p[0] for p in c.points]
            if fs != sorted(fs) or len(set(fs)) != len(fs) or fs[0] < 0 or fs[-1] > END:
                bad.append(f"{t.label} {t.prop}: frames {fs}")
            for f, v in c.keys():
                for x in (v if isinstance(v, list) else [v]):
                    if not math.isfinite(x):
                        bad.append(f"{t.label} {t.prop}: {x} at {f}")
    sun = next(t for t in tracks() if t.label == "FM_Sun" and t.kind == "transform").aim
    lux = next(t for t in tracks() if t.label == "FM_Sun" and t.prop == "Intensity").curve
    for f in range(END):
        if sun.at(f) < 0.5 and lux.at(f) > 200:
            bad.append(f"the sun at {sun.at(f):.1f} deg still gives {lux.at(f):.0f} lux at f{f}")
            break
    return bad


# ------------------------------------------------------------------------------------------------ test stills
TEST = "agent-05"
TEST_SEQ = f"/Game/Test/Test_{TEST}_Light"
TEST_CAMS = {  # label: (loc, look-at, focal, aperture); the S02 wide and the S11 sign
    f"Test_{TEST}_Wide": ([255, -35, 150], [WALL, 15, 140], 28.0, 5.6),
    f"Test_{TEST}_Sign": ([-95, 15, 170], [WALL + 4, 25, 228], 40.0, 4.0),
}
REMOTE = r"C:\UEProjects\HostStudio\Saved\Previs\reel_light"
DEL_SEQ = """import unreal
LSE = unreal.LevelSequenceEditorBlueprintLibrary
if LSE.get_current_level_sequence():
    LSE.close_level_sequence()
result = unreal.EditorAssetLibrary.delete_asset({path!r})
"""


def test(states: list, out: Path, keep: bool = False, width: int = 1920) -> list:
    from filmtools.unreal import client

    def ok(res):
        if not res.get("ok"):
            raise SystemExit(res.get("stdout", "") + res.get("error", ""))
        return res.get("result")
    out.mkdir(parents=True, exist_ok=True)
    made = []
    try:
        ok(client.op("seq.new", path=TEST_SEQ, start=0, end=END, fps=24, replace=True))
        for label, (loc, at, focal, ap) in TEST_CAMS.items():
            ok(client.op("look.camera", label=label, loc=loc, look_at=at, focal=focal, aperture=ap, pilot=False))
            made.append(label)
        apply(TEST_SEQ)
        # a throwaway still first: the first evaluation after opening the sequence can miss the material tracks
        warm = rf"{REMOTE}\warmup.png"
        ok(client.op("seq.still", path=TEST_SEQ, frame=STATES[states[0]][1], camera=f"Test_{TEST}_Wide", out=warm,
                     width=640, height=360, settle=40))
        shots = []
        for s in states:
            f = STATES[s][1]
            cams = [f"Test_{TEST}_Wide"] + ([f"Test_{TEST}_Sign"] if s in ("BLUE", "IGNITION", "NIGHT") else [])
            for cam in cams:
                name = f"{s.replace('+', '_').replace('-', '_')}_{cam.rsplit('_', 1)[1]}_f{f}.png"
                remote = rf"{REMOTE}\{name}"
                ok(client.op("seq.still", path=TEST_SEQ, frame=f, camera=cam, out=remote, width=width,
                             height=width * 9 // 16, settle=40))
                client.pull(remote, str(out / name))
                shots.append(out / name)
                print(s, f, cam, flush=True)
    finally:
        if made:
            ok(client.op("level.delete", labels=made))
        if not keep:
            ok(client.exec_code(DEL_SEQ.format(path=TEST_SEQ)))
    return shots


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="offline: check the curves, print the states' values")
    ap.add_argument("--json", default="", help="offline: write every track's baked keys (the ops' payloads) here")
    ap.add_argument("--seq", default="", help="key the timeline onto this level sequence (R3's /Game/Reel/SEQ_Reel)")
    ap.add_argument("--only", default="", help="with --seq: only these actors (comma-separated labels)")
    ap.add_argument("--test", action="store_true", help="viewport stills of the states in a Test_ sequence")
    ap.add_argument("--states", default=",".join(STATES))
    ap.add_argument("--keep", action="store_true", help="with --test: keep the Test_ sequence")
    a = ap.parse_args()
    if a.check or not (a.seq or a.test or a.json):
        bad = check()
        print(table({k: v[1] for k, v in STATES.items()}))
        print("\n".join(bad) or f"ok: {len(tracks())} tracks, {sum(len(payload(t)[1]['keys']) for t in tracks())} keys")
        if bad:
            raise SystemExit(1)
    if a.json:
        Path(a.json).write_text(json.dumps([[*payload(t)] for t in tracks()], indent=0))
    if a.seq:
        for row in apply(a.seq, set(a.only.split(",")) if a.only else None):
            print(*row)
    if a.test:
        for p in test(a.states.split(","), HERE / "light_test", a.keep):
            print(p)


if __name__ == "__main__":
    main()
