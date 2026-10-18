"""Timeless v3 finishing: every number the EffectCraft libs key (E.x.finish), computed from edl.json.

    E.x.finish = {passes, gradeEnd, looks, actKeys, trim, finish, lens, letterbox, textTint, textGlow, lightGlows}

* trims: v2's per-shot trims (filmtools.amv2.grade_spec, same shots and source ranges as v2), as per-frame-parameter keys:
  constant inside a shot, linear from A's trim at w0 to B's trim at w1 in each CUTS window.
* looks: v2's act looks (amv2/ec/grade.jsx GRADE.LOOKS) pushed toward the references (LOOK_PUSH).
* lens: one entry per CUTS window, keys on every frame of [w0, w1) from the window's time profile (`profile`).
Pure Python (numpy only through grade_spec, optional), Python 3.10.
"""
from __future__ import annotations

import copy
import json
import math
import os
import re
import struct
from pathlib import Path

ACT_ORDER = ("tobey", "andrew", "tom")
ACT_BLEND = 3                       # half-width (frames) of the look blend at an act change

# ---------------------------------------------------------------- looks
# v2 GRADE.LOOKS (tools/filmtools/amv2/ec/grade.jsx), copied so v2 stays untouched; bloom added (v2 had it under `glow`).
V2_LOOKS = {
    "tobey": dict(temp=10, tint=2, contrast=14, highlights=-8, shadows=8, whites=2, blacks=-2, exposure=0, saturation=106,
                  vibrance=10, cShadows=2, cMids=8, cHighlights=2,
                  wShadows=[0.46, 0.515, 0.56], wMids=[0.52, 0.505, 0.47], wHighlights=[0.61, 0.54, 0.37],
                  cbShadows=[-3, 1, 4], cbMids=[3, 1, -3], cbHighlights=[7, 3, -8],
                  hsSat=0, hsRed=2, hsYellow=8, hsCyan=0, hsBlue=-4),
    "andrew": dict(temp=-26, tint=-3, contrast=20, highlights=-6, shadows=4, whites=4, blacks=-4, exposure=0, saturation=110,
                   vibrance=12, cShadows=-2, cMids=8, cHighlights=4,
                   wShadows=[0.38, 0.50, 0.66], wMids=[0.44, 0.50, 0.58], wHighlights=[0.53, 0.52, 0.45],
                   cbShadows=[-8, 1, 10], cbMids=[-4, 1, 6], cbHighlights=[3, 1, -2],
                   hsSat=0, hsRed=0, hsYellow=14, hsCyan=26, hsBlue=14),
    "tom": dict(temp=6, tint=3, contrast=24, highlights=0, shadows=10, whites=8, blacks=-5, exposure=0, saturation=112,
                vibrance=8, cShadows=-3, cMids=10, cHighlights=8,
                wShadows=[0.41, 0.49, 0.60], wMids=[0.545, 0.495, 0.455], wHighlights=[0.58, 0.52, 0.43],
                cbShadows=[-7, 0, 9], cbMids=[5, -1, -4], cbHighlights=[6, 1, -5],
                hsSat=0, hsRed=24, hsYellow=0, hsCyan=-6, hsBlue=-8),
}
# The references' richness: saturated reds and teal, deeper contrast (blacks pulled down, toe kept by the limiter's
# output black), strong bloom above a high threshold. Skin: only red saturation is pushed, the hue wheels stay v2's.
LOOK_PUSH = {
    "tobey": dict(contrast=20, saturation=114, vibrance=16, blacks=-6, cShadows=-2, hsRed=10, hsYellow=12,
                  wShadows=[0.44, 0.52, 0.59], cbShadows=[-5, 1, 6],
                  bloomThreshold=78, bloomRadius=70, bloomIntensity=0.9, bloomColor=[1.0, 0.80, 0.52]),
    "andrew": dict(contrast=26, saturation=118, vibrance=18, blacks=-8, cShadows=-5, hsRed=8, hsYellow=18, hsCyan=34,
                   hsBlue=18, bloomThreshold=78, bloomRadius=60, bloomIntensity=0.95, bloomColor=[0.55, 0.86, 1.0]),
    "tom": dict(contrast=30, saturation=122, vibrance=14, blacks=-9, cShadows=-6, hsRed=34, hsYellow=6,
                cbShadows=[-9, 0, 11], bloomThreshold=80, bloomRadius=55, bloomIntensity=0.9, bloomColor=[1.0, 0.64, 0.44]),
}
FINISH = dict(sharpen=dict(amount=42, radius=0.9, threshold=2), grain=dict(intensity=0.22, size=0.7),
              vignette=dict(amount=-0.38, midpoint=52, roundness=0, feather=75),
              limit=dict(whites=-4, highlights=-6, outBlack=0.012, outWhite=0.975))

# ---------------------------------------------------------------- lens
LEAKS = {   # [picture-highlight leak colour, organic wash colour]
    "warm_gold": [[1.0, 0.70, 0.30], [1.0, 0.52, 0.16]],
    "cyan_amber": [[0.30, 0.82, 1.0], [1.0, 0.60, 0.20]],
    "red_orange": [[1.0, 0.30, 0.10], [1.0, 0.56, 0.16]],
}
ACT_LEAK_GAIN = {"tobey": 1.0, "andrew": 0.9, "tom": 0.85}
TYPE_GAIN = {   # (blur, bulge) multipliers by transition type: zooms smear radially, whips/cubes mostly carry their own blur
    "zt": (1.0, 1.0), "open": (0.6, 0.4), "whip": (0.55, 0.3), "cube": (0.5, 0.3), "flip": (0.5, 0.3), "slam": (0.9, 1.0),
}
DECAY = 5          # frames after the cut over which the profile falls to ~0 (landing sharp by cut + 3)
TRIPTYCH_PEAKS = [(777, 0.8), (785, 0.85), (794, 0.85), (802, 0.6)]


def ease_profile(x, f, w0, w1, peaks=None):
    """0..1 at frame x: cubic rise over [w0, f) (expo-in feel), peak 1 on f-1 and f, cubic fall over DECAY frames."""
    if peaks:       # several hits in one window (triptych): 2-frame rise into each, 4-frame fall
        return max(s * (_decay(x - p, 4) if x >= p else max(0.0, 1 - (p - x) / 2.0) ** 2) for p, s in peaks)
    if x < f:
        pre = max(1, f - w0)
        u = (x - w0 + 1) / pre
        return max(0.0, min(1.0, u)) ** 3
    return _decay(x - f, min(DECAY, max(1, w1 - f)))


def _decay(d, n):
    if d < 0:
        return 0.0
    return max(0.0, 1 - d / float(n)) ** 3


def zvec_profile(Z, w0, w1):
    """Camera speed (zvec.json from the stage) normalised to the window's peak, shaped like the eases (^1.5)."""
    v = [float(Z.get(str(x), Z.get(x, 0.0)) or 0.0) for x in range(w0, w1)]
    m = max(v) if v else 0
    if m <= 0:
        return None
    return [(s / m) ** 1.5 for s in v]


def lens_plan(E, zvec=None):
    out = []
    acts = E["acts"]
    for i, C in enumerate(E["cuts"]):
        f, w0, w1, L, typ = C["f"], C["w0"], C["w1"], C["lens"], C["type"]
        if w1 <= w0:
            continue
        act = next((a["id"] for a in acts if a["f0"] <= max(f, 0) < a["f1"] and a["id"] in ACT_ORDER), "tom")
        leak = L.get("leak") or next(a.get("leak") for a in acts if a["id"] == act)
        colors = None if leak == "none" else LEAKS.get(leak)
        peaks = TRIPTYCH_PEAKS if typ == "triptych" else None
        prof = zvec_profile(zvec, w0, w1) if zvec else None
        if prof is None:
            if typ == "open":
                prof = [(1 - (x - w0) / float(w1 - w0)) ** 2 for x in range(w0, w1)]
            else:
                prof = [ease_profile(x, f, w0, w1, peaks) for x in range(w0, w1)]
        gb, gu = TYPE_GAIN.get(typ, (0.85, 0.7))
        lg = ACT_LEAK_GAIN[act]
        fl = int(L.get("flash") or 0)
        K = {k: [] for k in ("blur", "ca", "bulge", "bloom", "bloomThr", "leak", "wash", "expo", "evo", "drift")}
        for j, x in enumerate(range(w0, w1)):
            p = prof[j]
            u = (x - w0) / float(max(1, w1 - w0 - 1))
            K["blur"].append([x, round(70.0 * L["zblur"] * gb * p * p, 2)])
            K["ca"].append([x, round(L["ca"] * p, 2)])
            K["bulge"].append([x, round(0.4 * L["zblur"] * gu * p, 3)])
            K["bloom"].append([x, round(1.4 * lg * p, 3)])
            K["bloomThr"].append([x, round(72 - 22 * p, 1)])
            K["leak"].append([x, round(min(100.0, 115.0 * lg * p ** 1.3), 1)])
            K["wash"].append([x, round(min(100.0, 70.0 * lg * p ** 1.1), 1)])
            e = 0.45 * p * p
            if fl and f <= x < f + fl:
                e = 2.6 if x == f else 1.8
            elif fl and f + fl <= x < f + fl + 3:
                e = max(e, [1.1, 0.5, 0.15][x - f - fl])
            K["expo"].append([x, round(e, 3)])
            K["evo"].append([x, round(360.0 * 2.2 * u + 37 * i, 1)])
            ang = (i * 137.5) % 360
            K["drift"].append([x, [round(960 + 700 * math.cos(math.radians(ang)) * (u - 0.5), 1),
                                   round(540 + 400 * math.sin(math.radians(ang)) * (u - 0.5), 1)]])
        out.append(dict(id=C["id"], type=typ, f=f, w0=w0, w1=w1, act=act, center=[960, 540], colors=colors, flash=fl,
                        seed=11 + 7 * i, leakKnee=0.55, leakRadius=70, bloomRadius=90, washContrast=170,
                        washBrightness=-48, washScale=[1100, 620], washAngle=round((i * 61.8) % 180, 1), keys=K))
    return out


# ---------------------------------------------------------------- grade
def looks():
    L = copy.deepcopy(V2_LOOKS)
    for a, d in LOOK_PUSH.items():
        L[a].update(copy.deepcopy(d))
    return L


def act_keys(E, end):
    A = {a["id"]: a for a in E["acts"]}
    c1, c2 = A["andrew"]["f0"], A["tom"]["f0"]
    h = ACT_BLEND
    return [[0, "tobey"], [c1 - h, "tobey"], [c1 + h, "andrew"], [c2 - h, "andrew"], [c2 + h, "tom"], [end, "tom"]]


TRIM_PARAMS = (("ib", "lev", "ib"), ("iw", "lev", "iw"), ("g", "lev", "g"), ("ob", "lev", "ob"), ("ow", "lev", "ow"),
               ("r", "ch", "r"), ("gg", "ch", "g"), ("b", "ch", "b"), ("sat", None, "sat"), ("hue", None, "hue"))


def trims(E):
    """{shot id: trim} from v2's grade_spec (same shots); neutral where missing."""
    from filmtools.amv2 import grade_spec as gs
    E2 = copy.deepcopy(E)
    gs.extend(E2)
    return E2["x"]["grade"]["shots"], gs.neutral()


def trim_keys(E, end):
    T, neutral = trims(E)
    pts = []
    first = E["shots"][0]
    pts.append((0, T[first["id"]]))
    for C in E["cuts"]:
        if C["f"] <= 0 or C["w1"] <= C["w0"]:
            continue
        ta = T.get(C["a"]) if C["a"] else neutral
        tb = T.get(C["b"]) if C["b"] else neutral
        if C["b"] is None:                              # into the triptych: back to neutral over 4 frames
            pts += [(C["f"], ta), (C["f"] + 4, tb)]
        else:
            pts += [(C["w0"], ta), (C["w1"], tb)]
    pts.append((end, pts[-1][1]))
    pts.sort(key=lambda p: p[0])
    out = {}
    for name, grp, key in TRIM_PARAMS:
        ks = []
        for f, t in pts:
            v = t[grp][key] if grp else t.get(key, 0)
            v = round(float(v or 0), 4)
            if ks and ks[-1][0] == f:
                continue
            ks.append([f, v])
        # drop interior keys equal to both neighbours (fewer keys, same curve)
        slim = [k for j, k in enumerate(ks) if j in (0, len(ks) - 1) or not (ks[j - 1][1] == k[1] == ks[j + 1][1])]
        out[name] = slim
    return out


# ---------------------------------------------------------------- passes
def png_size(p):
    with open(p, "rb") as fh:
        h = fh.read(24)
    return struct.unpack(">II", h[16:24])


def find_seq(d, pat=r"f_(\d+)\.png$"):
    """{first, start, n, w, h} of a numbered PNG sequence in d (contiguous run from the first file), or None."""
    d = Path(os.path.expandvars(str(d))).resolve()       # absolute: EffectCraft resolves relative media paths against the project
    if not d.is_dir():
        return None
    rx = re.compile(pat)
    fr = sorted((int(m.group(1)), n) for n in os.listdir(d) for m in [rx.search(n)] if m)
    if not fr:
        return None
    s = fr[0][0]
    n = 0
    for k, (f, _) in enumerate(fr):
        if f != s + k:
            break
        n += 1
    w, h = png_size(d / fr[0][1])
    return dict(first=str(d / fr[0][1]), start=s, n=n, w=w, h=h, dir=str(d))


def passes(stage_dir, outro_dir):
    P = {k: find_seq(Path(stage_dir) / k) for k in ("plate", "text", "light")} if stage_dir else {}
    P["outro"] = find_seq(outro_dir, r"(\d{4})\.png$") if outro_dir else None
    return P


def load_zvec(stage_dir):
    if not stage_dir:
        return None
    p = Path(os.path.expandvars(str(stage_dir))) / "zvec.json"
    if not p.exists():
        return None
    z = json.loads(p.read_text())
    return z.get("frames", z)


# ---------------------------------------------------------------- titles (v2 TITLES lib, unchanged)
V2_EXIT = {"zt": "zoom_in", "text_fly": "zoom_in", "eye_tunnel": "zoom_in", "sling_ring": "zoom_in", "lens_shatter": "impact",
           "lightning": "impact", "slam": "impact", "symbiote": "glitch_dark", "triptych": "panel_slam"}
ANDREW_CARD = dict(id="name_andrew", f=306, f1=336, style="namecard", text="ANDREW GARFIELD", sub="SPIDER-MAN  2012 - 2014",
                   act="andrew")   # v2 synthesised it from the AMAZING novax hero (titles.jsx); v3's AMAZING is 3D, so it is explicit


def titles_E(E):
    """E for v2's titles.jsx/titles_spec: only its 2D styles, the Andrew card, shots with v2's `xout` exit names."""
    from filmtools.amv2 import titles_spec as ts
    T = copy.deepcopy(E)
    T["titles"] = [t for t in E["titles"] if t["style"] in ("sub", "namecard", "caption_box")]
    if not any(t["style"] == "namecard" and t.get("act") == "andrew" for t in T["titles"]):
        T["titles"].append(dict(ANDREW_CARD))
    for s in T["shots"]:
        C = next((c for c in E["cuts"] if c["a"] == s["id"]), None)
        typ = C["type"] if C else None
        if typ == "whip":
            s["xout"] = "whip_" + C["p"].get("dir", "R").lower()
        else:
            s["xout"] = V2_EXIT.get(typ, "light_sweep")
    ts.extend(T)
    return T


def letterbox(E):
    out = []
    W, H = E["w"], E["h"]
    bar = (H - W / 2.39) / 2 + 0.5
    h = bar + 4
    for s in E["shots"]:
        if "letterbox" not in s.get("fx", []):
            continue
        f0, f1 = s["a"], s["b"]
        ys = [[], []]
        for side in (0, 1):
            y_in = H - bar + h / 2 if side else bar - h / 2
            y_out = H + h / 2 + 2 if side else -h / 2 - 2
            for x in range(f0, f1):
                u = 1 - 2 ** (-10 * min(1.0, (x - f0 + 1) / 10.0)) if x < f0 + 10 else 1.0
                if x >= f1 - 3:
                    u = 1 - ((x - (f1 - 3) + 1) / 3.0) ** 3
                ys[side].append([x, round(y_out + (y_in - y_out) * u, 2)])
        out.append(dict(id=s["id"], f0=f0, f1=f1, h=int(math.ceil(h)), y=ys))
    return out


def text_tint(L):
    """Colour Balance for the text pass: 35 % of each act's split tone (titles match the shot without being graded)."""
    return {a: [[round(0.35 * v, 2) for v in L[a][k]] for k in ("cbShadows", "cbMids", "cbHighlights")] for a in ACT_ORDER}


LIGHT_GLOWS = [dict(name="core", threshold=8, radius=10, intensity=1.3, opacity=100),
               dict(name="halo", threshold=8, radius=45, intensity=1.0, opacity=90),
               dict(name="bloom", threshold=8, radius=170, intensity=0.7, opacity=70)]
TEXT_GLOW = dict(threshold=55, radius=18, intensity=0.5)


def extend(E, stage_dir=None, outro_dir=None):
    """E (edl.json dict) -> E with E.x.finish and E.x.titles (and E.titles reduced to v2's 2D styles)."""
    end = E["outro"]["f0"]
    L = looks()
    act_idx = act_keys(E, end)
    X = dict(passes=passes(stage_dir, outro_dir), gradeEnd=end, looks=L, actKeys=act_idx, trim=trim_keys(E, end),
             finish=FINISH, lens=lens_plan(E, load_zvec(stage_dir)), letterbox=letterbox(E), textTint=text_tint(L),
             textGlow=TEXT_GLOW, lightGlows=LIGHT_GLOWS)
    T = titles_E(E)
    E = dict(E, titles=T["titles"])
    E.setdefault("x", {})
    E["x"] = dict(E["x"], finish=X, titles=T["x"]["titles"])
    return E
