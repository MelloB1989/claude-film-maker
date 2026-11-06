"""A face performance from its parts: the head (gaze turns, nods, tilts, micro-motion), the eyes (VOR, darts,
vergence), blinks and expression layers, laid over an animation's own curves (a speech solve's lip-sync, or nothing).

`build(...)` is the whole of `perf.face` without the engine: it takes the base curves as {name: (times, values)}
and returns the curves to write (complete values for every curve it touches; the rest of the animation is left
alone), the plan it followed (shifts, blinks, events) and the naturalness report.
"""
from __future__ import annotations

from . import blinks as B
from . import curves as C
from . import expressions as X
from . import eyes as E
from . import gaze as G
from . import head as H
from . import metrics as M
from . import stability as ST
from .rig import BLINKS, HEAD_POS, HEAD_ROT, HeadSigns

LAYERS = ("head", "eyes", "blinks", "expressions", "brows", "nods")
SOLVER_HEAD = ("replace", "clean", "soften", "keep")
BLINK_HEAD = ("still", "free")


def nod_span(n: H.Nod) -> tuple:
    """(t0, t1) of a nod's drop and return (s): where a blink would ride it."""
    return (n.t - 0.05, n.t + (0.45 * n.count + 0.1) / n.speed)


def solve_blinks(base: dict) -> list:
    """[(t0, t1)] of the blinks in a solve's own eyeBlink curves (either eye): its head nods with them."""
    out = []
    for n in BLINKS:
        if n in base and len(base[n][0]) > 1:
            t, v = base[n]
            g = C.grid(t[0], t[-1], 120.0)
            out += [(a, b) for a, b, _ in B.detect(g, C.resample(t, v, g), 0.5)]
    return sorted(out)


def _shift(d) -> G.Shift:
    if isinstance(d, G.Shift):
        return d
    return G.Shift(d["t"], d.get("yaw", 0.0), d.get("pitch", 0.0), d.get("dist_cm", 200.0), d.get("scan"),
                   d.get("head"), d.get("label", ""))


def _nod(d) -> H.Nod:
    if isinstance(d, H.Nod):
        return d
    return H.Nod(d["t"], d.get("kind", "nod"), d.get("depth_deg"), d.get("count", 1), d.get("speed", 1.0))


def _tilt(d) -> H.Tilt:
    if isinstance(d, H.Tilt):
        return d
    return H.Tilt(d["t"], d["until"], d.get("roll_deg", 5.0), d.get("pitch_deg", 0.0), d.get("yaw_deg", 0.0),
                  d.get("ease_s", 0.5))


def _event(d) -> X.Event:
    if isinstance(d, X.Event):
        return d
    keys = ("intensity", "attack_s", "release_s", "sustain", "asym", "alive", "lead_s")
    return X.Event(d.get("preset") or d["name"], d["t"], d.get("until", d["t"] + d.get("duration_s", 1.0)),
                   **{k: d[k] for k in keys if k in d})


def build(t0: float, t1: float, *, base: dict | None = None, shifts: list = (), start_gaze=(0.0, 0.0),
          lead: str = "eyes", head_style: dict | None = None, nods: list = (), tilts: list = (), moods: list = (),
          expressions: list = (), emphasis: list = (), phrase_ends: list = (), speech=None,
          layers=LAYERS, solver_head: str = "replace", blink_mode: str = "replace", blink_state="talk",
          signs: HeadSigns | None = None, energy: float = 1.0, mouth_mix: float = 0.5, brow_chance: float = 0.55,
          beat_every: int = 1, seed: int = 0, rate: float = 60.0, tol: float = 0.003,
          avoid_blinks: list = (), blink_head: str = "still") -> dict:
    """Compose a face performance from t0 to t1 (s). See the module docstring; arguments:

    base: the animation's own curves (a speech solve). shifts: gaze shifts [{"t", "yaw", "pitch", "dist_cm", "scan",
    "head"}] in the character's frame (degrees). lead: "eyes" (physiological: eyes jump, head follows) or "head".
    head_style: head.Style fields (gain, rest_roll_deg, micro_deg, ...). nods: [{"t", "kind", "depth_deg",
    "count"}]. tilts: [{"t", "until", "roll_deg"}]. moods: [{"t0", "t1", "mood", "intensity"}]. expressions:
    [{"preset", "t", "until", "intensity", "asym", ...}]. emphasis: [(t, strength)] (stressed words: beat nods and
    brow flashes). phrase_ends: [t] (blinks). speech: t -> loudness 0..1 (livelier head, quieter smile on a talking
    mouth). layers: which of LAYERS to make. solver_head: what to do with the base's head curves (its
    HeadYaw/Pitch/Roll and HeadTranslationX/Y/Z): "replace" (the default: dropped, the head is ours alone),
    "clean" (spikes removed, every blink window of the solve's and ours bridged, 1.5 Hz, 50%, under ours), "soften"
    (2 Hz, 60%, under ours: round 4's, which kept the solve's blink-nods), "keep" (as is). blink_mode:
    replace|keep|max. blink_head: "still" (the default: no blink moves the head: chin dips of turns that carry a
    blink are dropped, blinks keep off nods, and a last pass bridges any pitch/roll departure inside a blink window)
    or "free" (round 4's: whatever coincides, stays).

    Returns {"curves": {name: (times, values)}, "plan": {...}, "report": metrics.report}."""
    base = base or {}
    signs = signs or HeadSigns()
    layers = set(layers)
    bad = layers - set(LAYERS)
    if bad:
        raise ValueError(f"unknown layers {sorted(bad)}; layers are {', '.join(LAYERS)}")
    if solver_head not in SOLVER_HEAD:
        raise ValueError(f"solver_head {solver_head!r}: {', '.join(SOLVER_HEAD)}")
    if blink_head not in BLINK_HEAD:
        raise ValueError(f"blink_head {blink_head!r}: {', '.join(BLINK_HEAD)}")
    still = blink_head == "still"
    style = H.Style.from_json({"seed": seed, **(head_style or {})})
    sh = [_shift(s) for s in shifts]
    plan = G.GazePlan(sh, start=start_gaze, lead=lead, head_gain=style.gain, energy=energy, seed=seed)
    nod_list = [_nod(n) for n in nods]
    if "nods" in layers and emphasis:
        nod_list += H.beats_from_emphasis(emphasis, seed=seed, every=beat_every)
    tilt_list = [_tilt(t) for t in tilts]
    out: dict = {}
    head_nods = nod_list if "nods" in layers else []
    blink_list = []
    if "blinks" in layers:
        avoid = list(avoid_blinks)
        if still:  # a blink on a nod reads as the blink nodding the head (round 4): blinks keep off the nods' drops
            avoid += [nod_span(n) for n in head_nods if n.axis() == "pitch"]
        blink_list = B.plan(t0, t1, blink_state, plan.events, phrase_ends, emphasis, seed=seed, avoid=avoid)
    windows = [(b.t, b.end()) for b in blink_list]
    if still and windows:  # a big turn's chin dip under the gaze blink that comes with it: the blink "nods"
        plan.dips = [d for d in plan.dips if not any(d[0] - ST.PRE < w1 and w0 < d[0] + d[1] * 1.2 + ST.POST
                                                     for w0, w1 in windows)]
    head = H.compose(t0, t1, plan, head_nods, tilt_list, style, speech, rate)
    solver = H.from_rig({n: base[n] for n in HEAD_ROT if n in base}, signs)
    solver_info = None
    if solver and solver_head != "replace":
        solver_blinks = solve_blinks(base)
        solver_info = {"blinks": len(solver_blinks), "spikes": 0, "bridged": 0}
        for key in ("yaw", "pitch", "roll"):
            if key not in solver:
                continue
            st, sv = solver[key]
            if solver_head == "soften":
                st, sv = H.naturalize(st, sv, cutoff_hz=2.0, gain=0.6, rate=rate)
            elif solver_head == "clean":  # yaw keeps its turns: a blink-nod is pitch and roll
                st, sv, info = ST.clean(st, sv, solver_blinks + windows if key != "yaw" else (), rate=rate)
                solver_info["spikes"] += info["spikes"]
                solver_info["bridged"] += info["bridged"]
            mean = sum(sv) / len(sv) if sv else 0.0
            add = C.resample(st, [v - mean for v in sv], head["times"])
            head[key] = [a + b for a, b in zip(head[key], add)]
    guard = 0
    if still and windows:  # the last word: no pitch or roll departure inside a blink window, whatever made it
        for key in ("pitch", "roll"):
            head[key], n = ST.still_through_blinks(head["times"], head[key], windows)
            guard += n
    if "head" in layers:
        out.update(H.to_rig(head, signs, tol_deg=0.02))
        for n in HEAD_POS:  # the solve's head translation: dropped with its rotation, else cleaned like it
            if n not in base or not base[n][0]:
                continue
            bt, bv = base[n]
            if solver_head == "replace":
                out[n] = ([bt[0], bt[-1]], [0.0, 0.0])
            elif solver_head in ("clean", "soften"):
                soft = solver_head == "soften"
                g, v, _ = ST.clean(bt, bv, [] if soft else windows + solve_blinks(base), rate=rate,
                                   cutoff_hz=2.0 if soft else 1.5, gain=0.6 if soft else 0.5)
                out[n] = C.reduce(g, v, 0.01)
    if "eyes" in layers:
        ey = E.solve(plan, head, micro_deg=0.35, seed=seed)
        eye_curves = E.to_rig(ey, signs, tol=tol)
        out.update({k: v for k, v in eye_curves.items() if not k.startswith("lidfollow:")})
    else:
        ey = None
    if "blinks" in layers:
        ours = B.to_curves(blink_list, t0, t1)
        out.update(B.merge({k: base[k] for k in BLINKS if k in base}, ours, blink_mode))
    events = []
    if "expressions" in layers:
        events += X.mood_events(list(moods), seed=seed) + [_event(e) for e in expressions]
    if "brows" in layers and emphasis:
        events += X.brow_events(emphasis, seed=seed, chance=brow_chance)
    if events:
        layer = X.render(events, t0, t1, rate=30.0, seed=seed, speech=speech, mouth_mix=mouth_mix)
        for name, (t, v) in layer.items():
            if name in out:  # a layer over one of ours (a wince's blink): add
                tt = sorted(set(t) | set(out[name][0]))
                vv = [min(1.0, x) for x in C.combine([out[name], (t, v)], tt, "add")]
            elif name in base:  # over the base (lip-sync): add, then clamp
                bt, bv = base[name]
                tt = sorted(set(t) | set(bt))
                vv = [max(0.0, min(1.0, x)) for x in C.combine([(bt, bv), (t, v)], tt, "add")]
            else:
                tt, vv = t, v
            out[name] = C.reduce(tt, vv, tol)
    final = {**base, **out}
    plan_json = {"shifts": plan.events, "nods": [{"t": round(n.t, 3), "kind": n.kind, "depth_deg": round(n.depth_deg, 2)}
                                                 for n in nod_list],
                 "blinks": [b.to_json() for b in blink_list], "expressions": [
                     {"preset": e.preset if isinstance(e.preset, str) else "custom", "t": round(e.t, 3),
                      "until": round(e.until, 3), "intensity": round(e.intensity, 3)} for e in events],
                 "eyes_clipped_deg": ey["clipped_deg"] if ey else None, "lead": lead, "solver_head": solver_head
                 if solver else None, "solver": solver_info, "blink_head": blink_head, "blink_guard": guard,
                 "signs": signs.to_json()}
    return {"curves": out, "plan": plan_json, "report": M.report(final, signs)}
