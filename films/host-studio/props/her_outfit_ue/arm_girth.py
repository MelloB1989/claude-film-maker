"""Round 7 (agent-05): her arms a little fuller, on NEW assets (the operator, 8 Nov ~19:50: "her hand limbs are a little
bit (not much) thin compared to her body").

Each arm vertex moves straight out from the arm's bone axis (upperarm -> lowerarm -> hand, her reference pose) by
SCALE x its distance from it, so the cross-section grows by SCALE all round and the bones, weights, UVs, normals and
vertex order stay as they are: the rig poses the fuller arm the way it posed the slim one.
  - how much: her body's own skinning says what is arm (the summed weight on upperarm*/lowerarm*/bicep/tricep/elbow
    bones and helpers); the deltoid ramps in over the first UP_RAMP of the upper arm (the shoulder and armpit stay),
    full down the upper arm and the forearm to FORE_FULL, then down to WRIST_LEFT at WATCH_CM before hand_l/_r
    (her watch's loop sits there: it must still close round the wrist) and 0 on the hand;
  - the garments (the Top's short sleeves) move by the SAME field: each garment vertex takes the profile and arm
    weight of the nearest body vertex and scales out from the same axis, so a sleeve over skin stays over it (a
    radial scale about one axis never crosses two surfaces) and its gap grows by SCALE too.

STAGE='apply' writes BODY_DEST and one <garment>_Arms per GARMENTS entry (never an original), then reads them back.
STAGE='check' (read-only): the read-back only. Numbers: the radius at mid upper arm / mid forearm (median over the
fully-arm verts there) before and after per side, the largest move on the hand and in the watch band, the sleeves'
smallest radial gap over the skin before and after, and the vertex counts.

    film-ue exec -c "STAGE='apply'; SCALE=0.10; exec(open('<tree>/films/host-studio/props/her_outfit_ue/arm_girth.py').read())"

Then setplan GARMENT_SRC her Body / Top -> the _Arms assets (the cuts and hides run on them), leaders, and the arms
measure (agent-02: bust >= 3, side >= 0.5).
"""
import math
import re

import unreal

STAGE = globals().get("STAGE", "check")
SCALE = float(globals().get("SCALE", 0.10))
BODY_SRC = globals().get("BODY_SRC", "/Game/Host/Unpacked/Presenter/Body/SKM_Presenter_F_BodyMesh")
BODY_DEST = globals().get("BODY_DEST", BODY_SRC + "_Arms")
GARMENTS = list(globals().get("GARMENTS", ["/Game/Host/Presenter_Outfit/SKM_Presenter_Top_R7W"]))
UP_RAMP = 0.30      # of the upper arm from the shoulder joint: the deltoid ramps in (0 at the joint)
FORE_FULL = 0.55    # of the forearm from the elbow: full to here
WATCH_CM = 6.5      # cm before the hand bone: the watch band's zone (its loop is 2 cm wide, centred ~4 cm up)
WRIST_LEFT = 0.0    # the profile there and past it
REACH = 12.0        # cm from the axis: past this nothing moves (a hand on the thigh in the A-pose is not the arm)
ARM = re.compile(r"(upperarm|lowerarm|bicep|tricep|elbow)", re.I)
EAL = unreal.EditorAssetLibrary
LU = unreal.GeometryScript_List
MQ = unreal.GeometryScript_MeshQueries


def pick(res, cls):
    items = res if isinstance(res, tuple) else (res,)
    return next((x for x in items if type(x).__name__ == cls), items[0])


def lib():
    for n in ("GeometryScript_BoneWeights", "GeometryScript_MeshBoneWeights", "GeometryScript_SkinWeights"):
        if hasattr(unreal, n):
            return getattr(unreal, n)
    raise RuntimeError("no Geometry Script bone-weight library")


BW = lib()


def dm_of(skm):
    dm = unreal.DynamicMesh()
    lod = unreal.GeometryScriptMeshReadLOD()
    lod.set_editor_property("lod_index", 0)
    unreal.GeometryScript_AssetUtils.copy_mesh_from_skeletal_mesh(skm, dm, unreal.GeometryScriptCopyMeshFromAssetOptions(),
                                                                  lod)
    return dm


def positions(dm):
    return [(p.x, p.y, p.z) for p in LU.convert_vector_list_to_array(pick(MQ.get_all_vertex_positions(dm, False),
                                                                             "GeometryScriptVectorList"))]


def weights(dm, v):
    res = BW.get_vertex_bone_weights(dm, v)
    ws = next((x for x in (res if isinstance(res, tuple) else (res,)) if isinstance(x, (list, unreal.Array))), [])
    return [(int(w.get_editor_property("bone_index")), float(w.get_editor_property("weight"))) for w in ws]


def skeleton(mesh):
    """Bone names and reference-pose heads (component space, cm): cloth.bones' chaining."""
    comp = unreal.SkeletalMeshComponent()
    comp.set_skeletal_mesh_asset(mesh)
    names = [str(comp.get_bone_name(i)) for i in range(comp.get_num_bones())]
    world, heads = {}, {}
    for i, b in enumerate(names):
        p = str(comp.get_parent_bone(b))
        t = comp.get_ref_pose_transform(i)
        world[b] = t if not p or p == "None" else unreal.MathLibrary.compose_transforms(t, world[p])
        loc = world[b].translation
        heads[b] = (loc.x, loc.y, loc.z)
    return names, heads


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


class Arm:
    """One side's axis: shoulder -> elbow -> wrist, and the girth profile along it."""

    def __init__(self, heads, side):
        self.side = side
        self.s, self.e, self.w = (heads[f"{b}_{side}"] for b in ("upperarm", "lowerarm", "hand"))
        self.lu = math.sqrt(dot(sub(self.e, self.s), sub(self.e, self.s)))
        self.lf = math.sqrt(dot(sub(self.w, self.e), sub(self.w, self.e)))

    def axis(self, p):
        """(nearest axis point, profile 0..1, part 'upper'/'fore'/'hand'/'shoulder')."""
        best = None
        for a, b, ln, part in ((self.s, self.e, self.lu, "upper"), (self.e, self.w, self.lf, "fore")):
            d = sub(b, a)
            t = dot(sub(p, a), d) / (ln * ln)
            tc = min(1.0, max(0.0, t))
            q = (a[0] + d[0] * tc, a[1] + d[1] * tc, a[2] + d[2] * tc)
            r = sub(p, q)
            dd = dot(r, r)
            if best is None or dd < best[0]:
                best = (dd, q, t, part)
        _, q, t, part = best
        if part == "upper":
            prof = 0.0 if t <= 0 else smooth(t / UP_RAMP)
            part = "shoulder" if t <= 0 else part
        else:
            cm_left = (1.0 - t) * self.lf     # cm before the hand bone
            if t >= 1.0:
                prof, part = 0.0, "hand"
            elif t <= FORE_FULL:
                prof = 1.0
            else:
                ramp_end = max(FORE_FULL * self.lf, self.lf - WATCH_CM)
                x = (t * self.lf - FORE_FULL * self.lf) / max(1e-6, ramp_end - FORE_FULL * self.lf)
                prof = 1.0 - (1.0 - WRIST_LEFT) * smooth(x)
                if cm_left <= WATCH_CM:
                    prof = WRIST_LEFT
        return q, prof, t, part


class Grid:
    """Nearest point among a set, by a 2 cm hash (the arms only: a few thousand verts)."""

    def __init__(self, pts, ids, cell=2.0):
        self.cell, self.pts, self.g = cell, pts, {}
        for i in ids:
            self.g.setdefault(self.key(pts[i]), []).append(i)

    def key(self, p):
        return tuple(int(math.floor(c / self.cell)) for c in p)

    def nearest(self, p, rings=3):
        k = self.key(p)
        best = None
        for dx in range(-rings, rings + 1):
            for dy in range(-rings, rings + 1):
                for dz in range(-rings, rings + 1):
                    for i in self.g.get((k[0] + dx, k[1] + dy, k[2] + dz), ()):
                        d = sub(self.pts[i], p)
                        dd = dot(d, d)
                        if best is None or dd < best[0]:
                            best = (dd, i)
        return best


def body_field(dm, names, arms):
    """Per body vertex: (side, arm weight x profile, axis point) or None."""
    pts = positions(dm)
    field = [None] * len(pts)
    for v, p in enumerate(pts):
        side_w = {"l": 0.0, "r": 0.0}
        for i, w in weights(dm, v):
            n = names[i] if 0 <= i < len(names) else ""
            if ARM.search(n) and n[-2:] in ("_l", "_r"):
                side_w[n[-1]] += w
        side = max(side_w, key=side_w.get)
        aw = min(1.0, side_w[side])
        if aw <= 0.0:
            continue
        q, prof, t, part = arms[side].axis(p)
        r = sub(p, q)
        if dot(r, r) > REACH * REACH:
            continue
        field[v] = (side, aw * prof, q, part, t)
    return pts, field


def moved(pts, gain_axis):
    """New positions: p + SCALE * gain * (p - axis point)."""
    out = []
    for p, ga in zip(pts, gain_axis):
        if ga is None or ga[0] <= 0.0:
            out.append(p)
            continue
        g, q = ga
        out.append(tuple(p[k] + SCALE * g * (p[k] - q[k]) for k in range(3)))
    return out


def write(src_path, dest, new_pts):
    if EAL.does_asset_exist(dest):
        raise RuntimeError(f"{dest} exists: pass a new destination (never overwrite)")
    EAL.duplicate_asset(src_path, dest)
    dup = EAL.load_asset(dest)
    dm = dm_of(dup)
    n = len(positions(dm))
    if n != len(new_pts):
        raise RuntimeError(f"{dest}: {n} verts, expected {len(new_pts)}")
    set_positions(dm, new_pts)
    opts = unreal.GeometryScriptCopyMeshToAssetOptions()
    for k, val in (("enable_recompute_normals", False), ("enable_recompute_tangents", False),
                   ("enable_remove_degenerates", False), ("use_original_vertex_order", True),
                   ("replace_materials", False)):
        try:
            opts.set_editor_property(k, val)
        except Exception:  # noqa: BLE001
            pass
    lod = unreal.GeometryScriptMeshWriteLOD()
    lod.set_editor_property("lod_index", 0)
    unreal.GeometryScript_AssetUtils.copy_mesh_to_skeletal_mesh(dm, dup, opts, lod)
    EAL.save_asset(dest)


def set_positions(dm, pts):
    """MeshBasicEditFunctions.h (ScriptName MeshEdits): SetAllMeshVertexPositions, else one SetVertexPosition each."""
    ME = getattr(unreal, "GeometryScript_MeshEdits", None) or unreal.GeometryScript_MeshBasicEdits
    vl = pick(LU.convert_array_to_vector_list([unreal.Vector(*p) for p in pts]), "GeometryScriptVectorList")
    if hasattr(ME, "set_all_mesh_vertex_positions"):
        ME.set_all_mesh_vertex_positions(dm, vl)
    else:
        for v, p in enumerate(pts):
            ME.set_vertex_position(dm, v, unreal.Vector(*p))
    back = positions(dm)
    off = max(math.sqrt(dot(sub(a, b), sub(a, b))) for a, b in zip(back, pts))
    if off > 1e-3:
        raise RuntimeError(f"vertex positions did not take ({off:.4f} cm off)")


def radii(pts, field, arms):
    """Median radius of the fully-arm verts at mid upper arm (t 0.4-0.6) and mid forearm (t 0.3-0.5), per side."""
    out = {}
    for side, arm in arms.items():
        for part, lo, hi in (("upper", 0.4, 0.6), ("fore", 0.3, 0.5)):
            rs = []
            for p, f in zip(pts, field):
                if f and f[0] == side and f[3] == part and lo <= f[4] <= hi and f[1] >= 0.9 * 1.0:
                    q = arm.axis(p)[0]
                    rs.append(math.sqrt(dot(sub(p, q), sub(p, q))))
            rs.sort()
            out[f"{part}_{side}"] = round(rs[len(rs) // 2], 3) if rs else None
    return out


def sleeve_gap(gpts, bpts, bgrid, arms, gfield):
    """The garment's arm verts: the smallest (garment radius - nearest skin vertex's radius), cm."""
    worst = None
    for p, f in zip(gpts, gfield):
        if not f:
            continue
        nb = bgrid.nearest(p)
        if not nb:
            continue
        arm = arms[f[0]]
        q = arm.axis(p)[0]
        qb = arm.axis(bpts[nb[1]])[0]
        gap = math.sqrt(dot(sub(p, q), sub(p, q))) - math.sqrt(dot(sub(bpts[nb[1]], qb), sub(bpts[nb[1]], qb)))
        worst = gap if worst is None else min(worst, gap)
    return round(worst, 3) if worst is not None else None


body_src = EAL.load_asset(BODY_SRC)
names, heads = skeleton(body_src)
arms = {s: Arm(heads, s) for s in ("l", "r")}
bdm = dm_of(body_src)
bpts, bfield = body_field(bdm, names, arms)
arm_ids = [v for v, f in enumerate(bfield) if f]
bgrid = Grid(bpts, arm_ids)
bnew = moved(bpts, [(f[1], f[2]) if f else None for f in bfield])


def garment_field(gpts, grid=bgrid, field=bfield):
    """A garment vertex takes the nearest body arm vertex's side and gain (within 3 cm), its own axis point."""
    out = []
    for p in gpts:
        nb = grid.nearest(p, rings=2)
        if not nb or nb[0] > 9.0:
            out.append(None)
            continue
        f = field[nb[1]]
        q, _, t, part = arms[f[0]].axis(p)
        out.append((f[0], f[1], q, part, t))
    return out


report = {"stage": STAGE, "scale": SCALE, "body": {"src": BODY_SRC, "dest": BODY_DEST, "arm_verts": len(arm_ids)},
          "garments": {}}
if STAGE == "apply":
    write(BODY_SRC, BODY_DEST, bnew)
    for g in GARMENTS:
        gpts = positions(dm_of(EAL.load_asset(g)))
        gf = garment_field(gpts)
        write(g, g + "_Arms", moved(gpts, [(f[1], f[2]) if f else None for f in gf]))

# read-back (both stages)
bdest = EAL.load_asset(BODY_DEST)
if bdest is None:
    raise RuntimeError(f"no {BODY_DEST}: run STAGE='apply' first")
bpts2 = positions(dm_of(bdest))
hand_move = max((math.sqrt(dot(sub(a, b), sub(a, b))) for a, b, f in zip(bpts, bpts2, bfield) if not f or f[3] == "hand"),
                default=0.0)
watch_move = max((math.sqrt(dot(sub(a, b), sub(a, b))) for a, b, f in zip(bpts, bpts2, bfield)
                  if f and f[3] == "fore" and (1.0 - f[4]) * arms[f[0]].lf <= WATCH_CM), default=0.0)
report["body"].update({"verts": [len(bpts), len(bpts2)], "radius_before": radii(bpts, bfield, arms),
                       "radius_after": radii(bpts2, bfield, arms), "max_move_cm": round(max(
                           math.sqrt(dot(sub(a, b), sub(a, b))) for a, b in zip(bpts, bpts2)), 3),
                       "hand_or_unarm_max_move_cm": round(hand_move, 4), "watch_band_max_move_cm": round(watch_move, 4),
                       "arm_len_cm": {s: [round(a.lu, 2), round(a.lf, 2)] for s, a in arms.items()}})
grid2 = Grid(bpts2, arm_ids)
for g in GARMENTS:
    gpts = positions(dm_of(EAL.load_asset(g)))
    gd = EAL.load_asset(g + "_Arms")
    gpts2 = positions(dm_of(gd)) if gd else None
    gf = garment_field(gpts)
    gn, gh = skeleton(EAL.load_asset(g))
    bone_off = max(math.sqrt(dot(sub(gh[b], heads[b]), sub(gh[b], heads[b])))
                   for b in ("upperarm_l", "lowerarm_l", "hand_l", "upperarm_r", "lowerarm_r", "hand_r") if b in gh)
    report["garments"][g] = {"dest": g + "_Arms" if gd else None, "verts": [len(gpts), len(gpts2) if gpts2 else None],
                             "arm_verts": sum(1 for f in gf if f), "ref_bones_off_body_cm": round(bone_off, 3),
                             "sleeve_gap_min_cm_before": sleeve_gap(gpts, bpts, bgrid, arms, gf),
                             "sleeve_gap_min_cm_after": sleeve_gap(gpts2, bpts2, grid2, arms, gf) if gpts2 else None}
result = report
