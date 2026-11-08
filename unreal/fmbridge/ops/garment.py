"""Garments on a MetaHuman, measured and fitted the way round 4 of the karma reel had to learn (docs/unreal/garment.md,
docs/unreal/research/garment-fit.md):

    garment.export   the actor's body, face, garment(s), the UNCUT reference body and the anims it plays, as FBX, for
                     the Blender fit (film-ue garment fit runs blender/garment_fit.py on them)
    body.hide_under  the body triangles a garment covers, removed on a copy of the body mesh (or counted only)
    qa.clip          skin or an under-garment coming out through a garment, per shot/frame, from depth layers
                     (fmbridge.qa.clip: pairs, the intersection-edge rule, the collar-band neck_px, silhouette)
    qa.garment_look  the armor index: does the garment read as cloth (ease, thickness, silhouette, folds, motion)

The fitted garment comes back with mh.import_garment and goes on with mh.dress (leader pose last). A WPO inflate
(mh.cloth_inflate) is NOT a fit: it pushes the rendered surface out evenly, the silhouette grows with it, and
shadows, collision and cloth simulation never see it (qa.garment_look fails it as 'wpo')."""
from __future__ import annotations

import array
import json
import math
import os

import unreal

from . import op
from .assets import EAL
from ..errors import OpError, not_found
from ..qa import clip as _clip
from ..qa import garment_look as _look
from ..qa import image as _image
from ..qa import limbs as _limbs
from ..qa.issues import issue, worst
from .view import _scrub, camera_info, capture, cut_camera, find_actor, read_pixels, remove_rig, to_image

SKIN = ("Body", "Face")
NAMED = ("Trousers", "Top", "Overshirt", "Torso", "Legs", "Feet")
REF_LABEL = "FMQA_RefBody"
COL = {"Body": (220, 40, 40), "Face": (255, 150, 60), "tee": (40, 190, 70), "Top": (40, 190, 70),
       "Trousers": (50, 90, 230), "shoes": (240, 220, 40), "Overshirt": (40, 200, 200)}


def _result(issues: list, metrics: dict | None = None, **extra) -> dict:
    return {"pass": worst(issues) != "fail", "issues": issues, "metrics": metrics or {}, **extra}


def roles(a, given: dict | None = None) -> dict:
    """The actor's visible skeletal mesh parts by ROLE: Body, Face, its garments by component name, a MetaHuman's
    default garment (component "SkeletalMesh", or the one left over) as 'tee', a mesh with shoe/feet in its name as
    'shoes'; a component named Tee or Shirt (a refit dressed with mh.dress) is the 'tee' first, and the default
    garment then keeps its own name. `given` {role: component name} overrides (and adds). Grooms are left out: hair
    lies over a collar legitimately."""
    comps = {c.get_name(): c for c in a.get_components_by_class(unreal.SkeletalMeshComponent) if c.is_visible()}
    out = {}
    tee = next((n for n in comps if n.lower() in ("tee", "shirt")), None)  # a refit dressed as its own component
    if tee:
        out["tee"] = comps[tee]
    for n, c in comps.items():
        if n == tee:
            continue
        m = c.get_skeletal_mesh_asset()
        mesh = m.get_name().lower() if m else ""
        if n in SKIN or n in NAMED:
            out[n] = c
        elif "shoe" in mesh or "shoe" in n.lower() or "feet" in n.lower():
            out["shoes"] = c
        elif "tee" not in out and (n == "SkeletalMesh" or "garment" in mesh):
            out["tee"] = c
        else:
            out[n] = c
    for role, name in (given or {}).items():
        if name not in comps:
            raise not_found("component", name, sorted(comps), hint="qa.parts lists an actor's components")
        out = {k: v for k, v in out.items() if v != comps[name]}
        out[role] = comps[name]
    return out


def _frames_of(sequence: str, shots, n: int, extra: dict | None) -> dict:
    from . import call
    cuts = {c: (int(s), int(e)) for c, s, e in call("seq.cuts", path=sequence)}
    out = {}
    for shot in shots or sorted(cuts, key=lambda k: cuts[k][0]):
        if shot not in cuts:
            out[shot] = {"error": f"no camera cut {shot}: {sorted(cuts)}"}
            continue
        s, e = cuts[shot]
        span = max(0, e - 4 - s)
        fr = {s + 2 + round(k * span / max(1, n - 1)) for k in range(max(1, n))}
        fr |= {int(f) for f in (extra or {}).get(shot, ()) if s <= int(f) < e}
        out[shot] = sorted(fr)
    return out


def write_depth(path: str, w: int, h: int, fov: float, layers: dict) -> None:
    """The depth layers as one file (round 4's _depth.bin: a 4-byte header length, a JSON header, float32 layers),
    so the rules re-run off the editor (read_depth)."""
    with open(path, "wb") as fh:
        head = json.dumps({"w": w, "h": h, "fov": fov, "layers": list(layers)}).encode()
        fh.write(len(head).to_bytes(4, "little") + head)
        for n in layers:
            array.array("f", layers[n]).tofile(fh)


def read_depth(path: str) -> tuple:
    """(w, h, fov, {layer: list}) from write_depth's file."""
    with open(path, "rb") as fh:
        n = int.from_bytes(fh.read(4), "little")
        head = json.loads(fh.read(n))
        out = {}
        for name in head["layers"]:
            x = array.array("f")
            x.fromfile(fh, head["w"] * head["h"])
            out[name] = list(x)
    return head["w"], head["h"], head["fov"], out


def _mask_image(d: dict, clipped: set, w: int, h: int):
    data = bytearray(w * h * 3)
    for i in range(w * h):
        best, z = None, _clip.EMPTY
        for n, L in d.items():
            if L[i] < z:
                best, z = n, L[i]
        c = (255, 0, 255) if i in clipped else COL.get(best, (0, 200, 220)) if best else (0, 0, 0)
        data[3 * i:3 * i + 3] = bytes(c)
    return _image.Image(w, h, 3, data)


MOUTH_BONES = ("FACIAL_C_LipUpper", "FACIAL_C_LipLower", "FACIAL_L_LipCorner", "FACIAL_R_LipCorner")


def _props(props: dict | None) -> dict:
    """{role: "Label" | "Label:Component"} -> {role: [visible mesh components]} for qa.clip's set-piece layers."""
    out = {}
    for role, ref in (props or {}).items():
        label, _, comp = str(ref).partition(":")
        act = find_actor(label)
        cs = [c for cls in (unreal.StaticMeshComponent, unreal.SkeletalMeshComponent)
              for c in act.get_components_by_class(cls) if c.is_visible() and (not comp or c.get_name() == comp)]
        if not cs:
            raise OpError(f"prop {role}={ref!r}: no visible mesh component", code="not_found",
                          hint="level.actors lists the labels; the component is optional (Label or Label:Component)")
        out[role] = cs
    return out


def _mouth(parts: dict, layers: dict, info: dict, w: int, h: int, spec: dict) -> dict:
    """qa.clip's mouth check at one frame: the face's mouth bones projected through the shot camera, then
    qa.clip.mouth_blocked against the blocker's layer."""
    blocker = spec.get("blocker", "Mic")
    face = parts.get("Face")
    if blocker not in layers or face is None:
        return {"error": f"needs the Face and the {blocker!r} layer (props={{{blocker!r}: label}})", "blocker": blocker}
    names = {str(b) for b in face.get_all_socket_names()} if hasattr(face, "get_all_socket_names") else None
    centers = []
    for b in spec.get("bones") or MOUTH_BONES:
        if names is not None and b not in names:
            return {"error": f"the face has no bone {b!r}", "blocker": blocker}
        p = face.get_socket_location(b)
        centers.append(_clip.project_px(info, (p.x, p.y, p.z), w, h))
    zs = [c[2] for c in centers if c[2] > 0]
    if not zs:
        return {"error": "the mouth is behind the camera", "blocker": blocker}
    r_px = float(spec.get("radius_cm", 2.0)) / (2 * min(zs) * math.tan(math.radians(float(info["fov"])) / 2)) * w
    return {**_clip.mouth_blocked(layers, centers, r_px, blocker=blocker, w=w, h=h,
                                  tol_cm=float(spec.get("tol_cm", 0.5))), "blocker": blocker, "radius_px": round(r_px, 1)}


@op("qa.clip", mutates=False, idempotent=True, tags=["gpu", "slow", "metahuman"])
def clip(*, label: str, sequence: str, shots: list | None = None, n: int = 6, extra: dict | None = None,
         width_px: int = 480, roles_map: dict | None = None, pairs: list | None = None, ref_dir: str = "",
         before: str = "", out_dir: str = "", stills: bool = True, layer_masks: bool = False, neck_over: str = "",
         tol_cm: float = 0.3,
         band_cm: float = 3.0, near_cm: float = 1.5, neck_margin_cm: float = 1.0, at_open_960: float = 5.0,
         pair_fraction: float = 0.001, neck_max_px: int = 0, silhouette_pct: float = 2.0, props: dict | None = None,
         mouth: dict | None = None, mouth_max_px: int = 0, neck_rule: str = "rim", tongue_cm: float = 3.0):
    """Skin or an under-garment coming out through a garment, as the shot's camera sees it, per shot and frame.

    Each part (Body, Face, each garment) is depth-captured ALONE from the shot's camera; every (under, over) pair is
    judged by fmbridge.qa.clip: a pixel clips where the under layer is nearer by tol_cm..band_cm AND its blob meets an
    intersection edge (an arm in front of the cloth does not count). For a face under an upper garment the gate is
    `neck_px`: Face pixels through the garment more than neck_margin_cm under its collar rim and not hugging the
    opening. With `ref_dir` (an earlier qa.clip out_dir) each frame's over-garments' covered pixels are compared with
    the same frame there: `silhouette` (a balloon reads +%). With `before` (an earlier clip.json) a pair is judged
    against its own worst there + 0.01 (an open neckline that reads high on clean frames).

    Args: label: the character. sequence: the level sequence; shots: camera-cut names (default all); n frames spread
    per shot, `extra` {shot: [frames]} besides (twists, glances). roles_map {role: component} (default: roles()).
    pairs: [[under, over], ...] (default fmbridge.qa.clip.pairs). out_dir (on the box; face data stays there): per frame
    <shot>_<frame>_mask.png (body red, face orange, tee green, trousers blue, clip magenta), _depth.bin, with
    `stills` _final.png, with `layer_masks` <shot>_<frame>_<role>.png per part (grey, 255 where that part alone
    covers the pixel, 0 elsewhere: occlusion by other parts NOT applied). Gate knobs: pair_fraction, neck_max_px, silhouette_pct; neck_rule "rim" (neck_px) or "visible" (neck_visible: skin islands + tongues deeper than tongue_cm from the opening, the round-6 re-scope; both reported either way).
    props {role: "Label" | "Label:Component"}: set pieces captured as layers too (every visible mesh component of the
    actor, or the one named), for pairs such as [["Body","Chair"],["Chair","Trousers"],["Body","Desk"]] (a presenter
    sinking into a seat or a desk). mouth {"blocker": role (default "Mic", a prop), "bones": [face bones] (default
    MOUTH_BONES), "radius_cm": 2.0, "tol_cm": 0.5}: per frame, the mouth's pixels the blocker covers (qa.clip.mouth_blocked);
    over mouth_max_px fails. A bone the face lacks is an error in that frame (not measured), never a pass.
    Returns: {"pass", "issues", "metrics": {"worst", "shots": {shot: {frame: {"U>G": {...}, "neck_px", "silhouette"}}}},
    "out_dir"}. Multi-tick (~10 s a frame at 480 px).
    Example: film-ue op qa.clip label=Host sequence=/Game/Reel/SEQ_Reel 'shots=["Reel_S15"]' out_dir=/srv/ue/qa/clip/now
    Example: film-ue op qa.clip label=Host sequence=/Game/Expl/SEQ_WA 'props={"Chair":"Chair","Mic":"StudioMic"}' 'pairs=[["Body","Chair"],["Chair","Trousers"]]' 'mouth={"blocker":"Mic"}'
    """
    a = find_actor(label)
    w, h = int(width_px), round(int(width_px) * 9 / 16)
    plan = _frames_of(sequence, shots, n, extra)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    knobs = dict(tol_cm=tol_cm, band_cm=band_cm, near_cm=near_cm, neck_margin_cm=neck_margin_cm,
                 at_open_960=at_open_960, tongue_cm=tongue_cm)
    rep = {}
    try:
        for shot, frames in plan.items():
            if isinstance(frames, dict):
                rep[shot] = frames
                continue
            per = {}
            for f in frames:
                yield from _scrub(sequence, f, 10)
                info = camera_info(cut_camera(sequence, f), aspect=16 / 9)
                fov = float(info["fov"])
                parts = roles(a, roles_map)  # afresh each frame: a construction script may re-create components
                parts.update(_props(props))
                d = {}
                for name, c in parts.items():
                    rt = yield from capture(info, w, h, "depth", show_only=c if isinstance(c, list) else [c], warmup=1)
                    d[name] = read_pixels(rt, "r")[0]
                    yield
                fr = _clip.judge_frame(d, w, h, fov, pair_list=[tuple(p) for p in pairs] if pairs else None,
                                       neck_over=neck_over, **knobs)
                mask = fr.pop("_mask")
                if mouth:
                    fr["mouth"] = _mouth(parts, d, info, w, h, mouth)
                base = os.path.join(out_dir, f"{shot}_{f:04d}") if out_dir else ""
                if ref_dir:
                    rp = os.path.join(ref_dir, f"{shot}_{f:04d}_depth.bin")
                    if os.path.exists(rp):
                        rw, rh, _, ref = read_depth(rp)
                        over = [g for g in d if g not in SKIN and g in ref and (rw, rh) == (w, h)]
                        if over:
                            g = "tee" if "tee" in over else over[0]
                            fr["silhouette"] = {**_clip.silhouette(d[g], ref[g]), "layer": g}
                    else:
                        fr["silhouette"] = {"pct": None, "missing": rp}
                if base:
                    _image.write(_mask_image(d, mask, w, h), base + "_mask.png")
                    write_depth(base + "_depth.bin", w, h, fov, d)
                    if layer_masks:
                        for name, L in d.items():
                            _image.write(_image.Image(w, h, 1, bytearray(255 if z < _clip.EMPTY else 0 for z in L)),
                                         f"{base}_{name}.png")
                    if stills:
                        rt = yield from capture(info, 2 * w, 2 * h, "final", warmup=4)
                        _image.write(to_image(rt), base + "_final.png")
                per[f] = fr
                yield
            rep[shot] = per
    finally:
        remove_rig()
    prior = None
    if before:
        with open(before) as fh:
            b = json.load(fh)
        prior = b.get("metrics", b).get("shots", b.get("shots"))
    issues = _clip.gate(rep, label, pair_fraction=pair_fraction, neck_max_px=neck_max_px,
                        silhouette_pct=silhouette_pct, before=prior, mouth_max_px=mouth_max_px, neck_rule=neck_rule)
    out = _result(issues, {"worst": _clip.summarize(rep), "shots": rep, "size": [w, h], **knobs}, out_dir=out_dir)
    if out_dir:
        with open(os.path.join(out_dir, "clip.json"), "w") as fh:
            json.dump(out, fh, indent=1, default=str)
    return out


# --- posed meshes (Geometry Script) ----------------------------------------------------------------------------------

def _gs():
    if not hasattr(unreal, "GeometryScript_SceneUtils"):
        raise OpError("the Geometry Script plugin is not enabled", code="unsupported",
                      hint="enable GeometryScripting in the project's .uproject Plugins, restart the editor")
    return (unreal.GeometryScript_SceneUtils, unreal.GeometryScript_MeshSpatial, unreal.GeometryScript_MeshQueries,
            unreal.GeometryScript_List)


def _pick(res, cls_name: str):
    items = res if isinstance(res, tuple) else (res,)
    for x in items:
        if type(x).__name__ == cls_name:
            return x
    return items[0]


def _posed(comp):
    """The component's posed, skinned mesh (render LOD 0) as a DynamicMesh."""
    SU = _gs()[0]
    opts = unreal.GeometryScriptCopyMeshFromComponentOptions()
    lod = unreal.GeometryScriptMeshReadLOD()
    lod.set_editor_property("lod_type", unreal.GeometryScriptLODType.RENDER_DATA)
    lod.set_editor_property("lod_index", 0)
    opts.set_editor_property("requested_lod", lod)
    dm = unreal.DynamicMesh()
    SU.copy_mesh_from_component(comp, dm, opts, True)
    return dm


def _verts(dm) -> list:
    _, _, MQ, LU = _gs()
    return LU.convert_vector_list_to_array(_pick(MQ.get_all_vertex_positions(dm, False), "GeometryScriptVectorList"))


class _Surface:
    """Nearest-point and ray queries on a DynamicMesh."""

    def __init__(self, dm):
        _, self.SP, self.MQ, _ = _gs()
        self.dm = dm
        self.bvh = _pick(self.SP.build_bvh_for_mesh(dm), "GeometryScriptDynamicMeshBVH")
        self.q = unreal.GeometryScriptSpatialQueryOptions()

    def nearest(self, p):
        """(point, triangle id, outward face normal) or None."""
        tp = _pick(self.SP.find_nearest_point_on_mesh(self.dm, self.bvh, p, self.q), "GeometryScriptTrianglePoint")
        if not tp.get_editor_property("valid"):
            return None
        tid = tp.get_editor_property("triangle_id")
        return tp.get_editor_property("position"), tid, _pick(self.MQ.get_triangle_face_normal(self.dm, tid), "Vector")

    def signed(self, p):
        """Signed distance from the surface (+ along its outward normal), with the triangle; None off the mesh."""
        r = self.nearest(p)
        if r is None:
            return None
        q, tid, nrm = r
        return (p - q).dot(nrm), tid

    def ray(self, o, d, reach: float):
        """Distance along unit d to the first hit within reach, else None."""
        hit = _pick(self.SP.find_nearest_ray_intersection_with_mesh(self.dm, self.bvh, o, d, self.q),
                    "GeometryScriptRayHitResult")
        if not hit.get_editor_property("hit"):
            return None
        t = float(hit.get_editor_property("ray_parameter"))
        return t if t <= reach else None

    def centroid(self, tid):
        res = self.MQ.get_triangle_positions(self.dm, tid)
        vs = [x for x in (res if isinstance(res, tuple) else (res,)) if type(x).__name__ == "Vector"]
        if len(vs) < 3:
            return None
        return (vs[0] + vs[1] + vs[2]) * (1.0 / 3.0)


def _sample(seq, k: int) -> list:
    """About k items spread through seq (an unreal.Array refuses a slice step: list it first)."""
    seq = list(seq)
    step = max(1, len(seq) // max(1, k))
    return seq[::step]


def _ref_body(a, mesh: str, body: str = "Body"):
    """A temporary actor wearing the uncut reference body, on leader pose to the character's body (it moves with it)."""
    m = EAL.load_asset(mesh)
    if not isinstance(m, unreal.SkeletalMesh):
        raise OpError(f"no skeletal mesh {mesh}", code="not_found",
                      hint="the UNCUT body of the same build (garment.export lists it as ref_body), on the body skeleton")
    comps = {c.get_name(): c for c in a.get_components_by_class(unreal.SkeletalMeshComponent)}
    if body not in comps:
        raise not_found("component", body, sorted(comps))
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for x in eas.get_all_level_actors():
        if x.get_actor_label() == REF_LABEL:
            eas.destroy_actor(x)
    ref = eas.spawn_actor_from_class(unreal.SkeletalMeshActor, a.get_actor_location(), a.get_actor_rotation())
    ref.set_actor_label(REF_LABEL)
    rc = ref.get_editor_property("skeletal_mesh_component")
    rc.set_skeletal_mesh_asset(m)
    rc.set_world_transform(comps[body].get_world_transform(), False, False)
    rc.set_leader_pose_component(comps[body], True)
    return ref, rc


def _drop_ref():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for x in eas.get_all_level_actors():
        if x.get_actor_label() == REF_LABEL:
            eas.destroy_actor(x)


def _shown_verts(comp, dm, skip=("short", "hidden")):
    """Vertex ids of the triangles whose material slot is drawn: slots whose name or material has a `skip` word
    (round 5: the refit Tee still carries Epic's shorts, hidden; the hem check measured the shorts' hem) are left
    out. None when the mesh has no material ids (then every vertex counts)."""
    MQ, LU, MAT = unreal.GeometryScript_MeshQueries, unreal.GeometryScript_List, unreal.GeometryScript_Materials
    names = [str(n).lower() for n in comp.get_material_slot_names()]
    mats = [(m.get_name().lower() if m else "") for m in comp.get_materials()]
    bad = {i for i in range(len(names)) if any(w in names[i] or (i < len(mats) and w in mats[i]) for w in skip)}
    if not bad:
        return None
    fn = getattr(MAT, "get_all_triangle_material_i_ds", None) or getattr(MAT, "get_all_triangle_material_ids")
    res = fn(dm)
    ids = list(LU.convert_index_list_to_array(_pick(res, "GeometryScriptIndexList")))
    if not ids:  # no material ids on the copied mesh
        return None
    keep = set()
    for t, mid in enumerate(ids):
        if mid < 0 or mid in bad:
            continue
        iv = _pick(MQ.get_triangle_indices(dm, t), "IntVector")
        keep.update((iv.x, iv.y, iv.z))
    n = len(_verts(dm))
    # a mapping that drops most of the garment is not slot -> material id as assumed: measure everything instead
    return sorted(keep) if keep and len(keep) >= 0.3 * n else None


def _collar(a, parts, gv, body: str = "Body", gs=None) -> dict:
    """fmbridge.qa.garment_look.collar_stats at this pose: the garment's verts in the neck's frame (neck_01 ->
    head axis of the Body) and their distance to the skin (the Face's lower neck, or the Body). With `gs` (the
    garment's own _Surface) each vertex is also flagged as WALL (its triangle's normal within COLLAR_WALL_DEG of
    perpendicular to the neck axis), so the local roll ignores the yoke flowing out over the shoulder."""
    b = parts.get(body) or parts.get("Body")
    if b is None:
        return {"n": 0, "error": "no Body"}
    n0, hd = b.get_socket_location("neck_01"), b.get_socket_location("head")
    ax = hd - n0
    L = ax.length() or 1.0
    u = ax * (1.0 / L)
    skins = [_Surface(_posed(parts[k])) for k in ("Face", body) if k in parts]
    near = [p for p in gv if -10.0 <= (p - n0).dot(u) <= 6.0]
    # a frame round the neck axis for the angle (local roll): world X made perpendicular to it, and u x that
    ux, uy, uz = u.x, u.y, u.z
    k = ux  # X . u
    e1 = (1.0 - k * ux, -k * uy, -k * uz)
    n1 = math.sqrt(sum(c * c for c in e1)) or 1.0
    e1 = tuple(c / n1 for c in e1)
    e2 = (uy * e1[2] - uz * e1[1], uz * e1[0] - ux * e1[2], ux * e1[1] - uy * e1[0])
    axial, radial, gap, angle, wall = [], [], [], [], []
    lim = math.sin(math.radians(_look.COLLAR_WALL_DEG))
    for p in near:
        if gs is not None:
            r = gs.nearest(p)
            wall.append(r is None or abs(r[2].dot(u)) <= lim)
        t = (p - n0).dot(u)
        v = p - n0 - u * t
        radial.append(v.length())
        angle.append(math.degrees(math.atan2(v.x * e2[0] + v.y * e2[1] + v.z * e2[2],
                                             v.x * e1[0] + v.y * e1[1] + v.z * e1[2])) % 360.0)
        axial.append(t)
        ds = [(p - r[0]).length() for r in (sk.nearest(p) for sk in skins) if r is not None]
        gap.append(min(ds) if ds else float("nan"))
    return _look.collar_stats(axial, radial, gap, angle=angle, wall=wall if gs is not None else None)


def _hem(parts, gv, rc, body: str = "Body") -> dict:
    """fmbridge.qa.garment_look.hem_stats at this pose: radii from the vertical axis through the pelvis of the
    garment's verts in its lowest 3 cm, and of the uncut reference body's (rc) verts in that band (else the
    Trousers')."""
    b = parts.get(body) or parts.get("Body")
    if b is None or not gv:
        return {"n": 0}
    c = b.get_socket_location("pelvis")
    zlo = min(p.z for p in gv)

    def radii(vs, z0=0.0, z1=3.0):
        return [((p.x - c.x) ** 2 + (p.y - c.y) ** 2) ** 0.5 for p in vs if zlo + z0 <= p.z <= zlo + z1]

    ref, name = None, "body"
    if rc is not None:
        ref = radii(_verts(_posed(rc)))
    if not ref and "Trousers" in parts:
        ref, name = radii(_verts(_posed(parts["Trousers"]))), "trousers"
    return _look.hem_stats(radii(gv), ref or [], name, upper_r=radii(gv, 8.0, 11.0))


def _wpo_params(comp) -> dict:
    """The inflate parameters on the component's material instances (largest per name)."""
    out = {}
    MEL = unreal.MaterialEditingLibrary
    for m in comp.get_materials():
        if not isinstance(m, unreal.MaterialInstance):
            continue
        try:  # a dynamic instance (not a constant) has no editor-side getter: read through its parent chain
            names = [str(x) for x in MEL.get_scalar_parameter_names(m)]
            for k in _look.INFLATE_PARAMS:
                if k in names:
                    out[k] = max(out.get(k, 0.0), float(MEL.get_material_instance_scalar_parameter_value(m, k)))
        except Exception as e:  # noqa: BLE001
            out.setdefault("_unread", []).append(f"{m.get_name()}: {e}")
    return out


@op("qa.garment_look", mutates=False, idempotent=True, tags=["gpu", "slow", "metahuman", "experimental"])
def garment_look(*, label: str, garment: str = "", ref_body: str = "", sequence: str = "", frames: list | None = None,
                 motion_from: int | None = None, motion_frames: int = 0, width_px: int = 480, samples: int = 1500,
                 body: str = "Body", out_dir: str = "", ramps: dict | None = None, collar: bool = True,
                 hem: bool = True, skip_slots: list | None = None):
    """Does the garment read as cloth or as ARMOR (fmbridge.qa.garment_look: the armor index)?

    Measured: `ease` (each sampled garment vertex's distance to the UNCUT reference body, posed: its spread and
    median), `thickness` (the garment's wall: a ray in along -normal to its own inside), `wpo` (inflate parameters on
    its materials: FM_Inflate/FM_Neck/FM_Patch), and from the shot's camera at `frames`: `silhouette` ((garment U
    body) px / body px in the garment's rows) and `detail` (high-frequency energy of the garment's world normals); with
    motion_frames > 1, `motion` (the garment's motion relative to the body under it, frame to frame, from motion_from).

    Args: label: the character. garment: its garment component (default: the 'tee' role, qa.clip's roles).
    ref_body: the uncut body mesh of the same build (needed for ease, silhouette, motion; without it they are skipped
    and reported missing). sequence + frames: where to look (default the sequence's first cut, middle). out_dir:
    _look_normal.png per frame (the garment's normals) on the box.
    With `collar` (default), per frame the COLLAR band round the neck (fmbridge.qa.garment_look.collar_stats): its
    gap to the skin and its radial spread; FAIL (hard) over 0.8 cm gap or any rolled frame (round 5: Fit5's collar
    floated like a cowl while every other number passed). With `hem` (default), the hem's flare: its radius from the
    pelvis axis in its lowest 3 cm vs the uncut body's (else the trousers') in that band; FAIL over 1.15. Only the
    garment's DRAWN slots are measured (skip_slots: slot or material names with these words, default short/hidden).
    Returns: {"pass", "verdict": cloth|borderline|armor, "index", "terms", "issues", "missing", "metrics"}.
    Example: film-ue op qa.garment_look label=Host ref_body=/Game/Host/Unpacked/Host/Body/SKM_Host_BodyMesh sequence=/Game/Reel/SEQ_Reel 'frames=[1082,1150]' motion_from=1140 motion_frames=12
    """
    a = find_actor(label)
    skip_slots = tuple(skip_slots or ("short", "hidden"))
    parts = roles(a, {"tee": garment} if garment else None)
    g_role = "tee" if "tee" in parts else next((k for k in parts if k not in SKIN), None)
    if g_role is None:
        raise OpError(f"{label} has no garment component", code="not_found", hint="qa.parts lists its components")
    m = {"wpo": _wpo_params(parts[g_role])}
    per = {}
    ref = rc = None
    try:
        if ref_body:
            ref, rc = _ref_body(a, ref_body, body)
            yield
        if sequence and not frames:
            from . import call
            cuts = call("seq.cuts", path=sequence)
            frames = [(int(cuts[0][1]) + int(cuts[0][2])) // 2] if cuts else []
        for f in frames or [None]:
            if f is not None:
                yield from _scrub(sequence, f, 10)
            parts = roles(a, {"tee": garment} if garment else None)
            gc = parts[g_role]
            gdm = _posed(gc)
            gv = _verts(gdm)
            keep = _shown_verts(gc, gdm, skip_slots)
            if keep is not None:  # only what is drawn: a MetaHuman default garment's hidden shorts are still mesh
                gv = [gv[i] for i in keep if i < len(gv)]
            gs = _Surface(gdm)
            fr = {"shown_verts": len(gv)}
            pick = _sample(gv, samples)
            # thickness: from an outer point, a ray in along -normal to the garment's own inner wall
            walls = []
            for p in _sample(pick, 300):
                r = gs.nearest(p)
                if r is None:
                    continue
                _, _, nrm = r
                t = gs.ray(p - nrm * 0.02, nrm * -1.0, 3.0)
                if t is not None:
                    walls.append(t + 0.02)
            fr["thickness_cm"] = round(_look.percentile(walls, 0.5), 3) if len(walls) >= 10 else 0.0
            fr["walls"] = len(walls)
            yield
            if collar:
                fr["collar"] = _collar(a, parts, gv, body, gs=gs)
                yield
            if hem:
                fr["hem"] = _hem(parts, gv, rc, body)
                yield
            if rc is not None:
                bs = _Surface(_posed(rc))
                ease = []
                for k, p in enumerate(pick):
                    s = bs.signed(p)
                    if s is not None:
                        ease.append(s[0])
                    if k % 300 == 299:
                        yield
                fr["ease"] = _look.ease_stats(ease)
            if f is not None and sequence:
                info = camera_info(cut_camera(sequence, f), aspect=16 / 9)
                w, h = int(width_px), round(int(width_px) * 9 / 16)
                rt = yield from capture(info, w, h, "depth", show_only=[gc], warmup=1)
                gd = read_pixels(rt, "r")[0]
                mask = {i for i, z in enumerate(gd) if z < _clip.EMPTY}
                rt = yield from capture(info, w, h, "normal", show_only=[gc], warmup=2)
                nrm = read_pixels(rt, "rgb")
                fr["detail"] = _look.detail_energy(tuple(nrm), mask, w, h)
                if rc is not None:
                    rt = yield from capture(info, w, h, "depth", show_only=[rc], warmup=1)
                    fr["silhouette"] = _look.silhouette_ratio(gd, read_pixels(rt, "r")[0], w, h)
                if out_dir:
                    os.makedirs(out_dir, exist_ok=True)
                    data = bytearray(w * h * 3)
                    for c in range(3):
                        data[c::3] = bytes(max(0, min(255, int(127.5 * (v + 1.0)))) for v in nrm[c])
                    _image.write(_image.Image(w, h, 3, data), os.path.join(out_dir, f"{label}_{f:04d}_look_normal.png"))
            per[f if f is not None else "now"] = fr
        if motion_frames > 1 and rc is not None and sequence:
            f0 = motion_from if motion_from is not None else (frames or [0])[0]
            gtr, btr, anchor = [], [], None
            for k in range(int(motion_frames)):
                yield from _scrub(sequence, f0 + k, 4)
                gv = _verts(_posed(roles(a, {"tee": garment} if garment else None)[g_role]))
                bs = _Surface(_posed(rc))
                if anchor is None:
                    pick_i = list(range(0, len(gv), max(1, len(gv) // 400)))
                    anchor = [(i, (bs.nearest(gv[i]) or (None, None, None))[1]) for i in pick_i]
                    anchor = [(i, t) for i, t in anchor if t is not None]
                gtr.append([[gv[i].x, gv[i].y, gv[i].z] for i, _ in anchor])
                cs = [bs.centroid(t) for _, t in anchor]
                btr.append([[c.x, c.y, c.z] if c is not None else [0.0, 0.0, 0.0] for c in cs])
                yield
            m["motion"] = _look.secondary_motion(gtr, btr)
    finally:
        remove_rig()
        if ref is not None:
            _drop_ref()
    # the look from the frames: the worst (most armor-like) value per term
    vals = list(per.values())
    eases = [v["ease"] for v in vals if v.get("ease", {}).get("n")]
    if eases:
        m["ease"] = min(eases, key=lambda e: e["spread"] if e.get("spread") is not None else 9)
    th = [v["thickness_cm"] for v in vals if v.get("thickness_cm")]
    if th:
        m["thickness_cm"] = max(th)
    sil = [v["silhouette"]["ratio"] for v in vals if v.get("silhouette", {}).get("ratio")]
    if sil:
        m["silhouette"] = max(sil)
    det = [v["detail"]["energy"] for v in vals if v.get("detail", {}).get("energy") is not None]
    if det:
        m["detail"] = min(det)
    cols = [v["collar"] for v in vals if v.get("collar", {}).get("n")]
    if cols:
        meas = [c for c in cols if c.get("spread_cm") is not None]
        w = max(meas, key=lambda c: c["spread_cm"]) if meas else {}
        m["collar"] = {"frames": len(cols), "gap_cm": max(c["gap_cm"] for c in cols),
                       "spread_cm": w.get("spread_cm"), "spread_where": w.get("spread_where"),
                       "spread_window_cm": max((c.get("spread_window_cm") or 0) for c in cols),
                       "roll_frames": sum(1 for c in cols if c["roll"] is True),
                       "roll_unmeasured": sum(1 for c in cols if c["roll"] is None)}
    hems = [v["hem"] for v in vals if v.get("hem", {}).get("n")]
    if hems:
        rs = [h for h in hems if h.get("ratio")]
        w = max(rs, key=lambda h: h["ratio"]) if rs else {}
        ang = [h["angle_deg"] for h in hems if h.get("angle_deg") is not None]
        m["hem"] = {"frames": len(hems), "ratio": w.get("ratio"), "ease_cm": w.get("ease_cm"), "ref": w.get("ref"),
                    "angle_deg": max(ang) if ang else None}
    if isinstance(m.get("motion"), dict):
        m["motion"] = m["motion"].get("ratio")
        if m["motion"] is None:
            m.pop("motion")
    res = _look.look(m, f"{label}.{parts[g_role].get_name()}", ramps=ramps)
    res["metrics"] = {"frames": per, "measured": m}
    if not ref_body:
        res["issues"].append(issue("garment.no_ref_body", "warn", "no ref_body: ease, silhouette and motion skipped",
                                   "pass ref_body= the uncut body mesh of the same build (garment.export reports it)",
                                   subject=label))
    return res


# --- export for the fit ------------------------------------------------------------------------------------------

@op("qa.limb_clearance", mutates=False, idempotent=True, tags=["slow", "metahuman"])
def limb_clearance(*, label: str, sequence: str, frames: list | None = None, shots: list | None = None, n: int = 6,
                   body: str = "Body", sides: list | None = None, arm_r: float = 9.0, torso_r: float = 30.0,
                   min_cm: float = 3.0, stride: int = 3):
    """Upper arm vs torso clearance on the POSED meshes (round 7: 'her right boob is covering the upper limb of her right
    hand'). Per frame: the Body and the upper garment (tee/Top/Overshirt) posed (Geometry Script), split by bone
    segments into ARM points (upperarm_<s> -> lowerarm_<s>, 35-95 % along it) and TORSO points (spine_03 -> neck_01);
    fmbridge.qa.limbs.clearance gives the min distance, NEGATIVE where the arm sits inside the torso's volume.

    Args: label: the character. sequence + frames (or shots/n spread per camera cut). sides: ["l", "r"].
    stride: use every Nth vertex (speed). min_cm: the gate (body.upperarm_torso_clear_cm >= min_cm).
    Returns: {"pass", "issues", "metrics": {"worst_cm", "at", "frames": {frame: {side: {cm, at, n_arm, n_torso}}}}}.
    Example: film-ue op qa.limb_clearance label=Presenter sequence=/Game/Explainer/SEQ_Explain_Her 'frames=[1050,1060]'
    """
    a = find_actor(label)
    parts = roles(a)
    comp = parts.get(body)
    if comp is None:
        raise OpError(f"{label} has no {body!r} component", code="not_found")
    upper = [parts[k] for k in ("tee", "Top", "Overshirt", "Shirt") if k in parts]
    plan = {"frames": list(frames)} if frames else _frames_of(sequence, shots, n, None)
    out, worst, at = {}, None, None
    for shot, fs in plan.items():
        if isinstance(fs, dict):
            continue
        for f in fs:
            yield from _scrub(sequence, f, 10)
            pts = []
            for c in [comp] + upper:
                pts += [(v.x, v.y, v.z) for v in list(_verts(_posed(c)))[::max(1, int(stride))]]  # unreal.Array: no slice step
            yield
            loc = {b: comp.get_socket_location(b) for b in ("spine_03", "neck_01", "upperarm_l", "lowerarm_l",
                                                          "upperarm_r", "lowerarm_r")}
            P = {b: (v.x, v.y, v.z) for b, v in loc.items()}
            torso = (P["spine_03"], P["neck_01"])
            row = {}
            for sd in sides or ["l", "r"]:
                A, T = _limbs.classify(pts, (P[f"upperarm_{sd}"], P[f"lowerarm_{sd}"]), torso, arm_r=arm_r,
                                       torso_r=torso_r)
                r = _limbs.clearance(A, T, torso)
                row[sd] = r
                if r.get("cm") is not None and (worst is None or r["cm"] < worst):
                    worst, at = r["cm"], f"{shot}@{f} {sd}"
            out[f] = row
            yield
    issues = []
    if worst is None:
        issues.append(issue("limb.unmeasured", "fail", f"{label}: no frame measured an arm and a torso",
                            "check the bone names and the frames", subject=label))
    elif worst < min_cm:
        issues.append(issue("limb.clearance", "fail", f"{label} {at}: upper arm {worst:+.1f} cm from the torso "
                            f"(limit {min_cm}; negative = inside it)", "elbows away from the torso in the body pose "
                            "(agent-01), or slim the garment there", subject=label, value=worst, expected=min_cm))
    return _result(issues, {"worst_cm": worst, "at": at, "frames": out})


HAND_POINTS = {s: (f"hand_{s}", f"index_03_{s}", f"middle_03_{s}", f"ring_03_{s}", f"pinky_03_{s}", f"thumb_03_{s}")
               for s in ("l", "r")}  # the wrist + 5 fingertips (agent-10's offline framing.py uses the same)


@op("qa.hands_in_frame", mutates=False, idempotent=True, tags=["camera", "metahuman"])
def hands_in_frame(*, label: str, sequence: str, frames: list, body: str = "Body", width_px: int = 1920,
                   height_px: int = 1080):
    """Are her hands IN the shot's frame while she gestures? (round 7: in the MCU test the gestures happened below the
    frame: elbows out, no hands = still stiff.) Per frame: the cut camera, the wrist + 5 fingertips of each hand (1 % margin)
    projected through it (fmbridge.qa.clip.project_px); a frame counts when >= 1 hand is FULLY in frame. Per camera
    kind (MCU incl. MCU_L, CU, WIDE) the share of the given frames, against fmbridge.qa.limbs.HAND_LINES.

    Args: label, sequence; frames: the speaking frames (spans_<film>.json, every frame or every Nth).
    Returns: {"pass", "issues", "metrics": {"kinds": {kind: {frac, n, line, cameras}}, "frames": {f: {camera, in, l, r}}}}.
    Example: film-ue op qa.hands_in_frame label=Presenter sequence=/Game/Explainer/SEQ_Explain_Her 'frames=[0,6,12]'
    """
    a = find_actor(label)
    comp = roles(a).get(body)
    if comp is None:
        raise OpError(f"{label} has no {body!r} component", code="not_found")
    names = {str(b) for b in comp.get_all_socket_names()} if hasattr(comp, "get_all_socket_names") else None
    rows, missing = {}, set()
    for f in frames:
        yield from _scrub(sequence, f, 4)
        cam = cut_camera(sequence, f)
        info = camera_info(cam, aspect=width_px / height_px)
        row = {"camera": cam}
        for sd, pts in HAND_POINTS.items():
            px = []
            for b in pts:
                if names is not None and b not in names:
                    missing.add(b)
                    continue
                p = comp.get_socket_location(b)
                px.append(_clip.project_px(info, (p.x, p.y, p.z), width_px, height_px))
            row[sd] = (_limbs.hand_in(px, width_px, height_px, margin=round(0.01 * width_px))
                       if len(px) == len(pts) else False)  # a 1 % margin (agent-10's framing.py)
        row["in"] = bool(row["l"] or row["r"])
        rows[f] = row
        yield
    kinds = _limbs.hands_fracs(rows)
    issues = []
    if missing:
        issues.append(issue("hands.bones", "fail", f"{label}: no bone(s) {sorted(missing)}", "pass the rig's names",
                            subject=label))
    for k, v in kinds.items():
        if v["frac"] < v["line"]:
            issues.append(issue("hands.out_of_frame", "fail", f"{label} {k}: >= 1 hand fully in frame in "
                                f"{100 * v['frac']:.0f}% of {v['n']} frames (line {100 * v['line']:.0f}%)",
                                "raise the gesture space to chest-collarbone height, in front of the torso (agent-01)",
                                subject=label, value=v["frac"], expected=v["line"]))
    return _result(issues, {"kinds": kinds, "frames": rows})


@op("qa.hand_torso_clearance", mutates=False, idempotent=True, tags=["slow", "metahuman"])
def hand_torso_clearance(*, label: str, sequence: str, frames: list, body: str = "Body", stride: int = 2,
                         min_cm: float = 8.0):  # the orchestrator's desk-rest line (08 Nov)
    """Resting hands vs the chest (round 7: her high rest hovered at the top of her chest, 'fidgeting with her top').
    Per frame (the REST/bridge frames: film-qa perf-rest picks them from the hand samples): the torso surface (posed
    Body + upper garment points along spine_01 -> neck_01, the lap/thighs, arms, forearms and every finger excluded), and each hand's wrist + 5
    fingertips + 5 knuckles; the min distance (fmbridge.qa.limbs.nearest). The gate: >= min_cm on every rest frame.

    Returns: {"pass", "issues", "metrics": {"worst_cm", "at", "frames": {f: {"l", "r", "min"}}}}.
    Example: film-ue op qa.hand_torso_clearance label=Presenter sequence=/Game/Explainer/SEQ_Explain_Her 'frames=[8,90]'
    """
    a = find_actor(label)
    parts = roles(a)
    comp = parts.get(body)
    if comp is None:
        raise OpError(f"{label} has no {body!r} component", code="not_found")
    upper = [parts[k] for k in ("tee", "Top", "Overshirt", "Shirt") if k in parts]
    pts_of = {sd: [f"hand_{sd}"] + [f"{fg}_{j}_{sd}" for fg in ("index", "middle", "ring", "pinky", "thumb")
                                    for j in ("01", "03")] for sd in ("l", "r")}
    out, worst, at = {}, None, None
    for f in frames:
        yield from _scrub(sequence, f, 6)
        pts = []
        for c in [comp] + upper:
            pts += [(v.x, v.y, v.z) for v in list(_verts(_posed(c)))[::max(1, int(stride))]]
        yield
        names = ["spine_01", "neck_01"] + [f"{b}_{s}" for s in "lr" for b in ("upperarm", "lowerarm", "hand")] + \
                [f"{fg}_03_{s}" for s in "lr" for fg in ("index", "middle", "ring", "pinky", "thumb")]
        P = {b: comp.get_socket_location(b) for b in names}
        P = {b: (v.x, v.y, v.z) for b, v in P.items()}
        limbs_ = [(P[f"upperarm_{s}"], P[f"lowerarm_{s}"]) for s in "lr"] + \
                 [(P[f"lowerarm_{s}"], P[f"hand_{s}"]) for s in "lr"]
        fingers_ = [(P[f"hand_{s}"], P[f"{fg}_03_{s}"]) for s in "lr" for fg in ("index", "middle", "ring", "pinky",
                                                                                 "thumb")]
        cloud = _limbs.torso_cloud(pts, (P["spine_01"], P["neck_01"]), limbs_, fingers=fingers_)
        row = {}
        for sd, bones in pts_of.items():
            hp = [(v.x, v.y, v.z) for v in (comp.get_socket_location(b) for b in bones)]
            row[sd] = _limbs.nearest(hp, cloud).get("cm")
        vals = [v for v in row.values() if v is not None]
        row["min"] = min(vals) if vals else None
        if row["min"] is not None and (worst is None or row["min"] < worst):
            worst, at = row["min"], f
        out[f] = row
        yield
    issues = []
    if worst is None:
        issues.append(issue("rest.unmeasured", "fail", f"{label}: no rest frame measured", "check frames/bones",
                            subject=label))
    elif worst < min_cm:
        issues.append(issue("rest.hands_on_chest", "fail", f"{label} f{at}: a resting hand {worst:.1f} cm from the "
                            f"chest (limit {min_cm})", "rest the hands loosely together at the lower ribcage, 20-30 cm "
                            "in front of the torso (agent-01/agent-10)", subject=label, value=worst, expected=min_cm))
    return _result(issues, {"worst_cm": worst, "at": at, "frames": out})


def _export(asset, path: str, morphs: bool = False) -> list:
    t = unreal.AssetExportTask()
    t.set_editor_property("object", asset)
    t.set_editor_property("filename", path)
    for k, v in (("automated", True), ("prompt", False), ("replace_identical", True)):
        t.set_editor_property(k, v)
    o = unreal.FbxExportOption()
    for k, v in (("ascii", False), ("level_of_detail", False), ("collision", False), ("export_morph_targets", morphs),
                 ("vertex_color", True), ("map_skeletal_motion_to_root", False)):
        try:
            o.set_editor_property(k, v)
        except Exception:
            pass
    t.set_editor_property("options", o)
    ok = unreal.Exporter.run_asset_export_task(t)
    return [asset.get_path_name(), bool(ok), os.path.getsize(path) if os.path.exists(path) else 0]


@op("garment.export", mutates=True, idempotent=True, tags=["metahuman"])
def export(*, label: str, out_dir: str, garments: list | None = None, ref_body: str = "", anims: list | None = None,
           sequences: list | None = None) -> dict:
    """Export what the Blender fit (film-ue garment fit) needs, as FBX in cm on the body skeleton, to out_dir on the
    box: body.fbx (the body as worn: cut under its garments), face.fbx (its lower neck is in the collider: a
    MetaHuman's face mesh runs ~10 cm below neck_01, to the clavicles), ref_body.fbx (the UNCUT body: weights and
    ease come from it), garment_<name>.fbx per garment, anim_<name>.fbx for every animation the sequences play on
    the character (the fit's pose tests). Read-only on the project.

    Args: label: the character. garments: component names (default every garment role but shoes). ref_body: the
    uncut body mesh (default: another body mesh in the body's folder, e.g. SKM_<Name>_BodyMesh from an earlier
    build; refused when none: say which). sequences: level sequences whose skeletal animation sections count (default
    none); anims: extra AnimSequence paths.
    Returns: {"out_dir", "files": {name: [asset, ok, bytes]}, "ref_body", "manifest"} (manifest.json beside them).
    Example: film-ue op garment.export label=Host out_dir=/srv/ue/fit/host 'sequences=["/Game/Reel/SEQ_Reel"]'
    """
    a = find_actor(label)
    parts = roles(a)
    os.makedirs(out_dir, exist_ok=True)

    body_m = parts["Body"].get_skeletal_mesh_asset()
    if not ref_body:
        folder = body_m.get_path_name().rsplit("/", 1)[0]
        cands = [p.split(".")[0] for p in EAL.list_assets(folder, recursive=False, include_folder=False)
                 if p.split(".")[0] != body_m.get_path_name().split(".")[0]
                 and isinstance(EAL.load_asset(p.split(".")[0]), unreal.SkeletalMesh)]
        if not cands:
            raise OpError(f"no uncut body beside {body_m.get_path_name()}", code="not_found",
                          hint="pass ref_body= the uncut body mesh (MetaHuman cuts the body under its garments; "
                               "weights and ease need the whole one)")
        ref_body = cands[0]
    files = {"body": _export(body_m, os.path.join(out_dir, "body.fbx")),
             "ref_body": _export(EAL.load_asset(ref_body), os.path.join(out_dir, "ref_body.fbx"))}
    if "Face" in parts:
        files["face"] = _export(parts["Face"].get_skeletal_mesh_asset(), os.path.join(out_dir, "face.fbx"))
    for role, c in parts.items():
        if role in SKIN or role == "shoes" or (garments and c.get_name() not in garments and role not in garments):
            continue
        files[f"garment_{role}"] = _export(c.get_skeletal_mesh_asset(), os.path.join(out_dir, f"garment_{role}.fbx"))
    played = set(anims or [])
    for sp in sequences or ():
        seq = unreal.load_asset(sp)
        if not seq:
            continue
        for b in seq.get_bindings():
            for t in b.get_tracks():
                if isinstance(t, unreal.MovieSceneSkeletalAnimationTrack):
                    for s in t.get_sections():
                        an = s.get_editor_property("params").get_editor_property("animation")
                        if an:
                            played.add(an.get_path_name().split(".")[0])
    for p in sorted(played):
        an = unreal.load_asset(p)
        if an and an.get_class().get_name() == "AnimSequence":
            files["anim_" + p.rsplit("/", 1)[-1]] = _export(an, os.path.join(out_dir, f"anim_{p.rsplit('/', 1)[-1]}.fbx"))
    skel = body_m.get_editor_property("skeleton")
    man = {"label": label, "skeleton": skel.get_path_name() if skel else "", "ref_body": ref_body,
           "garments": {k[len("garment_"):]: v[0] for k, v in files.items() if k.startswith("garment_")},
           "components": {k: c.get_name() for k, c in parts.items()}, "files": files}
    with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
        json.dump(man, fh, indent=1)
    bad = [k for k, v in files.items() if not v[1] or not v[2]]
    if bad:
        raise OpError(f"export failed for {bad}", code="engine", hint="see the editor log (LogFbx / LogExporter)")
    return {"out_dir": out_dir, "files": files, "ref_body": ref_body, "manifest": os.path.join(out_dir, "manifest.json")}


# --- body under a garment --------------------------------------------------------------------------------------------

def fill_holes(n_verts: int, tris: list, hit: list, max_verts: int, ok=None) -> tuple:
    """Uncovered islands of at most max_verts vertices (joined by triangle edges) that only covered skin surrounds,
    marked covered: a patch the garment's rays missed (cloth that crosses the skin in the reference pose) is still
    under it. The biggest uncovered island (the rest of the skin) always stays, and so does any island ok(vertices)
    refuses. Pure: returns (hit, island sizes filled, every uncovered island's size, biggest first)."""
    nbr = [[] for _ in range(n_verts)]
    for a, b, c in tris:
        nbr[a] += (b, c)
        nbr[b] += (a, c)
        nbr[c] += (a, b)
    seen = [False] * n_verts
    islands = []
    for v in range(n_verts):
        if hit[v] or seen[v] or not nbr[v]:
            continue
        seen[v], comp, stack = True, [v], [v]
        while stack:
            for w in nbr[stack.pop()]:
                if not hit[w] and not seen[w]:
                    seen[w] = True
                    comp.append(w)
                    stack.append(w)
        islands.append(comp)
    out, filled = list(hit), []
    biggest = max(islands, key=len) if islands else []
    for comp in islands:
        if comp is not biggest and len(comp) <= max_verts and (ok is None or ok(comp)):
            for v in comp:
                out[v] = True
            filled.append(len(comp))
    return out, sorted(filled, reverse=True), sorted((len(c) for c in islands), reverse=True)


def covered(n_verts: int, tris: list, hit: list, rings: int = 2) -> list:
    """Triangles to hide: every corner covered (hit[v] True: a ray out along the skin's normal meets the garment
    within reach), then the hidden region shrunk by `rings` of triangles from its border with uncovered skin, so a
    gap never opens where the cloth moves off the body. Pure: tris [(a, b, c)], hit [bool] per vertex."""
    keep_v = [not h for h in hit]
    for _ in range(max(0, rings)):
        grow = list(keep_v)
        for a, b, c in tris:
            if keep_v[a] or keep_v[b] or keep_v[c]:
                grow[a] = grow[b] = grow[c] = True
        keep_v = grow
    return [i for i, (a, b, c) in enumerate(tris) if not (keep_v[a] or keep_v[b] or keep_v[c])]


@op("body.hide_under", mutates=True, idempotent=True, tags=["metahuman", "experimental"])
def hide_under(*, label: str, garment: str, body: str = "Body", reach_cm: float = 4.0, rings: int = 2,
               apply: bool = False, dest: str = "", inside_cm: float = 0.0, fill_max: int = 0,
               within: list | None = None) -> dict:
    """Hide the body where a garment covers it (MetaHuman does this for its own garments; a garment of your own
    needs it too): a body vertex is covered when a ray out along its normal meets the garment within reach_cm, a
    triangle is hidden when all its corners are, less `rings` triangles round the border (cloth that moves off the
    body never opens a gap). Measured in the reference pose (the meshes' own vertices), so it holds for every frame.
    inside_cm > 0 also counts a vertex covered when a ray IN along -normal meets the garment within inside_cm: cloth
    fitted in another pose (her seated waist refit, carried back to bind) can sit inside the skin in the reference
    pose, where the outward ray never meets it. fill_max > 0 also covers every uncovered island of at most that many
    vertices that covered skin surrounds and the garment is within reach of everywhere (fill_holes), before the
    rings shrink. within [[x, y, z, r], ...] (reference-pose cm): only body vertices inside one of these spheres can
    be covered (a local refit hides only its own region's skin).

    With apply=False (default) it only counts. With apply=True the triangles are deleted on a COPY of the body mesh
    (dest, default <body mesh>_Under_<garment>), set on the component, and leader pose re-applied (mh.leader).
    Never on the Face: its rig (DNA, morph targets) does not survive a mesh copy; refit the garment round the face
    instead (garment.fit's collider takes the face).
    Returns: {"vertices", "covered_vertices", "covered_inside", "islands" (uncovered islands' sizes), "holes_filled",
    "triangles", "hidden", "fraction", "mesh" (with apply)}.
    Example: film-ue op body.hide_under label=Ava garment=Top apply=true
    """
    if body == "Face" or garment in SKIN:
        raise OpError("body.hide_under works on the Body only", code="bad_args",
                      hint="for the face's neck under a collar: garment.fit with the face in the collider")
    a = find_actor(label)
    comps = {c.get_name(): c for c in a.get_components_by_class(unreal.SkeletalMeshComponent)}
    for nme in (body, garment):
        if nme not in comps:
            raise not_found("component", nme, sorted(comps), hint="qa.parts lists them")
    AU = unreal.GeometryScript_AssetUtils
    _, SP, MQ, LU = _gs()

    def ref_mesh(skm):
        dm = unreal.DynamicMesh()
        opts = unreal.GeometryScriptCopyMeshFromAssetOptions()
        lod = unreal.GeometryScriptMeshReadLOD()
        lod.set_editor_property("lod_index", 0)
        AU.copy_mesh_from_skeletal_mesh(skm, dm, opts, lod)
        return dm

    bm = comps[body].get_skeletal_mesh_asset()
    bdm, gdm = ref_mesh(bm), ref_mesh(comps[garment].get_skeletal_mesh_asset())
    yield
    gs = _Surface(gdm)
    vs = _verts(bdm)
    # GeometryScript_Normals.GetMeshPerVertexNormals (MeshNormalsFunctions.h, 5.8.4): a list as long as MaxVertexID
    normals = LU.convert_vector_list_to_array(_pick(unreal.GeometryScript_Normals.get_mesh_per_vertex_normals(bdm),
                                                    "GeometryScriptVectorList"))
    if not normals or len(normals) != len(vs):
        raise OpError(f"could not read the body's vertex normals ({len(normals or [])} for {len(vs)} verts)",
                      code="engine", hint="a mesh with vertex-ID gaps: re-save the body mesh, or check editor.api_names")
    hit, inside = [], 0
    spheres = [(unreal.Vector(x, y, z), float(r)) for x, y, z, r in (within or [])]
    for k, (p, n) in enumerate(zip(vs, normals)):
        if spheres and not any((p - c).length() <= r for c, r in spheres):
            hit.append(False)
            continue
        d = n * (1.0 / (n.length() or 1.0))
        h = gs.ray(p, d, float(reach_cm)) is not None
        if not h and inside_cm > 0 and gs.ray(p, d * -1.0, float(inside_cm)) is not None:
            h, inside = True, inside + 1
        hit.append(h)
        if k % 2000 == 1999:
            yield
    # GetAllTriangleIDs: UE's camel-case splitter makes it get_all_triangle_i_ds; take whichever this build exposes
    all_ids = getattr(MQ, "get_all_triangle_i_ds", None) or getattr(MQ, "get_all_triangle_ids")
    tl = LU.convert_index_list_to_array(_pick(all_ids(bdm), "GeometryScriptIndexList"))
    tris = []
    for t in tl:
        r = MQ.get_triangle_indices(bdm, t)
        iv = _pick(r, "IntVector")
        tris.append((iv.x, iv.y, iv.z))
    def under(comp):  # every vertex of the island within reach of the garment (a foot past a hem is not)
        for v in comp:
            r = gs.nearest(vs[v])
            if r is None or (vs[v] - r[0]).length() > max(reach_cm, inside_cm):
                return False
        return True

    hit, filled, islands = fill_holes(len(vs), tris, hit, int(fill_max), under)
    hide = covered(len(vs), tris, hit, rings)
    out = {"vertices": len(vs), "covered_vertices": sum(hit), "covered_inside": inside, "islands": islands[:12],
           "holes_filled": filled[:20],
           "triangles": len(tris), "hidden": len(hide), "fraction": round(len(hide) / max(1, len(tris)), 4)}
    if not apply:
        return out
    if not hide:
        raise OpError("no body triangle is covered", code="not_found",
                      hint=f"is {garment} on the body in the reference pose? raise reach_cm (now {reach_cm})")

    src = bm.get_path_name().split(".")[0]
    dest = dest or f"{src}_Under_{garment}"
    if EAL.does_asset_exist(dest):
        EAL.delete_asset(dest)
    EAL.duplicate_asset(src, dest)
    dup = EAL.load_asset(dest)
    il = _pick(LU.convert_array_to_index_list([tl[i] for i in hide]), "GeometryScriptIndexList")
    unreal.GeometryScript_MeshEdits.delete_triangles_from_mesh(bdm, il)  # MeshBasicEditFunctions.h, ScriptName MeshEdits
    wopts = unreal.GeometryScriptCopyMeshToAssetOptions()
    wlod = unreal.GeometryScriptMeshWriteLOD()
    wlod.set_editor_property("lod_index", 0)
    AU.copy_mesh_to_skeletal_mesh(bdm, dup, wopts, wlod)
    EAL.save_asset(dest)
    comps[body].set_skeletal_mesh_asset(dup)
    yield
    from . import call
    out["leader"] = call("mh.leader", label=label, body=body)["ok"] if body == "Body" else None
    out["mesh"] = dest
    return out


# --- MetaHuman's own hiding: the wardrobe item's hidden face maps -------------------------------------------------

def _prop(obj, name):
    """get_editor_property by the snake_case name, else the C++ one: an EditAnywhere-only UPROPERTY (the hidden face
    maps, FHiddenFaceMapSettings) has no Python name, but the C++ name finds it (box, round 5)."""
    err = None
    for n in (name, "".join(w[:1].upper() + w[1:] for w in name.split("_"))):
        try:
            return obj.get_editor_property(n)
        except Exception as e:  # noqa: BLE001
            err = e
    raise err


def _hfm(pipe, which: str) -> dict:
    """One FHiddenFaceMapTexture (texture + settings) of an item's editor pipeline, as plain values."""
    try:
        h = _prop(pipe, f"{which}_hidden_face_map_texture")
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(pipe).__name__} has no {which}_hidden_face_map_texture ({e})"}
    tex = _prop(h, "texture")
    s = _prop(h, "settings")
    return {"texture": tex.get_path_name() if tex else None,
            "max_cull_value": float(_prop(s, "max_cull_value")),
            "min_keep_value": float(_prop(s, "min_keep_value")),
            "max_shrink_distance": float(_prop(s, "max_shrink_distance"))}


@op("garment.hidden_face_maps", mutates=False, idempotent=True, tags=["metahuman"])
def hidden_face_maps(*, item: str) -> dict:
    """A MetaHuman wardrobe item's hidden face maps: what MetaHuman itself removes or SHRINKS of the head and body
    under this garment at assembly (5.7+: UMetaHumanOutfitEditorPipeline and UMetaHumanSkeletalMeshEditorPipeline
    both carry HeadHiddenFaceMapTexture and BodyHiddenFaceMapTexture; settings MaxCullValue 0.1, MinKeepValue 0.9,
    MaxShrinkDistance 0 by default, i.e. shrink OFF). Pixels <= max_cull are removed, between the two the skin is
    moved in along -normal by up to max_shrink_distance (cm), >= min_keep untouched; the head map is sampled in the
    head's UV space (the highest of R, G, B).

    Args: item: the wardrobe item's asset path (mh.palette lists a character's; a WI_ asset).
    Returns: {"item", "pipeline", "editor_pipeline", "head": {texture, max_cull_value, min_keep_value,
    max_shrink_distance}, "body": {...}}.
    Example: film-ue op garment.hidden_face_maps item=/MetaHumanCharacter/Optional/Clothing/DefaultGarment/WI_DefaultGarment
    """
    wi = EAL.load_asset(item)
    if wi is None:
        raise OpError(f"no asset {item}", code="not_found", hint="mh.palette / mh.wardrobe kind=Clothing list items")
    pipe = _prop(wi, "pipeline")
    if pipe is None:
        raise OpError(f"{item} has no pipeline", code="not_found", hint="is it a MetaHuman wardrobe item (WI_)?")
    ed = _prop(pipe, "editor_pipeline")
    if ed is None:
        raise OpError(f"{item}'s pipeline has no editor pipeline", code="not_found",
                      hint="open the item once in the editor (SetDefaultEditorPipeline runs then)")
    return {"item": item, "pipeline": type(pipe).__name__, "editor_pipeline": type(ed).__name__,
            "head": _hfm(ed, "head"), "body": _hfm(ed, "body")}
