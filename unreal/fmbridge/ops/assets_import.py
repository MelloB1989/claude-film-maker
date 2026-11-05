"""Import (WP2): any file format into the project by code, with no dialog, and the settings that make an import
right: textures by role (sRGB, compression), meshes (static/skeletal, scale, LODs, Nanite, collision), reimport.

How UE 5.8 imports (docs/unreal/assets.md API_NOTES): FBX, OBJ, glTF/GLB and images go through Interchange by
default. Its options are an InterchangeGenericAssetsPipeline put in the task's `options` through an
InterchangePipelineStackOverride (it replaces the translator's default stack, so glTF also gets Epic's
DefaultGLTFPipeline back). Alembic goes through the Alembic factory (AbcImportSettings; a groom through
GroomImportOptions), USD through the USD importer (UsdStageImportOptions) when that plugin is on. `automated=True`
on every task: no options window, no overwrite prompt (a hidden prompt answers its default, which is "no").
"""
from __future__ import annotations

import os

import unreal

from . import _assetlib as AL
from . import op
from .assets import EAL, _assets_under, _check_path, load
from ..errors import OpError, closest, not_found

MESH_EXT = (".fbx", ".obj", ".gltf", ".glb")
USD_EXT = (".usd", ".usda", ".usdc", ".usdz")
SOUND_EXT = (".wav", ".ogg", ".flac", ".aif", ".aiff")
GLTF_PIPELINE = "/Interchange/Pipelines/DefaultGLTFPipeline"
COLLISION = {"none": None, "box": "BOX", "sphere": "SPHERE", "capsule": "CAPSULE", "convex": "CONVEX18_DOP",
             "convex10": "CONVEX10_DOP_X", "convex26": "CONVEX26_DOP"}
ABC_PRESETS = {"maya": ([1.0, -1.0, 1.0], [90.0, 0.0, 0.0], True), "max": ([1.0, -1.0, 1.0], [0.0, 0.0, 0.0], True),
               "none": ([1.0, 1.0, 1.0], [0.0, 0.0, 0.0], False)}


def _tools():
    return unreal.AssetToolsHelpers.get_asset_tools()


def _enum(enum_name: str, value: str):
    """An enum value by name, tolerant of how the Python layer splits digits (Convex18DOP may be CONVEX18_DOP or
    CONVEX_18DOP; Model3D MODEL3_D): exact first, then the same letters and digits ignoring underscores."""
    e = getattr(unreal, enum_name)
    v = getattr(e, value, None)
    if v is not None:
        return v
    key = value.replace("_", "").upper()
    names = [n for n in dir(e) if n.isupper() and not n.startswith("_")]
    for n in names:
        if n.replace("_", "") == key:
            return getattr(e, n)
    raise OpError(f"{enum_name} has no {value} in this engine", code="unsupported", candidates=closest(value, names))


def _set(obj, **props) -> None:
    for k, v in props.items():
        obj.set_editor_property(k, v)


def folder_has_assets(folder: str) -> bool:
    return EAL.does_directory_exist(folder) and bool(_assets_under(folder))


def _task(f: str, dest: str, name: str = "", replace: bool = True, options=None, save: bool = True):
    t = unreal.AssetImportTask()
    _set(t, filename=f, destination_path=dest, automated=True, replace_existing=replace, save=save)
    if name:
        t.set_editor_property("destination_name", name)
    if options is not None:
        t.set_editor_property("options", options)
    return t


def _task_objects(t) -> list:
    try:
        objs = list(t.get_objects() or [])
    except Exception:
        objs = []
    paths = [str(p) for p in (t.get_editor_property("imported_object_paths") or [])]
    if objs:
        paths = paths or [o.get_path_name() for o in objs]
    return paths


# ------------------------------------------------------------------------------------------------- mesh options

def mesh_pipeline(*, kind: str = "auto", skeleton: str = "", scale: float = 1.0, combine: bool = True,
                  nanite: bool | None = None, collision: str = "none", lods: bool = True, materials: bool = True,
                  textures: bool = True, animations: bool = False, recompute_normals: bool = False,
                  sockets: bool = True, physics_asset: bool = True):
    """An InterchangeGenericAssetsPipeline set from plain arguments (every relevant field set explicitly)."""
    p = unreal.InterchangeGenericAssetsPipeline()
    cm = p.get_editor_property("common_meshes_properties")
    force = {"auto": "IFMT_NONE", "static": "IFMT_STATIC_MESH", "skeletal": "IFMT_SKELETAL_MESH"}
    if kind not in force:
        raise OpError(f"kind {kind!r}: auto, static or skeletal", code="bad_args", candidates=closest(kind, force))
    _set(cm, force_all_mesh_as_type=_enum("InterchangeForceMeshType", force[kind]), import_lods=bool(lods),
         recompute_normals=bool(recompute_normals), import_sockets=bool(sockets))
    sk = p.get_editor_property("common_skeletal_meshes_and_animations_properties")
    if skeleton:
        _set(sk, skeleton=load(skeleton))
    mp = p.get_editor_property("mesh_pipeline")
    _set(mp, import_static_meshes=kind != "skeletal", import_skeletal_meshes=kind != "static",
         combine_static_meshes_behavior=_enum("InterchangeCombineStaticMeshesBehavior",
                                              "ALL" if combine else "DO_NOT_COMBINE"),
         build_nanite=bool(nanite) if nanite is not None else kind != "skeletal",
         generate_lightmap_u_vs=False, collision=collision != "none", create_physics_asset=bool(physics_asset))
    if collision not in COLLISION:
        raise OpError(f"collision {collision!r}: one of {', '.join(COLLISION)}", code="bad_args",
                      candidates=closest(collision, COLLISION))
    if COLLISION[collision]:
        mp.set_editor_property("fallback_collision_type", _enum("InterchangeMeshCollision", COLLISION[collision]))
    _set(p.get_editor_property("animation_pipeline"), import_animations=bool(animations))
    mat = p.get_editor_property("material_pipeline")
    _set(mat, import_materials=bool(materials))
    _set(mat.get_editor_property("texture_pipeline"), import_textures=bool(textures))
    _set(p, import_offset_uniform_scale=float(scale))
    return p


def _stack(*pipelines):
    ov = unreal.InterchangePipelineStackOverride()
    for p in pipelines:
        ov.add_pipeline(p)
    return ov


def _gltf_pipeline():
    """Epic's glTF material pipeline (the override replaces the default stack, which has it)."""
    return EAL.load_asset(GLTF_PIPELINE)


def _abc_options(kind: str, preset: str, scale: float, groom: bool):
    if groom:
        o = unreal.GroomImportOptions()
        conv = o.get_editor_property("conversion_settings")
        sc, rot, _ = ABC_PRESETS[preset]
        _set(conv, scale=unreal.Vector(*(v * scale for v in sc)), rotation=unreal.Vector(*rot))
        o.set_editor_property("conversion_settings", conv)
        return o
    o = unreal.AbcImportSettings()
    t = {"static": "STATIC_MESH", "auto": "STATIC_MESH", "geometry_cache": "GEOMETRY_CACHE",
         "skeletal": "SKELETAL"}.get(kind)
    if t is None:
        raise OpError(f"kind {kind!r} for Alembic: static, geometry_cache or skeletal", code="bad_args")
    o.set_editor_property("import_type", _enum("AlembicImportType", t))
    conv = o.get_editor_property("conversion_settings")
    sc, rot, flip_v = ABC_PRESETS[preset]
    _set(conv, scale=unreal.Vector(*(v * scale for v in sc)), rotation=unreal.Vector(*rot), flip_v=flip_v,
         flip_u=False)
    o.set_editor_property("conversion_settings", conv)
    return o


def _usd_options(materials: bool):
    o = unreal.UsdStageImportOptions()
    _set(o, import_actors=False, import_geometry=True, import_materials=bool(materials),
         import_skeletal_animations=True, import_level_sequences=False)
    return o


# ------------------------------------------------------------------------------------------------------ textures

def texture_settings_for(path: str, role: str = "", *, save: bool = True, **overrides) -> dict:
    """Converge a texture asset's settings to its role (or to explicit overrides). Returns {"changed", "set"}."""
    t = load(path)
    want = {}
    if role:
        if role not in AL.ROLES and role != "hdr":
            raise not_found("texture role", role, list(AL.ROLES) + ["hdr"])
        if role == "hdr":
            want.update(srgb=False, compression_settings="TC_HDR")
        else:
            _, srgb, comp, _ = AL.ROLES[role]
            want.update(srgb=srgb, compression_settings=comp)
            if role == "normal":
                want["lod_group"] = "TEXTUREGROUP_WORLD_NORMAL_MAP"
    want.update({k: v for k, v in overrides.items() if v is not None})
    done = []
    for k, v in want.items():
        val = v
        if k == "compression_settings":
            val = _enum("TextureCompressionSettings", v)
        elif k == "lod_group":
            val = _enum("TextureGroup", v)
        elif k == "mip_gen_settings":
            val = _enum("TextureMipGenSettings", v)
        try:
            cur = t.get_editor_property(k)
        except Exception:
            raise OpError(f"a {type(t).__name__} has no setting {k}", code="bad_args") from None
        if str(getattr(cur, "name", cur)) == str(getattr(val, "name", val)) or cur == val:
            continue
        t.set_editor_property(k, val)
        done.append(k)
    if done and save:
        EAL.save_asset(AL.package_path(path), only_if_is_dirty=False)
    return {"changed": bool(done), "set": done}


def import_textures(*, files: list, dest: str, role: str = "", replace: bool = False, probe: bool = True) -> dict:
    """Import images and set each one's sRGB/compression by its role (from the name, else a PNG that looks like a
    normal map is one, else colour)."""
    dest = dest.rstrip("/")
    out = []
    tasks = []
    for f in files:
        if not os.path.isfile(f):
            raise OpError(f"no file {f} on the box", code="not_found", hint="push it first (client.push)")
        r = AL.texture_role(f) if not role else {"role": role}
        rl = r["role"]
        if not rl and probe and f.lower().endswith(".png") and AL.probe_png(f).get("normal_like"):
            rl = "normal"
        name = AL.safe_name(os.path.splitext(os.path.basename(f))[0])
        if not name.startswith("T_"):
            name = "T_" + name
        path = f"{dest}/{name}"
        if EAL.does_asset_exist(path) and not replace:
            out.append({"file": f, "path": path, "role": rl or "base_color", "imported": False})
            continue
        tasks.append((f, path, rl or "base_color", _task(f, dest, name, replace=True, save=False)))
    if tasks:
        _tools().import_asset_tasks([t for *_, t in tasks])
    for f, path, rl, t in tasks:
        if not EAL.does_asset_exist(path):
            raise OpError(f"importing {f} made nothing at {path}", code="engine", hint="see film-ue log")
        flip = AL.texture_role(f).get("flip_green") if rl == "normal" else None
        texture_settings_for(path, rl, save=True, flip_green_channel=True if flip else None)
        out.append({"file": f, "path": path, "role": rl, "imported": True})
    return {"textures": out, "changed": any(x["imported"] for x in out)}


@op("assets.texture", mutates=True, idempotent=True, tags=["textures"])
def texture(*, path: str, role: str = "", srgb: bool = None, compression: str = "", max_size_px: int = None,
            flip_green: bool = None, lod_group: str = "", virtual_texture: bool = None, mips: str = "") -> dict:
    """Converge a texture's settings: by role (base_color/emissive/translucency: sRGB colour; normal: TC_NORMALMAP
    linear; roughness/metallic/ao/orm/opacity/height/specular: TC_MASKS linear; hdr) and/or explicit ones.

    Args: path: /Game/... texture. role: a role (see above). srgb: override. compression: TC_DEFAULT, TC_NORMALMAP,
          TC_MASKS, TC_GRAYSCALE, TC_HDR, TC_BC7, ... max_size_px: cap (0 = none). flip_green: OpenGL normal maps.
          lod_group: TEXTUREGROUP_WORLD, TEXTUREGROUP_CHARACTER, ... virtual_texture: virtual texture streaming.
          mips: TMGS_FROM_TEXTURE_GROUP, TMGS_NO_MIPMAPS, ...
    Returns: {"path", "changed", "set": [settings written]}.
    Example: film-ue op assets.texture path=/Game/T/T_Rock_N role=normal
    """
    r = texture_settings_for(path, role, srgb=srgb, compression_settings=compression or None,
                             max_texture_size=max_size_px, flip_green_channel=flip_green, lod_group=lod_group or None,
                             virtual_texture_streaming=virtual_texture, mip_gen_settings=mips or None)
    return {"path": AL.package_path(path), **r}


@op("assets.import_textures", mutates=True, idempotent=True, tags=["import", "textures"])
def import_textures_op(*, files: list = (), folder: str = "", dest: str, role: str = "", replace: bool = False) -> dict:
    """Import image files as textures with the right settings for what each is: the role from its name
    (T_Rock_BaseColor, _Normal, _ORM, _Roughness, _AO, ... see assets.md), a PNG named nothing useful but that looks
    like a normal map is one, else colour.

    Args: files: images on the box. folder: every image in a box folder. dest: content folder. role: force one
          role for all. replace: import again over existing textures (else kept).
    Returns: {"textures": [{"file", "path", "role", "imported"}], "changed"}.
    Example: film-ue op assets.import_textures folder=/data/tex/rock dest=/Game/Rock/Textures
    """
    fl = list(files)
    if folder:
        fl += [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.lower().endswith(AL.IMAGE_EXT)]
    if not fl:
        raise OpError("give files or folder", code="bad_args")
    return import_textures(files=fl, dest=_check_path(dest + "/x").rsplit("/", 1)[0], role=role, replace=replace)


# -------------------------------------------------------------------------------------------------- any import

def import_any(*, files: list, dest: str, kind: str = "auto", skeleton: str = "", scale: float = 1.0,
               combine: bool = True, nanite: bool | None = None, collision: str = "none", lods: bool = True,
               materials: bool = True, textures: bool = True, animations: bool = False, groom: bool = False,
               abc_preset: str = "maya", replace: bool = True, name: str = "", recompute_normals: bool = False) -> dict:
    dest = dest.rstrip("/")
    if AL.valid_path(dest + "/x"):
        raise OpError(AL.valid_path(dest + "/x"), code="bad_args")
    if abc_preset not in ABC_PRESETS:
        raise OpError(f"abc_preset {abc_preset!r}: maya, max or none", code="bad_args")
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        raise OpError(f"no file {missing[0]} on the box", code="not_found", hint="push it first (client.push)")
    jobs = []
    pipe = None
    kept = []
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        nm = name if (name and len(files) == 1) else ""
        if not replace and ext not in AL.IMAGE_EXT:
            have = already_imported(f, dest)
            if have:
                kept.append({"file": f, "kind": "kept", "assets": have, "objects": [AL.object_path(h) for h in have]})
                continue
        if ext in AL.IMAGE_EXT:
            jobs.append((f, "texture", None))
        elif ext in MESH_EXT:
            if pipe is None:
                pipe = mesh_pipeline(kind=kind, skeleton=skeleton, scale=scale, combine=combine, nanite=nanite,
                                     collision=collision, lods=lods, materials=materials, textures=textures,
                                     animations=animations, recompute_normals=recompute_normals)
            stack = _stack(pipe, _gltf_pipeline()) if ext in (".gltf", ".glb") and _gltf_pipeline() else _stack(pipe)
            jobs.append((f, "mesh", _task(f, dest, nm, replace=replace, options=stack)))
        elif ext == ".abc":
            jobs.append((f, "abc", _task(f, dest, nm, replace=replace,
                                         options=_abc_options(kind, abc_preset, scale, groom))))
        elif ext in USD_EXT:
            jobs.append((f, "usd", _task(f, dest, nm, replace=replace, options=_usd_options(materials))))
        else:
            jobs.append((f, "other", _task(f, dest, nm, replace=replace)))
    imported = list(kept)
    tex = [f for f, k, _ in jobs if k == "texture"]
    if tex:
        r = import_textures(files=tex, dest=dest, replace=replace)
        for x in r["textures"]:
            imported.append({"file": x["file"], "kind": "texture", "assets": [x["path"]],
                             "objects": [AL.object_path(x["path"])], "role": x["role"]})
    tasks = [t for _, k, t in jobs if t is not None]
    if tasks:
        _tools().import_asset_tasks(tasks)
    for f, k, t in jobs:
        if t is None:
            continue
        objs = _task_objects(t)
        if not objs:
            raise OpError(f"importing {f} made nothing", code="engine",
                          hint="see film-ue log (LogInterchange); the format's plugin may be off (USD: USDImporter, "
                               "groom: HairStrands)")
        imported.append({"file": f, "kind": k, "assets": sorted({AL.package_path(o) for o in objs}), "objects": objs})
    return {"imported": imported, "changed": any(r["kind"] != "kept" for r in imported)}


def already_imported(f: str, dest: str) -> list:
    """Assets in `dest` (not below) imported from a file of this name (the AssetImportData registry tag)."""
    from .assets_catalog import _source
    base = os.path.basename(f).lower()
    out = []
    if not EAL.does_directory_exist(dest):
        return out
    for ad in _assets_under(dest, recursive=False):
        src = _source(ad)
        if src and os.path.basename(src.replace("\\", "/")).lower() == base:
            out.append(str(ad.package_name))
    return sorted(out)


@op("assets.import", mutates=True, idempotent=True, tags=["import"])
def import_files_op(files: list, dest: str, replace: bool = True, combine: bool = True, kind: str = "static",
                    skeleton: str = "", scale: float = 1.0, nanite: bool = None, collision: str = "none",
                    lods: bool = True, materials: bool = True, textures: bool = True, animations: bool = False,
                    groom: bool = False, abc_preset: str = "maya", name: str = "", detail: bool = False):
    """Import files on the box into a content folder, any format, with no dialog: FBX/OBJ/glTF/GLB (Interchange),
    Alembic (static, geometry cache, skeletal, or a groom), USD, images (settings by role, see
    assets.import_textures), WAV. Returns the new assets' object paths (or with detail, per file).

    Args: files: paths on the box. dest: content folder. replace: re-import over existing (an Interchange re-import);
          false keeps what an earlier import of the same file made in dest (changed false).
          combine: merge an FBX's parts into one static mesh. kind: static | skeletal | auto (what the file says) |
          geometry_cache (Alembic). skeleton: /Game/... Skeleton for skeletal meshes/animations (else a new one).
          scale: uniform import scale (the source's units are converted to cm first). nanite: build Nanite (default
          on for static). collision: none | box | sphere | capsule | convex | convex10 | convex26 (a simple shape
          generated). lods: import LODs in the file. materials/textures: import the file's materials and textures.
          animations: import animations. groom: an Alembic of hair curves -> a Groom asset. abc_preset: maya | max |
          none (Alembic axis conversion). name: asset name for a single file. detail: return
          {"imported": [{"file", "kind", "assets", "objects"}], "changed"}.
    Example: film-ue op assets.import 'files=["/data/props/chair.fbx"]' dest=/Game/Props/Chair collision=convex
    """
    res = import_any(files=list(files), dest=dest, replace=replace, combine=combine, kind=kind, skeleton=skeleton,
                     scale=scale, nanite=nanite, collision=collision, lods=lods, materials=materials,
                     textures=textures, animations=animations, groom=groom, abc_preset=abc_preset, name=name)
    return res if detail else [o for r in res["imported"] for o in r["objects"]]


# ------------------------------------------------------------------------------------------------- mesh settings

def _sme():
    return unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)


@op("assets.mesh", mutates=True, idempotent=True, tags=["meshes"])
def mesh(*, path: str, nanite: bool = None, nanite_keep_percent: float = None, lods: int = None,
         lod_percents: list = None, collision: str = "", convex_hulls: int = 4, lightmap_uv: bool = None,
         cpu_access: bool = None, lod_group: str = "") -> dict:
    """Converge a static mesh's build settings: Nanite, generated LODs, simple collision, lightmap UVs, CPU access.

    Args: path: /Game/... StaticMesh. nanite: on/off. nanite_keep_percent: 0..100 triangles kept by Nanite.
          lods: number of LODs to generate (1 = just the base; generated by reduction: LOD i keeps lod_percents[i] %
          of the triangles, default 100, 50, 25, 12.5...). collision: none (remove simple collision) | box | sphere |
          capsule | convex (a decomposition into convex_hulls hulls) | ndop10 | ndop18 | ndop26. lightmap_uv:
          generate lightmap UVs. cpu_access: allow CPU access (needed to read vertices at runtime).
          lod_group: a LOD group name (LargeProp, SmallProp, HighDetail, ...).
    Returns: {"path", "changed", "set": [...], "lods", "triangles", "nanite", "collision_prims"}.
    Example: film-ue op assets.mesh path=/Game/Props/SM_Chair nanite=true collision=convex convex_hulls=8
    """
    m = load(path)
    if not isinstance(m, unreal.StaticMesh):
        raise OpError(f"{AL.package_path(path)} is a {type(m).__name__}: assets.mesh works on static meshes",
                      code="bad_args")
    s = _sme()
    done = []
    if nanite is not None or nanite_keep_percent is not None:
        ns = s.get_nanite_settings(m)
        want_on = ns.get_editor_property("enabled") if nanite is None else bool(nanite)
        want_keep = (ns.get_editor_property("keep_percent_triangles") if nanite_keep_percent is None
                     else float(nanite_keep_percent) / 100.0)
        if bool(ns.get_editor_property("enabled")) != want_on or \
                abs(float(ns.get_editor_property("keep_percent_triangles")) - float(want_keep)) > 1e-6:
            ns.set_editor_property("enabled", want_on)
            ns.set_editor_property("keep_percent_triangles", float(want_keep))
            s.set_nanite_settings(m, ns, True)
            done.append("nanite")
    if lod_group:
        if str(s.get_lod_group(m)) != lod_group:
            s.set_lod_group(m, lod_group, True)
            done.append("lod_group")
    if lods is not None:
        n = max(1, int(lods))
        if s.get_lod_count(m) != n:
            pct = list(lod_percents or [100.0 / (2 ** i) for i in range(n)])[:n]
            opts = unreal.StaticMeshReductionOptions()
            opts.set_editor_property("auto_compute_lod_screen_size", True)
            red = []
            for p in pct:
                r = unreal.StaticMeshReductionSettings()
                r.set_editor_property("percent_triangles", float(p) / 100.0)
                red.append(r)
            opts.set_editor_property("reduction_settings", red)
            got = s.set_lods(m, opts)
            if got is None or int(got) < 0:
                raise OpError(f"could not generate {n} LODs on {path}", code="engine", hint="see film-ue log")
            done.append("lods")
    if collision:
        shapes = {"box": "BOX", "sphere": "SPHERE", "capsule": "CAPSULE", "ndop10": "NDOP10_X", "ndop18": "NDOP18",
                  "ndop26": "NDOP26"}
        cur = int(s.get_simple_collision_count(m) or 0)
        if collision == "none":
            if cur:
                s.remove_collisions(m)
                done.append("collision")
        elif collision == "convex":
            if int(s.get_convex_collision_count(m) or 0) != int(convex_hulls):
                s.set_convex_decomposition_collisions(m, int(convex_hulls), 16, 100000)
                done.append("collision")
        elif collision in shapes:
            if cur != 1 or m.get_editor_property("body_setup") is None:
                s.remove_collisions(m)
                s.add_simple_collisions(m, _enum("ScriptCollisionShapeType", shapes[collision]))
                done.append("collision")
        else:
            raise OpError(f"collision {collision!r}", code="bad_args",
                          candidates=closest(collision, ["none", "convex"] + list(shapes)))
    if lightmap_uv is not None:
        s.set_generate_lightmap_uv(m, bool(lightmap_uv))
        done.append("lightmap_uv")
    if cpu_access is not None and bool(m.get_editor_property("allow_cpu_access")) != bool(cpu_access):
        s.set_allow_cpu_access(m, bool(cpu_access))
        done.append("cpu_access")
    if done:
        EAL.save_asset(AL.package_path(path), only_if_is_dirty=False)
    return {"path": AL.package_path(path), "changed": bool(done), "set": done, "lods": s.get_lod_count(m),
            "triangles": int(m.get_num_triangles(0)), "nanite": bool(s.get_nanite_settings(m).get_editor_property(
                "enabled")), "collision_prims": int(s.get_simple_collision_count(m) or 0)}


# --------------------------------------------------------------------------------------------------- reimport

def source_files(obj) -> list:
    try:
        aid = obj.get_editor_property("asset_import_data")
        return [str(x) for x in (aid.extract_filenames() or [])] if aid is not None else []
    except Exception:
        return []


@op("assets.reimport", mutates=True, idempotent=True, tags=["import"])
def reimport(*, path: str, file: str = "") -> dict:
    """Re-import an asset from its source file (or from a new file), keeping its settings, with no dialog.

    Args: path: /Game/... asset. file: a new source file on the box (else the one it was imported from).
    Returns: {"path", "source", "changed"}.
    Example: film-ue op assets.reimport path=/Game/Props/SM_Chair file=/data/props/chair_v2.fbx
    """
    obj = load(path)
    src = source_files(obj)
    if file:
        if not os.path.isfile(file):
            raise OpError(f"no file {file} on the box", code="not_found", hint="push it first")
        aid = obj.get_editor_property("asset_import_data")
        if aid is None:
            raise OpError(f"{path} has no import data", code="unsupported", hint="assets.import it again instead")
        aid.scripted_add_filename(file, 0, "")
        src = [file]
    if not src or not os.path.isfile(src[0]):
        raise OpError(f"{path}'s source {src[0] if src else '(none)'} is not on the box", code="not_found",
                      hint="pass file= with the file to import from")
    params = unreal.ImportAssetParameters()
    params.set_editor_property("is_automated", True)
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    out = mgr.reimport_asset(obj, params)
    if out is None:
        raise OpError(f"could not re-import {path} from {src[0]}", code="engine",
                      hint="Interchange cannot reimport this class; assets.import replace=true over it instead")
    EAL.save_asset(AL.package_path(path), only_if_is_dirty=False)
    return {"path": AL.package_path(path), "source": src[0], "changed": True}


# ------------------------------------------------------------------------------------------------- Megascans

def import_megascans_gltf(gltf: str, dest: str, subtype: str) -> list:
    """A Fab-format Megascans .gltf the way the Fab plugin does (QuixelGLTFImporter.cpp): Epic's glTF pipelines,
    the per-type mesh/material settings, and InterchangeMegascansPipeline (it reads the gltf extras: texture slots,
    compression, which Fab parent material)."""
    types = {"3D": "MODEL3D", "Plants": "PLANT", "Surfaces": "SURFACE", "Decals": "DECAL",
             "Imperfections": "IMPERFECTION"}
    if subtype not in types:
        raise OpError(f"Megascans type {subtype!r}", code="bad_args", candidates=closest(subtype, types))
    gl = _gltf_pipeline()
    if gl is None:
        raise OpError("Epic's glTF pipeline is missing (/Interchange/Pipelines/DefaultGLTFPipeline)",
                      code="unsupported", hint="the Interchange plugins must be enabled")
    # a fresh generic pipeline (never the project's DefaultGLTFAssetsPipeline asset: edited in memory, a later
    # save_dirty_packages would write the change into the project's defaults)
    assets = unreal.InterchangeGenericAssetsPipeline()
    ms = getattr(unreal, "InterchangeMegascansPipeline", None)
    if ms is None:
        raise OpError("InterchangeMegascansPipeline is missing: the Fab plugin is off", code="unsupported",
                      hint="enable Fab, or import the .gltf with assets.import")
    ms = ms()
    ms.set_editor_property("megascan_import_type", _enum("MegascanImportType", types[subtype]))
    mp = assets.get_editor_property("mesh_pipeline")
    mat = assets.get_editor_property("material_pipeline")
    mat.set_editor_property("material_import", _enum("InterchangeMaterialImportOption", "IMPORT_AS_MATERIAL_INSTANCES"))
    meshes = subtype in ("3D", "Plants")
    _set(mp, import_static_meshes=meshes, import_skeletal_meshes=False)
    if subtype == "3D":
        mp.set_editor_property("build_nanite", True)
    if subtype == "Plants":
        mp.set_editor_property("collision", False)
        _set(assets.get_editor_property("common_meshes_properties"), recompute_normals=True)
        _set(mat.get_editor_property("texture_pipeline"), flip_normal_map_green_channel=True)
    if subtype == "Imperfections":
        mat.set_editor_property("import_materials", False)
    params = unreal.ImportAssetParameters()
    params.set_editor_property("is_automated", True)
    params.set_editor_property("override_pipelines", [unreal.SoftObjectPath(p.get_path_name())
                                                      for p in (assets, gl, ms)])
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    src = unreal.InterchangeManager.create_source_data(gltf)
    objs = mgr.import_asset(dest, src, params)
    if objs is None:
        raise OpError(f"Interchange could not import {gltf}", code="engine", hint="see film-ue log (LogInterchange)")
    return sorted({AL.package_path(o.get_path_name()) for o in objs})
