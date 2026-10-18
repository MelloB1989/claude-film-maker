"""v3 audio mix: v2's song / voice / master chain, with the SFX re-aimed at v3's 3D transitions (edl.json `cuts`).

    PYTHONPATH=tools python -m filmtools.amv3.mix3 [--edl films/timeless/amv3/edl.json]
        [--out /home/nikhil/code/film-making/work/timeless_v3] [--lufs -14] [--tp -1] [--stems]

Writes `<out>/mix.wav` (48 kHz, 24-bit stereo, -14 LUFS, -1 dBTP), `<out>/cues3.csv` (every SFX layer, voice cue and
word, with frame, time, gain and why) and `<out>/mix3_report.json`; `--stems` also writes `<out>/mix3_stems/`
(music, voice, sfx and one SFX-only wav per transition, for auditioning).

What is kept from v2 (`filmtools.amv2.mix`, unchanged): the song 0-30 s, the three voice lines and their sidechain
ducking with the per-line auto balance (>= 4 dB over the bed), the raised-cosine song end, the loudness/limiter loop,
and every hit SFX that is not a transition cut (in-shot hits, the outro hits and booms, the drops' impact_boom +
sub_drop on 480 / 656 / 819).

What is new: per transition (type, window [w0, w1), cut f) a layered design built from `sfx3` synthesis:
- the motion layer swells through the attack and peaks ON the cut (the picture's smear), rising in pitch for a push,
  falling for a pull, panned with whips/rolls/cube turns;
- the impact layer sits on the cut frame (sub thump when the cut is on a hit, slap, impact, snap, thunder, glass);
- the tail layer carries the landing (air, debris, tinkle).
Reference study (`filmtools.amv3.analysis.ref_audio` on refs a/b/c): the references' cuts sit on the song's kick
(sub band +10 dB, 1-2 f after the cut) and their sweeteners lift the 3-12 kHz band only ~+4-8 dB over the song at the
cut (b's biggest swells +12-17 dB over 10-13 f). So the gains below keep each transition's SFX under the music and the
audit measures that lift per cut.

Every cue is placed so its `hit` sample falls on the start of its frame (frame f = f / fps s), as v2 did.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
import soundfile as sf

from filmtools.amv2 import mix as M2
from filmtools.amv3 import sfx3 as X

SR = M2.SR
ROOT = Path(__file__).resolve().parents[3]
OUT = Path("/home/nikhil/code/film-making/work/timeless_v3")

# v2 kit gains (dB rel. the kit file, every file peaks at -1 dBFS), reused for the v2 cues kept
G2 = M2.G
BIG_DROPS = M2.BIG_DROPS

# impact layers keep their gain (set to sit with the song's kick); every other layer of a transition is scaled by
# its calibrated trim
FIXED = {"thump", "impact", "slap", "thunder", "metal_slam", "debris"}

# transition types whose design carries its own impact on the cut (the v2 'hit' there is replaced)
OWN_IMPACT = {"flip", "cube", "slam", "symbiote", "lightning", "lens_shatter", "sling_ring", "web_wipe", "triptych",
              "text_fly"}


# ---------------------------------------------------------------- the cue plan

def _hits(E):
    return {int(f): s for f, s in E["hits"]}


def transition_cues(T: dict, E: dict) -> list[dict]:
    """The SFX layers of one CUTS entry. A cue: {name, f (the frame its hit lands on), db, why, cut, gen, kw} for a
    synthesized layer (`sfx3.<gen>(**kw)`), or {name, f, db, why, cut, kit} for a v2 kit file."""
    fps = E["fps"]
    hits = _hits(E)
    f, w0, w1, typ, p = T["f"], T["w0"], T["w1"], T["type"], T.get("p", {})
    pre, post = max((f - w0) / fps, 0.2), max((w1 - f) / fps, 0.15)
    cid = T["id"]
    out = []

    def syn(name, at, d, gen, why, cal=None, **kw):
        kw.setdefault("seed", f"{cid}:{name}:{at}")
        out.append({"name": name, "f": at, "db": d, "why": why, "cut": cid, "gen": gen, "kw": kw,
                    "cal": name not in FIXED if cal is None else cal})

    def kit(name, at, d, why):
        out.append({"name": name, "f": at, "db": d, "why": why, "cut": cid, "kit": name})

    on_hit = f in hits
    if typ == "open":                         # out of the dark: a slow, dark, falling swell into S01, then air
        at = w0 + 12
        syn("swell_open", at, -21, "swell", "open: pull back out of darkness", pre=0.45, post=0.5, f_from=2600, f_to=380,
            rise_db=30, curve=1.2)
        syn("air_tail", at, -27, "air_tail", "open: landing air", dur=0.8, f=5000)
    elif typ == "zt":
        push = p.get("mode") == "push"
        roll = float(p.get("roll", 0))
        swirl = max(-1.0, min(1.0, roll / 120.0))
        syn("swell_" + ("push" if push else "pull"), f, -14, "swell",
            f"zt {p.get('mode')}: reverse swell w0 -> cut, pitch {'rising' if push else 'falling'}",
            pre=pre, post=0.16, f_from=520 if push else 7000, f_to=5200 if push else 1300,
            rise_db=32, curve=1.5, pan_from=-0.7 * swirl, pan_to=0.7 * swirl)
        if on_hit:
            syn("thump", f, -17, "thump", f"zt on hit {hits[f]}: sub thump", f0=92 if push else 80, f1=38)
        syn("air_tail", f, -25, "air_tail", "zt landing air", dur=post + 0.25, f=6500 if push else 5000)
        for o in T.get("over", []):
            if o == "dome_shards":
                syn("glass_dome", f, -15, "glass", "dome_shards: glass burst at the camera", dur=1.1, count=170, tau=0.09)
                syn("debris", f, -24, "debris", "dome_shards: small bits", dur=0.9, count=50, tau=0.15, bright=1.6)
    elif typ == "whip":
        d = p.get("dir", "R")
        syn("swish_" + d, f, -12, "swish", f"whip {d}: swish panned with the whip", direction=d, dur=0.26, peak=0.14)
        syn("air_tail", f, -27, "air_tail", "whip landing air", dur=post + 0.15)
    elif typ in ("cube", "flip"):
        d = p.get("dir", p.get("hinge", "L"))
        span = {"L": (0.6, -0.6), "R": (-0.6, 0.6)}.get(d, (0.0, 0.0))
        up = d == "U"
        syn("mech_swoosh", f, -14, "swell", f"{typ} {d}: mechanical swoosh (rotation flutter)", pre=pre, post=0.2,
            f_from=330, f_to=2200 if up else 1500, rise_db=26, curve=1.2, air=0.25,
            flutter_hz=22 if typ == "cube" else 13, pan_from=span[0], pan_to=span[1])
        syn("slap", f, -15, "slap", f"{typ}: soft panel slap as the face lands", bright=1.0 if typ == "flip" else 0.8,
            body_hz=150 if typ == "flip" else 120)
    elif typ == "slam":
        syn("swell_slam", f, -16, "swell", "slam: dolly-in rush", pre=pre, post=0.08, f_from=500, f_to=3000,
            rise_db=26)
        syn("impact", f, -9, "impact", "slam: deep superhero-landing impact", dur=1.4, deep=1.1, crunch=0.7,
            debris_amt=0.6)
        syn("dust", f + 1, -20, "debris", "slam: debris / dust", dur=1.2, count=110, tau=0.3, bright=1.5)
    elif typ == "symbiote":
        dur = (w1 - w0) / fps + 0.5
        syn("goo", f, -10, "goo", "symbiote: viscous crawl + growl swelling, wet snap on the cut", dur=dur,
            snap=(f - w0) / fps)
    elif typ == "eye_tunnel":
        dur = (w1 - w0) / fps + 0.35
        pass_f = max((h for h in hits if w0 < h < w1), default=f - 1)
        out_f = w1 - 5
        syn("tunnel", w0, -11, "tunnel", f"eye_tunnel: tunnel wind + multiverse tones, doppler pass {pass_f}, "
            f"whoosh out peaking {out_f}", dur=dur, pass_t=(pass_f - w0) / fps, out_t=(out_f - w0) / fps)
        syn("swell_iris", w0, -18, "swell", "eye_tunnel: the push into the iris (continues C07)", pre=0.2, post=0.3,
            f_from=1500, f_to=6000, rise_db=20)
    elif typ == "lightning":
        syn("crackle_in", f, -17, "crackle", "lightning: electric crackle building into the strike",
            dur=(f - w0) / fps + 0.04, rate=(80, 500), swell_to=3.0, buzz=0.6)
        syn("thunder", f, -10, "thunder", "lightning: thunder crack on the strike")
        syn("crackle_out", f, -21, "crackle", "lightning: crackle dying out", dur=(w1 - f) / fps + 0.25,
            rate=(500, 60), swell_to=0.25, buzz=0.5)
    elif typ == "lens_shatter":
        syn("riser", f, -15, "riser", "lens_shatter: riser into THE DROP", dur=1.2)
        syn("glass", f, -9, "glass", "lens_shatter: the lens glass shatters (with the drop's impact_boom + sub_drop)",
            dur=1.6, count=340, tau=0.11)
        syn("shockwave", f, -14, "shockwave", "lens_shatter: shockwave whoosh past the camera", dur=0.8)
        syn("tinkle", f + 3, -21, "tinkle", "lens_shatter: glass tinkle tail through the landing", dur=2.0, count=45)
    elif typ == "sling_ring":
        dur = (w1 - w0) / fps + 0.4
        syn("sparks_swirl", f, -16, "sparks_swirl", "sling_ring: sparks circling, peaking on the cut", dur=dur,
            peak=(f - w0) / fps)
        X_hit = (f - w0) / fps
        syn("magic_whoosh", f, -15, "magic_whoosh", "sling_ring: magical (comb-tuned) whoosh through the ring",
            pre=X_hit, post=0.4, root=220.0)
        if on_hit:
            syn("thump", f, -17, "thump", f"sling_ring on hit {hits[f]}", f0=85, f1=40)
    elif typ == "layer":
        side, conf, src = layer_side(T, E)
        mode = p.get("mode", "keep")
        if mode == "keep":
            # A's subject flies at the lens and leaves on `side` ~2 f after the cut: a close, fast stereo pass
            sgn = {"R": 1, "L": -1}.get(side, 0)
            syn("whoosh_by_close", f + 1, -12, "whoosh_by", f"layer keep: subject passes the lens, exits {side} "
                f"({src})", pre=pre + 1 / fps, post=post + 0.15, pan_dir=sgn * conf, near=0.035, body_hz=1300,
                low=0.6)
            syn("air_swell", f, -19, "swell", "layer keep: soft air swell as B arrives behind", pre=pre, post=0.35,
                f_from=2500, f_to=7500, rise_db=18, curve=1.0, air=0.8)
        else:
            # B's subject sweeps in big and close from `side` and crosses: a big pass-by from that side
            sgn = {"L": 1, "R": -1}.get(side, 0)               # from the left = pans left -> right
            syn("whoosh_by_sweep", f, -11, "whoosh_by", f"layer sweep: B's subject sweeps in from {side} ({src})",
                pre=pre + 0.1, post=post + 0.25, pan_dir=sgn * conf, near=0.09, body_hz=750, low=1.2)
            syn("air_swell", f + 2, -21, "swell", "layer sweep: B resolves behind (air)", pre=0.25, post=0.35,
                f_from=3000, f_to=7000, rise_db=16, curve=1.0, air=0.8)
    elif typ == "text_fly":
        syn("whoosh_by", f, -11, "whoosh_by", f"text_fly {p.get('title')}: letters rush past (stereo pass)",
            pre=pre, post=post + 0.2, pan_dir=1 if p.get("exit") != "dive" else -1)
        syn("air_tail", f, -25, "air_tail", "text_fly landing air", dur=post + 0.3)
    elif typ == "web_wipe":
        d = p.get("dir", "R")
        for k, at in enumerate((w0, w0 + 2, w0 + 4)):
            syn("thwip", at, -17 + k, "thwip", f"web_wipe: web strand {k + 1} shoots", direction=d)
        syn("rip", f, -12, "rip", "web_wipe: the strands yank S27 away (rip)", dur=0.42, peak=0.12, direction=d)
        if on_hit:
            syn("thump", f, -17, "thump", f"web_wipe on hit {hits[f]}", f0=80, f1=40)
    elif typ == "triptych":
        tp = E["triptych"]
        for k, pnl in enumerate(tp["panels"]):
            at = pnl["f"]
            side = (-0.6, 0.0, 0.6)[k]
            syn("swell_panel", at, -19, "swell", f"triptych {pnl['id']}: panel flies in", pre=0.2, post=0.06,
                f_from=700, f_to=3500, rise_db=24, pan_from=side, pan_to=side)
            syn("slap", at, -12, "slap", f"triptych {pnl['id']}: panel slam", bright=0.8, body_hz=110)
            if at not in BIG_DROPS and hits.get(at, 0) < 3.0:      # 785/794 keep v2's impact_boom (strong hits)
                syn("impact", at, -16, "impact", f"triptych {pnl['id']}: panel weight", dur=1.0, deep=0.9, crunch=0.4,
                    debris_amt=0.2)
        tf = tp.get("title", {}).get("f", 802)
        syn("metal_slam", tf, -11, "metal_slam", "triptych: TIMELESS lands (metallic slam)")
        end = w1                       # 819: everything shatters into the outro (fixed gains: v2's drop is there too)
        syn("swell_shatter", end, -12, "swell", "triptych: rush into the shatter", cal=False, pre=0.3, post=0.1,
            f_from=600, f_to=5000, rise_db=26)
        syn("glass_big", end, -8, "glass", "triptych: big glass shatter into the outro", cal=False, dur=1.9,
            count=420, tau=0.14)
        syn("shockwave", end, -13, "shockwave", "triptych: shards fly past", cal=False, dur=0.9)
    else:
        raise ValueError(f"{cid}: no sound design for transition type {typ!r}")
    return out


# Subject centroid x (plate px) the stage's `layer` module (blender/amv3/xfx/layer.py) uses to pick its side, measured on
# the VM mattes ($AMV3_DATA/mattes, 2026-10-18; queue job agent03-layer-probe): keep = A's subject at f - 1, sweep = B's
# subject at the landing frame. Used when the mattes are not on this machine.
MATTE_X = {("S02", 82): 1148, ("S06", 200): 975, ("S10", 305): 930, ("S31", 749): 1022}


def _matte_x(sid: str, f: int):
    d = OUT / "mattes" / sid
    if d.is_dir():
        have = sorted(int(n.name[2:7]) for n in d.glob("f_*.png") if n.name[2:7].isdigit())
        if have:
            from PIL import Image
            fr = min(have, key=lambda k: abs(k - f))
            a = np.asarray(Image.open(d / f"f_{fr:05d}.png").convert("L"), float)[::4, ::4]
            if a.sum() > 50 * 255:
                return float((a * np.arange(a.shape[1])[None, :]).sum() / a.sum() * 1920 / a.shape[1]), "matte"
    if (sid, f) in MATTE_X:
        return float(MATTE_X[(sid, f)]), "matte (VM)"
    return None, ""


def layer_side(T: dict, E: dict):
    """(side L|R|U|D, pan confidence 0.25-1, source) of a `layer` transition, following layer.py: keep exits on the side
    A's subject is nearer to; sweep enters from the side away from B's subject. An explicit p.dir / p.from wins. The
    reference x is the shot focus (else the frame centre), an approximation of the stage's hold-state centre, so a
    subject within ~40 px of it gets a narrow pan (the picture's side is uncertain there)."""
    p = T.get("p", {})
    mode = p.get("mode", "keep")
    given = p.get("dir") if mode == "keep" else (p.get("from") or p.get("dir"))
    if given:
        return given, 1.0, "edl"
    shots = {s["id"]: s for s in E["shots"]}
    if mode == "keep":
        sid, at = T["a"] if isinstance(T["a"], str) else T["a"]["id"], T["f"] - 1
    else:
        sid, at = T["b"] if isinstance(T["b"], str) else T["b"]["id"], min(T["w1"] - 1, T["f"] + 5)
    x, src = _matte_x(sid, at)
    foc = shots[sid].get("focus")
    if x is None:
        x, src = (foc[0], "focus") if foc else (960.0, "centre")
    ref = foc[0] if foc else 960.0
    dx = x - ref
    if mode == "keep":
        side = "L" if dx < 0 else "R"
    else:
        side = "R" if dx < 0 else "L"
    return side, float(np.clip(abs(dx) / 150.0, 0.25, 1.0)), f"{src} x {x:.0f} vs {ref:.0f}"


def edl_cues(E: dict) -> list[dict]:
    """Every SFX cue of the film: the transition layers + v2's hit cues that are not taken over by a transition."""
    hits = _hits(E)
    cues = []
    owned = set()                                        # hit frames whose impact a transition design carries
    for T in E["cuts"]:
        cs = transition_cues(T, E)
        cues += cs
        if T["type"] in OWN_IMPACT or any(c["name"] == "thump" for c in cs):
            owned.add(T["f"])
        if T["type"] == "triptych":
            owned |= {p["f"] for p in E["triptych"]["panels"]} | {E["triptych"].get("title", {}).get("f", 802)}
    for f, s in sorted(hits.items()):                    # v2's hit logic, verbatim, minus the owned hits
        if f in BIG_DROPS:
            cues.append({"name": "impact_boom", "f": f, "db": G2["impact_boom"] + (2 if f != 819 else 3), "why": "drop/hit (v2)", "cut": "", "kit": "impact_boom"})
            cues.append({"name": "sub_drop", "f": f, "db": G2["sub_drop"] + (0 if f != 480 else 2), "why": "drop/hit (v2)", "cut": "", "kit": "sub_drop"})
            continue
        if E["outro"]["f0"] < f < E["outro"]["f1"] or f in (785, 794):
            if s >= 3.0:
                cues.append({"name": "impact_boom", "f": f, "db": G2["impact_boom"] - 5, "why": "strong hit (v2)", "cut": "", "kit": "impact_boom"})
        if f in owned:
            continue
        cues.append({"name": "hit", "f": f, "db": -16 + 4 * (s - 1.6), "why": f"hit {s} (v2)", "cut": "", "kit": "hit"})
    return sorted(cues, key=lambda c: (c["f"], c["name"]))


# ---------------------------------------------------------------- calibration against the references

# target lift of the 3-12 kHz band at the cut (+-2 f), the transition's SFX over the song alone, dB. The references
# lift it ~+4-8 dB on ordinary cuts and up to +12-17 on their biggest moments (filmtools.amv3.analysis.ref_audio).
LIFT = {"open": 4.0, "zt": 5.0, "whip": 5.0, "cube": 4.5, "flip": 4.5, "slam": 4.0, "symbiote": 5.0,
        "eye_tunnel": 6.0, "text_fly": 8.0, "lightning": 8.0, "lens_shatter": 10.0, "sling_ring": 6.5,
        "web_wipe": 6.0, "triptych": 6.0, "layer": 5.0}
UNDER = -2.0            # a transition's SFX stay at least this far under the music across its window (broadband)
PUMP = 1.0              # ... and add at most this much master-limiter gain reduction over its window (no pumping)
TRIM = (-12.0, 18.0)    # dB range of the per-transition trim
AIR = (3000, 12000)


def _sos_air():
    import scipy.signal as sg
    return sg.butter(4, AIR, "band", fs=SR, output="sos")


def cut_spans(T: dict, fps: float, N: int):
    """(cut span, window span) in samples: +-2 f around the cut (the open: its peak frame), and [w0, w1)."""
    f = T["w0"] + 12 if T["type"] == "open" else T["f"]
    c0, c1 = max(0, int((f - 2) / fps * SR)), min(N, int((f + 3) / fps * SR))
    a0, a1 = int(T["w0"] / fps * SR), min(N, int(T["w1"] / fps * SR))
    return (c0, c1), (a0, a1)


def measure_cut(T: dict, music: np.ndarray, own: np.ndarray, fps: float, sos=None) -> dict:
    """Air-band lift at the cut of the transition's own SFX over the (ducked) music, and their broadband ratio over
    the window. music/own: mono."""
    import scipy.signal as sg
    sos = _sos_air() if sos is None else sos
    (c0, c1), (a0, a1) = cut_spans(T, fps, len(music))
    pad = int(0.05 * SR)
    lo, hi = max(0, c0 - pad), min(len(music), c1 + pad)
    bm = sg.sosfiltfilt(sos, music[lo:hi])[c0 - lo:c1 - lo]
    bo = sg.sosfiltfilt(sos, own[lo:hi])[c0 - lo:c1 - lo]
    pm, po = float(np.mean(bm ** 2)) + 1e-15, float(np.mean(bo ** 2))
    pt = float(np.mean((bm + bo) ** 2))
    win = 10 * np.log10((np.mean(own[a0:a1] ** 2) + 1e-15) / (np.mean(music[a0:a1] ** 2) + 1e-15))
    return {"air_lift_db": 10 * np.log10(pt / pm), "air_ratio": po / pm, "sfx_over_music_window_db": float(win)}


def calibrate(E: dict, adj: dict, log=print) -> dict:
    """Per-transition trims (dB on all its layers) so that each lifts the air band by LIFT[type] at its cut, never
    with its SFX less than UNDER dB under the music over its window. Solved in the power domain, 3 passes."""
    trims = {T["id"]: 0.0 for T in E["cuts"]}
    ceil = {T["id"]: TRIM[1] for T in E["cuts"]}
    fps = E["fps"]
    sos = _sos_air()
    for it in range(4):
        stems = build(E, adj, trims=trims)
        mus = stems["music"].mean(axis=1)
        pump = extra_reduction(E, stems)
        for T in E["cuts"]:
            own = stems["per_cut"].get(T["id"])
            if own is None:
                continue
            m = measure_cut(T, mus, own.mean(axis=1), fps, sos)
            want = 10 ** (LIFT[T["type"]] / 10) - 1                            # the SFX/music air power ratio
            d = 10 * np.log10(want / max(m["air_ratio"], 1e-6))
            d = min(d, UNDER - m["sfx_over_music_window_db"])                  # stay under the music
            if pump[T["id"]] > PUMP:                       # and off the limiter: a ceiling it never climbs over again
                ceil[T["id"]] = min(ceil[T["id"]], trims[T["id"]] - (pump[T["id"]] - PUMP) - 0.5)
            trims[T["id"]] = float(np.clip(trims[T["id"]] + d, TRIM[0], ceil[T["id"]]))
        log(f"  calibrate pass {it}: " + " ".join(f"{k}{v:+.1f}" for k, v in trims.items()))
    return trims


def limiter_gain_db(x: np.ndarray, g: float, ceil_db: float) -> np.ndarray:
    """Per-sample gain (dB, <= 0) that `amv2.mix.limit` applies to x * g."""
    y = M2.limit(x * g, ceil_db)
    a, b = np.abs(y).max(axis=1), np.abs(x * g).max(axis=1)
    r = np.ones(len(x))
    m = b > 1e-3
    r[m] = a[m] / b[m]
    return 20 * np.log10(np.clip(r, 1e-6, 1.0))


def extra_reduction(E: dict, stems: dict, target: float = -14.0, tp: float = -1.0) -> dict:
    """Per transition: how much more the master limiter pulls down (dB, max over [w0, w1)) with that transition's own
    layers than with everything else alone (music, voice and every other SFX, v2's drop booms included), at the
    master gain of the full mix. Computed on the window +-0.2 s."""
    mix = stems["music"] + stems["sfx"] + stems["voice"]
    g = M2.lin(target - M2.lufs(mix))
    fps, out, pad = E["fps"], {}, int(0.2 * SR)
    for T in E["cuts"]:
        own = stems["per_cut"].get(T["id"])
        if own is None:
            out[T["id"]] = 0.0
            continue
        a, b = int(T["w0"] / fps * SR), int(T["w1"] / fps * SR)
        lo, hi = max(0, a - pad), min(len(mix), b + pad)
        full = limiter_gain_db(mix[lo:hi], g, tp - 0.25)[a - lo:b - lo]
        rest = limiter_gain_db(mix[lo:hi] - own[lo:hi], g, tp - 0.25)[a - lo:b - lo]
        out[T["id"]] = float(max(0.0, rest.min() - full.min()))
    return out


# ---------------------------------------------------------------- the mix

def render_cue(c: dict, kit: dict, sfx_dir: Path):
    """(signal (n, 2), hit sample)."""
    if "kit" in c:
        K = kit[c["kit"]]
        return M2.read_stereo(sfx_dir / K["file"]).astype(np.float64), int(round(K["hit_offset"] * SR))
    return getattr(X, c["gen"])(**c["kw"])


def build(E: dict, adj=None, trims=None, log=print, _cache={}):
    """v2's build with the v3 SFX plan. adj: {voice name: (trim dB, extra duck dB)}; trims: {cut id: dB} on every
    layer of that transition (from `calibrate`). Synth renders are cached per cue."""
    adj, trims = adj or {}, trims or {}
    fps, dur = E["fps"], E["dur"]
    N = int(round(dur / fps * SR))
    sfx_dir, voice_dir = Path(E["sfx_dir"]), Path(E["voice_dir"])
    kit = json.loads((sfx_dir / "sfx_kit.json").read_text())
    fs = lambda f: int(round(f / fps * SR))                                  # noqa: E731

    song = M2.read_stereo(Path(E["song"]["file"]))
    t0 = int(round(E["song"].get("t0", 0.0) * SR))
    music = song[t0:t0 + N].astype(np.float64).copy()
    assert len(music) == N, "the song is shorter than the edit"

    meta = {v["name"]: v for v in json.loads((voice_dir / "voice_lines.json").read_text())}
    voice = np.zeros((N, 2))
    spans, lines = [], []
    for v in E["voice"]:
        y = M2.read_stereo(voice_dir / f"{v['name']}.wav").astype(np.float64) * M2.lin(v.get("db", 0))
        s = fs(v["f"])
        vt, xd = adj.get(v["name"], (0.0, 0.0))
        M2.place(voice, y, s, M2.lin(vt))
        w = meta[v["name"]]["words"]
        a, b = s + int((w[0]["t0"] - 0.12) * SR), s + int((w[-1]["t1"] + 0.30) * SR)
        spans.append((a, b, v.get("duck", -6) + xd))
        lines.append({**v, "trim": vt, "xduck": xd, "start": s, "end": min(N, s + len(y)), "words": w})
    env = M2.duck_env(N, spans)

    FADE = 1.4
    nf = int(FADE * SR)
    end = np.ones(N)
    end[N - nf:] = 0.5 + 0.5 * np.cos(np.pi * np.arange(nf) / (nf - 1))
    music *= (env * end)[:, None]

    cues = edl_cues(E)
    sfx = np.zeros((N, 2))
    per_cut = {}
    for c in cues:
        key = (c["name"], c["f"], json.dumps(c.get("kw", {}), sort_keys=True), c.get("kit", ""))
        if key not in _cache:
            _cache[key] = render_cue(c, kit, sfx_dir)
        y, h = _cache[key]
        c["start"] = fs(c["f"]) - h
        c["hit_sample"] = fs(c["f"])
        c["len"] = len(y)
        c["trim"] = trims.get(c["cut"], 0.0) if c.get("cal") else 0.0
        M2.place(sfx, y, c["start"], M2.lin(c["db"] + c["trim"]))
        if c["cut"]:
            buf = per_cut.setdefault(c["cut"], np.zeros((N, 2)))
            M2.place(buf, y, c["start"], M2.lin(c["db"] + c["trim"]))
    duck = (0.5 * (1 + env))[:, None]                                        # SFX duck half as deep as the music
    sfx *= duck
    per_cut = {k: v * duck for k, v in per_cut.items()}
    return {"N": N, "music": music, "voice": voice, "sfx": sfx, "cues": cues, "lines": lines, "env": env, "fps": fps,
            "per_cut": per_cut}


def auto_balance(E: dict, trims=None, log=print) -> dict:
    """v2's per-line voice balance: each line >= 4 dB over what is under it (trim <= +6 dB first, then duck deeper)."""
    adj = {}
    for _ in range(6):
        stems = build(E, adj, trims)
        r = {x["name"]: x["voice_over_bed_db"] for x in M2.voice_ratio(stems)}
        changed = False
        for v in E["voice"]:
            deficit = 4.0 - r[v["name"]]
            if deficit > 0.2:
                t, xd = adj.get(v["name"], (0.0, 0.0))
                use = min(deficit, 6.0 - t)
                adj[v["name"]] = (t + use, xd - 0.7 * (deficit - use) if deficit > use else xd)
                changed = True
        if not changed:
            break
    return adj


def write_cues(path: Path, E: dict, stems: dict):
    fps = stems["fps"]
    rows = []
    for c in stems["cues"]:
        src = c["kit"] + ".wav (v2 kit)" if "kit" in c else "sfx3." + c["gen"]
        rows.append(["sfx", c["name"], c["f"], round(c["f"] / fps, 4), round(c["start"] / SR, 4),
                     round(c["db"] + c["trim"], 1), c["cut"], src, c["why"]])
    for v in stems["lines"]:
        rows.append(["voice", v["name"], v["f"], round(v["f"] / fps, 4), round(v["start"] / SR, 4),
                     round(v.get("db", 0) + v["trim"], 1), "", "", f"duck {v.get('duck', -6) + v['xduck']:.1f} dB"])
        for w, o in zip(v["words"], M2.word_onsets(stems, v)):
            rows.append(["word", w["w"], round(o["t"] * fps, 2), round(o["t"], 4), round(w["t0"] + v["start"] / SR, 4),
                         "", "", "", f"{v['name']} spoken f{o['frame']} reveal f{o['frame'] + 1} conf {o['conf']:.0f}"])
    for T in E["cuts"]:
        rows.append(["transition", T["type"], T["f"], round(T["f"] / fps, 4), round(T["w0"] / fps, 4), "", T["id"], "",
                     f"window [{T['w0']}, {T['w1']}) over {T.get('over', [])}"])
    ef = E["dur"] - round(1.4 * fps)
    rows.append(["music", "end_fade", ef, round(ef / fps, 4), "", "", "", "", "raised cosine to silence at the last sample"])
    rows.sort(key=lambda r: (float(r[2]), r[0]))
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["kind", "name", "frame", "time_s", "start_s", "gain_db", "cut", "source", "note"])
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--edl", default=str(ROOT / "films/timeless/amv3/edl.json"))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--lufs", type=float, default=-14.0)
    ap.add_argument("--tp", type=float, default=-1.0)
    ap.add_argument("--stems", action="store_true", help="also write music/voice/sfx stems and per-transition SFX wavs")
    a = ap.parse_args(argv)
    E = json.loads(Path(a.edl).read_text())
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    adj = auto_balance(E)                         # the voice first (on the uncalibrated SFX), then the SFX levels,
    trims = calibrate(E, adj)                     # then the voice again over the final SFX
    adj = auto_balance(E, trims)
    stems = build(E, adj, trims)
    y, g = M2.master(stems, a.lufs, a.tp, print)
    sf.write(str(out / "mix.wav"), y.astype(np.float32), SR, subtype="PCM_24")
    write_cues(out / "cues3.csv", E, stems)
    if a.stems:
        sd = out / "mix3_stems"
        sd.mkdir(exist_ok=True)
        for k in ("music", "voice", "sfx"):
            sf.write(str(sd / f"{k}.wav"), (stems[k] * g).astype(np.float32), SR, subtype="FLOAT")
        fps = E["fps"]
        for T in E["cuts"]:
            b = stems["per_cut"].get(T["id"])
            if b is None:
                continue
            i0, i1 = max(0, int((T["w0"] / fps - 0.5) * SR)), min(stems["N"], int((T["w1"] / fps + 1.5) * SR))
            sf.write(str(sd / f"{T['id']}_{T['type']}_sfx.wav"), (b[i0:i1] * g).astype(np.float32), SR, subtype="FLOAT")
    chk, _ = sf.read(str(out / "mix.wav"), dtype="float64", always_2d=True)
    rep = {"frames": E["dur"], "samples": len(chk), "lufs": round(M2.lufs(chk), 2),
           "true_peak_dbtp": round(M2.true_peak_db(chk), 2), "master_gain_db": round(M2.db(g), 2),
           "voice_adjust": {k: {"trim_db": round(t, 1), "extra_duck_db": round(x, 1)} for k, (t, x) in adj.items()},
           "voice_over_bed": M2.voice_ratio(stems), "sfx_count": len(stems["cues"]),
           "transition_trim_db": {k: round(v, 2) for k, v in trims.items()},
           "limiter_extra_reduction_db": {k: round(v, 2) for k, v in extra_reduction(E, stems, a.lufs, a.tp).items()},
           "sfx_synth": sum("gen" in c for c in stems["cues"]), "last_sample": float(np.abs(chk[-1]).max())}
    (out / "mix3_report.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))
    return stems, g


if __name__ == "__main__":
    main()
