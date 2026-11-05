"""Knowing what is in the project (WP2): one asset's numbers (assets.describe), a catalog of a folder read from the
asset registry without loading anything (assets.catalog), search by words, size, class and tags ("a 45 cm chair":
assets.find), and a picture of an asset with no viewport (assets.thumbnail, through WP10's captures).

The catalog reads the tags the engine writes into every saved asset (StaticMesh.cpp GetAssetRegistryTags:
ApproxSize "XxYxZ" cm, Triangles, Vertices, LODs, NaniteEnabled, Materials, CollisionPrims; textures: Dimensions,
Format; skeletal meshes: Bones, Skeleton) so a folder of thousands of assets is listed in a second. A mesh saved while
it was still compiling has no counts; `load=true` fills those in by loading it.
"""
from __future__ import annotations

import fnmatch
import json
import os
import time

import unreal

from . import _assetlib as AL
from . import op
from .assets import EAL, _assets_under, _class_name, load, referencers, dependencies, tags_of
from ..errors import OpError, closest

CATALOG_CLASSES = ("StaticMesh", "SkeletalMesh", "Texture2D", "TextureCube", "Material", "MaterialInstanceConstant",
                   "Blueprint", "SoundWave", "AnimSequence", "GroomAsset", "GeometryCache", "NiagaraSystem",
                   "LevelSequence", "World", "Skeleton", "PhysicsAsset", "MaterialFunction")


def _tag(ad, name: str):
    """A registry tag's value, or None. (get_tag_value is bool + out FString: Python gives the string, or None
    when the tag is absent: PyGenUtil.cpp PackReturnValues.)"""
    try:
        if ad is None or not ad.is_valid():  # find_asset_data on a missing path gives an invalid AssetData
            return None
        v = ad.get_tag_value(name)
    except Exception:
        return None
    return None if v in (None, "") else str(v)


def _num(v):
    try:
        f = float(str(v).replace(",", ""))
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return None


def _size_tag(v) -> list | None:
    """ApproxSize 'XxYxZ' (cm, the bounding box's full extents) -> [x, y, z]."""
    if not v:
        return None
    try:
        parts = [float(x) for x in str(v).lower().split("x")]
        return parts if len(parts) == 3 else None
    except ValueError:
        return None


def _source(ad) -> str | None:
    raw = _tag(ad, "AssetImportData")
    if not raw:
        return None
    try:
        j = json.loads(raw)
        if isinstance(j, list) and j:
            return j[0].get("RelativeFilename") or None
    except ValueError:
        pass
    return None


def entry_from_asset_data(ad) -> dict:
    """A catalog entry from an AssetData's tags (no load)."""
    cls = _class_name(ad)
    p = str(ad.package_name)
    e = {"path": p, "name": str(ad.asset_name), "class": cls, "folder": str(ad.package_path)}
    if cls in ("StaticMesh", "SkeletalMesh"):
        e.update(size_cm=_size_tag(_tag(ad, "ApproxSize")), triangles=_num(_tag(ad, "Triangles")),
                 vertices=_num(_tag(ad, "Vertices")), lods=_num(_tag(ad, "LODs")),
                 nanite=(_tag(ad, "NaniteEnabled") or "").lower() == "true",
                 materials=_num(_tag(ad, "Materials")) if cls == "StaticMesh" else None)
        if cls == "StaticMesh":
            e["collision_prims"] = _num(_tag(ad, "CollisionPrims"))
        else:
            e.update(bones=_num(_tag(ad, "Bones")), skeleton=AL.package_path(_tag(ad, "Skeleton") or "") or None)
    elif cls.startswith("Texture"):
        dims = _tag(ad, "Dimensions")
        e.update(dimensions=[int(x) for x in dims.lower().split("x")] if dims and "x" in dims.lower() else None,
                 format=_tag(ad, "Format"), srgb=(_tag(ad, "SRGB") or "").lower() == "true",
                 compression=_tag(ad, "CompressionSettings"))
    src = _source(ad)
    if src:
        e["source"] = src
    return {k: v for k, v in e.items() if v is not None}


def _bounds_of(obj) -> list | None:
    try:
        if isinstance(obj, unreal.StaticMesh):
            b = obj.get_bounding_box()
            lo, hi = b.get_editor_property("min"), b.get_editor_property("max")
            return [round(hi.x - lo.x, 2), round(hi.y - lo.y, 2), round(hi.z - lo.z, 2)]
        if isinstance(obj, unreal.SkeletalMesh):
            b = obj.get_bounds()
            ext = b.get_editor_property("box_extent")
            return [round(2 * ext.x, 2), round(2 * ext.y, 2), round(2 * ext.z, 2)]
    except Exception:
        return None
    return None


def _catalog_file() -> str:
    d = os.path.join(unreal.Paths.project_saved_dir(), "fmbridge")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "catalog.json")


def _read_cache() -> dict:
    try:
        with open(_catalog_file(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def build(folder: str = "/Game", *, classes=CATALOG_CLASSES, load_missing: bool = False) -> list:
    out = []
    for ad in _assets_under(folder):
        cls = _class_name(ad)
        if classes and cls not in classes:
            continue
        e = entry_from_asset_data(ad)
        if load_missing and cls in ("StaticMesh", "SkeletalMesh") and not e.get("size_cm"):
            obj = EAL.load_asset(e["path"])
            e["size_cm"] = _bounds_of(obj)
            if isinstance(obj, unreal.StaticMesh):
                e["triangles"] = int(obj.get_num_triangles(0))
                e["lods"] = int(obj.get_num_lods())
        if load_missing:
            obj = EAL.load_asset(e["path"])
            t = tags_of(obj) if obj is not None else {}
            if t:
                e["tags"] = [f"{k}={v}" for k, v in sorted(t.items())] + sorted(set(t.values()))
        out.append(e)
    return out


@op("assets.catalog", mutates=False, idempotent=True, tags=["catalog"])
def catalog(*, folder: str = "/Game", cls: str = "", refresh: bool = False, load: bool = False,
            max_age_s: float = 600.0, limit: int = 2000) -> dict:
    """The assets of a folder as data, from the asset registry (no loading): path, class, size in cm, triangles,
    LODs, Nanite, material count, texture size/format, source file. Cached in Saved/fmbridge/catalog.json.

    Args: folder: content folder (recursive). cls: one class (StaticMesh, SkeletalMesh, Texture2D, Material,
          MaterialInstanceConstant, Blueprint, SoundWave, AnimSequence, GroomAsset, ...). refresh: rebuild now.
          load: also load meshes whose counts are missing, and read metadata tags (slower). max_age_s: reuse a
          cached catalog this young. limit: at most this many entries returned.
    Returns: {"folder", "count", "built_at", "entries": [{"path", "name", "class", "size_cm": [x, y, z],
             "triangles", "lods", "nanite", "materials", "dimensions", "format", "source", "tags"}]}.
    Example: film-ue op assets.catalog folder=/Game/Props cls=StaticMesh
    """
    cache = _read_cache()
    key = f"{folder}|{int(load)}"
    hit = cache.get(key)
    if not hit or refresh or time.time() - hit.get("built_at", 0) > max_age_s:
        hit = {"built_at": time.time(), "entries": build(folder, load_missing=load)}
        cache[key] = hit
        try:
            with open(_catalog_file(), "w", encoding="utf-8") as fh:
                json.dump(cache, fh)
        except OSError:
            pass
    ents = [e for e in hit["entries"] if not cls or e.get("class") == cls]
    return {"folder": folder, "count": len(ents), "built_at": hit["built_at"], "entries": ents[:limit]}


@op("assets.find", mutates=False, idempotent=True, tags=["catalog"])
def find(*, query: str = "", cls: str = "", folder: str = "/Game", name: str = "", tags: dict = None,
         min_size_cm: list = None, max_size_cm: list = None, limit: int = 10, refresh: bool = False) -> dict:
    """Search assets by what they are and how big: words (name, folders, tags; a few synonyms: sofa/couch...), a
    size ("a 45 cm chair", "table 120x80 cm", "lamp 1.5 m tall"), class, a name glob, tags, size bounds. Each hit
    says how far its size is from the asked one and the uniform scale that would make it exact.

    Args: query: plain words with optional sizes (mm/cm/m/in/ft; no unit = cm; tall/wide/long pick the axis).
          cls: StaticMesh, SkeletalMesh, Texture2D, MaterialInstanceConstant, ... folder: where to look.
          name: a glob on the asset name (SM_Chair*). tags: {key: value} metadata tags (assets.tag) to match.
          min_size_cm / max_size_cm: [x, y, z] bounds the size must be within (0 = no bound on that axis).
          limit: at most this many. refresh: rebuild the catalog first.
    Returns: {"query": parsed, "hits": [{"path", "class", "size_cm", "score" 0..1, "size_error", "scale", ...}],
             "count"}. Nothing found: hits [] and a hint.
    Example: film-ue op assets.find 'query=a 45 cm chair' cls=StaticMesh
    """
    cat = catalog(folder=folder, cls=cls, refresh=refresh, load=bool(tags), limit=10 ** 6)["entries"]
    if name:
        cat = [e for e in cat if fnmatch.fnmatchcase(e["name"].lower(), name.lower())]
    if tags:
        want = {f"{k}={v}" for k, v in tags.items()}
        cat = [e for e in cat if want <= set(e.get("tags", []))]
    for bound, cmp in ((min_size_cm, lambda a, b: a >= b), (max_size_cm, lambda a, b: a <= b)):
        if bound:
            cat = [e for e in cat if e.get("size_cm") and all(not b or cmp(a, b) for a, b in zip(e["size_cm"], bound))]
    hits = AL.search(cat, query, limit=limit) if query else sorted(cat, key=lambda e: e["path"])[:limit]
    out = {"query": AL.parse_query(query), "hits": hits, "count": len(hits)}
    if not hits:
        out["hint"] = (f"nothing in {folder} fits; try fewer words, a wider folder, refresh=true, or import one "
                       f"(assets.import / fab.library)")
    return out


def material_slots(m) -> list:
    """[{"index", "name", "material"}] of a static or skeletal mesh asset."""
    prop = "static_materials" if isinstance(m, unreal.StaticMesh) else "materials"
    out = []
    for i, s in enumerate(m.get_editor_property(prop) or []):
        mi = s.get_editor_property("material_interface")
        out.append({"index": i, "name": str(s.get_editor_property("material_slot_name")),
                    "material": AL.package_path(mi.get_path_name()) if mi is not None else None})
    return out


@op("assets.describe", mutates=False, idempotent=True, tags=["catalog"])
def describe(*, path: str, refs: bool = True) -> dict:
    """One asset as numbers: class, size in cm and bounds, triangles/vertices per LOD, Nanite, collision, material
    slots (meshes); size, sRGB, compression, LOD group (textures); parent and parameters (materials: see
    mat.describe); skeleton, bones (skeletal); duration (sounds); source file; metadata tags; who uses it.

    Args: path: /Game/... asset. refs: include referencers/dependencies.
    Returns: {"path", "class", ...per class..., "source", "tags", "referencers", "dependencies"}.
    Example: film-ue op assets.describe path=/Game/Props/SM_Chair
    """
    p = AL.package_path(path)
    obj = load(p)
    cls = type(obj).__name__
    out = {"path": p, "class": cls}
    if isinstance(obj, unreal.StaticMesh):
        sme = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        n = int(obj.get_num_lods())
        out.update(size_cm=_bounds_of(obj), lods=n, triangles=[int(obj.get_num_triangles(i)) for i in range(n)],
                   vertices=[int(obj.get_num_vertices(i)) for i in range(n)],
                   nanite=bool(sme.get_nanite_settings(obj).get_editor_property("enabled")),
                   collision={"simple": int(sme.get_simple_collision_count(obj) or 0),
                              "convex": int(sme.get_convex_collision_count(obj) or 0)},
                   uv_channels=int(sme.get_num_uv_channels(obj, 0)), materials=material_slots(obj))
    elif isinstance(obj, unreal.SkeletalMesh):
        sk = obj.get_editor_property("skeleton")
        pa = obj.get_editor_property("physics_asset")
        ad = EAL.find_asset_data(p)
        out.update(size_cm=_bounds_of(obj), skeleton=AL.package_path(sk.get_path_name()) if sk else None,
                   physics_asset=AL.package_path(pa.get_path_name()) if pa else None,
                   bones=_num(_tag(ad, "Bones")) if ad else None, triangles=_num(_tag(ad, "Triangles")) if ad else None,
                   lods=int(unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem).get_lod_count(obj)),
                   materials=material_slots(obj))
    elif isinstance(obj, unreal.Texture):
        ad = EAL.find_asset_data(p)
        dims = _tag(ad, "Dimensions") if ad else None
        g = lambda k: obj.get_editor_property(k)
        out.update(dimensions=[int(x) for x in dims.lower().split("x")] if dims and "x" in dims.lower() else None,
                   srgb=bool(g("srgb")), compression=str(getattr(g("compression_settings"), "name",
                                                                 g("compression_settings"))),
                   lod_group=str(getattr(g("lod_group"), "name", g("lod_group"))),
                   max_size_px=int(g("max_texture_size") or 0),
                   virtual_texture=bool(g("virtual_texture_streaming")),
                   role_by_name=AL.texture_role(p.rsplit("/", 1)[-1])["role"] or None)
    elif isinstance(obj, unreal.MaterialInterface):
        from .mat import describe as mdesc
        out.update({k: v for k, v in mdesc(path=p).items() if k not in ("path", "class")})
    elif isinstance(obj, unreal.SoundWave):
        try:
            out["duration_s"] = round(float(obj.get_editor_property("duration")), 3)
        except Exception:
            pass
    from .assets_import import source_files
    out["source"] = (source_files(obj) or [None])[0]
    out["tags"] = tags_of(obj)
    if refs:
        out["referencers"] = referencers(p)
        out["dependencies"] = dependencies(p)
    return out


@op("assets.thumbnail", mutates=False, idempotent=True, tags=["gpu", "catalog"])
def thumbnail(*, path: str, out_dir: str, views: int = 1, size_px: int = 512, elevation_deg: float = 20.0,
              yaw_deg: float = 35.0, loc: list = (0.0, 0.0, -50000.0), light: bool = True):
    """Pictures of an asset with no viewport: a temporary actor of it is placed away from the set, captured alone
    (WP10's view.turntable with isolate), and removed. One view (a 3/4 shot) or several around it plus a sheet.
    The open level's lights reach it only if it is placed among them (loc); `light` adds a temporary point light
    above and in front of it, removed afterwards.

    Args: path: /Game/... StaticMesh, SkeletalMesh or Blueprint. out_dir: where the PNGs go on the box. views: how
          many. size_px: square size. elevation_deg/yaw_deg: the camera's angle above and around it. loc: where the
          temporary actor stands [x, y, z] cm (default far below the set). light: add a temporary key light.
    Returns: {"path", "views": [{"yaw", "path"}], "sheet", "size_cm"}. Multi-tick.
    Example: film-ue op assets.thumbnail path=/Game/Props/SM_Chair out_dir=/tmp/thumbs/chair views=4
    """
    from ._util import find_actor
    from .view import turntable
    obj = load(path)
    label = f"__thumb_{AL.split(path)[1]}"
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    old = find_actor(label)
    if old is not None:
        eas.destroy_actor(old)
    actor = eas.spawn_actor_from_object(obj, unreal.Vector(*[float(v) for v in loc]),
                                        unreal.Rotator(roll=0, pitch=0, yaw=0))
    if actor is None:
        raise OpError(f"cannot place a {type(obj).__name__} to photograph it", code="unsupported",
                      hint="thumbnails work for meshes and actor Blueprints")
    actor.set_actor_label(label)
    lamp = None
    if light:
        size = _bounds_of(obj) or [100.0, 100.0, 100.0]
        r = max(size) or 100.0
        lamp = eas.spawn_actor_from_class(unreal.PointLight, unreal.Vector(loc[0] + 1.5 * r, loc[1] + 1.0 * r,
                                                                          loc[2] + 2.0 * r))
        if lamp is not None:
            lamp.set_actor_label(label + "_light")
            c = lamp.get_component_by_class(unreal.PointLightComponent)
            if c is not None:
                c.set_editor_property("attenuation_radius", 10.0 * r)
                c.set_intensity(8.0 * r * r / 100.0)
    try:
        res = yield from turntable(target=label, out_dir=out_dir, views=int(views), elevation_deg=elevation_deg,
                                   width_px=size_px, height_px=size_px, isolate=True, start_yaw_deg=yaw_deg,
                                   sheet=int(views) > 1)
    finally:
        eas.destroy_actor(actor)
        if lamp is not None:
            eas.destroy_actor(lamp)
    return {"path": AL.package_path(path), "views": [{"yaw": v["yaw"], "path": v["path"]} for v in res["views"]],
            "sheet": res.get("sheet"), "size_cm": _bounds_of(obj)}
