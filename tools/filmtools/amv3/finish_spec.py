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
                  hsSat=0, hsRed=2, hsYellow=8, hsCyan=0, hsBlue=-4, hsMagenta=0),
    "andrew": dict(temp=-26, tint=-3, contrast=20, highlights=-6, shadows=4, whites=4, blacks=-4, exposure=0, saturation=110,
                   vibrance=12, cShadows=-2, cMids=8, cHighlights=4,
                   wShadows=[0.38, 0.50, 0.66], wMids=[0.44, 0.50, 0.58], wHighlights=[0.53, 0.52, 0.45],
                   cbShadows=[-8, 1, 10], cbMids=[-4, 1, 6], cbHighlights=[3, 1, -2],
                   hsSat=0, hsRed=0, hsYellow=14, hsCyan=26, hsBlue=14, hsMagenta=0),
    "tom": dict(temp=6, tint=3, contrast=24, highlights=0, shadows=10, whites=8, blacks=-5, exposure=0, saturation=112,
                vibrance=8, cShadows=-3, cMids=10, cHighlights=8,
                wShadows=[0.41, 0.49, 0.60], wMids=[0.545, 0.495, 0.455], wHighlights=[0.58, 0.52, 0.43],
                cbShadows=[-7, 0, 9], cbMids=[5, -1, -4], cbHighlights=[6, 1, -5],
                hsSat=0, hsRed=24, hsYellow=0, hsCyan=-6, hsBlue=-8, hsMagenta=0),
}
# The references' richness: saturated reds and teal, deeper contrast (blacks pulled down, toe kept by the limiter's
# output black), strong bloom above a high threshold. Skin: only red saturation is pushed, the hue wheels stay v2's.
LOOK_PUSH = {
    "tobey": dict(contrast=20, saturation=112, vibrance=16, blacks=-6, cShadows=-2, hsRed=5, hsYellow=10, hsMagenta=-20,
                  wShadows=[0.44, 0.52, 0.59], cbShadows=[-5, 1, 6],
                  bloomThreshold=78, bloomRadius=70, bloomIntensity=0.9, bloomColor=[1.0, 0.80, 0.52]),
    # stage draft1: Andrew's skies are 25 % clipped in the plate: roll the highlights/whites down so the sky keeps detail
    # and colour, and keep the bloom to the very top (a wide bloom on a bright sky is the milky haze)
    "andrew": dict(contrast=26, saturation=134, vibrance=30, highlights=-34, whites=-16, blacks=-8, cShadows=-5, cHighlights=-6,
                   hsRed=8, hsYellow=18, hsCyan=40, hsMagenta=-10, hsBlue=26, bloomThreshold=90, bloomRadius=45, bloomIntensity=0.45,
                   bloomColor=[0.55, 0.86, 1.0]),
    "tom": dict(contrast=30, saturation=122, vibrance=14, blacks=-9, cShadows=-6, hsRed=34, hsYellow=6, hsMagenta=-8,
                cbShadows=[-9, 0, 11], bloomThreshold=80, bloomRadius=55, bloomIntensity=0.9, bloomColor=[1.0, 0.64, 0.44]),
}
# Skin qualifier (operator, s_grade1 f200: skin went hot orange-red): Lumetri HSL Secondary keyed on skin hue/sat/lightness,
# saturation pulled back inside the key, on its own layer after the look (before the lens light, so leaks keep their colour).
SKIN = dict(hueCenter=24, hueRange=14, hueSoftness=10, satLow=12, satHigh=80, satSoft=10, lumLow=12, lumHigh=92, lumSoft=10,
            blur=4, saturation=80)
FINISH = dict(sharpen=dict(amount=42, radius=0.9, threshold=2), grain=dict(intensity=0.22, size=0.7),
              vignette=dict(amount=-0.38, midpoint=52, roundness=0, feather=75),
              limit=dict(whites=-4, highlights=-6, outBlack=0.012, outWhite=0.975))

# ---------------------------------------------------------------- lens
LEAKS = {   # [picture-highlight leak colour, organic wash colour]
    "warm_gold": [[1.0, 0.78, 0.48], [1.0, 0.56, 0.22]],     # softer than the orange washes: Tobey's leaks sit on faces
    "cyan_amber": [[0.30, 0.82, 1.0], [1.0, 0.60, 0.20]],
    "red_orange": [[1.0, 0.30, 0.10], [1.0, 0.56, 0.16]],
}
ACT_LEAK_GAIN = {"tobey": 1.0, "andrew": 0.9, "tom": 0.85}
# Per CUTS type, from REFS.md "Recipes for v3": blur/bulge gains, CA = peak R/B split at the frame edge per unit of edl
# `lens.ca` (zt/whip smears 30-80 px), whether the window smears at all (portals: no unreadable frame, the hole/ring
# replaces it, CA 1-9 px), and the attack: "expo" (cubic into the cut) or "linear" (portals ramp ~linearly over 14-15 f).
RECIPE = {
    "zt":           dict(blur=1.0, bulge=1.0, ca=4.0, smear=True, attack="expo"),
    "whip":         dict(blur=0.55, bulge=0.3, ca=4.0, smear=True, attack="expo"),
    "cube":         dict(blur=0.5, bulge=0.3, ca=3.0, smear=True, attack="expo"),
    "flip":         dict(blur=0.5, bulge=0.3, ca=3.0, smear=True, attack="expo"),
    "slam":         dict(blur=0.9, bulge=1.0, ca=2.5, smear=True, attack="expo"),
    "text_fly":     dict(blur=0.9, bulge=0.8, ca=2.5, smear=True, attack="expo"),
    "lightning":    dict(blur=0.7, bulge=0.5, ca=3.0, smear=True, attack="expo"),
    "lens_shatter": dict(blur=0.9, bulge=1.0, ca=3.0, smear=True, attack="expo"),
    "symbiote":     dict(blur=0.6, bulge=0.5, ca=2.0, smear=True, attack="expo"),
    "web_wipe":     dict(blur=0.6, bulge=0.4, ca=3.0, smear=True, attack="expo"),
    "eye_tunnel":   dict(blur=0.15, bulge=0.6, ca=0.6, smear=False, attack="linear"),
    "sling_ring":   dict(blur=0.1, bulge=0.4, ca=0.5, smear=False, attack="linear", wash4=True),
    "triptych":     dict(blur=0.4, bulge=0.4, ca=2.0, smear=True, attack="expo"),
    "open":         dict(blur=0.6, bulge=0.4, ca=1.0, smear=False, attack="open"),
    # subject-motion layer wipe (keep/sweep, operator 2026-10-18): like a portal, moderate CA, no smear, soft leak as the
    # subject passes the lens
    "layer":        dict(blur=0.15, bulge=0.2, ca=1.6, smear=False, attack="linear", light=0.55),
}
DECAY = 5          # frames after the cut over which the profile falls to ~0 (landing sharp by cut + 3)
# Reference numbers (REFS.md): smear frames 30-80 px CA at the edges (zt/whip) and +50-100 % luma from an act-coloured
# leak; the first 4 frames after the cut keep 10-20 px CA; a white flash only on the biggest hits, 2-3 f with 17-30 %
# of the pixels clipped. The light is scaled per frame by the plate's own headroom (`headroom`): the same leak that
# lifts a dark Tobey frame +80 % turns an already bright frame milky white (v2's lesson; first v3 drop test, f478-482).
CA_EDGE_PER_UNIT = 1.65   # measured: VR Chromatic Aberrations amount N -> R/B split of 1.65 N px at the frame edge (linear to 0 at centre)
CA_TAIL = (8.0, 0.6, 8)   # after the cut: edge split (8 + 0.6 ca) px fading to 0 over 8 f (10-20 px over the first 4 f)
EXPO_PEAK = 0.5           # EV at the profile peak, before headroom (0.75 blew faces on stage draft1 landings, C05 175)
FLASH_EV = {1: [1.9, 1.3, 0.6], 2: [2.6, 1.8, 0.9]}   # the 3 white frames of a flash cut, by edl `flash` (2 = the drop)
FLASH_GAIN = {1: 1.0, 2: 0.55}  # stage draft1: the drop plate is already white at its centre; 1.0 clipped 41-48 % over 3 f (target 17-30)
WASH4_TINT = {-2: 0.15, -1: 0.25, 0: 0.15, 1: 0.1}  # sling ring orange Multiply, by frame from the cut: only a lead-in, the stage plate carries the 4-f orange wash itself (stage draft1 618-622)
WASH4_COLOR = [1.0, 0.52, 0.18]
LUMA_CAP = 0.58           # mean luma (0..1) the light aims under: at or above it the leak/bloom/exposure fade to HEAD_MIN
HEAD_MIN = 0.06
TRIPTYCH_PEAKS = [(777, 0.8), (785, 0.85), (794, 0.85), (802, 0.6)]


def ease_profile(x, f, w0, w1, peaks=None, attack="expo"):
    """0..1 at frame x: rise over [w0, f) (cubic = expo-in feel, or linear for portals), peak 1 on f-1 and f, cubic
    fall over DECAY frames."""
    if peaks:       # several hits in one window (triptych): 2-frame rise into each, 4-frame fall
        return max(s * (_decay(x - p, 4) if x >= p else max(0.0, 1 - (p - x) / 2.0) ** 2) for p, s in peaks)
    if x < f:
        pre = max(1, f - w0)
        u = max(0.0, min(1.0, (x - w0 + 1) / pre))
        return u if attack == "linear" else u ** 3
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


def headroom(m):
    """Light gain for a frame of mean luma m: 1 for a dark frame (m <= 0.25), HEAD_MIN at LUMA_CAP and above."""
    if m is None:
        return 1.0
    t = (LUMA_CAP - m) / (LUMA_CAP - 0.22)
    return round(max(HEAD_MIN, min(1.0, t)), 3)


def lens_plan(E, zvec=None, luma=None):
    """luma: {frame: mean luma 0..1 of the plate} (plate_luma) or None."""
    out = []
    acts = E["acts"]
    luma = luma or {}
    for i, C in enumerate(E["cuts"]):
        f, w0, w1, L, typ = C["f"], C["w0"], C["w1"], C["lens"], C["type"]
        if w1 <= w0:
            continue
        R = RECIPE.get(typ, RECIPE["zt"])
        act = next((a["id"] for a in acts if a["f0"] <= max(f, 0) < a["f1"] and a["id"] in ACT_ORDER), "tom")
        leak = L.get("leak") or next(a.get("leak") for a in acts if a["id"] == act)
        colors = None if leak == "none" else LEAKS.get(leak)
        peaks = TRIPTYCH_PEAKS if typ == "triptych" else None
        prof = zvec_profile(zvec, w0, w1) if zvec else None
        if prof is None:
            if typ == "open":
                prof = [(1 - (x - w0) / float(w1 - w0)) ** 2 for x in range(w0, w1)]
            else:
                prof = [ease_profile(x, f, w0, w1, peaks, R["attack"]) for x in range(w0, w1)]
        lg = ACT_LEAK_GAIN[act] * R.get("light", 1.0)
        fl = int(L.get("flash") or 0)
        K = {k: [] for k in ("blur", "ca", "bulge", "bloom", "bloomThr", "leak", "wash", "expo", "evo", "drift", "tint")}
        heads = []
        for j, x in enumerate(range(w0, w1)):
            p = prof[j]
            m = luma.get(x)
            h = headroom(m[0] if m else None)
            heads.append(h)
            u = (x - w0) / float(max(1, w1 - w0 - 1))
            K["blur"].append([x, round(70.0 * L["zblur"] * R["blur"] * p * p, 2)])
            edge = R["ca"] * L["ca"] * p
            if x > f and R["smear"] and typ != "open":
                edge = max(edge, (CA_TAIL[0] + CA_TAIL[1] * L["ca"]) * max(0.0, 1 - (x - f) / float(CA_TAIL[2])) ** 1.3)
            K["ca"].append([x, round(edge / CA_EDGE_PER_UNIT, 2)])
            K["bulge"].append([x, round(0.4 * L["zblur"] * R["bulge"] * p, 3)])
            pl = p
            if R.get("wash4"):          # sling ring: the frame goes orange for 4 frames around the cut (luma +230 % peak)
                w4 = {f - 2: 0.7, f - 1: 1.0, f: 1.0, f + 1: 0.55}.get(x, 0.0)
                pl = max(p, w4)
                if w4:
                    h = max(h, 0.5 * w4)    # the wash is the transition itself: it overrides the bright-frame headroom (partly)
            # the orange is a Multiply (orange x the picture: a white portal turns orange, detail kept; never a flat ADD fill)
            K["tint"].append([x, round(100.0 * WASH4_TINT.get(x - f, 0.0), 1) if R.get("wash4") else 0.0])
            K["bloom"].append([x, round(1.0 * lg * pl * h * h, 3)])          # a wide glow on a bright frame is a veil: h^2
            K["bloomThr"].append([x, round(76 - 14 * pl * h, 1)])
            K["leak"].append([x, round(min(100.0, 115.0 * lg * pl ** 1.3 * h), 1)])
            K["wash"].append([x, round(min(100.0, (10.0 if R.get("wash4") else 70.0) * lg * pl ** 1.1 * h), 1)])
            e = EXPO_PEAK * (p if R.get("wash4") else pl) ** 2 * h
            if fl and f <= x < f + 3:
                # white flash: ~30 % of the pixels clipped on the first frame. Exposure that takes the frame's 70th
                # percentile (~0.82 x its 90th, YHIGH) to white, x FLASH_EV shape (frames 2 and 3 fade).
                hi = m[1] if m else 0.6
                ev1 = max(0.5, min(2.6, math.log(0.95 / max(0.52 * hi, 0.05), 2)))
                sh = FLASH_EV[min(fl, 2)]
                e = max(e, FLASH_GAIN[min(fl, 2)] * ev1 * sh[x - f] / sh[0])
            K["expo"].append([x, round(e, 3)])
            K["evo"].append([x, round(360.0 * 2.2 * u + 37 * i, 1)])
            ang = (i * 137.5) % 360
            K["drift"].append([x, [round(960 + 700 * math.cos(math.radians(ang)) * (u - 0.5), 1),
                                   round(540 + 400 * math.sin(math.radians(ang)) * (u - 0.5), 1)]])
        out.append(dict(id=C["id"], type=typ, f=f, w0=w0, w1=w1, act=act, center=[960, 540], colors=colors, flash=fl,
                        tintColor=WASH4_COLOR if R.get("wash4") else None, seed=11 + 7 * i, leakKnee=round(0.55 + 0.3 * (1 - min(heads)), 3), leakRadius=70, bloomRadius=90, washContrast=115 if R.get("wash4") else 170,
                        washBrightness=-12 if R.get("wash4") else -48, washScale=[1100, 620], washAngle=round((i * 61.8) % 180, 1),
                        headroom=heads, keys=K))
    return out


def plate_luma(seq, frames, cache_dir=None):
    """{frame: [mean luma, 90th percentile luma] 0..1} of a plate sequence over `frames` (ffmpeg signalstats on a 240 px copy; full-range PNG ->
    YAVG is 0..255). Cached by path and file mtimes."""
    import subprocess
    if not seq:
        return {}
    d = Path(seq["dir"])
    want = sorted(f for f in set(frames) if seq["start"] <= f < seq["start"] + seq["n"])
    if not want:
        return {}
    key = f"v2|{d}|{seq['start']}|{seq['n']}|{os.path.getmtime(seq['first']):.0f}"
    cache = Path(cache_dir) / "plate_luma.json" if cache_dir else None
    C = json.loads(cache.read_text()) if cache and cache.exists() else {}
    if key in C and all(str(f) in C[key] for f in want):
        return {f: C[key][str(f)] for f in want}
    ff = "/home/nikhil/code/film-making/bin/ffmpeg"
    ff = ff if os.path.exists(ff) else "ffmpeg"
    r = subprocess.run([ff, "-v", "error", "-start_number", str(seq["start"]), "-i", str(d / "f_%05d.png"), "-vf",
                        "scale=240:-2,format=yuvj420p,signalstats,metadata=print:file=-",
                        "-f", "null", "-"], capture_output=True, text=True)
    ys = [float(v) / 255.0 for v in re.findall(r"YAVG=([\d.]+)", r.stdout)]
    hs = [float(v) / 255.0 for v in re.findall(r"YHIGH=([\d.]+)", r.stdout)]
    allf = {seq["start"] + k: [round(y, 4), round(hs[k] if k < len(hs) else y, 4)] for k, y in enumerate(ys)}
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        C[key] = {str(k): v for k, v in allf.items()}
        cache.write_text(json.dumps(C))
    return {f: allf[f] for f in want if f in allf}


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


# stage draft1: the light pass carries whole surfaces (rings, the TIMELESS letters, glass shards), not only small emitters,
# and the plate already contains them: glow only their brightest parts, gently (the first values, 8/1.3/1.0/0.7, blew the
# eye tunnel and the triptych title out to 26-36 % clipped)
LIGHT_GLOWS = [dict(name="core", threshold=45, radius=10, intensity=0.6, opacity=60),
               dict(name="halo", threshold=45, radius=45, intensity=0.45, opacity=50),
               dict(name="bloom", threshold=55, radius=170, intensity=0.35, opacity=40)]
TEXT_GLOW = dict(threshold=70, radius=18, intensity=0.25)


# ---------------------------------------------------------------- accents (EffectCraft transitions, lab/TRANSITIONS.md)
# Light Rays on every nest-zoom landing: a copy of the plate cut down to its highlights (Levels knee, dimmed), CC Light
# Rays from B's own brightest non-skin area, ADD, opacity decaying over 4 f (scaled by the frame's headroom; target
# <= ~15 % of pixels above 240 on the landing). Skipped where the next transition starts within 3 frames of the cut.
RAYS = dict(types=("zt",), shape=[1.0, 0.75, 0.45, 0.22, 0.08], opacity=50, head_min=0.25, intensity=150, radius=300,
            warpSoftness=30, knee=0.72, gain=0.25, min_frames=3)
# Shatter as an overlay burst on the slam hit: the landing frame frozen, extruded glass pieces blown outward over 8 f
# (fading 4 f), placed under the grade so the shards are graded and hit by the window's lens FX.
SHATTER = dict(cut="C22", reps=12, extrusion=0.2, strength=14, depth=0.3, rotation=0.35, lightIntensity=0.6,
               ambient=0.5, lightPos=[1300, 250], specular=0.3,     # front face ~1.0 x the picture (0.6 x 0.75 + 0.5)
               radius=[0.1, 0.5, 1.0, 1.6, 2.2, 2.6, 2.6, 2.6, 2.6], opacity=[100, 100, 100, 95, 85, 65, 40, 15, 0])
# Glass Wipe as a refractive accent where the symbiote peels away: the plate over itself, so only the moving edge band
# (luma contour = completion) is refracted. Subtle: low displacement, opacity <= 70.
GLASS = dict(cut="C04", f0=154, completion=[22, 34, 46, 58, 70], opacity=[35, 70, 70, 50, 20], displacement=32, softness=30)


def _rgb_frames(seq, frames, w=240):
    """{frame: HxWx3 float array} (numpy) of a PNG sequence, or None without numpy."""
    try:
        import numpy as np
    except ImportError:
        return None
    import subprocess
    ff = "/home/nikhil/code/film-making/bin/ffmpeg"
    ff = ff if os.path.exists(ff) else "ffmpeg"
    out = {}
    for f in frames:
        src = Path(seq["dir"]) / ("f_%05d.png" % f)
        if not src.exists():
            continue
        raw = subprocess.run([ff, "-v", "error", "-i", str(src), "-vf", f"scale={w}:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        h = len(raw) // (w * 3)
        out[f] = np.frombuffer(raw, np.uint8)[:h * w * 3].reshape(h, w, 3) / 255.0
    return out


def ray_center(a, W=1920, H=1080):
    """The brightest non-skin area of a frame (box-blurred highlight mask above its 90th percentile, biased to the
    frame centre so rays never start in a corner) -> [x, y] in comp pixels."""
    import numpy as np
    y = a @ [0.2126, 0.7152, 0.0722]
    h, w = y.shape
    mx, mn = a.max(2), a.min(2)
    sat = (mx - mn) / np.maximum(mx, 1e-4)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    hue = (np.degrees(np.arctan2(np.sqrt(3) * (g - b), 2 * r - g - b)) + 360) % 360
    skin = (hue > 5) & (hue < 48) & (sat > 0.15) & (sat < 0.65) & (mx > 0.3)
    sk = skin.astype(float)
    for ax in (0, 1):                      # grow the skin mask (r=10): face highlights are near-white, not skin-hued
        c = np.cumsum(np.pad(sk, [(11, 10) if k == ax else (0, 0) for k in (0, 1)], mode="edge"), ax)
        sk = (np.take(c, range(21, c.shape[ax]), ax) - np.take(c, range(0, c.shape[ax] - 21), ax)) / 21.0
    m = np.clip(y - np.quantile(y, 0.9), 0, None) * (sk < 0.04)
    for ax in (0, 1):                      # box blur r=12 along both axes
        c = np.cumsum(np.pad(m, [(13, 12) if k == ax else (0, 0) for k in (0, 1)], mode="edge"), ax)
        m = (np.take(c, range(25, c.shape[ax]), ax) - np.take(c, range(0, c.shape[ax] - 25), ax)) / 25.0
    yy, xx = np.indices(m.shape)
    m = m * np.exp(-(((xx - w / 2) / (0.3 * w)) ** 2 + ((yy - h / 2) / (0.3 * h)) ** 2))
    iy, ix = np.unravel_index(m.argmax(), m.shape)
    return [int(round(ix / w * W)), int(round(iy / h * H))]


def ray_centers(seq, frames, cache_dir=None):
    """{frame: [x, y]} for the given plate frames (cached like plate_luma); {} without numpy (rays then centre on the frame)."""
    if not seq or not frames:
        return {}
    key = f"rc2|{seq['dir']}|{seq['start']}|{seq['n']}|{os.path.getmtime(seq['first']):.0f}"
    cache = Path(cache_dir) / "ray_centers.json" if cache_dir else None
    C = json.loads(cache.read_text()) if cache and cache.exists() else {}
    have = C.get(key, {})
    need = [f for f in frames if str(f) not in have]
    if need:
        A = _rgb_frames(seq, need)
        if A is None:
            return {int(k): v for k, v in have.items()}
        for f, a in A.items():
            have[str(f)] = ray_center(a)
        if cache:
            C[key] = have
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(C))
    return {f: have[str(f)] for f in frames if str(f) in have}


def accents(E, P, luma, cache_dir=None):
    plate = P.get("plate")
    cuts = sorted(E["cuts"], key=lambda c: c["f"])
    rays = []
    for i, C in enumerate(cuts):
        if C["type"] not in RAYS["types"]:
            continue
        f = C["f"]
        nxt = cuts[i + 1]["w0"] if i + 1 < len(cuts) else E["outro"]["f0"]
        n = min(len(RAYS["shape"]), nxt - f)
        if n < RAYS["min_frames"]:
            continue
        op = []
        for k in range(n):
            m = luma.get(f + k)
            h = max(RAYS["head_min"], headroom(m[0] if m else None))
            op.append([f + k, round(RAYS["opacity"] * RAYS["shape"][k] * h, 1)])
        op.append([f + n, 0.0])
        rays.append(dict(id=C["id"], f0=f, f1=f + n, opacity=op))
    cen = ray_centers(plate, [r["f0"] + 1 for r in rays], cache_dir)
    for r in rays:
        r["center"] = cen.get(r["f0"] + 1, [960, 540])
    A = dict(rays=rays, raysFx={k: RAYS[k] for k in ("intensity", "radius", "warpSoftness", "knee", "gain")})
    S = next((c for c in cuts if c["id"] == SHATTER["cut"]), None)
    if S and plate and plate["start"] <= S["f"] < plate["start"] + plate["n"]:
        A["shatter"] = dict(SHATTER, f0=S["f"], still=str(Path(plate["dir"]) / ("f_%05d.png" % S["f"])))
    G = next((c for c in cuts if c["id"] == GLASS["cut"]), None)
    if G:
        A["glass"] = dict(GLASS)
    return A


def extend(E, stage_dir=None, outro_dir=None, cache_dir=None):
    """E (edl.json dict) -> E with E.x.finish and E.x.titles (and E.titles reduced to v2's 2D styles)."""
    end = E["outro"]["f0"]
    L = looks()
    act_idx = act_keys(E, end)
    P = passes(stage_dir, outro_dir)
    win = [x for C in E["cuts"] for x in range(C["w0"], C["w1"])]
    luma = plate_luma(P.get("plate"), win, cache_dir) if P.get("plate") else {}
    X = dict(passes=P, gradeEnd=end, looks=L, actKeys=act_idx, trim=trim_keys(E, end),
             finish=FINISH, skin=SKIN, lens=lens_plan(E, load_zvec(stage_dir), luma), letterbox=letterbox(E), textTint=text_tint(L),
             textGlow=TEXT_GLOW, lightGlows=LIGHT_GLOWS)
    X["accents"] = accents(E, P, plate_luma(P.get("plate"), [x for C in E["cuts"] for x in range(C["f"], C["f"] + 6)], cache_dir)
                           if P.get("plate") else {}, cache_dir)
    T = titles_E(E)
    E = dict(E, titles=T["titles"])
    E.setdefault("x", {})
    E["x"] = dict(E["x"], finish=X, titles=T["x"]["titles"])
    return E
