"""Round 6 (agent-02, for the orchestrator's neckline check on HER): WHICH mesh a screen box shows, and which side of
it. READ-ONLY (spawns nothing, moves nothing). Scrub first, as qa.clip does (F+1 then F):

    film-ue op seq.scrub path=<SEQ> frame=30 ; film-ue op seq.scrub path=<SEQ> frame=29
    film-ue exec -c "SEQ='<SEQ>'; FRAME=29; LABEL='Presenter'; BOX=(1040,600,1075,830); exec(open('<tree>/films/host-studio/reel/r6/strip_id.py').read())"

BOX is (x0, y0, x1, y1) in pixels of a W x H picture (default 1920 x 1080) from the camera the sequence cuts to at
FRAME. A camera ray goes through every STEP-th pixel of the box and is cast against the POSED mesh of EVERY skeletal
mesh component of the actor (hidden ones too, flagged: an undershirt or bra that is hidden still shows up here, and
is then not what the render sees). Per pixel the nearest hit wins. Reported per component: pixels won, how many of
those hit a BACK face (the ray meets the triangle from inside: the garment's inner surface seen through the opening),
the material slot(s) hit, and the hit depth. A control box (CTRL, default the same size as the
box shifted 15 px past its right edge, i.e. the Top's front just outside the neckline) is read the same way.

Grooms (hair) are not meshes here: a box whose pixels hit nothing, or hit far behind, is hair/shadow - say so.
Numbers only, no pixels or face data leave the box."""
import math

import unreal
from fmbridge.ops import garment as G
from fmbridge.ops import view as V

SEQ = globals()["SEQ"]
FRAME = int(globals().get("FRAME", 29))
LABEL = globals().get("LABEL", "Presenter")
W, H = (int(v) for v in globals().get("WH", (1920, 1080)))
BOX = tuple(int(v) for v in globals().get("BOX", (1040, 600, 1075, 830)))
STEP = int(globals().get("STEP", 5))
REACH = float(globals().get("REACH", 2000.0))
_bw = BOX[2] - BOX[0]
CTRL = tuple(int(v) for v in globals().get("CTRL", (BOX[2] + 15, BOX[1], BOX[2] + 15 + _bw, BOX[3])))

info = V.camera_info(V.cut_camera(SEQ, FRAME), aspect=W / H)
pr, yw, rl = (math.radians(float(info["rot"][k])) for k in ("pitch", "yaw", "roll"))
sp, cp, sy, cy, sr, cr = math.sin(pr), math.cos(pr), math.sin(yw), math.cos(yw), math.sin(rl), math.cos(rl)
fwd = unreal.Vector(cp * cy, cp * sy, sp)
right = unreal.Vector(sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp)
up = unreal.Vector(-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp)
half = math.tan(math.radians(float(info["fov"])) / 2)
org = unreal.Vector(*[float(v) for v in info["loc"]])


def ray_dir(px, py):
    """Inverse of fmbridge.qa.clip.project_px."""
    x = 2.0 * (px + 0.5) / W - 1.0
    y = (1.0 - 2.0 * (py + 0.5) / H) * (H / W)
    d = fwd + right * (x * half) + up * (y * half)
    return d * (1.0 / d.length())


a = G.find_actor(LABEL)
MAT = unreal.GeometryScript_Materials
LU = unreal.GeometryScript_List
meshes = {}
for c in a.get_components_by_class(unreal.SkeletalMeshComponent):
    if c.get_skeletal_mesh_asset() is None:
        continue
    dm = G._posed(c)
    fn = getattr(MAT, "get_all_triangle_material_i_ds", None) or getattr(MAT, "get_all_triangle_material_ids", None)
    try:
        ids = list(LU.convert_index_list_to_array(G._pick(fn(dm), "GeometryScriptIndexList"))) if fn else []
    except Exception:  # noqa: BLE001
        ids = []
    meshes[c.get_name()] = {"comp": c, "surf": G._Surface(dm), "ids": ids, "visible": bool(c.is_visible()),
                            "slots": [str(n) for n in c.get_material_slot_names()],
                            "mats": [(m.get_name() if m else None) for m in c.get_materials()],
                            "mesh": c.get_skeletal_mesh_asset().get_name()}


def hit(m, d):
    s = m["surf"]
    res = G._pick(s.SP.find_nearest_ray_intersection_with_mesh(s.dm, s.bvh, org, d, s.q), "GeometryScriptRayHitResult")
    if not res.get_editor_property("hit"):
        return None
    t = float(res.get_editor_property("ray_parameter"))
    if t > REACH:
        return None
    tid = int(res.get_editor_property("triangle_id"))
    n = G._pick(s.MQ.get_triangle_face_normal(s.dm, tid), "Vector")
    return t, tid, n.dot(d) > 0.0  # True = back face (seen from inside)


def read(box, visible_only):
    per, empty, n = {}, 0, 0
    for py in range(box[1], box[3] + 1, STEP):
        for px in range(box[0], box[2] + 1, STEP):
            n += 1
            d = ray_dir(px, py)
            best = None
            for name, m in meshes.items():
                if visible_only and not m["visible"]:
                    continue
                h = hit(m, d)
                if h and (best is None or h[0] < best[1][0]):
                    best = (name, h)
            if best is None:
                empty += 1
                continue
            name, (t, tid, back) = best
            m = meshes[name]
            r = per.setdefault(name, {"px": 0, "back_face": 0, "slots": {}, "depth_cm": []})
            r["px"] += 1
            r["back_face"] += int(back)
            mid = m["ids"][tid] if tid < len(m["ids"]) else -1
            slot = f"{mid}:{m['slots'][mid] if 0 <= mid < len(m['slots']) else '?'}/" \
                   f"{m['mats'][mid] if 0 <= mid < len(m['mats']) else '?'}"
            r["slots"][slot] = r["slots"].get(slot, 0) + 1
            r["depth_cm"].append(t)
    for r in per.values():
        ds = sorted(r.pop("depth_cm"))
        r["depth_cm"] = [round(ds[0], 1), round(ds[len(ds) // 2], 1), round(ds[-1], 1)]
    return {"samples": n, "no_mesh_hit": empty, "by_component": per}


result = {"camera": info["name"], "frame": FRAME, "box": BOX, "ctrl": CTRL, "wh": [W, H],
          "components": {k: {"mesh": m["mesh"], "visible": m["visible"]} for k, m in meshes.items()},
          "box_visible": read(BOX, True), "box_all_incl_hidden": read(BOX, False), "ctrl_visible": read(CTRL, True)}
