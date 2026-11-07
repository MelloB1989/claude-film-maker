"""Gesture annotation for the R7 mocap library (agent-08).

A retargeted clip's joint tracks (written by retarget_blender.py: per frame, component-space positions in cm of the
shoulders, elbows, wrists, spine_05 and head) become agent-10's clips.json entry: the gesture events (prep, stroke,
hold end, retract), hand, energy, size, target, and the frames where the hands rest.

The stroke is the apex of the wrist's speed in a movement phase that leaves the rest; the phase that brings the hand
back is its retraction (McNeill's prep / stroke / hold / retract). A phase that leaves and is followed by another that
leaves again (beats) holds until the next one starts. Both hands striking within 0.15 s make one `both` event.

    python3 annotate.py joints.json catalog.json clip_id     # prints the library entry
"""
import json
import math
import sys

SPEED_MOVE = 18.0   # cm/s: above it the wrist is moving (a phase)
SPEED_REST = 8.0    # cm/s: below it, both wrists, the hands rest
REST_MIN_S = 0.5
MIN_PHASE_S = 0.12
BOTH_S = 0.15
ENERGY_FULL = 160.0  # cm/s peak wrist speed for energy 1
SIZE_CM = (10.0, 25.0)  # displacement from the rest: < small < medium < big


def sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def norm(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = norm(a) or 1.0
    return [a[0] / n, a[1] / n, a[2] / n]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def body_frame(j, f=0):
    """(fwd, left, up) unit vectors at frame f: up from spine_05 to the head, left from the right shoulder to the left
    one, fwd perpendicular to both, toward the hands (UE's component space is left-handed, so no cross-product
    sign is trusted)."""
    up = unit(sub(j["head"][f], j["spine_05"][f]))
    left = sub(j["upperarm_l"][f], j["upperarm_r"][f])
    left = unit(sub(left, [u * dot(left, up) for u in up]))
    fwd = cross(left, up)
    n = len(j["hand_l"])
    hands = [sum(j[h][g][k] for h in ("hand_l", "hand_r") for g in range(n)) / (2 * n) for k in range(3)]
    if dot(fwd, sub(hands, j["spine_05"][f])) < 0:
        fwd = [-x for x in fwd]
    return fwd, left, up


def smooth(xs, w=2):
    out = []
    for i in range(len(xs)):
        lo, hi = max(0, i - w), min(len(xs), i + w + 1)
        out.append(sum(xs[lo:hi]) / (hi - lo))
    return out


def speeds(track, fps):
    """Wrist speed per frame, cm/s, smoothed over 5 frames."""
    v = [0.0] + [norm(sub(track[i], track[i - 1])) * fps for i in range(1, len(track))]
    v[0] = v[1] if len(v) > 1 else 0.0
    return smooth(v)


def phases(v, fps):
    """Runs of frames above SPEED_MOVE, at least MIN_PHASE_S long: [(f0, f1), …] inclusive."""
    out, f0 = [], None
    for i, s in enumerate(v + [0.0]):
        if s > SPEED_MOVE and f0 is None:
            f0 = i
        elif s <= SPEED_MOVE and f0 is not None:
            if (i - f0) / fps >= MIN_PHASE_S:
                out.append((f0, i - 1))
            f0 = None
    return out


def rest_windows(vl, vr, fps):
    out, f0 = [], None
    for i, (a, b) in enumerate(zip(vl + [99.0], vr + [99.0])):
        calm = a < SPEED_REST and b < SPEED_REST
        if calm and f0 is None:
            f0 = i
        elif not calm and f0 is not None:
            if (i - f0) / fps >= REST_MIN_S:
                out.append([f0, i - 1])
            f0 = None
    return out


def rest_point(track, vl, vr, rests):
    """The wrist's rest: its mean over the rest windows, else over its slowest tenth of frames."""
    fs = [f for a, b in rests for f in range(a, b + 1)]
    if not fs:
        order = sorted(range(len(track)), key=lambda f: vl[f] + vr[f])
        fs = order[:max(1, len(order) // 10)]
    return [sum(track[f][k] for f in fs) / len(fs) for k in range(3)]


def target_of(d, frame):
    """Where a stroke points, from the wrist's displacement d off its rest, in the body frame."""
    fwd, left, up = frame
    x, y, z = dot(d, fwd), dot(d, left), dot(d, up)
    if z > max(abs(x), abs(y)) and z > 8:
        return "up"
    if abs(y) > abs(x):
        return "her_right" if y < 0 else "her_left"
    return "front" if x > 0 else "camera"


def hand_events(track, v, rest, fps, frame, hand):
    """The strokes of one hand: [{prep_f, stroke_f, hold_end_f, retract_f, …}]."""
    ps = phases(v, fps)
    dist = [norm(sub(p, rest)) for p in track]
    out = []
    for i, (a, b) in enumerate(ps):
        apex = max(range(a, b + 1), key=lambda f: dist[f])
        if dist[apex] < dist[a] + 2.0:
            continue  # a return or a drift, not a stroke
        stroke = max(range(a, apex + 1), key=lambda f: v[f])
        nxt = ps[i + 1] if i + 1 < len(ps) else None
        if dist[b] < dist[apex] - 2.0:
            hold_end, retract = apex, b  # a beat: out and back in one movement
        elif nxt and dist[nxt[1]] < dist[nxt[0]] - 2.0:
            hold_end, retract = nxt[0], nxt[1]
        else:
            hold_end = nxt[0] if nxt else len(track) - 1
            retract = hold_end
            apex = max(range(a, hold_end + 1), key=lambda f: dist[f])
        disp = dist[apex]
        out.append({
            "hand": hand, "prep_f": a, "stroke_f": stroke, "hold_end_f": hold_end, "retract_f": retract,
            "energy": round(min(1.0, v[stroke] / ENERGY_FULL), 2),
            "size": "small" if disp < SIZE_CM[0] else "medium" if disp < SIZE_CM[1] else "big",
            "target": target_of(sub(track[apex], rest), frame),
            "peak_cm_s": round(v[stroke], 1), "disp_cm": round(disp, 1),
        })
    return out


def merge_both(ev_l, ev_r, fps):
    """Pairs of L and R strokes within BOTH_S become one `both` event (the earlier prep, the later retract)."""
    out, used = [], set()
    for r in ev_r:
        mate = next((k for k, l in enumerate(ev_l) if k not in used
                     and abs(l["stroke_f"] - r["stroke_f"]) / fps <= BOTH_S), None)
        if mate is None:
            out.append(r)
            continue
        used.add(mate)
        l = ev_l[mate]
        e = dict(r, hand="both", prep_f=min(l["prep_f"], r["prep_f"]),
                 hold_end_f=max(l["hold_end_f"], r["hold_end_f"]), retract_f=max(l["retract_f"], r["retract_f"]),
                 energy=max(l["energy"], r["energy"]), disp_cm=max(l["disp_cm"], r["disp_cm"]))
        e["size"] = "small" if e["disp_cm"] < SIZE_CM[0] else "medium" if e["disp_cm"] < SIZE_CM[1] else "big"
        out.append(e)
    out += [l for k, l in enumerate(ev_l) if k not in used]
    return sorted(out, key=lambda e: e["stroke_f"])


def annotate(joints: dict) -> dict:
    """Events, rest windows and side stats of one clip's joint tracks."""
    fps = joints["fps"]
    j = joints["joints"]
    frame = body_frame(j)
    vl, vr = speeds(j["hand_l"], fps), speeds(j["hand_r"], fps)
    rests = rest_windows(vl, vr, fps)
    ev_l = hand_events(j["hand_l"], vl, rest_point(j["hand_l"], vl, vr, rests), fps, frame, "L")
    ev_r = hand_events(j["hand_r"], vr, rest_point(j["hand_r"], vl, vr, rests), fps, frame, "R")
    events = merge_both(ev_l, ev_r, fps)
    travel = {h: round(sum(v) / len(v), 1) for h, v in (("L", vl), ("R", vr))}
    return {"fps": fps, "frames": [0, len(vl) - 1], "events": events, "rest": rests,
            "wrist_cm_s": travel,
            # the mic is on her LEFT: a clip whose left hand does more is mirrored before use
            "left_dominant": travel["L"] > 1.2 * travel["R"]}


def entry(cat: dict, ann: dict) -> dict:
    """agent-10's clips.json entry: the catalogue's fields + the annotation; each event gets the clip's first type
    unless the catalogue pins types to events (`event_types`)."""
    e = {k: cat[k] for k in ("id", "file", "source", "source_id", "licence", "licence_url", "seated", "types")}
    e.update(fps=ann["fps"], frames=ann["frames"], rest=ann["rest"], wrist_cm_s=ann["wrist_cm_s"],
             mirrored=cat.get("mirrored", False), length_s=round((ann["frames"][1] + 1) / ann["fps"], 2))
    pinned = cat.get("event_types", {})
    e["events"] = [dict(ev, type=pinned.get(str(i), cat["types"][0])) for i, ev in enumerate(ann["events"])]
    if "count" in cat["types"]:
        for ev in e["events"]:
            ev.setdefault("count", cat.get("count", 5))
    e["energy"] = round(max([ev["energy"] for ev in e["events"]] or [0.0]), 2)
    hands = {ev["hand"] for ev in e["events"]}
    e["hand"] = "both" if "both" in hands or hands == {"L", "R"} else (hands.pop() if hands else "none")
    if cat.get("derived_from"):
        e["derived_from"] = cat["derived_from"]
    return e


if __name__ == "__main__":
    joints = json.load(open(sys.argv[1]))
    cat = {c["id"]: c for c in json.load(open(sys.argv[2]))["clips"]}[sys.argv[3]]
    print(json.dumps(entry(cat, annotate(joints)), indent=1))
