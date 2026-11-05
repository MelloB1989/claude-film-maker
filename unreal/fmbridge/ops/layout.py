"""Layout and set dressing: rest things on what is under them, place one actor relative to another, lay out rows,
grids, circles and seeded scatters of an asset, align and distribute. Every op converges: re-running it with the
same arguments moves the same actors to the same places (patterns own their actors by label prefix and tag, and
remove the extras when the count shrinks).

Placement uses actor bounds (axis-aligned boxes): exact for boxy props, conservative for round ones. `mode="trace"`
on layout.drop asks the physics scene instead (needs collision on the support).
"""
from __future__ import annotations

import time

import unreal

from . import _layout as L
from . import op
from ..errors import OpError
from ._util import actor, actor_info, actors, bounds_box, eas, find_actor, set_tags, vec
from ._util import visibility_channel as _visibility_channel  # noqa: F401 (foliage imports it from here)
from ._util import tags as actor_tags
from .assets import load
from .level import SHAPES


def _move_by(a, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> bool:
    if abs(dx) < 1e-4 and abs(dy) < 1e-4 and abs(dz) < 1e-4:
        return False
    p = a.get_actor_location()
    a.set_actor_location(unreal.Vector(p.x + dx, p.y + dy, p.z + dz), False, False)
    return True


def _supports(exclude: set) -> list:
    """Boxes of everything that can hold something up: mesh actors other than `exclude`."""
    out = []
    for a in actors():
        if a.get_actor_label() in exclude or not isinstance(a, (unreal.StaticMeshActor, unreal.SkeletalMeshActor)):
            continue
        out.append(bounds_box(a))
    return out


def _trace_down(a, depth: float) -> float | None:
    """Z of the first blocking surface under the actor's bounds centre (Visibility channel), ignoring itself."""
    b = bounds_box(a)
    c = L.box_center(b)
    start = unreal.Vector(c[0], c[1], b[0][2] - 0.1)
    end = unreal.Vector(c[0], c[1], b[0][2] - depth)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    hit = unreal.SystemLibrary.line_trace_single(world, start, end, _visibility_channel(), True,
                                                 [a], unreal.DrawDebugTrace.NONE, True)
    if not hit:
        return None
    t = hit.to_tuple()  # GameplayStatics::BreakHitResult order: blocking_hit, initial_overlap, time, distance, location, impact_point, ...
    return t[5].z if t[0] else None


@op("layout.drop", mutates=True, idempotent=True)
def drop(*, labels: list, floor_z: float = 0.0, gap_cm: float = 0.0, mode: str = "bounds",
         trace_depth_cm: float = 10000.0) -> dict:
    """Rest each actor on whatever is under it: its bounds' bottom on the highest support below its centre whose
    footprint overlaps (a table top, a rug, a riser), else on `floor_z`. Actors are dropped in the order given, so
    list a table before the cup that sits on it.

    Args: labels: actors to drop. floor_z: the floor height in cm (None for no floor: an actor over nothing stays
    put). gap_cm: lift above the support. mode: bounds (boxes, deterministic) or trace (a line trace down; needs
    collision).
    Returns: {"changed": bool, "moved": {label: dz_cm}, "unsupported": [labels with nothing under them]}.
    Example: film-ue op layout.drop 'labels=["Desk","Lamp","Mug"]'
    """
    return _drop(labels, floor_z, gap_cm, mode, trace_depth_cm)


def _drop(labels, floor_z=0.0, gap_cm=0.0, mode="bounds", trace_depth_cm=10000.0) -> dict:
    if mode not in ("bounds", "trace"):
        raise OpError(f"mode must be bounds or trace, not {mode!r}", code="bad_args")
    targets = [actor(lab) for lab in labels]
    moved, unsupported = {}, []
    for a in targets:
        lab = a.get_actor_label()
        b = bounds_box(a)
        if mode == "trace":
            z = _trace_down(a, trace_depth_cm)
            if z is None and floor_z is not None:
                z = floor_z
            dz = None if z is None else z + gap_cm - b[0][2]
        else:
            dz = L.rest_z(b, _supports({lab}), floor_z, gap_cm)
        if dz is None:
            unsupported.append(lab)
            continue
        if _move_by(a, dz=dz):
            moved[lab] = round(dz, 3)
    return {"changed": bool(moved), "moved": moved, "unsupported": unsupported}


@op("layout.relative", mutates=True, idempotent=True)
def relative(*, label: str, of: str, offset_cm: list = (100, 0, 0), face: str = "toward", yaw_deg: float = 0.0,
             drop: bool = True, floor_z: float = 0.0) -> dict:
    """Put `label` at an offset in another actor's frame: [forward, right, up] cm from `of` along its own yaw (a
    chair 80 cm in front of a desk: offset_cm=[80, 0, 0]), then turn it and rest it on what is under it.

    Args: face: toward (look at `of`), away, same (copy its yaw), none (keep), or fixed (use yaw_deg).
    Returns: {"changed", "loc", "rot"}.
    Example: film-ue op layout.relative label=Chair of=Desk 'offset_cm=[80,0,0]' face=toward
    """
    a, ref = actor(label), actor(of)
    if face not in ("toward", "away", "same", "none", "fixed"):
        raise OpError(f"face must be toward|away|same|none|fixed, not {face!r}", code="bad_args")
    o, r = ref.get_actor_location(), ref.get_actor_rotation()
    p = L.local_to_world([o.x, o.y, o.z], r.yaw, list(offset_cm))
    before = (a.get_actor_location(), a.get_actor_rotation())
    a.set_actor_location(unreal.Vector(*p), False, False)
    yaw = {"toward": L.yaw_to(p, [o.x, o.y]), "away": L.yaw_to([o.x, o.y], p), "same": r.yaw,
           "fixed": yaw_deg}.get(face)
    if yaw is not None:
        cur = a.get_actor_rotation()
        a.set_actor_rotation(unreal.Rotator(roll=cur.roll, pitch=cur.pitch, yaw=yaw), False)
    if drop:
        dz = L.rest_z(bounds_box(a), _supports({label}), floor_z)
        if dz is not None:
            _move_by(a, dz=dz)
    after = (a.get_actor_location(), a.get_actor_rotation())
    changed = not (before[0].is_near_equal(after[0], 0.01) and before[1].is_near_equal(after[1], 0.01))
    info = actor_info(a)
    return {"changed": changed, "loc": info["loc"], "rot": info["rot"]}


def _owned(prefix: str) -> list:
    t = f"fm.layout:{prefix}"
    return [a for a in actors() if t in actor_tags(a)]


def _converge(prefix: str, points: list, yaws: list, asset: str, shape: str, scale, material: str, extra_tags,
              folder: str, keep_z: bool) -> dict:
    """Make actors prefix_00.. at `points` (one per point), reusing those already there; remove the rest of this
    pattern's actors."""
    src = SHAPES.get(shape) if shape else asset
    if not src:
        raise OpError("give an asset (/Game/...) or a shape (cube|sphere|cylinder|cone|plane)", code="bad_args")
    mesh = load(src)
    want = {L.numbered(prefix, k, len(points)): (p, y) for k, (p, y) in enumerate(zip(points, yaws))}
    made, moved, removed = [], [], []
    owner_tag = f"fm.layout:{prefix}"
    for a in _owned(prefix):
        if a.get_actor_label() not in want:
            removed.append(a.get_actor_label())
            eas().destroy_actor(a)
    for lab, (p, yaw) in want.items():
        a = find_actor(lab)
        loc = unreal.Vector(*p)
        r = unreal.Rotator(roll=0.0, pitch=0.0, yaw=float(yaw))
        if a is None:
            a = eas().spawn_actor_from_object(mesh, loc, r)
            if a is None:
                raise OpError(f"the engine did not spawn {src}", code="engine")
            a.set_actor_label(lab)
            made.append(lab)
        else:
            if keep_z:
                loc = unreal.Vector(p[0], p[1], a.get_actor_location().z)
            if not (a.get_actor_location().is_near_equal(loc, 0.01) and a.get_actor_rotation().is_near_equal(r, 0.01)):
                a.set_actor_location(loc, False, False)
                a.set_actor_rotation(r, False)
                moved.append(lab)
        if scale is not None:
            s = vec(scale)
            if not a.get_actor_scale3d().is_near_equal(s, 1e-4):
                a.set_actor_scale3d(s)
                if lab not in made and lab not in moved:
                    moved.append(lab)
        want_tags = [owner_tag, *extra_tags]
        old = actor_tags(a)
        if any(t not in old for t in want_tags):
            set_tags(a, old + [t for t in want_tags if t not in old])
        if material:
            for c in a.get_components_by_class(unreal.StaticMeshComponent):
                c.set_material(0, load(material))
        if folder:
            a.set_folder_path(folder)
    return {"changed": bool(made or moved or removed), "labels": list(want), "made": made, "moved": moved,
            "removed": removed}


@op("layout.array", mutates=True, idempotent=True)
def array(*, prefix: str, asset: str = "", shape: str = "", pattern: str = "row", count: int = 3,
          start: list = (0, 0, 0), step_cm: list = (100, 0, 0), cols: int = 3, center: list = (0, 0, 0),
          radius_cm: float = 300.0, start_deg: float = 0.0, arc_deg: float = 360.0, face: str = "none",
          yaw_deg: float = 0.0, scale=None, material: str = "", tags: list = (), folder: str = "",
          drop: bool = False, floor_z: float = 0.0) -> dict:
    """Lay out `count` copies of an asset (or a basic shape) as a row, a grid or a circle, labelled
    `<prefix>_00`, `<prefix>_01`, ...; re-running moves the same actors, and a smaller count removes the extras.

    Args: pattern: row (start + k * step_cm), grid (rows of `cols`, X by step_cm[0], Y by step_cm[1]) or circle
    (around `center`, radius_cm, from start_deg over arc_deg, counter-clockwise from above). face: none (yaw_deg),
    center (circle: each faces the centre), out (faces away). drop: rest each on what is under it.
    Returns: {"changed", "labels", "made", "moved", "removed"}.
    Example: film-ue op layout.array prefix=Chair asset=/Game/Props/SM_Chair pattern=circle count=6 \\
             'center=[0,0,0]' radius_cm=120 face=center
    """
    if pattern not in ("row", "grid", "circle"):
        raise OpError(f"pattern must be row|grid|circle, not {pattern!r}", code="bad_args")
    if count < 0:
        raise OpError("count must be >= 0", code="bad_args")
    if pattern == "row":
        pts = L.row(count, list(start), list(step_cm))
    elif pattern == "grid":
        pts = L.grid(count, list(start), list(step_cm), cols)
    else:
        pts = L.circle(count, list(center), radius_cm, start_deg, arc_deg)
    if face == "center":
        yaws = [L.yaw_to(p, center) for p in pts]
    elif face == "out":
        yaws = [L.yaw_to(center, p) for p in pts]
    elif face == "none":
        yaws = [yaw_deg] * len(pts)
    else:
        raise OpError(f"face must be none|center|out, not {face!r}", code="bad_args")
    res = _converge(prefix, pts, yaws, asset, shape, scale, material, list(tags), folder, keep_z=drop)
    if drop and res["labels"]:
        d = _drop(res["labels"], floor_z)
        res["changed"] = res["changed"] or d["changed"]
    return res


@op("layout.scatter", mutates=True, idempotent=True)
def scatter(*, prefix: str, asset: str = "", shape: str = "", count: int = 10, region: list = ((-500, -500), (500, 500)),
            min_dist_cm: float = 100.0, seed: int = 0, z: float = 0.0, exclude: list = (), avoid: list = (),
            yaw_range_deg: list = (0, 360), scale_range: list = (1, 1), material: str = "", tags: list = (),
            folder: str = "", drop: bool = True, floor_z: float = 0.0) -> dict:
    """Scatter up to `count` copies of an asset over a rectangle, no two closer than min_dist_cm, deterministic for
    a seed (Poisson disk), with random yaw and uniform scale in ranges; labelled `<prefix>_00`...; re-running with
    the same seed gives the same layout, a new seed a new one.

    Args: region: [[x0, y0], [x1, y1]] cm. exclude: rectangles to keep clear ([[x0, y0], [x1, y1]] each). avoid:
    actor labels whose footprints (plus min_dist_cm / 2) are kept clear. z: height before dropping. drop: rest each
    on what is under it.
    Returns: {"changed", "labels", "made", "moved", "removed", "placed": n} (n < count when the region is full).
    Example: film-ue op layout.scatter prefix=Rock asset=/Game/Env/SM_Rock count=30 \\
             'region=[[-1000,-1000],[1000,1000]]' min_dist_cm=150 seed=7 'avoid=["Path"]'
    """
    rects = [[list(e[0]), list(e[1])] for e in exclude]
    pad = min_dist_cm / 2
    for lab in avoid:
        b = bounds_box(actor(lab))
        rects.append([[b[0][0] - pad, b[0][1] - pad], [b[1][0] + pad, b[1][1] + pad]])
    pts2 = L.poisson(count, [list(region[0]), list(region[1])], min_dist_cm, seed, rects)
    pts = [[p[0], p[1], z] for p in pts2]
    yaws = L.jitter(len(pts), seed, float(yaw_range_deg[0]), float(yaw_range_deg[1]))
    scales = L.jitter(len(pts), seed + 1, float(scale_range[0]), float(scale_range[1]))
    res = _converge(prefix, pts, yaws, asset, shape, None, material, list(tags), folder, keep_z=drop)
    for lab, s in zip(res["labels"], scales):
        a = actor(lab)
        v = unreal.Vector(s, s, s)
        if not a.get_actor_scale3d().is_near_equal(v, 1e-4):
            a.set_actor_scale3d(v)
            res["changed"] = True
    if drop and res["labels"]:
        d = _drop(res["labels"], floor_z)
        res["changed"] = res["changed"] or d["changed"]
    res["placed"] = len(pts)
    return res


@op("layout.remove", mutates=True, idempotent=True)
def remove(*, prefix: str) -> dict:
    """Remove every actor a layout.array / layout.scatter with this prefix made (by its tag, not by name).

    Example: film-ue op layout.remove prefix=Rock
    """
    gone = []
    for a in _owned(prefix):
        gone.append(a.get_actor_label())
        eas().destroy_actor(a)
    return {"changed": bool(gone), "removed": gone}


@op("layout.align", mutates=True, idempotent=True)
def align(*, labels: list, axis: str = "x", to: str = "min", ref_cm: float = None, ref_label: str = "") -> dict:
    """Line actors up along one axis by their bounds: their min edges, max edges or centres on a common value
    (`ref_cm`, the same edge of `ref_label`, or the group's extreme / mean).

    Example: film-ue op layout.align 'labels=["Book_00","Book_01","Book_02"]' axis=y to=max
    """
    if axis not in ("x", "y", "z"):
        raise OpError(f"axis must be x|y|z, not {axis!r}", code="bad_args")
    acts = {lab: actor(lab) for lab in labels}
    boxes = {lab: bounds_box(a) for lab, a in acts.items()}
    if ref_label:
        rb = bounds_box(actor(ref_label))
        i = "xyz".index(axis)
        ref_cm = rb[0][i] if to == "min" else rb[1][i] if to == "max" else L.box_center(rb)[i]
    try:
        offs = L.align(boxes, axis, to, ref_cm)
    except ValueError as e:
        raise OpError(str(e), code="bad_args") from None
    moved = {}
    for lab, d in offs.items():
        kw = {"d" + axis: d}
        if _move_by(acts[lab], **kw):
            moved[lab] = round(d, 3)
    return {"changed": bool(moved), "moved": moved}


@op("layout.distribute", mutates=True, idempotent=True)
def distribute(*, labels: list, axis: str = "x", start_cm: float = None, end_cm: float = None,
               gap_cm: float = None) -> dict:
    """Space actors evenly along an axis, in the order given: centres from start_cm to end_cm (default: the first
    and last actors' current centres), or edge to edge `gap_cm` apart starting at the first one.

    Example: film-ue op layout.distribute 'labels=["A","B","C","D"]' axis=x gap_cm=20
    """
    if axis not in ("x", "y", "z"):
        raise OpError(f"axis must be x|y|z, not {axis!r}", code="bad_args")
    if len(labels) < 2:
        return {"changed": False, "moved": {}}
    acts = {lab: actor(lab) for lab in labels}
    offs = L.distribute({lab: bounds_box(a) for lab, a in acts.items()}, list(labels), axis, start_cm, end_cm, gap_cm)
    moved = {}
    for lab, d in offs.items():
        if _move_by(acts[lab], **{"d" + axis: d}):
            moved[lab] = round(d, 3)
    return {"changed": bool(moved), "moved": moved}


@op("layout.snap", mutates=True, idempotent=True)
def snap(*, labels: list, grid_cm: float = 10.0, yaw_step_deg: float = 0.0) -> dict:
    """Snap actor locations to a grid (X and Y; Z untouched) and, with yaw_step_deg, their yaw to multiples of it.

    Example: film-ue op layout.snap 'labels=["Desk","Chair"]' grid_cm=5 yaw_step_deg=15
    """
    moved = []
    for lab in labels:
        a = actor(lab)
        p = a.get_actor_location()
        q = unreal.Vector(L.snap(p.x, grid_cm), L.snap(p.y, grid_cm), p.z)
        r = a.get_actor_rotation()
        r2 = unreal.Rotator(roll=r.roll, pitch=r.pitch, yaw=L.snap(r.yaw, yaw_step_deg))
        if not (p.is_near_equal(q, 1e-3) and r.is_near_equal(r2, 1e-3)):
            a.set_actor_location(q, False, False)
            a.set_actor_rotation(r2, False)
            moved.append(lab)
    return {"changed": bool(moved), "moved": moved}


@op("layout.settle", mutates=True, idempotent=False, tags=["slow", "physics", "experimental"])
def settle(*, labels: list, seconds: float = 2.0, start_timeout_s: float = 60.0, keep_physics: bool = False):
    """Let props fall and come to rest under physics, then keep where they landed (a pile of books, a dropped
    cushion, a chair knocked over): runs Simulate in Editor for `seconds`, reads each actor's resting transform from
    the simulated world and writes it back onto the editor actor. Multi-tick. The actors' meshes need collision, and
    so does what they land on.

    Args: labels: actors to simulate (made Movable, physics on for the run; restored after unless keep_physics).
    seconds: simulated time to let them settle. start_timeout_s: how long to wait for Simulate to start.
    Returns: {"changed", "moved": {label: {"loc", "rot", "dist_cm"}}, "still": [labels that did not move > 0.5 cm]}.
    Example: film-ue op layout.settle 'labels=["Book_00","Book_01","Cushion"]' seconds=3
    """
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    if les.is_in_play_in_editor():
        raise OpError("a Play/Simulate session is already running", code="conflict",
                      hint="stop it first (editor.console 'Exit' or the level editor) and retry")
    acts = {lab: actor(lab) for lab in labels}
    saved = {}
    for lab, a in acts.items():
        comps = a.get_components_by_class(unreal.PrimitiveComponent)
        if not comps:
            raise OpError(f"{lab} has nothing physical to simulate", code="bad_args", hint="level.get shows its components")
        saved[lab] = [(c, c.get_editor_property("mobility"), c.is_simulating_physics()) for c in comps]
        for c in comps:
            c.set_mobility(unreal.ComponentMobility.MOVABLE)
            c.set_simulate_physics(True)
    before = {lab: (a.get_actor_location(), a.get_actor_rotation()) for lab, a in acts.items()}
    landed = {}
    try:
        les.editor_play_simulate()
        t0 = time.time()
        while ues.get_game_world() is None:
            if time.time() - t0 > start_timeout_s:
                raise OpError(f"Simulate did not start within {start_timeout_s:g}s", code="timeout",
                              hint="is the editor offscreen with no viewport? check film-ue log")
            yield 0.1
        world = ues.get_game_world()
        end = time.time() + float(seconds)
        while time.time() < end:
            yield
        for a in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor):
            lab = a.get_actor_label()
            if lab in acts:
                landed[lab] = (a.get_actor_location(), a.get_actor_rotation())
    finally:
        if les.is_in_play_in_editor():
            les.editor_request_end_play()
        for _ in range(600):  # until the play world is gone (a few frames)
            if not les.is_in_play_in_editor():
                break
            yield
        for lab, comps in saved.items():
            for c, mobility, sim in comps:
                c.set_simulate_physics(bool(sim) or keep_physics)
                if not keep_physics:
                    c.set_mobility(mobility)
    missing = sorted(set(acts) - set(landed))
    if missing:
        raise OpError(f"no simulated counterpart for {missing}", code="engine",
                      hint="their transforms are unchanged; is the actor editor-only or in a sublevel?")
    moved, still = {}, []
    for lab, (loc, rot) in landed.items():
        d = (loc - before[lab][0]).length()
        if d <= 0.5 and rot.is_near_equal(before[lab][1], 0.5):
            still.append(lab)
            continue
        acts[lab].set_actor_location(loc, False, True)
        acts[lab].set_actor_rotation(rot, True)
        moved[lab] = {"loc": [round(loc.x, 2), round(loc.y, 2), round(loc.z, 2)],
                      "rot": {"pitch": round(rot.pitch, 3), "yaw": round(rot.yaw, 3), "roll": round(rot.roll, 3)},
                      "dist_cm": round(d, 2)}
    return {"changed": bool(moved), "moved": moved, "still": still}
