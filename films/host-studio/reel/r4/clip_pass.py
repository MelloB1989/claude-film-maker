"""Round 4, clipping on a presenter (agent-02): what of the body (or an under-garment) shows through a garment, per
shot and frame of SEQ_Reel, from the shot's camera, as the viewer sees it. Editor-side, multi-tick; read-only on the
level (the QA capture rig comes and goes, as qa.penetration's does). Run in the editor:

    film-ue exec -c "TAG='before'; CHECKOUT='<checkout>'; exec(open(CHECKOUT + '/films/host-studio/reel/r4/clip_pass.py').read())"

Knobs (globals, all optional): LABEL ('Host' | 'Presenter'), SHOTS (camera-cut names, default his: Reel_S13, S15,
S17, S18; hers add S16), N (frames per shot, spread start..end, default 6), EXTRA ({shot: [frames]} measured too), W (capture width, default 480), BAND, TOL,
NEAR (cm, below), DIAG (True: also the A/B stills at each shot's middle frame), OUT (default /srv/ue/reel/r4/clip/TAG).

How a pixel is judged. Each layer (Body, Face, his tee, Trousers, shoes, ...) is depth-captured alone from the shot's
camera. For a pair (under U, over G), a pixel CLIPS where G is there and U is nearer than G by more than TOL and at
most BAND cm: U came out through G. BAND drops what is legitimately seen through an opening (her scoop neckline, his
neck in front of the tee's back collar: the gap there is the body's depth, 10-25 cm). An arm or hand in FRONT of the
garment is nearer by a few cm too, so a cluster of such pixels counts only if it meets an intersection edge: next to
it (8-neighbours) U lies just UNDER G (behind it by at most NEAR cm), i.e. the surface goes into the cloth there. An
arm held in front of the tee borders tee with nothing under it (MetaHuman cut the torso skin away under the tee), so
it does not count; a hand pressed into the trousers borders leg skin just under them, so it does.

The number per (frame, pair): `fraction` = clipping pixels / G's pixels (what agent-09's gate reads), with `raw` (all
in-band pixels, before the edge rule), the clusters (box as fractions of the frame, pixels, worst cm) and
`seen` = the share of clipping pixels actually visible (U is the nearest layer of all there).

Face>tee in pixels also takes in his neck seen just above the collar edge in front of the tee's inside (a band along
the collar, no clip: the orchestrator's review); depth alone does not tell that band from the blob just under it. So
for his face the gate reads `neck` instead, per frame, on the posed meshes (Geometry Script, as neck_probe.py): face
verts more than 2 cm below the tee's collar top and within 6 cm of it (n), how many stand outside the tee by more than
0.1 cm (out) and how far (max_out_cm). Clean: out 0.

Writes on the box only (face data with Host_Op on the level; never off it): OUT/clip.json (numbers), per frame
<shot>_<frame>_final.png (the scene through the camera), _depth.bin (the layers, for clip_rejudge.py), _mask.png (flat colours: body red, face orange, tee/top
green, trousers blue, shoes yellow, other garments cyan; clipping magenta), and with DIAG the A/B stills: _nobody.png
(body and face hidden), _nogarment.png (the over-garments hidden), _albedo_<layer>.png (each garment's own base
colour alone: a skin-coloured patch there is the garment's texture or material, not skin).
Returns the numbers (no images).
"""
import array
import json
import math
import os

try:
    import unreal
    from fmbridge.ops import call
    from fmbridge.ops.view import (_scrub, camera_info, capture, cut_camera, find_actor, read_pixels, remove_rig,
                                   to_image)
    from fmbridge.qa import image as _image
except ImportError:  # off the editor: clip_rejudge.py uses the rules below only
    unreal = None

SEQ = "/Game/Reel/SEQ_Reel"
LABEL = globals().get("LABEL", "Host")
HIS_SHOTS = ["Reel_S13", "Reel_S15", "Reel_S17", "Reel_S18"]
SHOTS = globals().get("SHOTS") or (HIS_SHOTS if LABEL == "Host" else ["Reel_S15", "Reel_S16", "Reel_S17", "Reel_S18"])
N = int(globals().get("N", 6))
W = int(globals().get("W", 480))
H = round(W * 9 / 16)
BAND, TOL, NEAR = float(globals().get("BAND", 3.0)), float(globals().get("TOL", 0.3)), float(globals().get("NEAR", 1.5))
DIAG = bool(globals().get("DIAG", True))
NECK_ONLY = bool(globals().get("NECK_ONLY", False))  # only the 3D neck check per frame (no captures: ~1 min)
# frames always measured besides the spread ones: his torso-twisting looks at her (agent-01, round 4): S15's hold at
# ~+65 deg neck with a 30 deg torso twist, S17's glance (neck ~+49, torso 12)
EXTRA = globals().get("EXTRA") or {"Reel_S15": [1150, 1220, 1290], "Reel_S17": [1390, 1397, 1404]}
TAG = globals().get("TAG", "now")
OUT = globals().get("OUT") or f"/srv/ue/reel/r4/clip/{LABEL}_{TAG}"
EMPTY = 1.0e7
FOV = 30.0  # the frame's horizontal field of view (deg), set per frame (saved with the layers)
SKIN = ("Body", "Face")
COL = {"Body": (220, 40, 40), "Face": (255, 150, 60), "tee": (40, 190, 70), "Top": (40, 190, 70),
       "Trousers": (50, 90, 230), "shoes": (240, 220, 40), "Overshirt": (40, 200, 200)}


def layers(a) -> dict:
    """The actor's skeletal mesh parts by role: Body, Face, and its garments (his default garment as 'tee', a
    component with shoes in its mesh name as 'shoes', the rest by component name). Grooms are left out: hair lies
    over a collar legitimately, so its depth says nothing about clipping (judged by eye on the stills)."""
    out = {}
    for c in a.get_components_by_class(unreal.SkeletalMeshComponent):
        if not c.is_visible():
            continue
        n = c.get_name()
        m = c.get_skeletal_mesh_asset()
        mesh = m.get_name().lower() if m else ""
        if n in SKIN or n in ("Trousers", "Top", "Overshirt"):
            out[n] = c
        elif "shoe" in mesh or "shoe" in n.lower() or "feet" in n.lower():
            out["shoes"] = c
        elif LABEL == "Host" and "tee" not in out:  # the default garment: "SkeletalMesh" on Trey, by elimination else
            out["tee"] = c
        else:
            out[n] = c
    return out


def pairs(names) -> list:
    """(under, over): skin under every garment; the trousers under his tee (the hem: its waistband must stay
    inside); the shoes under the trousers (the hem over the shoe tops); her top under her overshirt."""
    gs = [n for n in names if n not in SKIN]
    out = [(u, g) for g in gs for u in SKIN if u in names and (u == "Body" or g in ("tee", "Top", "Overshirt"))]
    for u, g in (("Trousers", "tee"), ("shoes", "Trousers"), ("Top", "Overshirt"), ("Trousers", "Overshirt")):
        if u in names and g in names:
            out.append((u, g))
    return out


def clusters(mask, keep_edge) -> list:
    """8-connected blobs of mask (a set of pixel indices): [(pixels, edge_ok)]: edge_ok if any 8-neighbour outside
    the blob is in keep_edge."""
    seen, out = set(), []
    for s in mask:
        if s in seen:
            continue
        stack, blob, edge = [s], [], False
        seen.add(s)
        while stack:
            i = stack.pop()
            blob.append(i)
            y, x = divmod(i, W)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    xx, yy = x + dx, y + dy
                    if (dx or dy) and 0 <= xx < W and 0 <= yy < H:
                        j = yy * W + xx
                        if j in mask:
                            if j not in seen:
                                seen.add(j)
                                stack.append(j)
                        elif j in keep_edge:
                            edge = True
        out.append((blob, edge))
    return out


def judge(d, under, over) -> dict:
    """One pair at one frame from the depth layers d[name] (lists, cm)."""
    U, G = d[under], d[over]
    inband, shallow, gpx = set(), set(), 0
    for i in range(W * H):
        g = G[i]
        if g >= EMPTY:
            continue
        gpx += 1
        u = U[i]
        if u >= EMPTY:
            continue
        gap = g - u
        if TOL < gap <= BAND:
            inband.add(i)
        elif -NEAR <= gap <= TOL:
            shallow.add(i)
    kept, blobs = set(), []
    for blob, edge in clusters(inband, shallow):
        if edge:
            kept.update(blob)
            xs = [i % W for i in blob]
            ys = [i // W for i in blob]
            blobs.append({"px": len(blob), "worst_cm": round(max(G[i] - U[i] for i in blob), 2),
                          "box": [round(min(xs) / W, 3), round(min(ys) / H, 3), round((max(xs) + 1) / W, 3),
                                  round((max(ys) + 1) / H, 3)]})
    blobs.sort(key=lambda b: -b["px"])
    nearest = [min(d[n][i] for n in d) for i in kept] if kept else []
    seen = sum(1 for i, z in zip(kept, nearest) if U[i] <= z + 1e-3)
    return {"g_px": gpx, "raw": round(len(inband) / gpx, 5) if gpx else 0.0, "px": len(kept),
            "fraction": round(len(kept) / gpx, 5) if gpx else 0.0, "seen": round(seen / len(kept), 3) if kept else 0.0,
            "clusters": blobs[:6], "_mask": kept}


RIM_JUMP = float(globals().get("RIM_JUMP", 4.0))  # cm: the tee's front surface ends at the collar (behind: its inside)
NECK_MARGIN = float(globals().get("NECK_MARGIN", 1.0))  # cm under the collar rim that is still the collar band


def neck_px(d, mask) -> dict:
    """The orchestrator's gate line for his neck patch, in pixels: Face>tee clip pixels (mask) BELOW the collar band.
    The collar rim, per image column x, is the lowest tee pixel of its front surface's top edge: a tee pixel whose
    pixel above has no tee or tee more than RIM_JUMP cm further (the tee's inside back, seen over the front collar),
    with his face nearer than the tee there (his neck seen above the collar). The band is NECK_MARGIN cm (projected at
    the rim's depth) under that rim. A column with no rim takes the nearest rim column's within 24 px; none: no band.
    The neck correctly in front of the collar's inner lip (the thin band) sits within it; the patch ~3 cm below does not."""
    F, T = d["Face"], d["tee"]
    fpx = (W / 2) / math.tan(math.radians(FOV) / 2)
    rim = {}
    for i in range(W, W * H):
        if T[i] >= EMPTY or F[i] >= EMPTY:
            continue
        j = i - W
        if F[j] >= EMPTY or not (T[j] >= EMPTY or T[j] - T[i] > RIM_JUMP) or not (T[j] >= EMPTY or F[j] < T[j]):
            continue
        x, y = i % W, i // W
        band = NECK_MARGIN * fpx / max(T[i], 1.0)
        rim[x] = max(rim.get(x, (-1, 0.0)), (y, band))
    xs = sorted(rim)

    def edge(x):
        if x in rim:
            return rim[x]
        near = [k for k in xs if abs(k - x) <= 24]
        return rim[min(near, key=lambda k: abs(k - x))] if near else None

    below = set()
    for i in mask:
        x, y = i % W, i // W
        e = edge(x)
        if e is None or y > e[0] + e[1]:
            below.add(i)
    blobs = []
    for blob, _ in clusters(below, set()):
        bx = [i % W for i in blob]
        by = [i // W for i in blob]
        blobs.append({"px": len(blob), "worst_cm": round(max(T[i] - F[i] for i in blob), 2),
                      "box": [round(min(bx) / W, 3), round(min(by) / H, 3), round((max(bx) + 1) / W, 3),
                              round((max(by) + 1) / H, 3)]})
    blobs.sort(key=lambda b: -b["px"])
    return {"px": len(below), "clusters": blobs[:6], "rim_cols": len(rim)}


def neck3d(face_c, tee_c, body_c) -> dict:
    """His face mesh out through the tee, on the posed meshes (render LOD 0). For each face vert below the tee's top,
    within 6 cm of it and outside the cloth as rendered (its inflate added) by > 0.1 cm (out_all), a ray is cast from his neck/spine axis (the nearest point
    on spine_05 -> neck_02) out to the vert: if it crosses the tee before reaching the vert, the vert came out
    THROUGH the cloth (out); if not, it is his throat seen through the neckline's opening, no clip. (His tee is a
    closed shell: it has no open rim to measure from.)"""
    SU, SP, MQ, LU = (unreal.GeometryScript_SceneUtils, unreal.GeometryScript_MeshSpatial,
                      unreal.GeometryScript_MeshQueries, unreal.GeometryScript_List)
    from fmbridge.ops.mh.actor import _pick
    opts = unreal.GeometryScriptCopyMeshFromComponentOptions()
    lod = unreal.GeometryScriptMeshReadLOD()
    lod.set_editor_property("lod_type", unreal.GeometryScriptLODType.RENDER_DATA)
    opts.set_editor_property("requested_lod", lod)

    def copy(comp):
        dm = unreal.DynamicMesh()
        SU.copy_mesh_from_component(comp, dm, opts, True)
        return dm

    def verts(dm):
        return LU.convert_vector_list_to_array(_pick(MQ.get_all_vertex_positions(dm, False), "GeometryScriptVectorList"))

    tee, face = copy(tee_c), copy(face_c)
    bvh = _pick(SP.build_bvh_for_mesh(tee), "GeometryScriptDynamicMeshBVH")
    q = unreal.GeometryScriptSpatialQueryOptions()
    top = max(p.z for p in verts(tee))
    a0, a1 = body_c.get_socket_location("spine_05"), body_c.get_socket_location("neck_02")
    ax = a1 - a0
    L2 = max(ax.dot(ax), 1e-6)

    def crosses(p) -> bool:
        t = max(0.0, min(1.0, (p - a0).dot(ax) / L2))
        o = a0 + ax * t
        d = p - o
        dist = d.length()
        if dist < 1e-3:
            return False
        hit = _pick(SP.find_nearest_ray_intersection_with_mesh(tee, bvh, o, d * (1.0 / dist), q),
                    "GeometryScriptRayHitResult")
        return bool(hit.get_editor_property("hit")) and float(hit.get_editor_property("ray_parameter")) < dist - 0.05

    # the inflate is a World Position Offset (no geometry): the cloth as rendered stands out along its normal by
    # FM_Inflate + FM_Neck x t x f (neck_inflate.py), read from his worn tee instance; t and f from the point's
    # position in his body's component space (= mesh space, the pose aside: close enough over his upper chest)
    mi = next((m for nm, m in zip(tee_c.get_material_slot_names(), tee_c.get_materials()) if "shirt" in str(nm).lower()),
              None)
    k = {}
    for name in ("FM_Inflate", "FM_Neck", "FM_NeckZ0", "FM_NeckZ1", "FM_NeckFront", "FM_NeckFrontBias"):
        try:
            k[name] = float(unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(mi, name))
        except Exception:
            k[name] = 0.0
    inv = body_c.get_world_transform()

    def inflate(qp) -> float:
        a = k["FM_Inflate"]
        if k["FM_Neck"] <= 0:
            return a
        m = inv.inverse_transform_location(qp)
        z0, z1 = k["FM_NeckZ0"], k["FM_NeckZ1"]
        t = max(0.0, min(1.0, (m.z - z0) / (z1 - z0 if z1 != z0 else 1.0)))
        f = max(0.0, min(1.0, m.y * k["FM_NeckFront"] + k["FM_NeckFrontBias"]))
        return a + k["FM_Neck"] * t * f

    n = out_all = out = 0
    mx = 0.0
    for p in verts(face):
        if p.z > top:
            continue
        tp = _pick(SP.find_nearest_point_on_mesh(tee, bvh, p, q), "GeometryScriptTrianglePoint")
        if not tp.get_editor_property("valid"):
            continue
        qp = tp.get_editor_property("position")
        dv = p - qp
        if dv.length() > 6.0:
            continue
        n += 1
        sd = dv.dot(_pick(MQ.get_triangle_face_normal(tee, tp.get_editor_property("triangle_id")), "Vector")) - inflate(qp)
        if sd > 0.1:
            out_all += 1
            if crosses(p):
                out += 1
                mx = max(mx, sd)
    return {"n": n, "out_all": out_all, "out": out, "max_out_cm": round(mx, 2),
            "inflate": {kk: round(v, 2) for kk, v in k.items() if v}}


def mask_image(d, clip) -> "_image.Image":
    names = list(d)
    data = bytearray(W * H * 3)
    for i in range(W * H):
        best, z = None, EMPTY
        for n in names:
            if d[n][i] < z:
                best, z = n, d[n][i]
        c = (255, 0, 255) if i in clip else COL.get(best, (0, 200, 220)) if best else (0, 0, 0)
        data[3 * i:3 * i + 3] = bytes(c)
    return _image.Image(W, H, 3, data)


def save(rt, path):
    _image.write(to_image(rt), path)
    return path


def run():
    os.makedirs(OUT, exist_ok=True)
    a = find_actor(LABEL)
    cuts = {c: (int(s), int(e)) for c, s, e in call("seq.cuts", path=SEQ)}
    rep = {"label": LABEL, "tag": TAG, "size": [W, H], "band_cm": BAND, "tol_cm": TOL, "near_cm": NEAR, "shots": {}}
    try:
        for shot in SHOTS:
            if shot not in cuts:
                rep["shots"][shot] = {"error": f"no camera cut {shot}: {sorted(cuts)}"}
                continue
            s, e = cuts[shot]
            frames = sorted({s + 2 + round(k * (e - 4 - s) / max(1, N - 1)) for k in range(N)} |
                            {f for f in EXTRA.get(shot, ()) if s <= f < e})
            mid = frames[len(frames) // 2]
            per = {}
            for f in frames:
                yield from _scrub(SEQ, f, 10)
                info = camera_info(cut_camera(SEQ, f), aspect=16 / 9)
                global FOV
                FOV = float(info["fov"])
                L = layers(a)  # fetched each frame: a component may have been re-created
                if NECK_ONLY:
                    per[f] = {"neck": neck3d(L["Face"], L["tee"], L["Body"])}
                    yield
                    continue
                d = {}
                for n, c in L.items():
                    rt = yield from capture(info, W, H, "depth", show_only=[c], warmup=1)
                    d[n] = read_pixels(rt, "r")[0]
                    yield
                fr, clip = {}, set()
                for u, g in pairs(list(d)):
                    r = judge(d, u, g)
                    if (u, g) == ("Face", "tee"):
                        fr["neck_px"] = neck_px(d, r["_mask"])
                    clip |= r.pop("_mask")
                    fr[f"{u}>{g}"] = r
                    yield
                base = os.path.join(OUT, f"{shot}_{f:04d}")
                _image.write(mask_image(d, clip), base + "_mask.png")
                # the depth layers themselves, so the rules can be re-run off the editor (clip_rejudge.py)
                with open(base + "_depth.bin", "wb") as fh:
                    head = json.dumps({"w": W, "h": H, "fov": FOV, "layers": list(d)}).encode()
                    fh.write(len(head).to_bytes(4, "little") + head)
                    for n in d:
                        array.array("f", d[n]).tofile(fh)
                rt = yield from capture(info, 2 * W, 2 * H, "final", warmup=4)
                save(rt, base + "_final.png")
                if DIAG and f == mid:
                    skin = [L[n] for n in SKIN if n in L]
                    over = [c for n, c in L.items() if n not in SKIN]
                    rt = yield from capture(info, 2 * W, 2 * H, "final", hidden=skin, warmup=4)
                    save(rt, base + "_nobody.png")
                    rt = yield from capture(info, 2 * W, 2 * H, "final", hidden=over, warmup=4)
                    save(rt, base + "_nogarment.png")
                    for n, c in L.items():
                        if n in SKIN:
                            continue
                        rt = yield from capture(info, 2 * W, 2 * H, "base_color", show_only=[c], warmup=1)
                        r_, g_, b_ = read_pixels(rt, "rgb")
                        lin = lambda v: int(255 * max(0.0, min(1.0, v)) ** (1 / 2.2))  # noqa: E731
                        data = bytearray(len(r_) * 3)
                        data[0::3] = bytes(lin(v) for v in r_)
                        data[1::3] = bytes(lin(v) for v in g_)
                        data[2::3] = bytes(lin(v) for v in b_)
                        _image.write(_image.Image(2 * W, 2 * H, 3, data), base + f"_albedo_{n}.png")
                        # skin-like albedo inside the garment alone: warm, mid-bright (r > g > b, r-b > 0.08)
                        warm = sum(1 for x, y, z in zip(r_, g_, b_) if x > y > z and x - z > 0.08 and x > 0.15)
                        cov = sum(1 for x, y, z in zip(r_, g_, b_) if x + y + z > 1e-4)
                        fr.setdefault("albedo_warm", {})[n] = round(warm / cov, 5) if cov else 0.0
                        yield
                if LABEL == "Host" and "Face" in L and "tee" in L:
                    fr["neck"] = neck3d(L["Face"], L["tee"], L["Body"])
                    yield
                per[f] = fr
            rep["shots"][shot] = per
    finally:
        remove_rig()
    worst = {}
    for shot, per in rep["shots"].items():
        for f, fr in (per.items() if isinstance(per, dict) else ()):
            for k, v in fr.items():
                if isinstance(v, dict) and "fraction" in v and v["fraction"] >= worst.get(k, (0, None))[0]:
                    worst[k] = (v["fraction"], f"{shot}@{f}")
    rep["worst"] = {k: {"fraction": v[0], "at": v[1]} for k, v in sorted(worst.items())}
    necks = [(fr["neck"]["out"], fr["neck"]["max_out_cm"], f"{shot}@{f}") for shot, per in rep["shots"].items()
             for f, fr in (per.items() if isinstance(per, dict) else ()) if "neck" in fr]
    npx = [(fr["neck_px"]["px"], f"{shot}@{f}") for shot, per in rep["shots"].items()
           for f, fr in (per.items() if isinstance(per, dict) else ()) if "neck_px" in fr]
    if npx:
        rep["worst"]["neck_px"] = {"px": max(npx)[0], "at": max(npx)[1]}
    if necks:
        o, cm, at = max(necks)
        rep["worst"]["neck"] = {"out": o, "max_out_cm": max(x[1] for x in necks), "at": at}
    with open(os.path.join(OUT, "clip.json"), "w") as fh:
        json.dump(rep, fh, indent=1)
    rep["out"] = OUT
    return rep


if unreal is not None and globals().get("RUN", True):
    result = run()
