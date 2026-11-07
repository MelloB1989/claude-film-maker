"""Garment clipping from depth layers, per (under, over) pair and per frame: the rules agent-02 built for round 4 of
the karma reel (films/host-studio/reel/r4/clip_pass.py) as a core module, so qa.clip, the cloth QA (qa.cloth runs it
per simulated frame) and the gate all judge a pixel the same way.

Every layer is the depth (cm from the camera, >= EMPTY where the layer is absent) of ONE part captured alone from the
same camera: Body, Face, each garment. A flat list of w*h floats, row-major, top row first.

How a pixel is judged, for a pair (under U, over G):
- it CLIPS where G is there and U is nearer than G by more than `tol_cm` and at most `band_cm`: U came out through
  G. The band drops what is legitimately seen through an opening (a scoop neckline, his neck in front of the tee's
  back collar: the gap there is the body's depth, 10-25 cm).
- An arm or a hand held in FRONT of the garment is nearer by a few cm too. So a cluster of such pixels counts only if
  it meets an INTERSECTION EDGE: next to it (8-neighbours) U lies just under G (behind it by at most `near_cm`), i.e.
  the surface goes into the cloth there. An arm in front of a tee borders tee with nothing under it (MetaHuman cuts
  the torso skin away under its garments), so it does not count; a hand pressed into the trousers does.

`fraction` = clipping px / G's px. For a MetaHuman's face under a tee, `neck_px` is the gate (the round-4 ruling):
Face>tee pixels under the collar BAND, i.e. more than `neck_margin_cm` (projected at the rim's depth) below the
tee's front collar rim, and not within `at_open_960` px (at 960 wide) of the opening (his neck at the collar's edge).

The silhouette check compares the garment's covered pixels with a reference capture of the same frame (the garment's
real shape, or a previous version): a balloon (a WPO inflate, a thick refit) shows as + percent.

A presenter on a set adds two checks (round 6, the explainers): set pieces (a chair, a desk, a studio mic) are captured
as layers like any part, so a pair such as (Body, Chair) or (Chair, Trousers) is judged by the same rule; and
`mouth_blocked` counts the pixels of a disc around the mouth where a blocker (the mic) is nearer than the face: a mic
covering the mouth, from the camera's own view.

Pure Python, no `unreal`: runs in the editor and in tests."""
from __future__ import annotations

import math

from .issues import issue

EMPTY = 1.0e7
SKIN = ("Body", "Face")
# what an under layer may never come through: skin under every garment that covers it; the trousers under a tee's or
# top's hem; shoes under the trousers' hem; a top under an overshirt
UNDER_OVER = (("Trousers", "tee"), ("Trousers", "Top"), ("shoes", "Trousers"), ("Top", "Overshirt"),
              ("Trousers", "Overshirt"))
UPPER = ("tee", "Top", "Overshirt", "Torso", "Shirt", "Hoodie", "Jacket")  # garments a face's neck can come through
DEFAULTS = {"tol_cm": 0.3, "band_cm": 3.0, "near_cm": 1.5, "rim_jump_cm": 4.0, "neck_margin_cm": 1.0,
            "at_open_960": 5.0, "rim_reach_px": 24, "tongue_cm": 4.0}
GATE = {"pair_fraction": 0.001, "neck_px": 0, "silhouette_pct": 2.0}


def pairs(names) -> list:
    """(under, over) pairs to judge among the captured layer names: Body under every garment; Face under upper-body
    garments; the fixed garment-over-garment pairs (UNDER_OVER) where both are there."""
    names = list(names)
    gs = [n for n in names if n not in SKIN]
    out = [(u, g) for g in gs for u in SKIN if u in names and (u == "Body" or g in UPPER)]
    out += [(u, g) for u, g in UNDER_OVER if u in names and g in names]
    return out


def _clusters(mask: set, w: int, h: int, keep_edge: set) -> list:
    """8-connected blobs of mask (pixel indices): [(pixels, edge_ok)], edge_ok if any 8-neighbour outside the blob
    is in keep_edge."""
    seen, out = set(), []
    for s in mask:
        if s in seen:
            continue
        stack, blob, edge = [s], [], False
        seen.add(s)
        while stack:
            i = stack.pop()
            blob.append(i)
            y, x = divmod(i, w)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    xx, yy = x + dx, y + dy
                    if (dx or dy) and 0 <= xx < w and 0 <= yy < h:
                        j = yy * w + xx
                        if j in mask:
                            if j not in seen:
                                seen.add(j)
                                stack.append(j)
                        elif j in keep_edge:
                            edge = True
        out.append((blob, edge))
    return out


def _box(blob, w, h) -> list:
    xs = [i % w for i in blob]
    ys = [i // w for i in blob]
    return [round(min(xs) / w, 3), round(min(ys) / h, 3), round((max(xs) + 1) / w, 3), round((max(ys) + 1) / h, 3)]


def judge_pair(layers: dict, under: str, over: str, w: int, h: int, *, tol_cm: float = 0.3, band_cm: float = 3.0,
               near_cm: float = 1.5) -> dict:
    """One pair at one frame. Returns {g_px, raw, px, fraction, seen, clusters: [{px, worst_cm, box}], mask: set}:
    raw = in-band px / g_px before the edge rule; seen = the share of clipping px where U is the nearest layer of all
    (actually visible)."""
    U, G = layers[under], layers[over]
    inband, shallow, gpx = set(), set(), 0
    for i in range(w * h):
        g = G[i]
        if g >= EMPTY:
            continue
        gpx += 1
        u = U[i]
        if u >= EMPTY:
            continue
        gap = g - u
        if tol_cm < gap <= band_cm:
            inband.add(i)
        elif -near_cm <= gap <= tol_cm:
            shallow.add(i)
    kept, blobs = set(), []
    for blob, edge in _clusters(inband, w, h, shallow):
        if edge:
            kept.update(blob)
            blobs.append({"px": len(blob), "worst_cm": round(max(G[i] - U[i] for i in blob), 2),
                          "box": _box(blob, w, h)})
    blobs.sort(key=lambda b: -b["px"])
    seen = sum(1 for i in kept if U[i] <= min(L[i] for L in layers.values()) + 1e-3)
    return {"g_px": gpx, "raw": round(len(inband) / gpx, 5) if gpx else 0.0, "px": len(kept),
            "fraction": round(len(kept) / gpx, 5) if gpx else 0.0, "seen": round(seen / len(kept), 3) if kept else 0.0,
            "clusters": blobs[:6], "mask": kept}


def neck_px(layers: dict, mask: set, w: int, h: int, fov_deg: float, *, face: str = "Face", over: str = "tee",
            rim_jump_cm: float = 4.0, neck_margin_cm: float = 1.0, at_open_960: float = 5.0, band_cm: float = 3.0,
            rim_reach_px: int = 24) -> dict:
    """The neck gate in pixels: of the Face>over clip pixels (mask), those BELOW the collar band.

    The collar rim, per image column, is the lowest pixel of the garment's front-surface top edge: a garment pixel
    whose pixel above has no garment, or garment more than rim_jump_cm further (its inside back seen over the front
    collar), with the face present above and nearer than the garment there (the neck seen above the collar). The band
    is neck_margin_cm (projected at the rim's depth) under that rim; a column without a rim takes the nearest rim
    column's within rim_reach_px, none: no band (everything counts). Of what lies below the band, a pixel within
    at_open_960 px (scaled from 960 wide) of the opening (face with no garment in front, or the garment's inside more
    than band_cm behind) is the neck at the collar's edge: counted as at_opening only.

    Returns {px, at_opening, clusters, rim_cols}."""
    F, T = layers[face], layers[over]
    fpx = (w / 2) / math.tan(math.radians(fov_deg) / 2)
    rim = {}
    for i in range(w, w * h):
        if T[i] >= EMPTY or F[i] >= EMPTY:
            continue
        j = i - w
        if F[j] >= EMPTY or not (T[j] >= EMPTY or T[j] - T[i] > rim_jump_cm) or not (T[j] >= EMPTY or F[j] < T[j]):
            continue
        x, y = i % w, i // w
        band = neck_margin_cm * fpx / max(T[i], 1.0)
        rim[x] = max(rim.get(x, (-1, 0.0)), (y, band))
    xs = sorted(rim)

    def edge(x):
        if x in rim:
            return rim[x]
        near = [k for k in xs if abs(k - x) <= rim_reach_px]
        return rim[min(near, key=lambda k: abs(k - x))] if near else None

    r = max(1, math.ceil(at_open_960 * w / 960 - 1e-6))
    below, at_open = set(), 0
    for i in mask:
        x, y = i % w, i // w
        e = edge(x)
        if not (e is None or y > e[0] + e[1]):
            continue
        near = False
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                xx, yy = x + dx, y + dy
                if 0 <= xx < w and 0 <= yy < h:
                    j = yy * w + xx
                    if F[j] < EMPTY and (T[j] >= EMPTY or T[j] - F[j] > band_cm):
                        near = True
                        break
            if near:
                break
        if near:
            at_open += 1
        else:
            below.add(i)
    blobs = [{"px": len(b), "worst_cm": round(max(T[i] - F[i] for i in b), 2), "box": _box(b, w, h)}
             for b, _ in _clusters(below, w, h, set())]
    blobs.sort(key=lambda b: -b["px"])
    return {"px": len(below), "at_opening": at_open, "clusters": blobs[:6], "rim_cols": len(rim)}


def neck_visible(layers: dict, mask: set, w: int, h: int, fov_deg: float, *, face: str = "Face", over: str = "tee",
                 band_cm: float = 3.0, tongue_cm: float = 4.0, seen_tol_cm: float = 1e-3) -> dict:
    """The neck gate as the VIEWER sees it (round 6, the orchestrator's re-scope): Face skin poking through the
    garment, not the neck rising a little above a hugging collar.

    Of the Face>over clip pixels (mask), only those where the face is the nearest of ALL layers (hair or a hand over
    it hides it) count, in two kinds:
    - ISLANDS: clusters (8-connected) that touch no OPENING pixel (face with no garment in front, or the garment's
      inside more than band_cm behind: the neck seen above/through the collar). Skin enclosed by cloth is a poke-through
      whatever its size (round 6 r6n1: a 39 px island under the collar at S15, the blob the orchestrator saw).
    - TONGUES: in a cluster joined to the opening, the pixels whose distance from the opening, walked through the
      cluster and converted to cm at their own depth, exceeds tongue_cm. Near the opening the neck simply continues
      over the collar's top edge (r6n2: one 262 px cluster from the rim down, passed by eye as a natural crew-neck
      hug); a long tongue of skin running down into the cloth still fails.
    Returns {px, island_px, tongue_px, islands, max_tongue_cm, clusters}."""
    F, T = layers[face], layers[over]
    fpx = (w / 2) / math.tan(math.radians(fov_deg) / 2)
    names = list(layers)
    seen = {i for i in mask if F[i] <= min(layers[n][i] for n in names) + seen_tol_cm}

    def opening(j):
        return F[j] < EMPTY and (T[j] >= EMPTY or T[j] - F[j] > band_cm) and j not in mask

    island_px, tongue_px, islands, max_tongue, blobs = 0, 0, 0, 0.0, []
    for blob, touches in _clusters(mask, w, h, {j for j in range(w * h) if opening(j)} if mask else set()):
        if not touches:
            vis = [i for i in blob if i in seen]
            if vis:
                islands += 1
                island_px += len(vis)
                blobs.append({"px": len(vis), "kind": "island", "worst_cm": round(max(T[i] - F[i] for i in vis), 2),
                              "box": _box(vis, w, h)})
            continue
        bset = set(blob)
        dist, frontier = {}, []
        for i in blob:  # seeds: cluster pixels next to an opening pixel
            y, x = divmod(i, w)
            if any(0 <= x + dx < w and 0 <= y + dy < h and opening((y + dy) * w + x + dx)
                   for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dx or dy):
                dist[i] = 0.0
                frontier.append(i)
        while frontier:  # Dijkstra-light: BFS by pixel steps, each step's length in cm at that pixel's depth
            nxt = []
            for i in frontier:
                y, x = divmod(i, w)
                step = F[i] / fpx
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        j = (y + dy) * w + x + dx
                        if (dx or dy) and 0 <= x + dx < w and 0 <= y + dy < h and j in bset:
                            d = dist[i] + step * (1.4142 if dx and dy else 1.0)
                            if d < dist.get(j, 1e18) - 1e-9:
                                dist[j] = d
                                nxt.append(j)
            frontier = nxt
        far = [i for i in blob if i in seen and dist.get(i, 0.0) > tongue_cm]
        if dist:
            max_tongue = max(max_tongue, max(dist.values()))
        if far:
            tongue_px += len(far)
            blobs.append({"px": len(far), "kind": "tongue", "worst_cm": round(max(T[i] - F[i] for i in far), 2),
                          "box": _box(far, w, h)})
    blobs.sort(key=lambda b: -b["px"])
    return {"px": island_px + tongue_px, "island_px": island_px, "tongue_px": tongue_px, "islands": islands,
            "max_tongue_cm": round(max_tongue, 2), "tongue_cm": tongue_cm, "clusters": blobs[:6]}


def coverage(layer: list) -> int:
    """Pixels a layer covers."""
    return sum(1 for z in layer if z < EMPTY)


def silhouette(layer: list, ref: list) -> dict:
    """The garment's covered pixels against a reference capture of the same frame and camera: {px, ref_px, pct}
    (+ = bigger than the reference: ballooned)."""
    a, b = coverage(layer), coverage(ref)
    return {"px": a, "ref_px": b, "pct": round(100.0 * (a - b) / b, 2) if b else None}


def judge_frame(layers: dict, w: int, h: int, fov_deg: float, *, pair_list=None, neck_over: str = "",
                **knobs) -> dict:
    """Every pair at one frame: {"U>G": judge_pair minus its mask, ..., "neck_px": {...} (with a Face>upper pair),
    "_mask": the union of clip pixels (for the mask image)}. knobs: DEFAULTS' names."""
    k = {**DEFAULTS, **knobs}
    out, union = {}, set()
    for u, g in (pair_list or pairs(layers)):
        if u not in layers or g not in layers:
            continue
        r = judge_pair(layers, u, g, w, h, tol_cm=k["tol_cm"], band_cm=k["band_cm"], near_cm=k["near_cm"])
        m = r.pop("mask")
        if u == "Face" and g in UPPER and (not neck_over or g == neck_over) and "neck_px" not in out:
            out["neck_px"] = neck_px(layers, m, w, h, fov_deg, over=g, rim_jump_cm=k["rim_jump_cm"],
                                     neck_margin_cm=k["neck_margin_cm"], at_open_960=k["at_open_960"],
                                     band_cm=k["band_cm"], rim_reach_px=k["rim_reach_px"])
            out["neck_px"]["over"] = g
            out["neck_visible"] = neck_visible(layers, m, w, h, fov_deg, over=g, band_cm=k["band_cm"],
                                               tongue_cm=k["tongue_cm"])
            out["neck_visible"]["over"] = g
        union |= m
        out[f"{u}>{g}"] = r
    out["_mask"] = union
    return out


def project_px(info: dict, p, w: int, h: int) -> tuple:
    """A world point in a camera's picture (view.camera_info's loc, rot, fov = horizontal degrees): (x px, y px,
    depth cm along the lens axis); depth <= 0 is behind the lens."""
    pr, yw, rl = (math.radians(float(info["rot"][k])) for k in ("pitch", "yaw", "roll"))
    sp, cp, sy, cy, sr, cr = math.sin(pr), math.cos(pr), math.sin(yw), math.cos(yw), math.sin(rl), math.cos(rl)
    fwd = (cp * cy, cp * sy, sp)
    right = (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp)
    up = (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp)
    d = [float(p[i]) - float(info["loc"][i]) for i in range(3)]
    z = sum(a * b for a, b in zip(d, fwd))
    if z <= 1e-6:
        return float("nan"), float("nan"), z
    half = math.tan(math.radians(float(info["fov"])) / 2)
    x = sum(a * b for a, b in zip(d, right)) / (z * half)  # -1..1 across the width
    y = sum(a * b for a, b in zip(d, up)) / (z * half) * (w / h)
    return (x + 1) / 2 * w, (1 - y) / 2 * h, z


def mouth_blocked(layers: dict, centers: list, radius_px: float, *, blocker: str = "Mic", face: str = "Face",
                  w: int, h: int, tol_cm: float = 0.5) -> dict:
    """Pixels of the mouth (discs of radius_px around each projected mouth point (x, y, depth)) where `blocker` is
    nearer than the face (or than the point's own depth where the face layer is absent) by more than tol_cm.
    Returns {"disc_px", "blocked_px", "share", "box"}; blocked_px 0 = the mouth is clear in this camera."""
    B, F = layers[blocker], layers.get(face)
    disc, hit = set(), set()
    r = max(1.0, float(radius_px))
    for cx, cy, cz in centers:
        if not (cz > 0) or math.isnan(cx):
            continue
        for y in range(max(0, int(cy - r)), min(h, int(cy + r) + 1)):
            for x in range(max(0, int(cx - r)), min(w, int(cx + r) + 1)):
                if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
                    continue
                i = y * w + x
                disc.add(i)
                ref = F[i] if F is not None and F[i] < EMPTY else cz
                if B[i] < EMPTY and B[i] < ref - tol_cm:
                    hit.add(i)
    return {"disc_px": len(disc), "blocked_px": len(hit), "share": round(len(hit) / len(disc), 4) if disc else 0.0,
            "box": _box(hit, w, h) if hit else None}


def summarize(frames: dict) -> dict:
    """{shot: {frame: judge_frame result}} -> the worst per pair ({fraction, at}), the worst neck_px ({px, at}) and
    the worst silhouette ({pct, at}) where frames carry one."""
    worst = {}
    for shot, per in frames.items():
        if not isinstance(per, dict):
            continue
        for f, fr in per.items():
            if not isinstance(fr, dict):
                continue
            at = f"{shot}@{f}"
            for key, v in fr.items():
                if not isinstance(v, dict):
                    continue
                if "fraction" in v and v["fraction"] >= worst.get(key, {"fraction": -1})["fraction"]:
                    worst[key] = {"fraction": v["fraction"], "px": v.get("px", 0), "at": at}
                elif key == "neck_px" and v["px"] >= worst.get(key, {"px": -1})["px"]:
                    worst[key] = {"px": v["px"], "at_opening": v.get("at_opening", 0), "at": at}
                elif key == "neck_visible" and v["px"] >= worst.get(key, {"px": -1})["px"]:
                    worst[key] = {"px": v["px"], "island_px": v.get("island_px", 0), "tongue_px": v.get("tongue_px", 0),
                                  "max_tongue_cm": v.get("max_tongue_cm"), "at": at}
                elif key == "mouth" and v.get("blocked_px", 0) >= worst.get(key, {"blocked_px": -1})["blocked_px"]:
                    worst[key] = {"blocked_px": v["blocked_px"], "share": v.get("share", 0.0), "at": at}
                elif key == "silhouette" and v.get("pct") is not None and \
                        abs(v["pct"]) >= abs(worst.get(key, {"pct": 0.0})["pct"] or 0.0):
                    worst[key] = {"pct": v["pct"], "at": at}
    return worst


def gate(frames: dict, subject: str, *, pair_fraction: float = GATE["pair_fraction"], neck_max_px: int = GATE["neck_px"],
         silhouette_pct: float = GATE["silhouette_pct"], before: dict | None = None, before_slack: float = 0.01,
         mouth_max_px: int = 0, neck_rule: str = "rim",
         info_pairs=("Face>tee", "Face>Top", "Face>Overshirt")) -> list:
    """Issues from a qa.clip run's frames ({shot: {frame: result}}):
    - every frame's pair fraction over `pair_fraction` (~4 px of a 4400 px tee): fail, except the info_pairs (a face
      under an upper garment: depth cannot tell the neck band from a patch there, neck_px gates it), and, with
      `before` (an earlier run's frames, e.g. a costume whose open neckline reads high on clean frames), a pair is
      judged against its own worst before + before_slack instead;
    - neck_px over neck_max_px in any frame: fail (a missing neck_px where a Face>upper pair was judged: fail too);
      with neck_rule "visible" the gated count is neck_visible (islands + tongues, the round-6 re-scope) and neck_px
      stays in the frames as info;
    - |silhouette pct| over silhouette_pct: fail (a balloon, or a garment that shrank);
    - a mouth check (frames with "mouth") over mouth_max_px blocked pixels: fail (the mic covers the mouth)."""
    out = []
    prior = summarize(before) if before else {}
    for shot, per in frames.items():
        if not isinstance(per, dict):
            continue
        if "error" in per:
            out.append(issue("clip.shot_error", "fail", f"{subject} {shot}: {per['error']}",
                             "fix the shot name (seq.cuts lists them) and run qa.clip again", subject=subject))
            continue
        for f, fr in per.items():
            for key, v in fr.items():
                if not isinstance(v, dict) or "fraction" not in v or key in info_pairs:
                    continue
                limit = (prior[key]["fraction"] + before_slack) if key in prior else pair_fraction
                if v["fraction"] > limit:
                    u, g = key.split(">")
                    c = (v.get("clusters") or [{}])[0]
                    out.append(issue("clip.pair", "fail",
                                     f"{subject} {shot} f{f}: {u} comes out through {g}: {v['px']} px "
                                     f"({100 * v['fraction']:.2f}% of {g}, limit {100 * limit:.2f}%), up to "
                                     f"{c.get('worst_cm', 0)} cm",
                                     _pair_fix(u, g), subject=subject, frame=f, camera=shot, box=c.get("box"),
                                     value=v["fraction"], expected=limit))
            if any(k.startswith("Face>") and k.split(">")[1] in UPPER for k in fr) and "neck_px" not in fr:
                out.append(issue("clip.neck_missing", "fail", f"{subject} {shot} f{f}: no neck_px measured",
                                 "run qa.clip with the Face layer and the upper garment captured", subject=subject,
                                 frame=f, camera=shot))
            n = fr.get("neck_visible") if neck_rule == "visible" else fr.get("neck_px")
            if neck_rule == "visible" and fr.get("neck_px") is not None and n is None:
                out.append(issue("clip.neck_missing", "fail", f"{subject} {shot} f{f}: no neck_visible measured",
                                 "re-judge the frame with this fmqa (neckscan reads a qa.clip out_dir)",
                                 subject=subject, frame=f, camera=shot))
            if n and n["px"] > neck_max_px:
                c = (n.get("clusters") or [{}])[0]
                out.append(issue("clip.neck", "fail",
                                 f"{subject} {shot} f{f}: the face's neck comes out through the {n.get('over', 'tee')} "
                                 f"below the collar band: {n['px']} px (limit {neck_max_px}), up to "
                                 f"{c.get('worst_cm', 0)} cm",
                                 "refit the garment with the FACE in the collider (garment.fit: --collider body,face, "
                                 "neck ease >= 0.8 cm), not a WPO push; then qa.clip again",
                                 subject=subject, frame=f, camera=shot, box=c.get("box"), value=n["px"],
                                 expected=neck_max_px))
            m = fr.get("mouth")
            if m and (m.get("error") or m.get("blocked_px", 0) > mouth_max_px):
                out.append(issue("clip.mouth", "fail",
                                 f"{subject} {shot} f{f}: " + (f"mouth not measured: {m['error']}" if m.get("error") else
                                 f"the {m.get('blocker', 'mic')} covers the mouth: {m['blocked_px']} of "
                                 f"{m['disc_px']} px (limit {mouth_max_px})"),
                                 "move the mic down/aside on its arm (it sits below the chin line, off the lips' axis "
                                 "to the lens), or re-angle this camera", subject=subject, frame=f, camera=shot,
                                 box=m.get("box"), value=m.get("blocked_px"), expected=mouth_max_px))
            s = fr.get("silhouette")
            if s and s.get("pct") is not None and abs(s["pct"]) > silhouette_pct:
                out.append(issue("clip.silhouette", "fail",
                                 f"{subject} {shot} f{f}: the garment covers {s['pct']:+.1f}% px vs the reference "
                                 f"(limit +-{silhouette_pct}%)",
                                 "a balloon: lower the ease/inflate (garment.fit ease_cm), remove any WPO inflate; "
                                 "a shrink: the garment lost its leader or LOD", subject=subject, frame=f, camera=shot,
                                 value=s["pct"], expected=silhouette_pct))
    return out


def _pair_fix(u, g) -> str:
    if u in SKIN:
        return (f"refit {g} around the {u.lower()} with real ease (garment.fit) or hide the {u.lower()} under it "
                f"(body.hide_under); check the pose's twist/bend at this frame (a garment weight problem shows only "
                f"in poses: garment.fit transfers weights from the body)")
    return f"refit {u} to sit inside {g} (garment.fit with {g} in the collider and ease_cm >= 0.3 there)"
