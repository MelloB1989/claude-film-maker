"""Round 6 (agent-02, for agent-09's question): what qa.garment_look's collar gap and wall-only roll actually see at the
current frame. READ-ONLY (spawns nothing). Scrub first (film-ue op seq.scrub path=/Game/Reel/SEQ_Reel frame=F, twice
F+1 then F as qa.clip does), then:

    film-ue exec -c "exec(open('<tree>/films/host-studio/reel/r6/collar_cells.py').read())"

Same frame and math as fmbridge.ops.garment._collar (neck_01 -> head axis, angle from world X):
- per 10-degree angle: the band's LOCAL top (highest garment vert near the ring) vs the single top the roll uses;
- the worst wall-only roll cells (1 cm x 10 deg, as local_spread): every vertex's radius, height below the top and
  |n.u| (0 = a wall along the neck, 1 = a ledge across it), sorted by radius, so two layers show as two radius groups
  and a shoulder slope as radii rising with depth;
- the ring's gap: per 30-degree sector the ring verts' p75 distance to the skin and where the nearest skin point is
  (cm above/below the vertex along the neck axis): skin far BELOW = the culled face under the collar.
Numbers only."""
import math

import unreal
from fmbridge.ops import garment as G
from fmbridge.qa import garment_look as L

LABEL = globals().get("LABEL", "Host")
a = G.find_actor(LABEL)
parts = G.roles(a)
gc = parts["tee"]
gdm = G._posed(gc)
gv = G._verts(gdm)
keep = G._shown_verts(gc, gdm, ("short", "hidden"))
if keep is not None:
    gv = [gv[i] for i in keep if i < len(gv)]
gs = G._Surface(gdm)
b = parts["Body"]
n0, hd = b.get_socket_location("neck_01"), b.get_socket_location("head")
u = (hd - n0) * (1.0 / ((hd - n0).length() or 1.0))
ux, uy, uz = u.x, u.y, u.z
e1 = (1.0 - ux * ux, -ux * uy, -ux * uz)
n1 = math.sqrt(sum(c * c for c in e1)) or 1.0
e1 = tuple(c / n1 for c in e1)
e2 = (uy * e1[2] - uz * e1[1], uz * e1[0] - ux * e1[2], ux * e1[1] - uy * e1[0])
skins = [G._Surface(G._posed(parts[k])) for k in ("Face", "Body") if k in parts]
lim = math.sin(math.radians(L.COLLAR_WALL_DEG))
rows = []
for p in gv:
    t = (p - n0).dot(u)
    if not (-8.0 <= t <= 4.0):
        continue
    v = p - n0 - u * t
    ang = math.degrees(math.atan2(v.x * e2[0] + v.y * e2[1] + v.z * e2[2], v.x * e1[0] + v.y * e1[1] + v.z * e1[2])) % 360
    r = gs.nearest(p)
    nu = abs(r[2].dot(u)) if r else None
    best = None
    for sk in skins:
        q = sk.nearest(p)
        if q is not None and (best is None or (p - q[0]).length() < best[0]):
            best = ((p - q[0]).length(), (q[0] - p).dot(u))
    rows.append({"t": t, "r": v.length(), "ang": ang, "nu": nu, "wall": nu is None or nu <= lim,
                 "gap": best[0] if best else float("nan"), "skin_dt": best[1] if best else None})
rs = sorted(x["r"] for x in rows)
rmin = rs[min(L.COLLAR_MIN_N, len(rs)) - 1]
ring = [x for x in rows if rmin - 0.5 <= x["r"] <= rmin + 2.0]
top = max(x["t"] for x in ring)
out = {"n_window": len(rows), "rmin": round(rmin, 2), "top_used": round(top, 2), "local_top": {}, "gap": {}, "cells": []}
for k in range(36):
    sec = [x["t"] for x in rows if int(x["ang"] // 10) == k and x["r"] <= rmin + 4.0]
    if sec:
        out["local_top"][k * 10] = round(max(sec) - top, 2)
for k in range(12):
    g = sorted((x["gap"], x["skin_dt"]) for x in ring if int(x["ang"] // 30) == k)
    if g:
        p75 = g[int(0.75 * (len(g) - 1))]
        out["gap"][k * 30] = {"n": len(g), "p75": round(p75[0], 2), "skin_dt_at_p75": round(p75[1], 2) if p75[1] is not None else None}
cells = {}
for x in rows:
    if x["wall"] and top - L.COLLAR_ROLL_DEPTH_CM <= x["t"] <= top + 0.5:
        cells.setdefault((int(math.floor((x["t"] - top) / L.COLLAR_CELL[0])), int(x["ang"] // L.COLLAR_CELL[1])), []).append(x)
scored = []
for key, xs in cells.items():
    if len(xs) < 4:
        continue
    r0 = min(x["r"] for x in xs)
    xs = sorted((x for x in xs if x["r"] <= r0 + 4.0), key=lambda x: x["r"])
    rr = [x["r"] for x in xs]
    sp = L.percentile(rr, 0.9) - L.percentile(rr, 0.1)
    scored.append((sp, key, xs))
scored.sort(key=lambda s: -s[0])
for sp, key, xs in scored[:4]:
    out["cells"].append({"spread": round(sp, 2), "below_top_cm": -key[0], "angle_deg": key[1] * 10,
                         "verts": [[round(x["r"], 2), round(top - x["t"], 2), round(x["nu"], 2) if x["nu"] is not None else None]
                                   for x in xs]})
result = out
