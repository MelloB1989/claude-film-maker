"""Chaos cloth on a presenter's garments: describe what simulates, set a garment up from a fabric preset, pre-roll the
live level, and check that a render plan gives the cloth its settle frames.

    cloth.describe     every garment of an actor: clothing data, config, painted map stats, component settings, solver
    cloth.setup        a skeletal-mesh garment -> Chaos cloth from a preset (cotton_tee, overshirt_light, trousers):
                       rule-painted max distance (anchored at the collar/shoulders or the waist, free at the hem and
                       sleeves), the body's physics asset for collision, teleport-and-reset at cuts
    cloth.preroll      settle the cloth in the live level before a frame (hold or play), for stills and checks
    cloth.render_check whether a render plan's chunks give the cloth its settle frames (MRQ warm-up), and the fix
    cloth.presets      the presets, their values and zones

The arithmetic (presets, painted maps, pre-roll) lives in fmbridge.clothkit (pure Python, unit-tested); qa.cloth
(ops/qa_cloth.py) judges the simulation. docs/unreal/cloth.md has the recipes, docs/unreal/research/cloth-physics.md
the reasons and sources.

Traps these ops handle:
- MetaHuman garments are leader-posed followers of Body. Cloth on a follower simulates in the follower's own space;
  without `bind_cloth_to_leader_pose_component` it can lag a frame behind the leader on fast moves.
- A cut that re-places a presenter is a teleport: with no teleport threshold the cloth sees a 3 m/frame jump and
  explodes. cloth.setup sets the thresholds and reset-after-teleport; the reset then needs pre-roll.
- Cloth simulates on LOD 0 only (clothing data is bound per LOD): a garment drawn at LOD 1+ is skinned (armour).
  Renders force LOD 0 (MRQ game overrides); cloth.describe reports the LOD the component draws.
"""
from __future__ import annotations

import json

import unreal

from . import op
from .assets import EAL
from ..errors import OpError
from ..clothkit import paint as _paint
from ..clothkit import presets as _presets
from ..clothkit import preroll as _preroll

BODY = "Body"
PIN_MAX_FRACTION = 0.6   # fit colours pin the collar and shoulder seams (5-15%); more than this is someone else's colours
SKIP = ("Body", "Face")   # a MetaHuman's skin components: never cloth

# preset COMPONENT keys -> USkeletalMeshComponent property names (Python snake_case of the UPROPERTY)
COMPONENT_PROPS = {
    "teleport_distance_threshold": "teleport_distance_threshold",
    "teleport_rotation_threshold": "teleport_rotation_threshold",
    "reset_after_teleport": "reset_after_teleport",
    "allow_cloth_actors": "allow_cloth_actors",
    "disable_cloth_simulation": "disable_cloth_simulation",
    "collide_with_environment": "collide_with_environment",
    "wait_for_parallel_cloth_task": "wait_for_parallel_cloth_task",
}


# ------------------------------------------------------------------------------------------------------- helpers

def _actor(label: str):
    from .mh.actor import _actor as mh_actor
    return mh_actor(label)


def _components(label: str) -> dict:
    """The actor's skeletal mesh components by name, fetched afresh (a Blueprint may have re-created them)."""
    a = _actor(label)
    return {c.get_name(): c for c in a.get_components_by_class(unreal.SkeletalMeshComponent)}


def garment(label: str, component: str):
    comps = _components(label)
    if component not in comps:
        from ..errors import closest
        raise OpError(f"{label} has no component {component!r}", code="not_found",
                      candidates=closest(component, list(comps)), hint="cloth.describe lists the garments")
    if component in SKIP:
        raise OpError(f"{component} is the MetaHuman's skin, not a garment", code="bad_args",
                      hint="name the garment component (Torso, Top, Overshirt, Tee...)")
    return comps[component]


def _get(obj, name, default=None):
    try:
        return obj.get_editor_property(name)
    except Exception:
        return default


def _call(obj, name, *args, default=None):
    fn = getattr(obj, name, None)
    if fn is None:
        return default
    try:
        return fn(*args)
    except Exception:
        return default


def clothing_assets(mesh) -> list:
    """The skeletal mesh's clothing data (USkeletalMesh.MeshClothingAssets), [] when none or not readable."""
    if mesh is None:
        return []
    return list(_get(mesh, "mesh_clothing_assets", []) or [])


def solver_stats(comp) -> dict:
    """What the solver reports through the component's clothing interactor (UClothingSimulationInteractor): how many
    cloths and particles simulate, and its iterations/substeps. {} when the component has no simulation."""
    it = _call(comp, "get_clothing_simulation_interactor")
    if it is None:
        return {}
    out = {"tick_option": str(_get(comp, "visibility_based_anim_tick_option")),
           "recently_rendered": _call(comp, "was_recently_rendered"),
           "tick_enabled": _call(comp, "is_component_tick_enabled")}
    for k, fn in (("cloths", "get_num_cloths"), ("dynamic_particles", "get_num_dynamic_particles"),
                  ("kinematic_particles", "get_num_kinematic_particles"), ("iterations", "get_num_iterations"),
                  ("substeps", "get_num_substeps"), ("sim_time_ms", "get_simulation_time")):
        v = _call(it, fn)
        if v is not None:
            out[k] = round(float(v), 3) if k == "sim_time_ms" else int(v)
    return out


def _config_values(asset) -> dict:
    """The cloth config properties a preset sets, read back from the clothing asset's configs (Chaos + shared)."""
    out = {}
    for cfg in (_get(asset, "cloth_configs", {}) or {}).values():
        for k, dv in _presets.BASE_CONFIG.items():
            if k in out:
                continue
            try:
                out[k] = _plain(_cfg_get(cfg, k, dv)[1])
            except Exception:  # noqa: BLE001 - not on this config (or no Python type: the weighted values)
                pass
    return out


def _plain(v):
    if isinstance(v, (bool, int, float, str)):
        return v
    if hasattr(v, "low") and hasattr(v, "high"):        # FChaosClothWeightedValue
        return {"low": float(v.low), "high": float(v.high)}
    return str(v)


def describe_component(comp) -> dict:
    mesh = comp.get_skeletal_mesh_asset() if hasattr(comp, "get_skeletal_mesh_asset") else None
    assets = clothing_assets(mesh)
    lead = _get(comp, "leader_pose_component")
    d = {"mesh": mesh.get_path_name().split(".")[0] if mesh is not None else None,
         "leader": lead.get_name() if lead is not None else None,
         "clothing": [{"name": a.get_name(), "physics_asset": (lambda p: p.get_path_name().split(".")[0] if p else None)(
             _get(a, "physics_asset")), "config": _config_values(a)} for a in assets],
         "settings": {k: _plain(_get(comp, p)) for k, p in COMPONENT_PROPS.items() if _get(comp, p) is not None},
         "max_distance_scale": _call(comp, "get_cloth_max_distance_scale"),
         "suspended": _call(comp, "is_clothing_simulation_suspended"),
         "forced_lod_model": _get(comp, "forced_lod_model"),   # ForcedLodModel: 0 = auto, N = LOD N-1
         "solver": solver_stats(comp)}
    flm = d["forced_lod_model"]
    d["drawn_lod"] = "auto" if not isinstance(flm, int) or flm <= 0 else flm - 1
    d["simulating"] = bool(assets) and not d["settings"].get("disable_cloth_simulation", False) and \
        not d["suspended"] and d["solver"].get("dynamic_particles", 1) > 0
    return d


# ------------------------------------------------------------------------------------------------------- ops

@op("cloth.presets", mutates=False, idempotent=True, tags=["cloth"])
def presets(*, name: str = "") -> dict:
    """The fabric presets cloth.setup takes: each one's solver config, zones (where it is anchored and where it hangs
    free, with max distances in cm) and settle time. Offline facts, no engine.

    Args: name: one preset (else all).
    Returns: {name: {"about", "config", "zones", "free", "pinned", "settle_s", "max_cm"}}.
    Example: film-ue op cloth.presets name=cotton_tee
    """
    try:
        names = [name] if name else _presets.names()
        return {n: dict(_presets.get(n), max_cm=_presets.max_cm(_presets.get(n))) for n in names}
    except KeyError as e:
        raise OpError(str(e).strip("'\""), code="bad_args", candidates=_presets.names()) from None


@op("cloth.describe", mutates=False, idempotent=True, tags=["cloth", "metahuman"])
def describe(*, label: str, component: str = "") -> dict:
    """Which garments of a placed character simulate cloth, and how: per garment its clothing data (config values as
    the solver has them, physics asset), the component's teleport/LOD settings, and the solver's live numbers.

    A garment with `"clothing": []` is skinned only: it moves like armour. `simulating` false with clothing data
    means it is disabled, suspended or has no dynamic particles (all painted 0).
    Args: label: the actor. component: one garment (else every skeletal mesh component but Body and Face).
    Returns: {"label", "garments": {name: {"mesh", "leader", "clothing", "settings", "max_distance_scale",
    "suspended", "forced_lod_model", "drawn_lod", "solver", "simulating"}}, "skinned_only": [names]}.
    Example: film-ue op cloth.describe label=Host
    """
    comps = {component: garment(label, component)} if component else \
        {n: c for n, c in _components(label).items() if n not in SKIP}
    g = {n: describe_component(c) for n, c in comps.items()}
    out = {"label": label, "garments": g, "skinned_only": sorted(n for n, d in g.items() if not d["clothing"])}
    # MetaHuman outfits (Chaos Outfit/Cloth Assets) simulate on their own ChaosClothComponent, not on a skeletal mesh
    CCC = getattr(unreal, "ChaosClothComponent", None)
    if CCC is not None and not component:
        out["cloth_components"] = {
            c.get_name(): {"asset": (lambda a: a.get_path_name().split(".")[0] if a else None)(_call(c, "get_asset")),
                           "simulation_enabled": _call(c, "is_simulation_enabled"),
                           "suspended": _call(c, "is_simulation_suspended"),
                           "teleport_distance_threshold": _get(c, "teleport_distance_threshold")}
            for c in _actor(label).get_components_by_class(CCC)}
    return out


def _plugin():
    """The FMCloth editor plugin (unreal/plugins/FMCloth): clothing data, weight maps and simulated positions are C++
    only in 5.8 (docs/unreal/cloth.md "Why a plugin"). None when it is not built into the project."""
    return getattr(unreal, "FMCloth", None)


def _need_plugin():
    L = _plugin()
    if L is None:
        raise OpError("the FMCloth editor plugin is not loaded: skeletal-mesh clothing data and its weight maps "
                      "cannot be written from Python in 5.8", code="unsupported",
                      hint="film-ue --box B plugin-build FMCloth, then film-ue --box B editor restart "
                           "(docs/unreal/cloth.md 'Build the plugin'); dry_run=true shows the maps meanwhile")
    return L


def _render_colours(mesh, lod: int = 0):
    """The garment's render vertices and their vertex colours (the fit's: R ease, G pinned), through Geometry
    Script; (points, colours) or (points, None) when it has no colours."""
    if not hasattr(unreal, "GeometryScript_AssetUtils"):
        return [], None
    from .mh.actor import _pick
    AU, MQ, LU = unreal.GeometryScript_AssetUtils, unreal.GeometryScript_MeshQueries, unreal.GeometryScript_List
    dm = unreal.DynamicMesh()
    req = unreal.GeometryScriptMeshReadLOD()
    req.set_editor_property("lod_index", int(lod))
    AU.copy_mesh_from_skeletal_mesh(mesh, dm, unreal.GeometryScriptCopyMeshFromAssetOptions(), req)
    pts = [(p.x, p.y, p.z) for p in LU.convert_vector_list_to_array(
        _pick(MQ.get_all_vertex_positions(dm, False), "GeometryScriptVectorList"))]
    VC = getattr(unreal, "GeometryScript_VertexColors", None)
    if VC is None or not hasattr(VC, "get_mesh_per_vertex_colors"):
        return pts, None
    cl = _pick(VC.get_mesh_per_vertex_colors(dm), "GeometryScriptColorList")
    arr = _call(LU, "convert_color_list_to_array", cl) if cl is not None else None
    if not arr or len(arr) != len(pts) or all((c.r, c.g) == (1.0, 1.0) for c in arr):
        return pts, None
    return pts, [(c.r, c.g, c.b, c.a) for c in arr]


def nearest_colours(points: list, src: list, colours: list, cell_cm: float = 2.0) -> list:
    """For each point, the colour of the nearest source point (a grid hash; cloth and render vertices share
    positions, so the nearest is at ~0 cm). None where nothing is within 3 cells."""
    grid: dict = {}
    for i, p in enumerate(src):
        grid.setdefault((int(p[0] // cell_cm), int(p[1] // cell_cm), int(p[2] // cell_cm)), []).append(i)
    out = []
    for p in points:
        k = (int(p[0] // cell_cm), int(p[1] // cell_cm), int(p[2] // cell_cm))
        best, bi = None, None
        for r in (1, 3):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    for dz in range(-r, r + 1):
                        for i in grid.get((k[0] + dx, k[1] + dy, k[2] + dz), ()):
                            q = src[i]
                            d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
                            if best is None or d < best:
                                best, bi = d, i
            if bi is not None:
                break
        out.append(colours[bi] if bi is not None else None)
    return out


def bones(mesh) -> tuple:
    """Reference-pose bone heads (component space, cm) and parents, from a transient component on the mesh
    (SkinnedMeshComponent GetNumBones/GetBoneName/GetParentBone/GetRefPoseTransform; parent-relative, chained)."""
    comp = unreal.SkeletalMeshComponent()
    comp.set_skeletal_mesh_asset(mesh)
    names = [str(comp.get_bone_name(i)) for i in range(comp.get_num_bones())]
    parents, world, heads = {}, {}, {}
    for i, b in enumerate(names):
        p = str(comp.get_parent_bone(b))
        parents[b] = p if p and p != "None" else None
        t = comp.get_ref_pose_transform(i)
        world[b] = t if parents[b] is None else unreal.MathLibrary.compose_transforms(t, world[parents[b]])
        loc = world[b].translation
        heads[b] = (loc.x, loc.y, loc.z)
    return heads, parents


def plan_maps(points: list, mesh, preset: dict, colours_from=None) -> dict:
    """The painted maps for the cloth's simulation points (rest pose): zones, max distance, backstop; `colours_from`
    = (render points, colours) to pin and cap by the fit's vertex colours."""
    heads, parents = bones(mesh)
    segs = _paint.bone_segments(heads, parents)
    try:
        zones = _paint.assign(points, segs, preset)
    except ValueError as e:
        raise OpError(str(e), code="failed", hint="the garment must be skinned to the MetaHuman body skeleton") from None
    cols = nearest_colours(points, colours_from[0], colours_from[1]) if colours_from and colours_from[1] else None
    ignored = ""
    if cols:
        pinned = sum(1 for c in cols if c is not None and c[1] > _paint.PIN_LEVEL) / float(len(cols))
        if pinned > PIN_MAX_FRACTION:   # not the fit's encoding (a garment's own colours): round 5, her overshirt
            ignored = (f"the vertex colours pin {pinned:.0%} of the garment: not garment.fit's encoding (G = pinned "
                       "collar/shoulder), ignored")
            cols = None
    maps = _paint.paint(points, zones, segs, preset, parents, colours=cols)
    return {"maps": maps, "problems": _paint.check_maps(maps, preset), "colours": cols is not None,
            "colours_ignored": ignored}


def _preset(name: str, overrides=None) -> dict:
    try:
        return _presets.get(name, overrides)
    except KeyError as e:
        raise OpError(str(e).strip("'\""), code="bad_args", candidates=_presets.names(),
                      hint="cloth.presets lists the presets, their zones and config keys") from None


# Config keys Python cannot write on the asset in 5.8.4: FChaosClothWeightedValue and EClothMassMode have no Python
# type (round 5: "Cannot nativize float as StructBase" on drag). The weighted ones go through the per-cloth
# UChaosClothingInteractor at runtime (ChaosClothingSimulationInteractor.h:41-84); mass_mode stays the engine's
# default, Density.
INTERACTOR_KEYS = ("edge_stiffness_weighted", "bending_stiffness_weighted", "area_stiffness_weighted",
                   "tether_stiffness", "tether_scale", "anim_drive_stiffness", "drag", "lift", "mass_mode")


def apply_interactor(comp, cloth_name: str, config: dict) -> dict:
    """The weighted config values a preset sets, through the component's Chaos clothing interactor (runtime: they
    live on the simulation, not the asset, so cloth.settings re-applies them after a respawn). Returns what it set or
    {"error": ...}."""
    it = _call(comp, "get_clothing_simulation_interactor")
    ci = _call(it, "get_clothing_interactor", cloth_name) if it is not None else None
    if ci is None:
        return {"error": f"no clothing interactor for {cloth_name} (is the cloth simulating? cloth.describe)"}
    c = config
    out = {}
    try:
        ci.set_material_linear(float(c["edge_stiffness_weighted"]), float(c["bending_stiffness_weighted"]),
                               float(c["area_stiffness_weighted"]))
        out["material"] = [c["edge_stiffness_weighted"], c["bending_stiffness_weighted"], c["area_stiffness_weighted"]]
        ci.set_long_range_attachment_linear(float(c["tether_stiffness"]), float(c["tether_scale"]))
        out["long_range_attachment"] = [c["tether_stiffness"], c["tether_scale"]]
        ci.set_anim_drive_linear(float(c["anim_drive_stiffness"]))
        out["anim_drive"] = c["anim_drive_stiffness"]
        ci.set_aerodynamics(float(c["drag"]), float(c["lift"]), unreal.Vector(0, 0, 0))
        out["aerodynamics"] = [c["drag"], c["lift"]]
    except Exception as e:  # noqa: BLE001 - report it with what did get set
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def cpp_name(key: str, value=None) -> str:
    """The C++ property name for a snake_case config key. EditAnywhere-only properties (not BlueprintVisible) have no
    Python name, so get/set_editor_property looks the given string up as the C++ name, case-insensitively
    (PyWrapperObject.cpp FindEditorPropertyImpl): "density" finds Density, "collision_thickness" finds nothing
    (round 5). bools carry the b prefix: use_ccd -> bUseCcd (= bUseCCD)."""
    camel = "".join(w[:1].upper() + w[1:] for w in key.split("_"))
    return ("b" + camel) if isinstance(value, bool) else camel


def _cfg_get(c, key: str, value=None):
    """(name that worked, value) for a config property by its Python name, else its C++ name; raises the last error."""
    err = None
    for n in (key, cpp_name(key, value)):
        try:
            return n, c.get_editor_property(n)
        except Exception as e:  # noqa: BLE001
            err = e
    raise err


def write_weighted(L, cloth, config: dict) -> dict:
    """The INTERACTOR_KEYS (but mass_mode, Density by default) written on the clothing asset through
    FMCloth.SetConfigValue by C++ name. {key: "low,high" read back} or {"unsupported": why} with an older plugin."""
    if not hasattr(L, "set_config_value"):
        return {"unsupported": "FMCloth without SetConfigValue: rebuild it (film-ue plugin-build FMCloth); until then "
                               "renders use the engine's weighted defaults (bending 1.0)"}
    out = {}
    for k in INTERACTOR_KEYS:
        if k == "mass_mode" or k not in config:
            continue
        v = float(config[k])
        err = L.set_config_value(cloth, cpp_name(k), v, v)
        out[k] = f"error: {err}" if err else L.get_config_value(cloth, cpp_name(k))
    return out


def write_config(asset, config: dict) -> dict:
    """Write a preset's config onto the clothing asset's config objects (cloth_configs: Chaos + shared), except the
    INTERACTOR_KEYS. The configs are fetched afresh for every key and written without edit notifications: in round 5
    every key after the first notified write came back unreadable. Returns {"set": {key: value read back},
    "missing": ["key: why", ...]}."""
    done, missing = {}, []
    quiet = getattr(getattr(unreal, "PropertyAccessChangeNotifyMode", None), "NEVER", None)
    for k, v in config.items():
        if k in INTERACTOR_KEYS:
            continue
        why = []
        target = None
        for c in list((asset.get_editor_property("cloth_configs") or {}).values()):
            try:
                name, cur = _cfg_get(c, k, v)
                target = c
                break
            except Exception as e:  # noqa: BLE001 - collect the engine's reason
                why.append(f"{type(c).__name__}: {e}")
        if target is None:
            missing.append(f"{k}: " + ("; ".join(why) or "no config objects"))
            continue
        val = type(cur)(*[float(x) for x in v]) if isinstance(v, list) and len(v) == 3 else v
        try:
            if quiet is not None:
                target.set_editor_property(name, val, quiet)
            else:
                target.set_editor_property(name, val)
            done[k] = _plain(target.get_editor_property(name))
        except Exception as e:  # noqa: BLE001 - one refused key must not stop the rest
            missing.append(f"{k}: {type(e).__name__}: {e}")
    return {"set": done, "missing": missing}


@op("cloth.setup", mutates=True, idempotent=True, tags=["cloth", "metahuman", "experimental"])
def setup(*, label: str, component: str, preset: str, overrides: dict | None = None, physics_asset: str = "",
          lod: int = 0, section: int = -1, use_colours: bool = True, dry_run: bool = False, save: bool = True) -> dict:
    """Make a skeletal-mesh garment Chaos cloth from a fabric preset: clothing data on its LOD-0 section, the max
    distance painted by rule (0 at the collar/shoulder seams or the waistband, ramping to the preset's cm at the hem
    and sleeve ends; the fit's vertex colours pin and cap it), the preset's solver config, the body's physics asset
    for collision, and the component settings cloth needs (cloth.settings). Converges: re-running repaints and
    re-configures the same clothing data. Needs the FMCloth plugin (dry_run does not).

    Args: label: the placed character. component: the garment component (cloth.describe lists them). preset:
    cotton_tee | overshirt_light | trousers (cloth.presets). overrides: {"config": {key: value}, "zones": {zone:
    {"to_cm": cm}}, "settle_s": s}. physics_asset: collision shapes (default: the Body's physics asset).
    lod/section: the garment section to simulate (-1 = the largest). use_colours: read the fit's vertex colours
    (R ease, G pinned). dry_run: paint the garment's render vertices and return the stats; write nothing.
    Returns: {"changed", "cloth", "points", "maps": {zone: {"n", "min_cm", "max_cm", "mean_cm"}}, "colours",
    "config": {"set", "missing"}, "settings", "physics_asset", "readback_max_cm"}.
    Example: film-ue op cloth.setup label=Host component=Torso preset=cotton_tee
    """
    p = _preset(preset, overrides)
    comp = garment(label, component)
    mesh = comp.get_skeletal_mesh_asset()
    if mesh is None:
        raise OpError(f"{label}.{component} has no skeletal mesh", code="failed", hint="mh.dress it first")
    phys = physics_asset or _body_physics(label)
    if phys and not EAL.does_asset_exist(phys):
        raise OpError(f"no physics asset {phys}", code="not_found", hint="give physics_asset= (the MetaHuman body's)")
    render = _render_colours(mesh, lod) if use_colours else ([], None)
    if dry_run:
        pts = render[0]
        if not pts:
            raise OpError("dry_run reads the garment through Geometry Script, which is not enabled", code="unsupported",
                          hint="enable GeometryScripting in the .uproject")
        pm = plan_maps(pts, mesh, p, render)
        return {"changed": False, "dry_run": True, "points": len(pts), "maps": pm["maps"]["stats"],
                "problems": pm["problems"], "colours": pm["colours"], "colours_ignored": pm["colours_ignored"],
                "physics_asset": phys, "preset": preset}
    if render[0]:   # check the rule on the render vertices BEFORE creating clothing data (a refusal changes nothing)
        pre = plan_maps(render[0], mesh, p, render if render[1] else None)
        if pre["problems"]:
            raise OpError(f"{component}: the painted maps are wrong: {'; '.join(pre['problems'])}", code="failed",
                          details={"maps": pre["maps"]["stats"], "colours_ignored": pre["colours_ignored"]},
                          hint="use_colours=false when the garment's vertex colours are not garment.fit's; or change "
                               "the preset's zones (overrides.zones)")
    L = _need_plugin()
    sec = int(section) if section >= 0 else int(L.largest_section(mesh, int(lod)))
    err = L.ensure_cloth_on_section(mesh, int(lod), sec, f"Cloth_{component}",
                                    unreal.load_asset(phys) if phys else None)
    if err:
        raise OpError(f"clothing data on {mesh.get_path_name()} LOD {lod} section {sec}: {err}", code="engine",
                      hint="see the editor log (LogClothingAsset, LogSkeletalMesh)")
    cloth = L.section_cloth(mesh, int(lod), sec)
    pts = [(v.x, v.y, v.z) for v in L.rest_vertices(cloth, 0)]
    pm = plan_maps(pts, mesh, p, render if render[1] else None)
    if pm["problems"]:
        raise OpError(f"{component}: the painted maps are wrong: {'; '.join(pm['problems'])}", code="failed",
                      details={"maps": pm["maps"]["stats"]},
                      hint="change the preset's zones (overrides.zones) or the fit's pinned colours")
    maps = pm["maps"]
    for target, vals in (("MaxDistance", maps["max_distance"]), ("BackstopDistance", maps["backstop_distance"]),
                         ("BackstopRadius", maps["backstop_radius"])):
        e = L.set_weight_map(cloth, 0, target, [float(x) for x in vals])
        if e:
            raise OpError(f"writing the {target} map: {e}", code="engine", hint="see the editor log")
    back = list(L.get_weight_map(cloth, 0, "MaxDistance") or [])
    cfg = write_config(cloth, p["config"])
    settings_done = _apply_component(garment(label, component))
    _call(garment(label, component), "recreate_clothing_actors")
    cfg["interactor"] = apply_interactor(garment(label, component), cloth.get_name(), p["config"])
    # ... and ON THE ASSET when the plugin can (FMCloth.SetConfigValue): interactor values live on this world's
    # simulation only, and an MRQ render builds its own from the asset (round 5)
    cfg["asset_weighted"] = write_weighted(L, cloth, p["config"])
    EAL.set_metadata_tag(mesh, "FMClothPreset", preset)   # qa.cloth reads it
    # cloth.settings re-applies the interactor values after a respawn: it needs the overrides too
    EAL.set_metadata_tag(mesh, "FMClothOverrides", json.dumps(overrides or {}, sort_keys=True))
    if save:
        EAL.save_loaded_asset(mesh)
    return {"changed": True, "cloth": cloth.get_name(), "section": sec, "points": len(pts),
            "maps": maps["stats"], "colours": pm["colours"], "colours_ignored": pm["colours_ignored"], "config": cfg, "settings": settings_done,
            "physics_asset": phys, "preset": preset, "readback_max_cm": round(max(back), 3) if back else None}


@op("cloth.remove", mutates=True, idempotent=True, tags=["cloth", "metahuman"])
def remove(*, label: str, component: str, lod: int = 0, section: int = -1, save: bool = True) -> dict:
    """Take the cloth off a garment section again (it is skinned only: the A side of an A/B). Idempotent.

    Returns: {"changed", "section"}.
    Example: film-ue op cloth.remove label=Host component=Torso
    """
    L = _need_plugin()
    mesh = garment(label, component).get_skeletal_mesh_asset()
    sec = int(section) if section >= 0 else int(L.largest_section(mesh, int(lod)))
    had = L.section_cloth(mesh, int(lod), sec) is not None
    err = L.remove_cloth_from_section(mesh, int(lod), sec)
    if err:
        raise OpError(f"removing cloth: {err}", code="engine")
    if had and save:
        EAL.save_loaded_asset(mesh)
    return {"changed": had, "section": sec}


def _body_physics(label: str) -> str:
    comps = _components(label)
    b = comps.get(BODY)
    pa = _get(b, "physics_asset_override") if b is not None else None
    if pa is None and b is not None and b.get_skeletal_mesh_asset() is not None:
        pa = _get(b.get_skeletal_mesh_asset(), "physics_asset")
    return pa.get_path_name().split(".")[0] if pa is not None else ""


def _apply_component(comp) -> dict:
    """The preset's component settings (teleport thresholds, reset, no environment collision) and cloth bound to the
    leader's pose; returns what it set."""
    done = {}
    for k, prop in COMPONENT_PROPS.items():
        v = _presets.COMPONENT[k]
        try:
            comp.set_editor_property(prop, v)
            done[k] = v
        except Exception as e:  # noqa: BLE001 - report, do not hide
            done[k] = f"not set: {e}"
    _call(comp, "set_cloth_max_distance_scale", float(_presets.COMPONENT["cloth_max_distance_scale"]))
    if _get(comp, "leader_pose_component") is not None:
        _call(comp, "bind_cloth_to_leader_pose_component")
        done["bound_to_leader"] = True
    return done


@op("cloth.settings", mutates=True, idempotent=True, tags=["cloth", "metahuman"])
def settings(*, label: str, component: str = "") -> dict:
    """Give a character's cloth garments the component settings cloth needs on a presenter: teleport thresholds
    (30 cm / 30 deg) with reset-after-teleport (a cut that re-places them must not fling the cloth), no environment
    collision, the max distance at full scale, and the cloth bound to the leader's pose. Run it after any respawn
    (mh.dress, a host swap): component settings live on the placed actor, not the asset.

    Returns: {"changed", "garments": {name: {setting: value}}}.
    Example: film-ue op cloth.settings label=Host
    """
    comps = {component: garment(label, component)} if component else \
        {n: c for n, c in _components(label).items() if n not in SKIP}
    out = {}
    for n, c in comps.items():
        mesh = c.get_skeletal_mesh_asset()
        assets = clothing_assets(mesh)
        if not assets:
            continue
        out[n] = _apply_component(c)
        tag = EAL.get_metadata_tag(mesh, "FMClothPreset")
        if tag:   # the weighted values live on the simulation, not the asset: a respawn loses them
            try:
                ov = json.loads(EAL.get_metadata_tag(mesh, "FMClothOverrides") or "{}")
            except ValueError:
                ov = {}
            out[n]["interactor"] = apply_interactor(c, assets[0].get_name(), _presets.get(tag, ov)["config"])
    return {"changed": bool(out), "garments": out}


def _cloth_comps(label: str, component: str = "") -> dict:
    comps = {component: garment(label, component)} if component else \
        {n: c for n, c in _components(label).items() if n not in SKIP}
    return {n: c for n, c in comps.items() if clothing_assets(c.get_skeletal_mesh_asset())}


def editor_cloth(comp) -> None:
    """Make an editor-world garment simulate: the flag first, then re-create the clothing simulation, because the
    simulation is only created when the world is ready for it (bShouldSimulatePhysics, false in the editor, or
    bUpdateClothInEditor: SkeletalMeshComponentPhysics.cpp:3146-3150) and the cloth tick runs in the editor only with
    the flag (:83). Round 5: the flag alone left sim_time 0."""
    _call(comp, "set_update_cloth_in_editor", True)
    _call(comp, "set_component_tick_enabled", True)
    # TickClothing steps the cloth only when the component was recently RENDERED or always ticks its pose; otherwise
    # it teleports-and-resets every tick (SkeletalMeshComponentPhysics.cpp:3820-3845). The offscreen editor renders
    # nothing, so a garment on OnlyTickPoseWhenRendered never simulates there (round 5: sim_time 0 with realtime on).
    opt = getattr(getattr(unreal, "VisibilityBasedAnimTickOption", None), "ALWAYS_TICK_POSE_AND_REFRESH_BONES", None)
    if opt is not None:
        try:
            comp.set_editor_property("visibility_based_anim_tick_option", opt)
        except Exception:  # noqa: BLE001 - reported by solver_stats
            pass
    _call(comp, "recreate_clothing_actors")


def reset(comps) -> None:
    """Teleport-and-reset every cloth on its next update (back to the skinned pose)."""
    for c in comps:
        _call(c, "force_cloth_next_update_teleport_and_reset")


@op("cloth.preroll", mutates=False, idempotent=True, tags=["cloth", "sequencer"])
def preroll_live(*, sequence: str, frame: int, labels: list | None = None, frames: int = 0, mode: str = "hold",
                 start: int | None = None, fps: float = 24.0):
    """Settle the cloth in the live level before reading a frame (a still, qa.clip under simulation): reset the cloth,
    then evaluate the sequence one tick per frame (hold: the frame itself `frames` times, as MRQ's warm-up does;
    play: the `frames` frames before it, from `start` at the earliest) and land on `frame`. Multi-tick.

    Args: sequence: the level sequence. frame: the frame to land on. labels: the characters (default: every actor
    with cloth garments). frames: settle frames (0 = what the slowest preset needs, clothkit.preroll.need_frames).
    mode: hold | play. start: the cut's first frame (play never runs before it).
    Returns: {"frame", "steps", "mode", "garments": {label.component: simulating}}.
    Example: film-ue op cloth.preroll sequence=/Game/Reel/SEQ_Reel frame=1080 'labels=["Host"]' mode=play start=960
    """
    from . import call
    from ._scrub import set_frame
    if mode not in ("hold", "play"):
        raise OpError(f"mode {mode!r}: hold or play", code="bad_args")
    comps = []
    names = labels or _cloth_actors()
    for lab in names:
        comps += [(f"{lab}.{n}", c) for n, c in _cloth_comps(lab).items()]
    n = int(frames) or _preroll.need_frames(_settle_for(), fps)
    steps = _preroll.live_steps(int(frame), n, mode, start)
    for _, c in comps:
        editor_cloth(c)
    yield
    call("seq.scrub", path=sequence, frame=steps[0])
    yield
    reset([c for _, c in comps])
    for f in steps:
        set_frame(f)
        yield
    return {"frame": int(frame), "steps": len(steps), "mode": mode,
            "garments": {k: describe_component(c)["simulating"] for k, c in comps}}


def _settle_for(preset_names=None) -> float:
    return max(_presets.get(n)["settle_s"] for n in (preset_names or _presets.names()))


def _cloth_actors() -> list:
    out = []
    for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        for c in a.get_components_by_class(unreal.SkeletalMeshComponent):
            if c.get_name() not in SKIP and clothing_assets(c.get_skeletal_mesh_asset()):
                out.append(a.get_actor_label())
                break
    return out


@op("cloth.render_check", mutates=False, idempotent=True, tags=["cloth", "render"])
def render_check(*, chunks: list, warmup_engine: int = 0, warmup_render: int = 0, presets_used: list | None = None,
                 fps: float = 24.0) -> dict:
    """Does a render plan give the cloth its settle frames before every chunk's first frame? Pure: feed it
    render.plan's chunks and the spec's warm-up counts. A chunk that starts on its cut holds the first frame for
    warmup_engine + warmup_render frames; a chunk that starts mid-cut plays the cut's frames before it.

    Args: chunks: render.plan's "chunks". warmup_engine/warmup_render: the spec's (resolved) counts. presets_used:
    the cloth presets in the shots (default all: the slowest decides). fps: the sequence rate.
    Returns: {"ok", "need", "warmup_engine": what to set, "chunks": [{"id", "mode", "frames", "ok", "fix"}]}.
    Example: film-ue op cloth.render_check 'chunks=[{"id":"c0","cut_start":1080,"start":1080,"end":1200,"preroll":0}]' warmup_render=8
    """
    try:
        need = _preroll.need_frames(_settle_for(presets_used), fps)
    except KeyError as e:
        raise OpError(str(e).strip("'\""), code="bad_args", candidates=_presets.names()) from None
    return _preroll.check_chunks(chunks, need=need, warmup_engine=int(warmup_engine), warmup_render=int(warmup_render))


CACHE_MODES = {"record": "RECORD", "play": "PLAY", "off": "NONE"}


@op("cloth.cache", mutates=True, idempotent=True, tags=["cloth", "render", "experimental"])
def cache(*, label: str, mode: str, collection: str = "", components: list | None = None,
          manager: str = "") -> dict:
    """A Chaos Cache Manager for a character's cloth garments, so a render plays the cloth back instead of
    simulating it: `record` (the next PIE/MRQ run of the shot writes the cache), then `play` (every later render of
    that shot reads it: identical cloth in every chunk and every re-render), `off` (simulate live). Converges on one
    manager actor per character. Needs the ChaosCaching plugin (experimental, off by default).

    Record and play must start on the same frame (one MRQ job per shot, from its first frame): the cache's time is
    the world's time since the job began. Check after `play` with qa.cloth or render.compare against the record pass.
    Args: label: the character. mode: record | play | off. collection: the cache collection asset (default
    /Game/FM/ClothCache/CC_<label>). components: garment names (default every cloth garment). manager: the actor
    label (default ClothCache_<label>).
    Returns: {"changed", "manager", "mode", "collection", "observed": [names]}.
    Example: film-ue op cloth.cache label=Host mode=record
    """
    if mode not in CACHE_MODES:
        raise OpError(f"mode {mode!r}: one of {', '.join(CACHE_MODES)}", code="bad_args")
    if not hasattr(unreal, "ChaosCacheManager"):
        raise OpError("the ChaosCaching plugin is not enabled", code="unsupported",
                      hint="enable ChaosCaching in the .uproject Plugins and restart the editor; meanwhile render "
                           "each shot from its first frame with cloth.render_check's warm-up (simulated live)")
    comps = _cloth_comps(label)
    if components:
        missing = [c for c in components if c not in comps]
        if missing:
            raise OpError(f"no cloth garment(s) {missing} on {label}", code="not_found", candidates=list(comps),
                          hint="cloth.setup them first; cloth.describe lists them")
        comps = {n: comps[n] for n in components}
    if not comps:
        raise OpError(f"{label} has no cloth garments", code="failed", hint="cloth.setup first")

    coll_path = collection or f"/Game/FM/ClothCache/CC_{label}"
    changed = False
    if not EAL.does_asset_exist(coll_path):
        folder, name = coll_path.rsplit("/", 1)
        factory = getattr(unreal, "CacheCollectionFactory", None)
        coll = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name, folder, unreal.ChaosCacheCollection, factory() if factory else None)
        if coll is None:
            raise OpError(f"could not create {coll_path}", code="engine")
        EAL.save_asset(coll_path)
        changed = True
    coll = EAL.load_asset(coll_path)
    name = manager or f"ClothCache_{label}"
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    mgr = next((a for a in eas.get_all_level_actors() if a.get_actor_label() == name), None)
    if mgr is None:
        mgr = eas.spawn_actor_from_class(unreal.ChaosCacheManager, unreal.Vector(0, 0, 0))
        mgr.set_actor_label(name)
        changed = True
    want = getattr(unreal.CacheMode, CACHE_MODES[mode])
    if _get(mgr, "cache_mode") != want:
        mgr.set_editor_property("cache_mode", want)
        changed = True
    if _get(mgr, "cache_collection") != coll:
        mgr.set_editor_property("cache_collection", coll)
        changed = True
    mgr.set_editor_property("start_mode", unreal.StartMode.TIMED)
    for n, c in comps.items():
        mgr.find_or_add_observed_component(c, f"{label}_{n}", False)
    return {"changed": changed, "manager": name, "mode": mode, "collection": coll_path, "observed": sorted(comps)}
