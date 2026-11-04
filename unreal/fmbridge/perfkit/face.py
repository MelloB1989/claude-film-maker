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
from .rig import BLINKS, HEAD_ROT, HeadSigns

LAYERS = ("head", "eyes", "blinks", "expressions", "brows", "nods")


def _shift(d) -> G.Shift:
    if isinstance(d, G.Shift):
        return d
    return G.Shift(d["t"], d.get("yaw", 0.0), d.get("pitch", 0.0), d.get("dist_cm", 200.0), d.get("scan"),
                   d.get("head"), d.get("label", ""))


def _nod(d) -> H.Nod:
    if isinstance(d, H.Nod):
        return d
    return H.Nod(d["t"], d.get("kind", "yes"), d.get("depth_deg"), d.get("count", 1), d.get("speed", 1.0))


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
          layers=LAYERS, solver_head: str = "soften", blink_mode: str = "replace", blink_state="talk",
          signs: HeadSigns | None = None, energy: float = 1.0, mouth_mix: float = 0.5, brow_chance: float = 0.55,
          beat_every: int = 1, seed: int = 0, rate: float = 60.0, tol: float = 0.003) -> dict:
    """Compose a face performance from t0 to t1 (s). See the module docstring; arguments:

    base: the animation's own curves (a speech solve). shifts: gaze shifts [{"t", "yaw", "pitch", "dist_cm", "scan",
    "head"}] in the character's frame (degrees). lead: "eyes" (physiological: eyes jump, head follows) or "head".
    head_style: head.Style fields (gain, rest_roll_deg, micro_deg, ...). nods: [{"t", "kind", "depth_deg",
    "count"}]. tilts: [{"t", "until", "roll_deg"}]. moods: [{"t0", "t1", "mood", "intensity"}]. expressions:
    [{"preset", "t", "until", "intensity", "asym", ...}]. emphasis: [(t, strength)] (stressed words: beat nods and
    brow flashes). phrase_ends: [t] (blinks). speech: t -> loudness 0..1 (livelier head, quieter smile on a talking
    mouth). layers: which of LAYERS to make. solver_head: what to do with the base's head curves: "soften"
    (low-passed, 60%, under ours), "keep" (as is, under ours), "replace" (ours only). blink_mode: replace|keep|max.

    Returns {"curves": {name: (times, values)}, "plan": {...}, "report": metrics.report}."""
    base = base or {}
    signs = signs or HeadSigns()
    layers = set(layers)
    bad = layers - set(LAYERS)
    if bad:
        raise ValueError(f"unknown layers {sorted(bad)}; layers are {', '.join(LAYERS)}")
    if solver_head not in ("soften", "keep", "replace"):
        raise ValueError(f"solver_head {solver_head!r}: soften, keep or replace")
    style = H.Style.from_json({"seed": seed, **(head_style or {})})
    sh = [_shift(s) for s in shifts]
    plan = G.GazePlan(sh, start=start_gaze, lead=lead, head_gain=style.gain, energy=energy, seed=seed)
    nod_list = [_nod(n) for n in nods]
    if "nods" in layers and emphasis:
        nod_list += H.beats_from_emphasis(emphasis, seed=seed, every=beat_every)
    tilt_list = [_tilt(t) for t in tilts]
    out: dict = {}
    head = H.compose(t0, t1, plan, nod_list if "nods" in layers else [], tilt_list, style, speech, rate)
    solver = H.from_rig({n: base[n] for n in HEAD_ROT if n in base}, signs)
    if solver and solver_head != "replace":
        for key in ("yaw", "pitch", "roll"):
            if key not in solver:
                continue
            st, sv = solver[key]
            if solver_head == "soften":
                st, sv = H.naturalize(st, sv, cutoff_hz=2.0, gain=0.6, rate=rate)
            mean = sum(sv) / len(sv) if sv else 0.0
            add = C.resample(st, [v - mean for v in sv], head["times"])
            head[key] = [a + b for a, b in zip(head[key], add)]
    if "head" in layers:
        out.update(H.to_rig(head, signs, tol_deg=0.02))
    if "eyes" in layers:
        ey = E.solve(plan, head, micro_deg=0.35, seed=seed)
        eye_curves = E.to_rig(ey, signs, tol=tol)
        out.update({k: v for k, v in eye_curves.items() if not k.startswith("lidfollow:")})
    else:
        ey = None
    blink_list = []
    if "blinks" in layers:
        blink_list = B.plan(t0, t1, blink_state, plan.events, phrase_ends, emphasis, seed=seed)
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
                 if solver else None, "signs": signs.to_json()}
    return {"curves": out, "plan": plan_json, "report": M.report(final, signs)}
