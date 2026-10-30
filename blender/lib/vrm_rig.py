"""Past a VRM's humanoid (blender/lib/vrm.py) into the rest of what VRoid Studio exports: the face's raw shape keys,
the hair's chains of bones, the garments' meshes and textures, and the fingers of a hand closed round a grip.

Faces. A VRoid face carries a shape key per part and mood: Fcl_BRW_Angry (the brows), Fcl_EYE_Angry, Fcl_EYE_Close (the
eyes), Fcl_MTH_Close, Fcl_MTH_Sorrow (the mouth), Fcl_HA_Hide (the teeth), and Fcl_ALL_Angry, Fcl_ALL_Joy, ... (a whole
face: what the VRM's presets bind, the angry one with its teeth bared). `compose(ch, "glare", {"Fcl_BRW_Angry": 1.0,
"Fcl_EYE_Angry": 0.8, "*MTH_Sorrow": 0.45})` makes an expression of parts (names or fnmatch patterns, any case) that
`vrm.express` then sets like any of the file's own, its weights adding up per shape key with the others'.

Hair. VRoid hangs its strands on chains of bones under the head (J_Sec_Hair1_05 > J_Sec_Hair2_05 > J_Sec_Hair3_05 >
J_Sec_Hair3_05_end). `chains(ch, "J_Sec_Hair*")` lists them, root first; `turn_bones` poses any bone of the armature
by vrm.pose's convention ((x, y, z) degrees about the character's axes, or a 3x3, from rest, relative to its parent);
`sweep` swings a chain toward a direction, most of the swing at its root so the strand bends as hair does, and `part`
sweeps chains off the middle of the face to their own sides: bangs parted off the eyes.

Garments. Points are in the character's frame (x its left, y its back, z up; metres as it stands, after vrm.scale_to),
the meshes as they are at rest: change them before posing and the armature carries the change. `faces_of(ob, "Bottoms")`
picks a garment's faces by its material; `lengthen` lets a hem down (a skirt to the ankles, flaring); `cut` deletes
faces (a shirt's collar); `collar` lays a band on the body along a path (a kimono's collar crossing the chest) and
`skin_like` makes a new mesh deform with the clothes under it. Textures: `recolor` turns a garment one colour, its
pattern gone and its folds kept; `paint` colours the texels under some faces (skin where a shirt was cut, bare feet
where socks were) and `sample` reads the colour under others.

Hands. `wrap(ch, side, radius)` curls each finger of a hand that vrm.grasp has put on a grip so that its joints land on
the grip's round (a hilt `radius` thick), where vrm.grip_pose curls every hand the same.

The numpy halves (patterns, swings, a finger's curl, a hem let down, a texture flattened, triangles rasterised, a
collar's band) are tested without Blender in blender/tests/test_vrm_rig.py.
"""
from __future__ import annotations

import fnmatch
import math

import numpy as np

from . import vrm

VROID_HAIR = "J_Sec_Hair*"
# a VRoid finger's three bones, knuckle first
_JOINTS = {"Thumb": ("Metacarpal", "Proximal", "Distal"), "Index": ("Proximal", "Intermediate", "Distal"),
           "Middle": ("Proximal", "Intermediate", "Distal"), "Ring": ("Proximal", "Intermediate", "Distal"),
           "Little": ("Proximal", "Intermediate", "Distal")}


# ---------------------------------------------------------------------------------------------------- the face

def resolve(names, parts: dict) -> dict:
    """{name: weight} for `parts` ({name or fnmatch pattern: weight}, any case) over `names`: a name several patterns
    match takes the sum of their weights. KeyError for a pattern that matches none."""
    names = list(names)
    out: dict = {}
    for pattern, w in parts.items():
        hits = [n for n in names if fnmatch.fnmatchcase(n.lower(), pattern.lower())]
        if not hits:
            near = [n for n in names if pattern.strip("*").lower()[:6] in n.lower()]
            raise KeyError(f"no shape key matches {pattern!r}" + (f" (did you mean {', '.join(near[:4])}?)" if near else ""))
        for n in hits:
            out[n] = out.get(n, 0.0) + float(w)
    return out


# ---------------------------------------------------------------------------------------------------- swings, chains

def rotation(axis, degrees: float) -> np.ndarray:
    """The rotation (3x3) by `degrees` about `axis` (right-handed)."""
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    k = np.array([[0.0, -a[2], a[1]], [a[2], 0.0, -a[0]], [-a[1], a[0], 0.0]])
    t = math.radians(float(degrees))
    return np.eye(3) + math.sin(t) * k + (1.0 - math.cos(t)) * k @ k


def swing(direction, toward, degrees: float) -> np.ndarray:
    """The rotation (3x3) that turns `direction` by `degrees` toward `toward`, about the axis square to both (none
    when they are parallel)."""
    d, t = np.asarray(direction, float), np.asarray(toward, float)
    axis = np.cross(d, t)
    if np.linalg.norm(axis) < 1e-9 * np.linalg.norm(d) * max(np.linalg.norm(t), 1e-9):
        return np.eye(3)
    return rotation(axis, degrees)


def shares(n: int, root: float = 0.55) -> np.ndarray:
    """How a swing is split down a chain of `n` bones: `root` of it at the first, each next bone half the one before's
    share of what is left, summing to 1."""
    if n <= 0:
        return np.zeros(0)
    if n == 1:
        return np.ones(1)
    rest = 0.5 ** np.arange(n - 1)
    return np.concatenate([[root], (1.0 - root) * rest / rest.sum()])


# ---------------------------------------------------------------------------------------------------- hands

def curl_to_round(joints, center, radius: float, *, step: float = 1.0, most: float = 110.0) -> list[float]:
    """A finger's curl round a grip, in its plane of bending (2D: x out along the hand, y toward the palm): `joints`
    are its knuckle and each next joint to the tip at rest (k + 1 points for k bones), `center` the grip's middle and
    `radius` how far each joint should come to rest from it. Each bone turns from where its parent left it toward the
    palm (+: from x toward y), in `step` degree steps up to `most`, until its end reaches the round, or as near as it
    comes. Returns each bone's turn relative to its parent's, degrees."""
    p = np.asarray(joints, float)
    c = np.asarray(center, float)
    turns, total = [], 0.0
    at = p[0].copy()
    for i in range(len(p) - 1):
        seg = p[i + 1] - p[i]
        length = float(np.linalg.norm(seg))
        rest = math.atan2(seg[1], seg[0])
        best, best_err = 0.0, None
        for k in np.arange(0.0, most + step / 2, step):
            a = rest + math.radians(total + k)
            end = at + length * np.array([math.cos(a), math.sin(a)])
            err = float(np.linalg.norm(end - c)) - radius
            if err <= 0.0:
                best = k
                break
            if best_err is None or err < best_err:
                best, best_err = k, err
        turns.append(float(best))
        total += best
        a = rest + math.radians(total)
        at = at + length * np.array([math.cos(a), math.sin(a)])
    return turns


def grip(ch: vrm.Character, side: str, radius: float, *, amount: float = 1.0, depth: float = 0.028,
         reach: float = 0.85, thumb: float = 0.6) -> dict:
    """A hand closed round a grip `radius` thick (`wrap`: each finger on it, none through it), the thumb opposed
    round it from the other side by `thumb`; `amount` under 1 eases it toward the relaxed hand (vrm.hand_pose: a
    grip loosening, or closing as it reaches)."""
    out = wrap(ch, side, radius, depth=depth, reach=reach, thumb=thumb)
    out.update(opposed_thumb(side, radius, thumb))
    if amount >= 1.0:
        return out
    rel = vrm.hand_pose(side)
    k = max(0.0, float(amount))
    return {n: vrm_blend_turn(rel.get(n, (0.0, 0.0, 0.0)), t, k) for n, t in out.items()}


def opposed_thumb(side: str, radius: float, amount: float = 0.6) -> dict:
    """The thumb's joints round a grip `radius` thick from the side opposite the fingers: dropped toward the palm and
    swung in over the grip, curled the more the thinner it is (a pole: the tip on the index's middle joint)."""
    s = 1.0 if side == "left" else -1.0
    thin = min(1.0, max(0.0, (0.03 - radius) / 0.02))       # 0 at 3 cm, 1 at 1 cm
    a = float(amount) / 0.6
    return {f"{side}ThumbMetacarpal": (34.0 * a, s * 8.0 * a, s * (24.0 + 8.0 * thin) * a),
            f"{side}ThumbProximal": (0.0, s * (18.0 + 14.0 * thin) * a, s * 12.0 * a),
            f"{side}ThumbDistal": (0.0, s * (22.0 + 18.0 * thin) * a, 0.0)}


def pinch(side: str, amount: float = 1.0) -> dict:
    """A pinch of something thin (a pipe's stem, a brush) between the thumb's pad and the index's and middle's sides:
    those two curled round it, the ring and little tucked in under them. {bone: (x, y, z)} from the flat hand."""
    s = 1.0 if side == "left" else -1.0
    a = float(amount)
    curls = {"Index": (38, 44, 18), "Middle": (46, 52, 24), "Ring": (62, 74, 40), "Little": (70, 80, 44)}
    fan = {"Index": -2.0, "Middle": 0.0, "Ring": 2.0, "Little": 4.0}
    out = {}
    for f, cs in curls.items():
        for j, c in zip(_JOINTS[f], cs):
            out[f"{side}{f}{j}"] = (0.0, s * c * a, s * fan[f] * a if j == "Proximal" else 0.0)
    out[f"{side}ThumbMetacarpal"] = (30.0 * a, s * 4.0 * a, s * 30.0 * a)
    out[f"{side}ThumbProximal"] = (0.0, s * 12.0 * a, s * 8.0 * a)
    out[f"{side}ThumbDistal"] = (0.0, s * 8.0 * a, 0.0)
    return out


def vrm_blend_turn(a, b, k: float):
    """Between two turns ((x, y, z) degrees or 3x3s) by k: degrees blended as numbers, a 3x3 by its rotation."""
    if np.shape(a) == (3,) and np.shape(b) == (3,):
        return tuple(float(x) + (float(y) - float(x)) * k for x, y in zip(a, b))
    ma = a if np.shape(a) == (3, 3) else vrm.euler(a)
    mb = b if np.shape(b) == (3, 3) else vrm.euler(b)
    r = mb @ np.asarray(ma).T
    ang = math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(r) - 1.0) / 2.0))))
    if ang < 1e-6:
        return np.asarray(mb)
    axis = np.array([r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1]])
    if np.linalg.norm(axis) < 1e-9:
        return np.asarray(mb) if k > 0.5 else np.asarray(ma)
    return rotation(axis, ang * k) @ np.asarray(ma)


# ---------------------------------------------------------------------------------------------------- garments

def stretch(points, top: float, bottom: float, *, flare: float = 0.0, center=(0.0, 0.0)) -> np.ndarray:
    """`points` (n, 3) with the part below `top` (z) let down so the lowest comes to `bottom`, evenly, and widened
    about `center` (x, y) by `flare` more at the bottom (0 at `top`): a hem let down. Points above `top` stay."""
    p = np.array(points, dtype=float, copy=True)
    low = float(p[:, 2].min())
    if low >= top:
        return p
    below = p[:, 2] < top
    p[below, 2] = top - (top - p[below, 2]) * (top - bottom) / (top - low)
    t = (top - p[below, 2]) / (top - bottom)
    c = np.asarray(center, float)
    p[below, :2] = c + (p[below, :2] - c) * (1.0 + flare * t)[:, None]
    return p


def cinch_points(points, a, b, radius: float, *, keep: float = 0.25, ease: float = 0.3) -> np.ndarray:
    """`points` (n, 3) round the segment a..b (a limb at rest) pulled in toward it where they stand further than
    `radius` off it: keeping `keep` of the excess, eased in from nothing at `a` over the first `ease` of the way (a
    sleeve tied back from the shoulder out). Points before `a` or more than a tenth of the way past `b` stay."""
    p = np.array(points, dtype=float, copy=True)
    a, b = np.asarray(a, float), np.asarray(b, float)
    ab = b - a
    t = (p - a) @ ab / float(ab @ ab)
    on = (t > 0.0) & (t < 1.1)     # to a little past the wrist: the cuff
    axis = a + np.outer(t, ab)
    off = p - axis
    d = np.linalg.norm(off, axis=1)
    far = on & (d > radius)
    w = np.clip(t / max(ease, 1e-6), 0.0, 1.0)
    w = w * w * (3 - 2 * w)
    goal = radius + (d - radius) * keep
    scale = np.where(far, (d + (goal - d) * w) / np.maximum(d, 1e-9), 1.0)
    p[far] = axis[far] + off[far] * scale[far, None]
    return p


def _off_axis(points, a, b) -> np.ndarray:
    """Each point's offset (n, 3) from the line through a and b, square to it."""
    p, a, b = np.asarray(points, float), np.asarray(a, float), np.asarray(b, float)
    ab = (b - a) / np.linalg.norm(b - a)
    d = p - a
    return d - np.outer(d @ ab, ab)


def relax_points(points, edges, moving, *, iterations: int = 4, k: float = 0.5) -> np.ndarray:
    """`points` (n, 3) with those in `moving` (indices) eased `k` of the way to the mean of their neighbours along
    `edges` ((m, 2) index pairs), `iterations` times; the rest stay. A sleeve pulled in (`cinch`) keeps its old folds
    as crumples of single faces, which a toon shade's hard edge draws as a sawtooth: this irons them out."""
    p = np.array(points, dtype=float, copy=True)
    e = np.asarray(edges, int).reshape(-1, 2)
    mv = np.zeros(len(p), bool)
    mv[np.asarray(moving, int)] = True
    count = np.bincount(e.ravel(), minlength=len(p)).astype(float)
    for _ in range(iterations):
        acc = np.zeros_like(p)
        np.add.at(acc, e[:, 0], p[e[:, 1]])
        np.add.at(acc, e[:, 1], p[e[:, 0]])
        has = mv & (count > 0)
        p[has] += k * (acc[has] / count[has, None] - p[has])
    return p


def box_blur(img, radius: int) -> np.ndarray:
    """A 2D array blurred by a box `radius` pixels either way (edges clamped)."""
    out = np.asarray(img, float)
    if radius <= 0:
        return out.copy()
    for axis in (0, 1):
        pad = [(0, 0), (0, 0)]
        pad[axis] = (radius + 1, radius)
        c = np.cumsum(np.pad(out, pad, mode="edge"), axis=axis)
        hi = np.take(c, range(2 * radius + 1, c.shape[axis]), axis=axis)
        lo = np.take(c, range(0, c.shape[axis] - 2 * radius - 1), axis=axis)
        out = (hi - lo) / (2 * radius + 1)
    return out


def flatten(pixels, *, keep: float = 0.3, blur: float = 0.02, opaque: bool = False) -> np.ndarray:
    """Texture pixels ((h, w, 4) RGBA, 0..1) as one grey: their light and dark blurred over `blur` of the width (a
    pattern's small checks go, a fold's broad shading stays), `keep` of it kept over flat white (0: all white), the
    alpha as it was (all 1 when `opaque`: a hem's cut-out zigzag made whole). The transparent texels between a
    texture's islands do not darken their edges."""
    px = np.asarray(pixels, float)
    luma = px[..., :3] @ np.asarray(vrm.LUMA)
    alpha = (px[..., 3] > 0.5).astype(float)
    r = max(0, int(round(blur * px.shape[1])))
    seen = box_blur(alpha, r)
    soft = box_blur(luma * alpha, r) / np.maximum(seen, 1e-6)
    ref = np.percentile(soft[alpha > 0], 95) if alpha.any() else 1.0
    grey = np.clip(1.0 - keep + keep * soft / max(ref, 1e-6), 0.0, 1.0)
    out = np.empty_like(px)
    out[..., :3] = grey[..., None]
    out[..., 3] = 1.0 if opaque else px[..., 3]
    return out


def raster(triangles, width: int, height: int, *, grow: int = 0) -> np.ndarray:
    """Which texels ((height, width) bool, row 0 at v 0) the UV `triangles` ((k, 3, 2), 0..1) cover, by their centres;
    `grow` texels more round them (so a texture's filtering at an island's edge finds the new colour too)."""
    mask = np.zeros((height, width), bool)
    for tri in np.asarray(triangles, float).reshape(-1, 3, 2):
        p = tri * (width, height) - 0.5            # texel centres at whole numbers
        x0, y0 = np.floor(p.min(0)).astype(int)
        x1, y1 = np.ceil(p.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, width - 1), min(y1, height - 1)
        if x0 > x1 or y0 > y1:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        (ax, ay), (bx, by), (cx, cy) = p
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        l1 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / d
        l2 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / d
        inside = (l1 >= -1e-9) & (l2 >= -1e-9) & (l1 + l2 <= 1 + 1e-9)
        mask[y0:y1 + 1, x0:x1 + 1] |= inside
    for _ in range(grow):
        g = mask.copy()
        g[1:] |= mask[:-1]
        g[:-1] |= mask[1:]
        g[:, 1:] |= mask[:, :-1]
        g[:, :-1] |= mask[:, 1:]
        mask = g
    return mask


def resample(path, n: int) -> np.ndarray:
    """`n` points evenly along a polyline (by length), its ends kept."""
    p = np.asarray(path, float)
    d = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
    s = np.linspace(0.0, d[-1], n)
    return np.column_stack([np.interp(s, d, p[:, k]) for k in range(p.shape[1])])


def along(path, values, n: int):
    """`values` given one per point of a polyline, at `n` points evenly along it (`resample`); one value stays one."""
    if not np.ndim(values):
        return float(values)
    p = np.asarray(path, float)
    d = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
    return np.interp(np.linspace(0.0, d[-1], n), d, np.asarray(values, float))


def ribbon(points, normals, width, thickness: float) -> tuple[np.ndarray, list]:
    """A flat band along `points` lying on a surface whose normals there are `normals`: `width` across (one, or one per
    point), `thickness` out from the surface (its underside on the points). Returns (vertices, quad faces): a box
    section per point."""
    p = np.asarray(points, float)
    nrm = np.asarray(normals, float)
    nrm = nrm / np.linalg.norm(nrm, axis=1, keepdims=True)
    t = np.gradient(p, axis=0)
    across = np.cross(nrm, t)
    across /= np.linalg.norm(across, axis=1, keepdims=True)
    h = np.broadcast_to(np.asarray(width, float), (len(p),))[:, None] / 2
    # round the section: under-left, under-right, top-right, top-left
    verts = np.stack([p - across * h, p + across * h, p + across * h + nrm * thickness, p - across * h + nrm * thickness],
                     axis=1).reshape(-1, 3)
    faces = []
    for i in range(len(p) - 1):
        a, b = 4 * i, 4 * (i + 1)
        for j in range(4):
            k = (j + 1) % 4
            faces.append((a + j, a + k, b + k, b + j))
    last = 4 * (len(p) - 1)
    faces += [(3, 2, 1, 0), (last, last + 1, last + 2, last + 3)]
    return verts, faces


# ---------------------------------------------------------------------------------------------------- Blender: the face

def shape_keys(ch: vrm.Character) -> dict:
    """{shape key name: [mesh object, ...]} over the character's meshes, their Basis left out."""
    out: dict = {}
    for ob in ch.meshes:
        keys = ob.data.shape_keys
        if keys is None:
            continue
        for kb in keys.key_blocks[1:]:
            out.setdefault(kb.name, []).append(ob)
    return out


def compose(ch: vrm.Character, name: str, parts: dict, *, binary: bool = False) -> list:
    """An expression `name` of the face's own shape keys (`parts`: {name or pattern: weight}, see `resolve`), set by
    vrm.express like any of the file's: [(mesh object, shape key, weight)]."""
    keys = shape_keys(ch)
    binds = [(ob, k, w) for k, w in resolve(keys, parts).items() for ob in keys[k]]
    ch.expressions[name] = binds
    if binary:
        ch.binary.add(name)
    return binds


# ---------------------------------------------------------------------------------------------------- Blender: bones

def chains(ch: vrm.Character, pattern: str = VROID_HAIR) -> list[list[str]]:
    """The armature's chains of bones named like `pattern` (fnmatch), each root first then down its first children
    (a strand of hair does not branch)."""
    out = []
    for b in ch.armature.data.bones:
        if not fnmatch.fnmatchcase(b.name, pattern) or (b.parent and fnmatch.fnmatchcase(b.parent.name, pattern)):
            continue
        chain, c = [b.name], b
        while c.children:
            c = c.children[0]
            chain.append(c.name)
        out.append(chain)
    return out


def rest_point(ch: vrm.Character, bone: str, *, tail: bool = False) -> np.ndarray:
    """Any bone's head (or tail) at rest in the character's frame (vrm.Character.rest for the humanoid's)."""
    b = ch.armature.data.bones[bone]
    return ch.frame.T @ np.array(b.tail_local if tail else b.head_local) * ch.scale


def turn_of(rest, frame, local) -> np.ndarray:
    """The turn (3x3, about the character's axes: vrm.pose's convention) that a pose bone's local rotation `local`
    (3x3, the bone's own space) is, for a bone at rest orientation `rest` in a character of axes `frame`: what
    vrm.local_rotation undoes."""
    rest, frame = np.asarray(rest, float), np.asarray(frame, float)
    return frame.T @ rest @ np.asarray(local, float) @ rest.T @ frame


def release(ch: vrm.Character) -> dict:
    """Drop the IK and the holds a builder left on the character's limbs (vrm.reach, vrm.hold, vrm.grasp), each bone
    kept where they had it, and return that pose ({humanoid bone: 3x3 turn}, vrm.pose's convention) to key on top of:
    vrm.pose(ch, {**release(ch), **changes}, hips=...) (vrm.pose puts the hips back unless given them)."""
    import bpy

    bpy.context.view_layer.update()
    names = {b: h for h, b in ch.bones.items()}
    seen = [pb for pb in ch.armature.pose.bones if pb.name in names]
    held = {pb.name: pb.matrix.copy() for pb in seen}
    for pb in seen:
        for c in [c for c in pb.constraints if c.type in ("IK", "COPY_ROTATION")]:
            pb.constraints.remove(c)
    for pb in seen:                       # parents first, as the armature lists them
        pb.matrix = held[pb.name]
        bpy.context.view_layer.update()
    for e in ch.handles.values():
        bpy.data.objects.remove(e, do_unlink=True)
    ch.handles.clear()
    ch.bends.clear()
    out = {}
    for pb in seen:
        rest = np.array(ch.armature.data.bones[pb.name].matrix_local.to_3x3())
        out[names[pb.name]] = turn_of(rest, ch.frame, np.array(pb.matrix_basis.to_3x3()))
    return out


def turn_bones(ch: vrm.Character, turns: dict) -> None:
    """Pose bones by the armature's own names ({name: (x, y, z) degrees or a 3x3}, about the character's axes from
    rest, relative to the parent: vrm.pose's convention); the bones not named are left as they are."""
    from mathutils import Matrix

    for name, turn in turns.items():
        pb = ch.armature.pose.bones[name]
        rest = np.array(ch.armature.data.bones[name].matrix_local.to_3x3())
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = Matrix(vrm.local_rotation(rest, ch.frame, turn).tolist()).to_quaternion()


def sweep(ch: vrm.Character, chain: list[str], toward, degrees: float, *, root: float = 0.55) -> None:
    """Swing a chain of bones (a strand) by `degrees` toward `toward` (a direction in the character's frame), `root`
    of it at its first bone and the rest down it (`shares`): bent as a strand bends, not turned as a stick."""
    tip = rest_point(ch, chain[-1], tail=True) - rest_point(ch, chain[0])
    turn_bones(ch, {b: swing(tip, toward, degrees * s) for b, s in zip(chain, shares(len(chain), root))})


def thin(ch: vrm.Character, chain: list[str], width: float, length: float = 1.0) -> None:
    """A strand made `width` as wide and thick and `length` as long, from its root (the chain's first bone scaled; the
    rest of it follows)."""
    pb = ch.armature.pose.bones[chain[0]]
    pb.scale = (float(width), float(length), float(width))    # a bone's own y runs along it


def part(ch: vrm.Character, chains_: list[list[str]], degrees: float, *, at: float = 0.0, down: float = 0.0,
         root: float = 0.55) -> None:
    """Part strands off the middle of the face: each chain swept `degrees` away from the plane x = `at` (the
    character's middle) to its own side (its root's; its tip's when the root is on the plane), toward `down` of
    straight down as well (wet hair hangs)."""
    for chain in chains_:
        x = rest_point(ch, chain[0])[0] - at
        if abs(x) < 0.005:
            x = rest_point(ch, chain[-1], tail=True)[0] - at
        sweep(ch, chain, (math.copysign(1.0, x), 0.0, -down), degrees, root=root)


def wrap(ch: vrm.Character, side: str, radius: float, *, depth: float = 0.028, reach: float = 0.85,
         fingers=("Index", "Middle", "Ring", "Little"), slack: float = 0.006, thumb: float = 0.6) -> dict:
    """The fingers of a hand closed round a grip `radius` thick (metres) that runs along its knuckles through the fist's
    hole where vrm.grasp puts it (`reach` of the way from the wrist to the middle knuckle, `depth` out from the palm):
    each finger curled in its own plane until each joint lies on the grip, `slack` off it (a finger's half thickness),
    the thumb across them as vrm.grip_pose has it. Pass the same `depth` as the grasp; returns the fingers' pose."""
    k0, p0, r0 = vrm.hand_rest(ch, side)
    wrist = ch.rest(f"{side}Hand")
    hole = wrist + r0 * reach + p0 * depth
    out = {k: v for k, v in vrm.grip_pose(side, 1.0, thumb).items() if "Thumb" in k}
    for finger in fingers:
        names = [f"{side}{finger}{j}" for j in _JOINTS[finger]]
        if not all(ch.has(n) for n in names):
            continue
        pts = [ch.rest(n) for n in names] + [ch.rest(names[-1], tail=True)]
        # the finger's plane of bending: out along it, toward the palm; square to the knuckles (the grip's run)
        out_ = pts[-1] - pts[0]
        out_ = out_ - k0 * np.dot(out_, k0)
        out_ /= np.linalg.norm(out_)
        palm = np.cross(k0, out_)
        palm *= math.copysign(1.0, np.dot(palm, p0))
        flat = [((q - hole) @ out_, (q - hole) @ palm) for q in pts]
        turns = curl_to_round(flat, (0.0, 0.0), radius + slack)
        axis = np.cross(out_, palm)       # turning about it takes out_ toward the palm
        for n, deg in zip(names, turns):
            out[n] = rotation(axis, deg)
    return out


# ---------------------------------------------------------------------------------------------------- Blender: meshes

def faces_of(ob, which: str) -> np.ndarray:
    """The polygons of `ob` whose material's name has `which` in it ("Bottoms", "Tops") or is of that vrm.kind
    ("cloth", "skin")."""
    idx = [i for i, slot in enumerate(ob.material_slots) if slot.material is not None
           and (which.lower() in slot.material.name.lower() or vrm.kind(slot.material.name) == which.lower())]
    mi = np.empty(len(ob.data.polygons), np.int32)
    ob.data.polygons.foreach_get("material_index", mi)
    return np.flatnonzero(np.isin(mi, idx))


def _to_frame(ch: vrm.Character, ob) -> tuple[np.ndarray, np.ndarray]:
    """(the mesh's rest vertices in the character's frame, the 4x4 from the mesh's space to the armature's)."""
    me = ob.data
    co = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", co)
    m = np.array(ch.armature.matrix_world.inverted() @ ob.matrix_world)
    arm = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
    return arm @ ch.frame * ch.scale, m


def _from_frame(ch: vrm.Character, ob, points, m) -> None:
    arm = (np.asarray(points, float) / ch.scale) @ ch.frame.T
    co = (arm - m[:3, 3]) @ np.linalg.inv(m[:3, :3]).T
    ob.data.vertices.foreach_set("co", co.astype(np.float32).ravel())
    ob.data.update()


def face_centers(ch: vrm.Character, ob) -> np.ndarray:
    """Each polygon's middle at rest, in the character's frame."""
    pts, _ = _to_frame(ch, ob)
    return np.array([pts[list(p.vertices)].mean(0) for p in ob.data.polygons])


def lengthen(ch: vrm.Character, ob, faces, top: float, bottom: float, *, flare: float = 0.0, center=None) -> None:
    """Let a garment's hem down: the vertices of `faces` below `top` stretched so the lowest come to `bottom` (heights
    in the character's frame, at rest), flared `flare` wider at the hem about `center` (x, y; the garment's middle at
    `top` when not given). Before posing: the vertices keep their weights, so the hem follows the shins."""
    pts, m = _to_frame(ch, ob)
    vs = np.unique(np.concatenate([list(ob.data.polygons[i].vertices) for i in faces]))
    sel = pts[vs]
    if center is None:
        near = sel[np.abs(sel[:, 2] - top) < 0.05]
        center = near[:, :2].mean(0) if len(near) else sel[:, :2].mean(0)
    pts[vs] = stretch(sel, top, bottom, flare=flare, center=center)
    _from_frame(ch, ob, pts, m)


# a limb cinch can take cloth in round: (the bones its segment runs between at rest, the bones that carry it)
LIMBS = {"arm": (("UpperArm", "Hand"), ("UpperArm", "LowerArm", "Hand")),
         "thigh": (("UpperLeg", "LowerLeg"), ("UpperLeg",)),
         "shin": (("LowerLeg", "Foot"), ("LowerLeg", "Foot")),
         "leg": (("UpperLeg", "Foot"), ("UpperLeg", "LowerLeg", "Foot"))}


def cinch(ch: vrm.Character, ob, faces, side: str, radius: float, *, keep: float = 0.25, ease: float = 0.3,
          limb: str = "arm", relax: int = 0) -> None:
    """A sleeve's volume taken in (cinch_points): the vertices of `faces` the `side` arm ("left", "right") carries,
    from the upper arm to the wrist at rest, pulled in to `radius` (metres) of it, keeping `keep` of the rest. `limb`
    "thigh", "shin" or "leg" (hip to ankle) does the same round a leg's (a long skirt handed to the legs: shift_weights); `side` "both" takes
    in what the two sides carry together (the cloth between the knees, held half by each) round the line midway
    between them. Before posing: the vertices keep their weights, so the cloth follows the limb, no longer a bell
    hanging off it. `relax` irons the pulled-in cloth that many times (relax_points), its crumpled folds smoothed."""
    pts, m = _to_frame(ch, ob)
    vs = np.unique(np.concatenate([list(ob.data.polygons[int(i)].vertices) for i in faces]))
    (top, end), carry = LIMBS[limb]
    sides = ("left", "right") if side == "both" else (side,)
    a = np.mean([ch.rest(f"{sd}{top}") for sd in sides], axis=0)
    b = np.mean([ch.rest(f"{sd}{end}") for sd in sides], axis=0)
    # how much of each vertex each side carries (its weights on that side's bones)
    held = []
    for sd in sides:
        names = {ch.bones[vrm.canonical(f"{sd}{bone}")] for bone in carry}
        groups = {g.index for g in ob.vertex_groups if g.name in names}
        held.append(np.array([sum(g.weight for g in ob.data.vertices[int(v)].groups if g.group in groups) for v in vs]))
    if side == "both":
        keep_v = (held[0] > 0.2) & (held[1] > 0.2) & (np.maximum(held[0], held[1]) <= 0.5)
    else:
        s = 1.0 if side == "left" else -1.0
        # on its side, mostly its own: not a long robe's skirt off an arm, nor the cloth the two legs share
        keep_v = (held[0] > 0.5) & (pts[vs, 0] * s > (abs(a[0]) if limb == "arm" else 0.0))
    vs = vs[keep_v]
    pts[vs] = cinch_points(pts[vs], a, b, radius, keep=keep, ease=ease)
    if relax:
        edges = np.empty(len(ob.data.edges) * 2, int)
        ob.data.edges.foreach_get("vertices", edges)
        edges = edges.reshape(-1, 2)
        inside = np.zeros(len(pts), bool)
        inside[vs] = True
        before = _off_axis(pts[vs], a, b)
        # the cloth's edge where it joins the rest (a sleeve at the shoulder) stays put, so no seam opens
        rim = np.unique(edges[inside[edges[:, 0]] != inside[edges[:, 1]]])
        free = np.setdiff1d(vs, rim)
        pts = relax_points(pts, edges[inside[edges[:, 0]] & inside[edges[:, 1]]], free, iterations=relax)
        # ironing a tube shrinks it: back out to its girth (each point off the limb's line by the same share)
        after = _off_axis(pts[vs], a, b)
        grow = np.median(np.linalg.norm(before, axis=1)) / max(np.median(np.linalg.norm(after, axis=1)), 1e-9)
        pts[free] += _off_axis(pts[free], a, b) * (grow - 1.0)
    _from_frame(ch, ob, pts, m)


def _bone_name(ch: vrm.Character, name: str) -> str:
    """The armature's bone a humanoid name is, or the name itself (already the armature's)."""
    try:
        return ch.bones.get(vrm.canonical(name), name)
    except KeyError:
        return name


def shift_weights(ch: vrm.Character, ob, faces, below: float, band: float, moves: dict) -> int:
    """Hand the weight of some vertices from one bone to another ({from: to}, humanoid names or the armature's own,
    e.g. a thigh's to its shin): those of `faces` lower than `below` (metres, the character's frame at rest) fully, eased to none over
    `band` above it. A long robe's skirt seated: below the knees it then hangs from the shins, not jutting on from the
    thighs. Returns how many vertices changed."""
    pts, _ = _to_frame(ch, ob)
    vs = np.unique(np.concatenate([list(ob.data.polygons[int(i)].vertices) for i in faces]))
    k = np.clip((below + band - pts[vs, 2]) / max(band, 1e-6), 0.0, 1.0)
    k = k * k * (3 - 2 * k)
    groups = {}
    for a, b in moves.items():
        ga, gb = _bone_name(ch, a), _bone_name(ch, b)
        if ga in ob.vertex_groups:
            groups[ob.vertex_groups[ga].index] = ob.vertex_groups.get(gb) or ob.vertex_groups.new(name=gb)
    n = 0
    for v, kv in zip(vs, k):
        if kv <= 0.0:
            continue
        for g in list(ob.data.vertices[int(v)].groups):
            to = groups.get(g.group)
            if to is not None and g.weight > 0.0:
                w = g.weight * float(kv)
                ob.vertex_groups[g.group].add([int(v)], g.weight - w, "REPLACE")
                to.add([int(v)], w, "ADD")
                n += 1
    return n


def cut(ob, faces) -> int:
    """Delete `faces` (polygon indices) from a mesh without shape keys, and the vertices only they used; returns how
    many went."""
    import bmesh

    if ob.data.shape_keys is not None:
        raise ValueError(f"{ob.name}: cutting a mesh with shape keys would break them")
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    gone = [bm.faces[i] for i in sorted(set(int(i) for i in faces))]
    bmesh.ops.delete(bm, geom=gone, context="FACES_ONLY")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    return len(gone)


def _uv_triangles(ob, faces) -> np.ndarray:
    me = ob.data
    uv = me.uv_layers.active.data
    tris = []
    for i in faces:
        loops = list(me.polygons[int(i)].loop_indices)
        for k in range(1, len(loops) - 1):
            tris.append([uv[loops[0]].uv[:], uv[loops[k]].uv[:], uv[loops[k + 1]].uv[:]])
    return np.array(tris, float).reshape(-1, 3, 2)


def _base_image(mat):
    return mat.vrm_addon_extension.mtoon1.pbr_metallic_roughness.base_color_texture.index.source


def _textures(mat) -> list:
    mt = mat.vrm_addon_extension.mtoon1
    return [mt.pbr_metallic_roughness.base_color_texture, mt.extensions.vrmc_materials_mtoon.shade_multiply_texture]


def _own_image(mat, suffix: str):
    """The material's lit texture as an image of its own (a copy, packed, put on the lit and shade sides where they had
    the same one), so painting it leaves every other material's alone."""
    src = _base_image(mat)
    if src.name.endswith(suffix):
        return src
    img = src.copy()
    img.name = f"{src.name}{suffix}"
    img.pack()
    for info in _textures(mat):
        if info.index.source in (src, None) or info.index.source.name == src.name:
            info.index.source = img
    return img


def _pixels(img) -> np.ndarray:
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(h, w, 4)


def _store(img, px) -> None:
    img.pixels.foreach_set(np.asarray(px, np.float32).ravel())
    img.pack()


def sample(ob, faces, mat=None) -> tuple:
    """The median colour (RGB, as the texture stores it) of the lit texture under `faces` (of `mat`, default the
    first face's material)."""
    mat = mat or ob.material_slots[ob.data.polygons[int(faces[0])].material_index].material
    img = _base_image(mat)
    px = _pixels(img)
    mask = raster(_uv_triangles(ob, faces), img.size[0], img.size[1])
    return tuple(float(v) for v in np.median(px[mask][:, :3], axis=0))


def paint(ob, faces, color, *, mat=None, grow: int = 2) -> None:
    """Colour the texels of the lit (and shade) texture under `faces` `color` (RGB as the texture stores it, sRGB for
    VRoid's), on a copy of the texture its material takes for its own."""
    mat = mat or ob.material_slots[ob.data.polygons[int(faces[0])].material_index].material
    img = _own_image(mat, "-painted")
    px = _pixels(img)
    mask = raster(_uv_triangles(ob, faces), img.size[0], img.size[1], grow=grow)
    px[mask, :3] = np.asarray(color, np.float32)[:3]
    _store(img, px)


def recolor(mat, lit, shade, *, keep: float = 0.3, blur: float = 0.02, opaque: bool = False, outline=None) -> None:
    """One colour for a garment: its lit and shade textures made one grey of their own light and dark (`flatten`:
    a print or a plaid gone, the folds kept by `keep`; `opaque` fills its cut-outs, a cuff's zigzag), its MToon lit
    colour `lit` and shade colour `shade` (linear), and its outline's colour `outline` when given (VRoid's warm brown
    suits the colours it came in; seen from inside a cut garment the outline's hull shows as a patch of it)."""
    src = _base_image(mat)
    img = src.copy()
    img.name = f"{src.name}-flat"
    _store(img, flatten(_pixels(src), keep=keep, blur=blur, opaque=opaque))
    for info in _textures(mat):
        info.index.source = img
    mt = mat.vrm_addon_extension.mtoon1
    mt.pbr_metallic_roughness.base_color_factor = (*(float(c) for c in lit[:3]), 1.0)
    mt.extensions.vrmc_materials_mtoon.shade_color_factor = tuple(float(c) for c in shade[:3])
    if outline is not None:
        mt.extensions.vrmc_materials_mtoon.outline_color_factor = tuple(float(c) for c in outline[:3])


def _surface(ch: vrm.Character, ob, faces):
    """A BVH of `faces` of `ob` at rest, in the character's frame."""
    from mathutils.bvhtree import BVHTree

    pts, _ = _to_frame(ch, ob)
    polys = [tuple(ob.data.polygons[int(i)].vertices) for i in faces]
    return BVHTree.FromPolygons([tuple(p) for p in pts], polys)


def collar(ch: vrm.Character, name: str, path, width, *, on, material=None, coll=None, push: float = 0.004,
           thickness: float = 0.004, shift=0.0, n: int = 40, smooth: int = 4):
    """A band laid on the body along `path` (points in the character's frame, at rest, near the surface): a kimono's
    collar from the back of the neck down across the chest. Each point is put on the nearest of `on` ([(mesh, faces)]),
    `push` off it, the band `width` across (one, or one per point of `path`) and `thickness` thick, lying flat on it
    (its points and normals eased over `smooth` passes: a stiff collar bridges a cloth's lumps), moved `shift` across
    itself (one, or one per point; + to its left as it runs, seen from outside: a lining's edge along a collar's). It
    deforms with the clothes under it (`skin_like`). Returns the object."""
    from mathutils import Vector

    from . import shapes

    trees = [_surface(ch, ob, faces) for ob, faces in on]
    pts, nrms = [], []
    width, shift = along(path, width, n), along(path, shift, n)
    for q in resample(path, n):
        hits = [t.find_nearest(Vector(q)) for t in trees]
        loc, nrm, _, _ = min((h for h in hits if h[0] is not None), key=lambda h: h[3])
        pts.append(np.array(loc))
        nrms.append(np.array(nrm))
    pts, nrms = np.array(pts), np.array(nrms)
    for _ in range(smooth):      # a cloth's lumps under it smoothed over, as a stiff collar lies
        pts[1:-1] = (pts[:-2] + 2 * pts[1:-1] + pts[2:]) / 4
        nrms[1:-1] = (nrms[:-2] + 2 * nrms[1:-1] + nrms[2:]) / 4
    nrms /= np.linalg.norm(nrms, axis=1, keepdims=True)
    if np.any(shift):
        across = np.cross(nrms, np.gradient(pts, axis=0))
        pts = pts + across / np.linalg.norm(across, axis=1, keepdims=True) * np.reshape(shift, (-1, 1))
    verts, faces = ribbon(pts + nrms * push, nrms, width, thickness)
    arm = (verts / ch.scale) @ ch.frame.T
    ob = shapes.mesh_object(name, arm, faces, material=material, coll=coll or ch.coll)
    ob.parent = ch.armature
    ob.matrix_parent_inverse.identity()
    ob.matrix_basis.identity()
    skin_like(ob, ch, list({m.name: m for m, _ in on}.values()))
    return ob


def skin_like(ob, ch: vrm.Character, sources) -> None:
    """Make `ob` (a child of the character's armature, its vertices in the armature's space at rest) deform with the
    meshes `sources`: each vertex takes the bone weights of the nearest of theirs."""
    import bpy
    from mathutils import Vector
    from mathutils.kdtree import KDTree

    bpy.context.view_layer.update()
    owners = []
    for src in sources:
        pts, _ = _to_frame(ch, src)
        owners += [(src, i, p) for i, p in enumerate(pts)]
    tree = KDTree(len(owners))
    for k, (_, _, p) in enumerate(owners):
        tree.insert(Vector(p), k)
    tree.balance()
    mine, _ = _to_frame(ch, ob)
    groups = {}
    for vi, p in enumerate(mine):
        _, k, _ = tree.find(Vector(p))
        src, i, _ = owners[k]
        for g in src.data.vertices[i].groups:
            gname = src.vertex_groups[g.group].name
            if gname not in groups:
                groups[gname] = ob.vertex_groups.get(gname) or ob.vertex_groups.new(name=gname)
            groups[gname].add([vi], g.weight, "REPLACE")
    md = ob.modifiers.new("armature", "ARMATURE")
    md.object = ch.armature
