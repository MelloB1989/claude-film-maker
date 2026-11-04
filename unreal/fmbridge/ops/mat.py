"""Materials (WP2): a library of master materials built by code, instances converged from a dict of parameters,
PBR materials from a texture set, presets (glass, chrome, emissive in nits...), any material from a node-graph spec,
and numbers to check them by (does it compile, do the textures match their samplers).

Masters live in /Game/FM/Lib (`mat.masters` lists them with their parameters); everything else is an instance of
one. look.* (WP5) keeps its own materials and may build on these (`from .mat import master`).
"""
from __future__ import annotations

import os

import unreal

from . import _assetlib as AL
from . import _matgraph as G
from . import _matlib as LIB
from . import op
from ._util import actors as _level_actors, color as _color
from .assets import EAL, load
from ..errors import OpError, closest, not_found

MEL = unreal.MaterialEditingLibrary
FP_TAG = "fm_spec"  # metadata: the fingerprint of the spec a material was built from
MASTER_TAG = "fm_master"  # metadata: the library master's name


def _tools():
    return unreal.AssetToolsHelpers.get_asset_tools()


def _enum(enum_name: str, value: str):
    e = getattr(unreal, enum_name)
    try:
        return getattr(e, value)
    except AttributeError:
        raise OpError(f"{enum_name} has no {value} in this engine", code="unsupported") from None


# ------------------------------------------------------------------------------------------------- default textures

def _ensure_default_textures() -> list:
    """The library's 4x4 default textures (white sRGB, white linear masks, black, flat normal, ORM), made once."""
    made = []
    for name, d in LIB.DEFAULT_TEXTURES.items():
        path = f"{LIB.TEX}/{name}"
        if EAL.does_asset_exist(path):
            continue
        png = AL.write_png(os.path.join(unreal.Paths.project_saved_dir(), "fmbridge", "lib", name + ".png"), d["rgb"])
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", png)
        t.set_editor_property("destination_path", LIB.TEX)
        t.set_editor_property("destination_name", name)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", False)
        _tools().import_asset_tasks([t])
        tex = EAL.load_asset(path)
        if tex is None:
            raise OpError(f"could not import the library texture {path} from {png}", code="engine",
                          hint="see the editor log (film-ue log); the Saved dir must be writable")
        tex.set_editor_property("srgb", d["srgb"])
        tex.set_editor_property("compression_settings", _enum("TextureCompressionSettings", d["compression"]))
        EAL.save_asset(path, only_if_is_dirty=False)
        made.append(path)
    return made


# ---------------------------------------------------------------------------------------------- who wears what

def _parent(m):
    try:
        return m.get_editor_property("parent") if isinstance(m, unreal.MaterialInstance) else None
    except Exception:
        return None


def _chain(m) -> list:
    """A material's parent chain, itself first: [MI, its parent MI, ..., the Material]."""
    out, seen = [], set()
    while m is not None and m.get_path_name() not in seen:
        seen.add(m.get_path_name())
        out.append(m)
        m = _parent(m)
    return out


def users_in_level(path: str) -> list:
    """Labels of the actors in the open level drawing `path` (directly, or through an instance of it)."""
    target = AL.object_path(path)
    out = []
    for a in _level_actors():
        for c in a.get_components_by_class(unreal.PrimitiveComponent) or []:
            try:
                n = c.get_num_materials()
            except Exception:
                continue
            if any(m is not None and any(x.get_path_name() == target for x in _chain(m))
                   for m in (c.get_material(i) for i in range(int(n)))):
                out.append(a.get_actor_label())
                break
    return out


def _refuse_if_drawn(path: str, what: str, force: bool) -> None:
    users = [] if force else users_in_level(path)
    if users:
        raise OpError(f"{path} is drawn by {', '.join(users[:5])}{'...' if len(users) > 5 else ''}: {what} it now "
                      f"could crash the editor (unreal/README.md: never change a material while it is drawn)",
                      code="conflict", details={"users": users},
                      hint="build into a new path and swap the actors to it with level.material, or open an empty "
                           "level first; force=true skips this check")


# --------------------------------------------------------------------------------------------------- graph build

def _value(cls: str, key: str, v):
    """A spec value to the engine value an expression property wants."""
    if key in ("texture", "material_function", "collection") and isinstance(v, str):
        return load(v)
    if key == "sampler_type":
        return _enum("MaterialSamplerType", v)
    if key in ("default_value", "constant") and isinstance(v, (list, tuple)):
        return _color(v)
    if key == "parameter_name":
        return str(v)
    return v


def _build(path: str, spec: dict, *, rebuild: bool = False, force: bool = False, save: bool = True,
           master_name: str = "") -> dict:
    try:
        plan = G.normalize(spec)
    except G.GraphError as e:
        raise OpError(f"material spec: {e}", code="bad_args", candidates=e.candidates,
                      hint="film-ue ops mat.graph shows the spec format") from None
    err = AL.valid_path(path)
    if err:
        raise OpError(err, code="bad_args")
    path = AL.package_path(path)
    folder, name = AL.split(path)
    m = EAL.load_asset(path) if EAL.does_asset_exist(path) else None
    if m is not None and not isinstance(m, unreal.Material):
        raise OpError(f"{path} is a {type(m).__name__}, not a Material", code="conflict",
                      hint="pick another path, or remove it with assets.remove")
    if m is not None and EAL.get_metadata_tag(m, FP_TAG) == plan["fingerprint"] and not rebuild:
        return {"path": path, "changed": False, "fingerprint": plan["fingerprint"], "nodes": len(plan["nodes"])}
    if any(n["class"] == "MaterialExpressionTextureSampleParameter2D" and
           str(n["props"].get("texture", "")).startswith(LIB.TEX) for n in plan["nodes"]):
        _ensure_default_textures()
    if m is not None:
        _refuse_if_drawn(path, "recompiling", force)
        # one by one: delete_all_material_expressions deletes while iterating the live array and skips every other
        # node in 5.8 (MaterialEditingLibrary.cpp DeleteAllMaterialExpressions), leaving duplicate parameters
        for e in list(MEL.get_material_expressions(m) or []):
            MEL.delete_material_expression(m, e)
        left = MEL.get_num_material_expressions(m)
        if left:
            raise OpError(f"could not clear {path}'s old graph ({left} nodes left)", code="engine",
                          hint="remove the material with assets.remove and build it again")
    else:
        if not EAL.does_directory_exist(folder):
            EAL.make_directory(folder)
        m = _tools().create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())
        if m is None:
            raise OpError(f"could not create the material {path}", code="engine", hint="see film-ue log")
    for prop, v in plan["material"].items():
        enum = {"blend_mode": "BlendMode", "shading_model": "MaterialShadingModel", "material_domain": "MaterialDomain",
                "translucency_lighting_mode": "TranslucencyLightingMode"}.get(prop)
        m.set_editor_property(prop, _enum(enum, v) if enum else v)
    made = {}
    for n in plan["nodes"]:
        cls = getattr(unreal, n["class"], None)
        if cls is None:
            raise OpError(f"no expression class {n['class']} in this engine (node {n['id']!r})", code="bad_args",
                          candidates=closest(n["class"], G.NODE_TYPES.values()))
        e = MEL.create_material_expression(m, cls, n["x"], n["y"])
        if e is None:
            raise OpError(f"could not create {n['class']} (node {n['id']!r})", code="engine")
        for k, v in n["props"].items():
            try:
                e.set_editor_property(k, _value(n["class"], k, v))
            except Exception as ex:
                raise OpError(f"node {n['id']!r} ({n['type']}): cannot set {k}={v!r}: {ex}", code="bad_args",
                              hint=f"properties are the expression's editor properties: assets.props on a "
                                   f"{n['class']}") from None
        made[n["id"]] = e
    for src, out, dst, pin in plan["links"]:
        if not MEL.connect_material_expressions(made[src], out, made[dst], pin):
            raise OpError(f"could not connect {src}{'.' + out if out else ''} -> {dst}.{pin or '(input)'}",
                          code="bad_args", hint="check the output name (RGB/R/G/B/A) and the input pin name")
    for mp, src, out in plan["outputs"]:
        if not MEL.connect_material_property(made[src], out, _enum("MaterialProperty", mp)):
            raise OpError(f"could not connect {src}{'.' + out if out else ''} to the material's {mp}",
                          code="engine", hint="this input may not exist for the material's domain/shading model")
    errors = [str(x) for x in (MEL.recompile_material(m) or [])]  # 5.8 returns the compile errors
    EAL.set_metadata_tag(m, FP_TAG, plan["fingerprint"])
    if master_name:
        EAL.set_metadata_tag(m, MASTER_TAG, master_name)
    if save:
        EAL.save_asset(path, only_if_is_dirty=False)
    st = _stats(m)  # (get_statistics waits for the shaders to finish compiling)
    if errors or st.get("num_samplers") == -1:
        raise OpError(f"{path} was built but does not compile (the engine draws its checker): "
                      f"{'; '.join(errors[:3]) or 'no error text'}", code="failed", details={**st, "errors": errors}, hint="mat.check names the texture/sampler mismatches; see film-ue log for the "
                                       "compiler's message")
    return {"path": path, "changed": True, "fingerprint": plan["fingerprint"], "nodes": len(plan["nodes"]),
            "stats": st}


def _stats(m) -> dict:
    try:
        s = MEL.get_statistics(m)
    except Exception:
        return {}
    out = {}
    for k in ("num_vertex_shader_instructions", "num_pixel_shader_instructions", "num_samplers",
              "num_vertex_texture_samples", "num_pixel_texture_samples", "num_virtual_texture_samples",
              "num_uv_scalars", "num_interpolator_scalars"):
        try:
            out[k] = int(s.get_editor_property(k))
        except Exception:
            pass
    return out


# ------------------------------------------------------------------------------------------------------- masters

def master(name: str, *, rebuild: bool = False, force: bool = False) -> str:
    """The library master `name`'s package path, built if missing (for other ops: `from .mat import master`)."""
    if name not in LIB.MASTERS:
        raise not_found("master", name, LIB.MASTERS, hint="mat.masters lists them")
    path = LIB.master_path(name)
    _build(path, LIB.MASTERS[name](), rebuild=rebuild, force=force, master_name=name)
    return path


@op("mat.masters", mutates=False, idempotent=True, tags=["materials"])
def masters(*, name: str = "") -> dict:
    """The library's master materials: what each is for, its path, whether it is built and current, and its
    parameters with what they do.

    Args: name: one master (else all).
    Returns: {master: {"path", "description", "built": bool, "current": bool, "params": {name: {"kind",
             "default", "doc"}}}}.
    Example: film-ue op mat.masters name=glass
    """
    if name and name not in LIB.MASTERS:
        raise not_found("master", name, LIB.MASTERS, hint="call mat.masters with no name to list them")
    out = {}
    for k in ([name] if name else sorted(LIB.MASTERS)):
        spec = LIB.MASTERS[k]()
        path = LIB.master_path(k)
        built = EAL.does_asset_exist(path)
        cur = built and EAL.get_metadata_tag(load(path), FP_TAG) == G.fingerprint(spec)
        params = G.parameters(spec)
        for p, d in params.items():
            d["doc"] = LIB.PARAMS.get(p, d.get("doc", ""))
        out[k] = {"path": path, "description": spec.get("description", ""), "built": built, "current": bool(cur),
                  "params": params}
    return out


@op("mat.master", mutates=True, idempotent=True, tags=["materials"])
def build_master(*, name: str, rebuild: bool = False, force: bool = False) -> dict:
    """Build (or keep) one library master material in /Game/FM/Lib, with its default textures.

    A master already built from the same spec is left alone (changed false). One built from an older spec is
    rebuilt in place, but only when nothing in the open level draws it (recompiling a drawn material can crash the
    editor): otherwise it fails with code conflict, unless force.
    Args: name: a master from mat.masters (opaque, opaque_orm, masked, masked_orm, foliage, glass, emissive, screen,
          cloth, skin, unlit, decal). rebuild: rebuild even if current. force: skip the drawn-by check.
    Returns: {"path", "changed", "fingerprint", "nodes", "stats"}.
    Example: film-ue op mat.master name=opaque_orm
    """
    if name not in LIB.MASTERS:
        raise not_found("master", name, LIB.MASTERS, hint="mat.masters lists them")
    return _build(LIB.master_path(name), LIB.MASTERS[name](), rebuild=rebuild, force=force, master_name=name)


@op("mat.graph", mutates=True, idempotent=True, tags=["materials"])
def graph(*, path: str, spec: dict, rebuild: bool = False, force: bool = False, save: bool = True) -> dict:
    """Build a Material from a node-graph spec (material by spec); re-running the same spec changes nothing.

    spec: {"blend": opaque|masked|translucent|additive|modulate, "shading": default_lit|unlit|subsurface|
    subsurface_profile|two_sided_foliage|cloth|clear_coat|thin_translucent|hair|eye, "two_sided": bool,
    "domain": surface|deferred_decal|post_process|light_function|ui, "translucency_lighting": surface_per_pixel|...,
    "usage": [skeletal_mesh, instanced, nanite, groom, morph_targets, ...], "opacity_mask_clip": 0.333,
    "nodes": {id: {"type": Scalar|Vector|Texture|Switch|Const|Multiply|Add|Lerp|OneMinus|Power|TexCoord|Fresnel|
    VertexColor|Function|... or any MaterialExpression class, "in": {pin: "node" | "node.R" | number | [r,g,b]},
    other keys: editor properties (name, default, texture, sampler: color|normal|masks|linear_color|grayscale)}},
    "outputs": {BaseColor|Metallic|Specular|Roughness|EmissiveColor|Opacity|OpacityMask|Normal|SubsurfaceColor|
    AmbientOcclusion|Refraction|WorldPositionOffset|CustomData0|...: source}}.
    The spec is checked before anything is touched (unknown node/pin/source -> bad_args with near names). A
    material drawn in the open level is not rebuilt (conflict) unless force.
    Args: path: /Game/... of the Material. spec: as above. rebuild: even if unchanged. save: save the asset.
    Returns: {"path", "changed", "fingerprint", "nodes", "stats": {"num_samplers", "num_pixel_shader_instructions"}}.
    Example: film-ue op mat.graph path=/Game/Mats/M_Stripes 'spec={"nodes": {"c": {"type": "Vector", "name": "Col",
             "default": [1, 0, 0, 1]}}, "outputs": {"BaseColor": "c"}}'
    """
    return _build(path, spec, rebuild=rebuild, force=force, save=save)


# ------------------------------------------------------------------------------------------------------ instances

def _param_kinds(m) -> dict:
    """{name: scalar|vector|texture|switch} for a material or instance."""
    out = {}
    for kind, fn in (("scalar", "get_scalar_parameter_names"), ("vector", "get_vector_parameter_names"),
                     ("texture", "get_texture_parameter_names"), ("switch", "get_static_switch_parameter_names")):
        try:
            for n in getattr(MEL, fn)(m) or []:
                out[str(n)] = kind
        except Exception:
            pass
    return out


def _get_param(mi, kind: str, name: str):
    try:
        if kind == "scalar":
            return round(float(MEL.get_material_instance_scalar_parameter_value(mi, name)), 6)
        if kind == "vector":
            c = MEL.get_material_instance_vector_parameter_value(mi, name)
            return [round(float(x), 6) for x in (c.r, c.g, c.b, c.a)]
        if kind == "texture":
            t = MEL.get_material_instance_texture_parameter_value(mi, name)
            return AL.package_path(t.get_path_name()) if t is not None else None
        if kind == "switch":
            return bool(MEL.get_material_instance_static_switch_parameter_value(mi, name))
    except Exception:
        return None
    return None


def _norm_value(kind: str, v):
    if kind == "scalar":
        return round(float(v), 6)
    if kind == "vector":
        v = list(v) + [1.0] * (4 - len(v))
        return [round(float(x), 6) for x in v[:4]]
    if kind == "texture":
        return AL.package_path(v) if v else None
    if kind == "switch":
        return bool(v)
    return v


def _set_param(mi, kind: str, name: str, v) -> None:
    """Set one parameter. The MEL setters return False whatever happens (MaterialEditingLibrary.cpp: bResult is
    never set) and accept any name, so callers check names first and read the values back after."""
    if kind == "scalar":
        MEL.set_material_instance_scalar_parameter_value(mi, name, float(v))
    elif kind == "vector":
        MEL.set_material_instance_vector_parameter_value(mi, name, _color(v))
    elif kind == "texture":
        MEL.set_material_instance_texture_parameter_value(mi, name, load(v))
    elif kind == "switch":  # one permutation update for all switches, at the end
        MEL.set_material_instance_static_switch_parameter_value(mi, name, bool(v), update_material_instance=False)


def _guess_kind(v) -> str:
    if isinstance(v, bool):
        return "switch"
    if isinstance(v, (int, float)):
        return "scalar"
    if isinstance(v, (list, tuple)):
        return "vector"
    return "texture"


def converge_instance(path: str, parent: str, params: dict, *, force: bool = False, save: bool = True) -> dict:
    err = AL.valid_path(path)
    if err:
        raise OpError(err, code="bad_args")
    path = AL.package_path(path)
    if not EAL.does_asset_exist(parent):
        raise not_found("material", parent, [], hint="a library master by name (mat.masters), or a material path "
                                                     "(assets.find cls=Material)")
    par = load(parent)
    kinds = _param_kinds(par)
    unknown = [k for k in params if kinds and k not in kinds]
    if unknown:
        raise OpError(f"{parent} has no parameter {unknown[0]!r}", code="bad_args",
                      candidates=closest(unknown[0], kinds), hint=f"mat.describe path={parent} lists them")
    for k, v in params.items():
        if kinds.get(k) == "texture" and v and not EAL.does_asset_exist(str(v)):
            raise not_found("texture", str(v), [], hint="import it first (assets.import, mat.pbr)")
    folder, name = AL.split(path)
    changed = []
    mi = EAL.load_asset(path) if EAL.does_asset_exist(path) else None
    if mi is not None and not isinstance(mi, unreal.MaterialInstanceConstant):
        raise OpError(f"{path} is a {type(mi).__name__}, not a material instance", code="conflict",
                      hint="pick another path, or remove it with assets.remove")
    if mi is None:
        if not EAL.does_directory_exist(folder):
            EAL.make_directory(folder)
        mi = _tools().create_asset(name, folder, unreal.MaterialInstanceConstant,
                                   unreal.MaterialInstanceConstantFactoryNew())
        if mi is None:
            raise OpError(f"could not create {path}", code="engine", hint="see film-ue log")
        MEL.set_material_instance_parent(mi, par)
        changed.append("created")
    else:
        cur = _parent(mi)
        if cur is None or cur.get_path_name() != par.get_path_name():
            _refuse_if_drawn(path, "reparenting", force)
            MEL.set_material_instance_parent(mi, par)
            changed.append("parent")
    for k, v in params.items():
        kind = kinds.get(k) or _guess_kind(v)
        want = _norm_value(kind, v)
        if _get_param(mi, kind, k) == want and "created" not in changed:
            continue
        _set_param(mi, kind, k, v)
        changed.append(k)
    if changed:
        MEL.update_material_instance(mi)
        wrong = {k: _get_param(mi, kinds.get(k) or _guess_kind(v), k) for k, v in params.items()
                 if _get_param(mi, kinds.get(k) or _guess_kind(v), k) != _norm_value(kinds.get(k) or _guess_kind(v), v)}
        if wrong:
            raise OpError(f"{path}: parameters did not take: {wrong}", code="engine", details={"read_back": wrong},
                          hint=f"mat.describe path={path} shows its parameters and kinds")
        if save:
            EAL.save_asset(path, only_if_is_dirty=False)
    return {"path": path, "parent": AL.package_path(par.get_path_name()), "changed": bool(changed),
            "updated": changed}


@op("mat.instance", mutates=True, idempotent=True, tags=["materials"])
def instance(*, path: str, master: str = "", parent: str = "", params: dict = None, force: bool = False,
             save: bool = True) -> dict:
    """Make or update a material instance: its parent, and parameters from a dict; only what differs is written.

    Args: path: /Game/... of the instance. master: a library master by name (mat.masters: opaque, glass, emissive,
          ...; built on demand) or parent: any material/instance path. params: {name: value}: a number (scalar), a
          list [r, g, b(, a)] linear (vector), a /Game texture path (texture), true/false (static switch). Names are
          checked against the parent's parameters. force: reparent even if the open level draws it (unsafe).
    Returns: {"path", "parent", "changed", "updated": [what was written]}.
    Example: film-ue op mat.instance path=/Game/Mats/MI_RedPaint master=opaque
             'params={"Tint": [0.6, 0.05, 0.04], "Roughness": 0.35}'
    """
    return converge_instance(path, _resolve_parent_named(master, parent), dict(params or {}), force=force, save=save)


def _resolve_parent_named(master_name: str, parent: str) -> str:
    if master_name and parent:
        raise OpError("give master (a library master's name) or parent (a material path), not both", code="bad_args")
    if master_name:
        return globals()["master"](master_name)
    if parent:
        return AL.package_path(parent)
    raise OpError("give master (opaque, glass, ...: mat.masters) or parent (a material path)", code="bad_args")


@op("mat.preset", mutates=True, idempotent=True, tags=["materials"])
def preset(*, path: str, name: str, color: list = None, roughness: float = None, metallic: float = None,
           opacity: float = None, nits: float = None, params: dict = None, force: bool = False) -> dict:
    """A ready-made material: an instance of a library master with a named look (chrome, gold, glass_clear, water,
    plastic_gloss, rubber, emissive_panel, screen, ...), adjusted by a few plain arguments.

    Args: path: /Game/... of the instance. name: a preset (mat.presets lists them with their master and values).
          color: linear [r, g, b] (Tint, or Color for emitters). roughness, metallic, opacity: 0..1. nits:
          emitted luminance in cd/m2 for emissive/screen presets. params: any other master parameters.
    Returns: mat.instance's result plus {"preset", "master"}.
    Example: film-ue op mat.preset path=/Game/Mats/MI_Panel name=emissive_panel nits=400 'color=[1, 0.9, 0.8]'
    """
    if name not in LIB.PRESETS:
        raise not_found("preset", name, LIB.PRESETS, hint="mat.presets lists them")
    m, vals = LIB.PRESETS[name]
    vals = dict(vals)
    colour_key = "Color" if m in ("emissive", "screen") else "Tint"
    for k, v in ((colour_key, color), ("Roughness", roughness), ("Metallic", metallic), ("Opacity", opacity),
                 ("Luminance_nits", nits)):
        if v is not None:
            vals[k] = v
    vals.update(params or {})
    res = converge_instance(path, globals()["master"](m), vals, force=force)
    return {**res, "preset": name, "master": m}


@op("mat.presets", mutates=False, idempotent=True, tags=["materials"])
def presets() -> dict:
    """The named looks mat.preset makes: {name: {"master", "params"}}.

    Example: film-ue op mat.presets
    """
    return {k: {"master": m, "params": dict(v)} for k, (m, v) in sorted(LIB.PRESETS.items())}


# ----------------------------------------------------------------------------------------------- read and check

@op("mat.describe", mutates=False, idempotent=True, tags=["materials"])
def describe(*, path: str) -> dict:
    """A material or instance as JSON: class, parent chain, library master (if any), blend/shading, every parameter
    with its current value, compile statistics, and which actors in the open level draw it.

    Args: path: /Game/... of a Material or MaterialInstance.
    Returns: {"path", "class", "chain": [paths], "master", "blend", "shading", "two_sided", "params": {name:
             {"kind", "value"}}, "stats", "users": [labels]}.
    Example: film-ue op mat.describe path=/Game/Mats/MI_RedPaint
    """
    p = AL.package_path(path)
    if not EAL.does_asset_exist(p):
        raise not_found("material", p, [], hint="find one with assets.find cls=MaterialInstanceConstant")
    m = load(p)
    if not isinstance(m, unreal.MaterialInterface):
        raise OpError(f"{p} is a {type(m).__name__}, not a material", code="bad_args")
    chain = _chain(m)
    base = chain[-1]
    params = {}
    for name, kind in sorted(_param_kinds(m).items()):
        params[name] = {"kind": kind, "value": _get_param(m, kind, name) if isinstance(m, unreal.MaterialInstance)
                        else None}
    out = {"path": p, "class": type(m).__name__, "chain": [AL.package_path(x.get_path_name()) for x in chain],
           "master": EAL.get_metadata_tag(base, MASTER_TAG) or None, "params": params, "users": users_in_level(p)}
    for key, prop in (("blend", "blend_mode"), ("shading", "shading_model"), ("two_sided", "two_sided")):
        try:
            v = base.get_editor_property(prop)
            out[key] = v if isinstance(v, bool) else str(getattr(v, "name", v))
        except Exception:
            out[key] = None
    out["stats"] = _stats(base)
    return out


@op("mat.check", mutates=False, idempotent=True, tags=["materials", "qa"])
def check(*, path: str) -> dict:
    """Does a material render as meant: it compiles (else the engine draws its checker), and every texture it uses
    has the compression its sampler needs (a normal map TC_NORMALMAP, a data map TC_MASKS and linear, a colour map
    sRGB and neither).

    Args: path: /Game/... of a Material or instance.
    Returns: {"pass", "issues": [{"code": material.not_compiling | material.texture_kind, "severity", "message",
             "fix", "subject", "value", "expected"}], "metrics": {"num_samplers", ..., "textures_checked"}}.
    Example: film-ue op mat.check path=/Game/Mats/MI_Rock
    """
    d = describe(path=path)
    issues = []
    if d["stats"].get("num_samplers") == -1:
        issues.append({"code": "material.not_compiling", "severity": "fail", "subject": d["path"],
                       "message": f"{d['chain'][-1]} does not compile: the engine draws its checker",
                       "fix": f"film-ue log for the compiler error; rebuild with mat.graph/mat.master rebuild=true"})
    expect = {}
    master_name = d.get("master")
    if master_name and master_name in LIB.MASTERS:
        for n in LIB.MASTERS[master_name]()["nodes"].values():
            if n.get("type") == "Texture":
                expect[n["name"]] = n.get("sampler", "color")
    checked = 0
    for name, info in d["params"].items():
        sampler = expect.get(name)
        if info["kind"] != "texture" or not info["value"] or sampler not in ("normal", "masks", "color"):
            continue
        t = load(info["value"])
        try:
            comp = str(getattr(t.get_editor_property("compression_settings"), "name",
                               t.get_editor_property("compression_settings"))).upper()
            srgb = bool(t.get_editor_property("srgb"))
        except Exception:
            continue
        checked += 1
        role = {"normal": "normal", "masks": "roughness", "color": "base_color"}[sampler]
        want_comp, want_srgb = AL.ROLES[role][2], AL.ROLES[role][1]
        ok_comp = want_comp in comp if sampler != "color" else ("NORMALMAP" not in comp and "MASKS" not in comp)
        if not ok_comp or srgb != want_srgb:
            issues.append({"code": "material.texture_kind", "severity": "fail", "subject": name,
                           "message": f"{name} is a {sampler} sampler but {info['value']} is {comp} srgb={srgb}: "
                                      f"the engine draws a checker or wrong values",
                           "value": f"{comp} srgb={srgb}",
                           "expected": f"{want_comp if sampler != 'color' else 'TC_DEFAULT'} srgb={want_srgb}",
                           "fix": f"film-ue op assets.texture path={info['value']} role={role}, or set another "
                                  f"texture with mat.instance"})
    return {"pass": not any(i["severity"] == "fail" for i in issues), "issues": issues,
            "metrics": {**d["stats"], "textures_checked": checked}}


# ------------------------------------------------------------------------------------------------ PBR from a set

@op("mat.pbr", mutates=True, idempotent=True, tags=["materials", "import"])
def pbr(*, path: str, maps: dict = None, files: list = None, folder: str = "", texture_dest: str = "",
        cutout: bool = False, foliage: bool = False, params: dict = None, force: bool = False) -> dict:
    """A PBR material instance from a texture set: imports the files (or takes textures already in the project),
    sets each texture's sRGB/compression by its role, picks the master (opaque, opaque_orm for a packed ORM map,
    masked/foliage for cut-outs) and wires every map in.

    Args: path: /Game/... of the instance. maps: {role: texture path or file}: roles base_color, normal, orm,
          roughness, metallic, ao, opacity, translucency, emissive, gloss (inverted into roughness is not
          supported: convert it first). files: files on the box (a texture set; roles from their names, e.g.
          T_Rock_BaseColor.png, T_Rock_Normal.png, T_Rock_ORM.png). folder: a folder on the box holding one set.
          texture_dest: where textures are imported (default: the instance's folder + /Textures). cutout: use the
          masked master (opacity map, or base colour alpha). foliage: the foliage master. params: other master
          parameters (Tint, Tiling, NormalStrength, ...).
    Returns: {"path", "master", "maps": {role: texture path}, "changed", "imported": [paths], "ignored": [files]}.
    Example: film-ue op mat.pbr path=/Game/Mats/MI_Rock folder=/data/megascans/rock_4k
    """
    from . import assets_import as A
    maps = dict(maps or {})
    files = list(files or [])
    if folder:
        if not os.path.isdir(folder):
            raise OpError(f"no folder {folder} on the box", code="not_found", hint="push it first (client.push)")
        files += [os.path.join(folder, f) for f in sorted(os.listdir(folder))]
    ignored = []
    if files:
        sets = AL.texture_set(files)
        ignored = sets.pop("_unknown", [])
        if not sets:
            raise OpError("no texture in files names its role (BaseColor, Normal, ORM, Roughness...)",
                          code="bad_args", details={"files": files}, hint="pass maps={role: file} instead")
        if len(sets) > 1:
            raise OpError(f"files hold {len(sets)} texture sets ({', '.join(sorted(sets))}): one material each",
                          code="bad_args", hint="call mat.pbr once per set, with its files")
        for role, f in next(iter(sets.values())).items():
            maps.setdefault(role, f)
    if "gloss" in maps:
        ignored.append(maps.pop("gloss"))
    if not maps:
        raise OpError("give maps, files or folder", code="bad_args")
    folder_ = AL.split(path)[0]
    dest = texture_dest or f"{folder_}/Textures"
    imported = []
    tex = {}
    for role, src in maps.items():
        if role not in AL.ROLES:
            raise not_found("texture role", role, AL.ROLES)
        if str(src).startswith("/") and EAL.does_asset_exist(AL.package_path(src)) and not os.path.isfile(src):
            tex[role] = AL.package_path(src)
            A.texture_settings_for(tex[role], role)
        else:
            res = A.import_textures(files=[src], dest=dest, role=role)
            tex[role] = res["textures"][0]["path"]
            imported.append(tex[role])
    orm = "orm" in tex
    if foliage:
        m = "foliage"
    elif cutout or "opacity" in tex:
        m = "masked_orm" if orm else "masked"
    else:
        m = "opaque_orm" if orm else "opaque"
    if foliage and orm:
        raise OpError("the foliage master takes separate AO/roughness/metallic maps, not ORM", code="unsupported")
    p = {}
    names = {"base_color": "BaseColorMap", "normal": "NormalMap", "orm": "ORMMap", "roughness": "RoughnessMap",
             "metallic": "MetallicMap", "ao": "AOMap", "opacity": "OpacityMap", "translucency": "TranslucencyMap"}
    for role, t in tex.items():
        if role in names and (role != "translucency" or m == "foliage"):
            p[names[role]] = t
        elif role not in names:
            ignored.append(t)
    if "base_color" in tex:
        p["Tint"] = [1.0, 1.0, 1.0]
    if orm or "roughness" in tex:
        p["Roughness"] = 1.0
    if orm or "metallic" in tex:
        p["Metallic"] = 1.0
    if cutout and "opacity" not in tex and m.startswith("masked"):
        p["UseBaseAlpha"] = True
    p.update(params or {})
    res = converge_instance(path, globals()["master"](m), p, force=force)
    return {**res, "master": m, "maps": tex, "imported": imported, "ignored": ignored}


@op("mat.assign", mutates=True, idempotent=True, tags=["materials"])
def assign(*, mesh: str, material: str, slot=0) -> dict:
    """Set a material on a mesh ASSET's slot (every actor showing the mesh changes). For one actor only use
    level.material.

    Args: mesh: /Game/... StaticMesh or SkeletalMesh. material: /Game/... material or instance. slot: index or slot
          name.
    Returns: {"mesh", "slot", "slot_name", "material", "changed"}.
    Example: film-ue op mat.assign mesh=/Game/Props/SM_Chair material=/Game/Mats/MI_Oak slot=0
    """
    from . import assets_catalog as A
    mp = AL.package_path(mesh)
    if not EAL.does_asset_exist(mp):
        raise not_found("mesh", mp, [], hint="assets.find cls=StaticMesh")
    m = load(mp)
    mat_ = load(AL.package_path(material))
    slots = A.material_slots(m)
    if isinstance(slot, str) and not slot.isdigit():
        idx = next((i for i, s in enumerate(slots) if s["name"] == slot), None)
        if idx is None:
            raise not_found("material slot", slot, [s["name"] for s in slots], hint=f"assets.describe path={mp}")
    else:
        idx = int(slot)
    if not 0 <= idx < len(slots):
        raise OpError(f"{mp} has {len(slots)} material slots; no slot {idx}", code="bad_args",
                      candidates=[s["name"] for s in slots])
    want = AL.package_path(mat_.get_path_name())
    if slots[idx]["material"] == want:
        return {"mesh": mp, "slot": idx, "slot_name": slots[idx]["name"], "material": want, "changed": False}
    if isinstance(m, unreal.StaticMesh):
        m.set_material(idx, mat_)
    else:
        mats = list(m.get_editor_property("materials"))
        sm = mats[idx]
        sm.set_editor_property("material_interface", mat_)
        mats[idx] = sm
        m.set_editor_property("materials", mats)
    EAL.save_asset(mp, only_if_is_dirty=False)
    return {"mesh": mp, "slot": idx, "slot_name": slots[idx]["name"], "material": want, "changed": True}
