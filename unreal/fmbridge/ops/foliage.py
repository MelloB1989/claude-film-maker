"""Foliage by code: seeded scatters of meshes (grass, rocks, trees, litter) as foliage instances (one InstancedFoliage
actor draws them all as hierarchical instanced static meshes, never thousands of actors), placed on the ground by
line traces, converged per prefix + seed; and PCG graphs run with parameters and a seed on any actor with a PCG
component.

The maths (where, which mesh, yaw/scale/tilt) is ops/_foliage.py, pure. A scatter named `prefix` owns one foliage
type per mesh under /Game/_Foliage/<prefix>/ (FT_<prefix>_<i>_<mesh>); re-running it replaces exactly its own
instances (RemoveAllInstances on its types, then AddInstances), so it converges and never touches anyone else's.
Its arguments' hash, seed and instance counts are kept as asset metadata on its types (`foliage.describe`).
"""
from __future__ import annotations

import json

import unreal

from . import op
from . import _foliage as F
from ._util import actors, find_actor, vec
from ..errors import OpError, not_found

ROOT = "/Game/_Foliage"
from .assets import EAL  # EditorAssetLibrary, or the EditorAssetSubsystem when its plugin is off
TAG_HASH, TAG_ARGS, TAG_COUNT, TAG_MESH = "fm_scatter_hash", "fm_scatter_args", "fm_scatter_count", "fm_scatter_mesh"


def _world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def _folder(prefix: str) -> str:
    if not prefix or any(c in prefix for c in "/\\.: "):
        raise OpError(f"prefix {prefix!r}: letters, digits, _ or - (it names the scatter and its folder)",
                      code="bad_args")
    return f"{ROOT}/{prefix}"


def _types(prefix: str) -> list:
    """The foliage type assets of a scatter, by package path, in index order."""
    folder = _folder(prefix)
    if not EAL.does_directory_exist(folder):
        return []
    return sorted(p.split(".")[0] for p in EAL.list_assets(folder, False, False))


def _type_for(prefix: str, index: int, mesh: str, cull_cm=None, shadows: bool = True):
    """The foliage type of mesh `index`, made when missing (no dialog: a missing path is created, an existing one
    reused) and set to the mesh, culling and shadows. Returns (asset, path, made)."""
    path = f"{_folder(prefix)}/{F.asset_name(prefix, index, mesh)}"
    made = False
    if EAL.does_asset_exist(path):
        ft = EAL.load_asset(path)
    else:
        folder, name = path.rsplit("/", 1)
        ft = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name, folder, unreal.FoliageType_InstancedStaticMesh, unreal.FoliageType_InstancedStaticMeshFactory())
        if ft is None:
            raise OpError(f"the engine did not create the foliage type {path}", code="engine")
        made = True
    ft.set_editor_property("mesh", EAL.load_asset(mesh))
    if cull_cm is not None:
        ci = ft.get_editor_property("cull_distance")
        ci.set_editor_property("min", int(cull_cm[0]))
        ci.set_editor_property("max", int(cull_cm[1]))
        ft.set_editor_property("cull_distance", ci)
    ft.set_editor_property("cast_shadow", bool(shadows))
    return ft, path, made


def _footprints(labels: list, margin_cm: float) -> list:
    """Exclusion rectangles from actors' bounds (seen from above), grown by `margin_cm`."""
    out = []
    for lab in labels or []:
        a = find_actor(lab)
        if a is None:
            raise not_found("actor", lab, [x.get_actor_label() for x in actors()], hint="exclude_actors are labels")
        o, e = a.get_actor_bounds(False)
        out.append({"rect": [[o.x - e.x - margin_cm, o.y - e.y - margin_cm], [o.x + e.x + margin_cm,
                                                                               o.y + e.y + margin_cm]]})
    return out


def _ignore_list() -> list:
    """What traces must not hit: every foliage actor (other scatters' grass is not ground)."""
    return [a for a in actors() if isinstance(a, unreal.InstancedFoliageActor)]


def _trace(world, x: float, y: float, z_from: float, z_to: float, ignore: list, channel=None):
    """(z, normal) of the first blocking surface straight down at (x, y), or None. `channel`: the Visibility trace
    channel (layout._visibility_channel: ECC_VISIBILITY live, TRACE_TYPE_QUERY1 only as a deprecated alias)."""
    if channel is None:
        from .layout import _visibility_channel
        channel = _visibility_channel()
    hit = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x, y, z_from), unreal.Vector(x, y, z_to),
                                                 channel, True, ignore,
                                                 unreal.DrawDebugTrace.NONE, True)
    if not hit:
        return None
    t = hit.to_tuple()  # BreakHitResult order: blocking_hit, initial_overlap, time, distance, location, impact_point,
    if not t[0]:        # normal, impact_normal, ...
        return None
    p, n = t[5], t[7]
    return p.z, (n.x, n.y, n.z)


def measured() -> dict:
    """Foliage instances in the level now, per static mesh path: {mesh: count} (all InstancedFoliage actors)."""
    out: dict = {}
    for a in actors():
        if not isinstance(a, unreal.InstancedFoliageActor):
            continue
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            m = c.get_editor_property("static_mesh")
            if m is None:
                continue
            k = m.get_path_name().split(".")[0]
            out[k] = out.get(k, 0) + int(c.get_instance_count())
    return out


def _state(prefix: str) -> dict:
    types = _types(prefix)
    if not types:
        return {}
    first = EAL.load_asset(types[0])
    args = EAL.get_metadata_tag(first, TAG_ARGS) or ""
    per = []
    for t in types:
        ft = EAL.load_asset(t)
        per.append({"type": t, "mesh": EAL.get_metadata_tag(ft, TAG_MESH),
                    "count": int(EAL.get_metadata_tag(ft, TAG_COUNT) or 0)})
    return {"prefix": prefix, "hash": EAL.get_metadata_tag(first, TAG_HASH), "args": json.loads(args) if args else None,
            "types": per, "count": sum(p["count"] for p in per)}


@op("foliage.scatter", mutates=True, idempotent=True, tags=["layout", "foliage"])
def scatter(*, prefix: str, meshes: list, region: dict, seed: int = 0, count: int | None = None,
            density_per_m2: float | None = None, min_dist_cm: float | None = None, exclude: list | None = None,
            exclude_actors: list | None = None, exclude_margin_cm: float = 30.0, patchiness: float = 0.0,
            patch_cm: float = 400.0, surface: str = "trace", z_cm: float = 0.0, trace_from_z_cm: float = 10000.0,
            trace_to_z_cm: float = -10000.0, max_slope_deg: float = 90.0, cull_cm: list | None = None,
            shadows: bool = True, force: bool = False, dry_run: bool = False):
    """Scatter meshes over a region as foliage instances, the same for the same seed; re-running converges (the
    scatter's own instances are replaced; nothing else is touched).

    Args: prefix: the scatter's name (its foliage types live in /Game/_Foliage/<prefix>/). meshes: [{"mesh":
    "/Game/...", "weight": 1, "scale": [lo, hi], "height_jitter": [lo, hi], "tilt_deg": 0, "yaw": "random" | [lo, hi]
    | deg, "z_offset_cm": 0, "align_to_normal": false}]. region: {"rect": [[x0, y0], [x1, y1]]} | {"circle": [cx, cy,
    r]} | {"ring": [cx, cy, r0, r1]} | {"polygon": [[x, y], ...]} (cm). count, or density_per_m2. min_dist_cm:
    spacing (default from the density). exclude: regions to keep clear; exclude_actors: labels whose footprints
    (plus exclude_margin_cm) stay clear. patchiness 0..1 with patch_cm: clumps. surface: "trace" (drop onto what is
    below, between trace_from_z_cm and trace_to_z_cm; instances over nothing or steeper than max_slope_deg are
    dropped) or "flat" (at z_cm). cull_cm: [start, end] distance culling. force: rewrite even when unchanged.
    A multi-tick job (traces yield every 500).
    Returns: {"prefix", "changed", "placed", "planned", "dropped": {"no_ground", "too_steep"}, "per_mesh",
    "types", "hash", "area_m2"}.
    Example: film-ue op foliage.scatter prefix=Lawn seed=7 'meshes=[{"mesh":"/Game/Env/SM_Grass","scale":[0.8,1.2]}]' 'region={"rect":[[-1000,-1000],[1000,1000]]}' density_per_m2=4
    """
    args = {"meshes": meshes, "region": region, "seed": int(seed), "count": count, "density_per_m2": density_per_m2,
            "min_dist_cm": min_dist_cm, "exclude": exclude or [], "exclude_actors": exclude_actors or [],
            "exclude_margin_cm": exclude_margin_cm, "patchiness": patchiness, "patch_cm": patch_cm,
            "surface": surface, "z_cm": z_cm, "trace_from_z_cm": trace_from_z_cm, "trace_to_z_cm": trace_to_z_cm,
            "max_slope_deg": max_slope_deg, "cull_cm": cull_cm, "shadows": shadows}
    h = F.args_hash(args)
    _folder(prefix)
    if surface not in ("trace", "flat"):
        raise OpError(f"surface {surface!r}: trace or flat", code="bad_args")
    for i, m in enumerate(meshes or []):
        if not isinstance(m, dict) or not EAL.does_asset_exist(str(m.get("mesh", ""))):
            raise OpError(f"meshes[{i}]: no static mesh {m.get('mesh') if isinstance(m, dict) else m!r}",
                          code="not_found", hint="assets.list cls=StaticMesh finds them")
    cur = _state(prefix)
    if not force and cur.get("hash") == h:
        now = measured()
        if all(now.get(t["mesh"], 0) >= t["count"] for t in cur["types"]):
            return {"prefix": prefix, "changed": False, "placed": cur["count"], "planned": cur["count"],
                    "dropped": {}, "per_mesh": {t["mesh"]: t["count"] for t in cur["types"]},
                    "types": [t["type"] for t in cur["types"]], "hash": h, "area_m2": None}
    try:
        p = F.plan({**args, "exclude": (exclude or []) + _footprints(exclude_actors, exclude_margin_cm)})
    except ValueError as e:
        raise OpError(str(e), code="bad_args", hint="docs/unreal/foliage.md lists the scatter arguments") from None
    if dry_run:  # what a run would do, changing nothing (the spec kind's state)
        return {"prefix": prefix, "changed": True, "dry_run": True, "planned": len(p["instances"]), "hash": h,
                "stored_hash": cur.get("hash"), "area_m2": p["area_m2"]}
    world = _world()
    types = []
    for i, m in enumerate(meshes):
        ft, path, _ = _type_for(prefix, i, m["mesh"], cull_cm, shadows)
        unreal.InstancedFoliageActor.remove_all_instances(world, ft)  # before tracing: our old grass is not ground
        types.append((ft, path))
    stale = [t for t in _types(prefix) if t not in [p_ for _, p_ in types]]
    for t in stale:  # a mesh dropped from the list: its instances and type go
        unreal.InstancedFoliageActor.remove_all_instances(world, EAL.load_asset(t))
        EAL.delete_asset(t)
    ignore = _ignore_list() if surface == "trace" else []
    from .layout import _visibility_channel
    channel = _visibility_channel() if surface == "trace" else None
    xf: list = [[] for _ in meshes]
    no_ground = too_steep = 0
    for k, inst in enumerate(p["instances"]):
        m = meshes[inst["mesh"]]
        pitch, roll = inst["tilt"]
        if surface == "trace":
            got = _trace(world, inst["x"], inst["y"], trace_from_z_cm, trace_to_z_cm, ignore, channel)
            if got is None:
                no_ground += 1
                continue
            z, n = got
            if F.slope_deg(n) > max_slope_deg:
                too_steep += 1
                continue
            if m.get("align_to_normal"):
                dp, dr = F.normal_rotation(n)
                pitch, roll = pitch + dp, roll + dr
        else:
            z = z_cm
        xf[inst["mesh"]].append(unreal.Transform(
            location=unreal.Vector(inst["x"], inst["y"], z + inst["z_offset"]),
            rotation=unreal.Rotator(roll=roll, pitch=pitch, yaw=inst["yaw"]), scale=vec(inst["scale"])))
        if k % 500 == 499:
            yield
    per = {}
    for i, (ft, path) in enumerate(types):
        if xf[i]:
            unreal.InstancedFoliageActor.add_instances(world, ft, xf[i])
        EAL.set_metadata_tag(ft, TAG_HASH, h)
        EAL.set_metadata_tag(ft, TAG_COUNT, str(len(xf[i])))
        EAL.set_metadata_tag(ft, TAG_MESH, meshes[i]["mesh"].split(".")[0])
        EAL.set_metadata_tag(ft, TAG_ARGS, json.dumps(args, sort_keys=True) if i == 0 else "")
        EAL.save_asset(path, False)
        per[meshes[i]["mesh"]] = len(xf[i])
    placed = sum(len(x) for x in xf)
    return {"prefix": prefix, "changed": True, "placed": placed, "planned": len(p["instances"]),
            "short_of_target": p["short"], "dropped": {"no_ground": no_ground, "too_steep": too_steep},
            "per_mesh": per, "types": [path for _, path in types], "hash": h, "area_m2": p["area_m2"],
            "min_dist_cm": p["min_dist_cm"]}


@op("foliage.describe", mutates=False, idempotent=True, tags=["layout", "foliage"])
def describe(*, prefix: str = "") -> dict:
    """The scatters in the project (or one): their arguments, seed, foliage types and instance counts as placed,
    and the foliage instances in the level now per mesh (`measured`), so a lost or doubled scatter shows.

    Example: film-ue op foliage.describe prefix=Lawn
    """
    if prefix:
        st = _state(prefix)
        if not st:
            raise not_found("scatter", prefix, _prefixes(), hint="foliage.scatter makes one")
        return {"scatters": [st], "measured": measured()}
    return {"scatters": [_state(p) for p in _prefixes()], "measured": measured()}


def _prefixes() -> list:
    if not EAL.does_directory_exist(ROOT):
        return []
    out = set()
    for p in EAL.list_assets(ROOT, True, False):
        rel = p.split(".")[0][len(ROOT) + 1:]
        if "/" in rel:
            out.add(rel.split("/", 1)[0])
    return sorted(out)


@op("foliage.remove", mutates=True, idempotent=True, tags=["layout", "foliage"])
def remove(*, prefix: str) -> dict:
    """Remove a scatter: its instances and its foliage types (removing nothing is fine).

    Example: film-ue op foliage.remove prefix=Lawn
    """
    world = _world()
    gone = []
    for t in _types(prefix):
        ft = EAL.load_asset(t)
        if ft is not None:
            unreal.InstancedFoliageActor.remove_all_instances(world, ft)
        EAL.delete_asset(t)
        gone.append(t)
    if gone and EAL.does_directory_exist(_folder(prefix)):
        EAL.delete_directory(_folder(prefix))
    return {"prefix": prefix, "removed": gone, "changed": bool(gone)}


# --- PCG ----------------------------------------------------------------------------------------------------------

def _pcg_component(label: str):
    a = find_actor(label)
    if a is None:
        raise not_found("actor", label, [x.get_actor_label() for x in actors()],
                        hint="a PCG Volume (or any actor with a PCG component) by label; foliage.pcg can spawn one")
    comps = a.get_components_by_class(unreal.PCGComponent)
    if not comps:
        raise OpError(f"{label!r} has no PCG component", code="bad_args",
                      hint="use a PCG Volume, or a Blueprint with a PCGComponent")
    return a, comps[0]


SETTERS = {bool: "set_bool_parameter", int: "set_int32_parameter", float: "set_double_parameter",
           str: "set_string_parameter"}


def _set_param(gi, name: str, value):
    H = unreal.PCGGraphParametersHelpers
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return H.set_vector_parameter(gi, name, vec(value))
    if isinstance(value, str) and value.startswith("/"):
        return H.set_soft_object_parameter(gi, name, unreal.SoftObjectPath(value))
    fn = SETTERS.get(type(value))
    if fn is None:
        raise OpError(f"PCG parameter {name}: unsupported value {value!r}", code="bad_args",
                      hint="bool, int, float, string, [x, y, z] or an asset path")
    return getattr(H, fn)(gi, name, value)


@op("foliage.pcg", mutates=True, idempotent=True, tags=["layout", "foliage", "pcg", "experimental"])
def pcg(*, label: str, graph: str = "", seed: int | None = None, params: dict | None = None,
        loc: list | None = None, extent_cm: list | None = None, timeout_s: float = 120.0):
    """Run a PCG graph on an actor with a PCG component, with parameters and a seed, and wait until it has generated.
    With `loc` (and `extent_cm`, the half size) a PCG Volume named `label` is made there first if missing.

    Args: graph: a PCG graph asset (/Game/...; keep the actor's own when ""). seed: the component's seed.
    params: {graph parameter: value} (bool, int, float, string, [x, y, z], or an asset path).
    Returns: {"label", "graph", "seed", "generated", "instances": ISM instances on the actor, "changed"}.
    Example: film-ue op foliage.pcg label=PCG_Forest graph=/Game/PCG/PG_Forest seed=3 'params={"Density":0.6}'
    """
    if find_actor(label) is None and loc is not None:
        a = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(
            unreal.PCGVolume, vec(loc), unreal.Rotator(roll=0.0, pitch=0.0, yaw=0.0))
        if a is None:
            raise OpError("the engine did not spawn a PCGVolume", code="engine", hint="is the PCG plugin enabled?")
        a.set_actor_label(label)
        if extent_cm is not None:  # the volume's default brush is a 200 cm cube: scale it to the half extent
            a.set_actor_scale3d(unreal.Vector(*[float(e) / 100.0 for e in extent_cm]))
        o, e = a.get_actor_bounds(False)
        if e.x <= 0 or e.y <= 0:
            raise OpError(f"the spawned PCG Volume {label} has no bounds (no brush)", code="unsupported",
                          hint="place a PCG Volume in the level once (or a Blueprint with a PCGComponent) and pass "
                               "its label without loc")
    a, comp = _pcg_component(label)
    if graph:
        g = EAL.load_asset(graph)
        if g is None:
            raise not_found("PCG graph", graph, [], hint="assets.list cls=PCGGraph")
        comp.set_graph(g)
    if seed is not None:
        comp.set_editor_property("seed", int(seed))
    if params:
        gi = comp.get_editor_property("graph_instance")
        for k, v in params.items():
            _set_param(gi, k, v)
    comp.generate_local(True)
    import time
    end = time.time() + timeout_s
    while time.time() < end:
        yield 0.2
        if comp.get_editor_property("generated"):
            break
    else:
        raise OpError(f"{label}: PCG did not finish generating in {timeout_s} s", code="timeout",
                      hint="raise timeout_s, or check the graph in the editor log (editor.log)")
    n = sum(int(c.get_instance_count()) for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent))
    g = comp.get_graph()
    return {"label": label, "graph": g.get_path_name().split(".")[0] if g else None,
            "seed": int(comp.get_editor_property("seed")), "generated": True, "instances": n, "changed": True}


@op("foliage.pcg_clear", mutates=True, idempotent=True, tags=["layout", "foliage", "pcg"])
def pcg_clear(*, label: str, delete: bool = False) -> dict:
    """Clear what a PCG component generated (and delete the actor with `delete`). Missing actors are fine.

    Example: film-ue op foliage.pcg_clear label=PCG_Forest
    """
    a = find_actor(label)
    if a is None:
        return {"label": label, "changed": False}
    comps = a.get_components_by_class(unreal.PCGComponent)
    if comps:
        comps[0].cleanup_local(True)
    if delete:
        unreal.get_editor_subsystem(unreal.EditorActorSubsystem).destroy_actor(a)
    return {"label": label, "changed": True, "deleted": bool(delete)}
