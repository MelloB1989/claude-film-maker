"""Hair (grooms) by numbers, on any actor with GroomComponents (a built MetaHuman's Hair/Eyebrows/Beard/...):
read it (`groom.describe`), tune it per instance (`groom.set`: strand width, root/tip scale, shadow density, LOD
bias, length, and the hair material's melanin/redness/roughness/white/light/dye), guard the sky-lighting trap
(`groom.sky_lighting`), and measure what the hair looks like (`groom.measure`: coverage and colour from captures),
so every change comes with a before/after in numbers.

Per-instance only: geometry overrides go in the component's GroomGroupsDesc (the asset is untouched, nothing is
rebuilt), colours in dynamic material instances on the component (a plain material swap, which the renderer handles;
a parameter change on a worn instance is safe: unreal/README.md). Strand count ("density") lives in the groom asset
(decimation, a rebuild shared by every user of the asset): `groom.set strand_fraction=` changes it only with
`edit_asset=true`.

Material parameter names are the MetaHuman hair materials' (MetaHumanDefaultGroomPipeline.h, MaterialParamName):
melanin hairMelanin, redness hairRedness, roughness HairRoughness, white WhiteAmount, light LightAmount, dye HairDye;
any other parameter goes through `params`."""
from __future__ import annotations

import math
import os

import unreal

from . import op
from ..errors import OpError
from ..qa import framing as _framing
from ..qa import image as _image
from ..qa import metrics as _metrics
from .view import _xyz, capture, camera_info, find_actor, read_pixels, remove_rig, to_image

PARAMS = {"melanin": "hairMelanin", "redness": "hairRedness", "roughness": "HairRoughness", "white": "WhiteAmount",
          "light": "LightAmount"}
VECTOR_PARAMS = {"dye": "HairDye"}
# GroomGroupsDesc fields: our argument -> (property, its override flag or None)
DESC = {"width_cm": ("hair_width", "hair_width_override"), "root_scale": ("hair_root_scale", "hair_root_scale_override"),
        "tip_scale": ("hair_tip_scale", "hair_tip_scale_override"),
        "shadow_density": ("hair_shadow_density", "hair_shadow_density_override"), "lod_bias": ("lod_bias", None),
        "length_scale": ("hair_length_scale", "hair_length_scale_override")}
SKY_CVAR = "r.HairStrands.SkyLighting"
FACE_PARTS = ("Face", "Body")
EMPTY_DEPTH = 1.0e7
MID_PREFIX = "FMQA_"


def _grooms(a) -> list:
    cls = getattr(unreal, "GroomComponent", None)
    if cls is None:
        raise OpError("this editor has no GroomComponent (the HairStrands plugin is off)", code="unsupported",
                      hint="enable the HairStrands plugin (editor.plugins)")
    return list(a.get_components_by_class(cls))


def _pick(label: str, component: str = "") -> list:
    """The actor's groom components (all, or the one named), fetched afresh (Blueprint components go stale)."""
    a = find_actor(label)
    comps = _grooms(a)
    if not comps:
        raise OpError(f"{label} has no groom components", code="not_found",
                      hint="qa.parts lists its components; a MetaHuman needs its build (mh.build) for hair")
    if component:
        got = [c for c in comps if c.get_name() == component]
        if not got:
            from ..errors import not_found
            raise not_found("groom component", component, [c.get_name() for c in comps],
                            hint=f"groom.describe label={label} lists them")
        return got
    return comps


def _path(o) -> str | None:
    return o.get_path_name() if isinstance(o, unreal.Object) else None


def _scalar_names(m) -> list:
    try:
        return [str(n) for n in unreal.MaterialEditingLibrary.get_scalar_parameter_names(m)]
    except Exception:
        return []


def _vector_names(m) -> list:
    try:
        return [str(n) for n in unreal.MaterialEditingLibrary.get_vector_parameter_names(m)]
    except Exception:
        return []


def _get_scalar(m, name: str):
    try:
        if isinstance(m, unreal.MaterialInstanceDynamic):
            return float(m.get_scalar_parameter_value(name))
        if isinstance(m, unreal.MaterialInstanceConstant):
            return float(unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(m, name))
    except Exception:
        return None
    return None


def _desc(d) -> dict:
    out = {}
    for arg, (prop, flag) in DESC.items():
        try:
            v = d.get_editor_property(prop)
            out[arg] = round(float(v), 6)
            if flag:
                out[arg + "_override"] = bool(d.get_editor_property(flag))
        except Exception:
            continue
    return out


def _materials(c) -> list:
    out = []
    for i, m in enumerate(c.get_materials()):
        names = _scalar_names(m)
        out.append({"slot": i, "material": _path(m), "dynamic": isinstance(m, unreal.MaterialInstanceDynamic),
                    "params": {k: _get_scalar(m, n) for k, n in PARAMS.items() if n in names},
                    "scalar_names": names[:40]})
    return out


def _cvar(name: str):
    try:
        return int(unreal.SystemLibrary.get_console_variable_int_value(name))
    except Exception:
        return None


@op("groom.describe", mutates=False, idempotent=True)
def describe(*, label: str) -> dict:
    """An actor's grooms as numbers: per component its groom/binding assets, per group the instance overrides
    (width_cm, root/tip scale, shadow density, LOD bias, length scale, and whether each is overridden), per material
    slot the hair parameters (melanin, redness, roughness, white, light) and every scalar parameter name; plus the
    sky-lighting cvar.

    Returns: {"label", "components": [{"name", "groom", "binding", "visible", "groups": [...], "materials": [...]}],
    "cvars": {"r.HairStrands.SkyLighting"}}.
    Example: film-ue op groom.describe label=Ada
    """
    comps = []
    for c in _pick(label):
        comps.append({"name": c.get_name(), "groom": _path(c.get_editor_property("groom_asset")),
                      "binding": _path(c.get_editor_property("binding_asset")), "visible": bool(c.is_visible()),
                      "groups": [_desc(d) for d in c.get_editor_property("groom_groups_desc")],
                      "materials": _materials(c)})
    return {"label": label, "components": comps, "cvars": {SKY_CVAR: _cvar(SKY_CVAR)}}


def _set_desc(c, group: int, values: dict) -> dict:
    """Write instance overrides into one component's GroomGroupsDesc; returns {group: {arg: [before, after]}}."""
    descs = list(c.get_editor_property("groom_groups_desc"))
    if not descs:
        raise OpError(f"{c.get_name()} has no groom groups yet (no groom asset, or not registered)", code="failed",
                      hint="check groom.describe; a MetaHuman's hair appears after mh.build")
    idx = range(len(descs)) if group < 0 else [group]
    if group >= len(descs):
        raise OpError(f"group {group}: {c.get_name()} has {len(descs)}", code="bad_args")
    changes = {}
    for g in idx:
        d = descs[g]
        for arg, v in values.items():
            prop, flag = DESC[arg]
            before = float(d.get_editor_property(prop))
            on = bool(d.get_editor_property(flag)) if flag else True
            if abs(before - float(v)) > 1e-6 or not on:
                d.set_editor_property(prop, float(v))
                if flag:
                    d.set_editor_property(flag, True)
                changes.setdefault(g, {})[arg] = [round(before, 6), float(v)]
    if changes:
        c.set_editor_property("groom_groups_desc", descs)
    return changes


def _set_params(c, scalars: dict, vectors: dict) -> dict:
    """Hair material parameters on every slot whose material has them (a dynamic instance is made where needed)."""
    changes = {}
    mats = list(c.get_materials())
    for i, m in enumerate(mats):
        names, vnames = _scalar_names(m), _vector_names(m)
        want_s = {n: v for n, v in scalars.items() if n in names}
        want_v = {n: v for n, v in vectors.items() if n in vnames}
        if not (want_s or want_v):
            continue
        before = {n: _get_scalar(m, n) for n in want_s}
        if all(before[n] is not None and abs(before[n] - float(v)) < 1e-6 for n, v in want_s.items()) and not want_v:
            continue
        mid = m if isinstance(m, unreal.MaterialInstanceDynamic) else c.create_dynamic_material_instance(
            i, m, f"{MID_PREFIX}{c.get_name()}_{i}")
        if mid is None:
            raise OpError(f"could not make a dynamic material instance on {c.get_name()} slot {i}", code="engine")
        for n, v in want_s.items():
            mid.set_scalar_parameter_value(n, float(v))
        for n, v in want_v.items():
            col = list(v) + [1.0] * (4 - len(v))
            mid.set_vector_parameter_value(n, unreal.LinearColor(r=col[0], g=col[1], b=col[2], a=col[3]))
        changes[i] = {**{n: [before[n], float(v)] for n, v in want_s.items()}, **{n: list(v) for n, v in want_v.items()}}
    return changes


def _facing(a) -> list:
    """Which way the character faces (horizontal): head -> eyes when a Face has eye bones, else the actor's forward."""
    from .qa import bones_of
    try:
        b, _ = bones_of(a.get_actor_label())
    except Exception:
        b = {}
    if "head" in b and "eyes" in b:
        dx, dy = b["eyes"][0] - b["head"][0], b["eyes"][1] - b["head"][1]
        n = math.hypot(dx, dy)
        if n > 1e-3:
            return [dx / n, dy / n, 0.0]
    f = a.get_actor_forward_vector()
    n = math.hypot(f.x, f.y) or 1.0
    return [f.x / n, f.y / n, 0.0]


def _views(a, comps, n: int, fov: float = 30.0) -> list:
    """Cameras around the hair's bounds: n views starting from the face, slightly above."""
    o, e, r = unreal.SystemLibrary.get_component_bounds(comps[0])
    lo = [o.x - e.x, o.y - e.y, o.z - e.z]
    hi = [o.x + e.x, o.y + e.y, o.z + e.z]
    for c in comps[1:]:
        o2, e2, _ = unreal.SystemLibrary.get_component_bounds(c)
        lo = [min(lo[k], v) for k, v in enumerate((o2.x - e2.x, o2.y - e2.y, o2.z - e2.z))]
        hi = [max(hi[k], v) for k, v in enumerate((o2.x + e2.x, o2.y + e2.y, o2.z + e2.z))]
    centre = [(lo[k] + hi[k]) / 2 for k in range(3)]
    radius = max(10.0, math.sqrt(sum(((hi[k] - lo[k]) / 2) ** 2 for k in range(3))))
    dist = 1.15 * radius / math.sin(math.radians(fov / 2))
    f = _facing(a)
    base = math.degrees(math.atan2(f[1], f[0]))
    names = {0: "front", 90: "left", 180: "back", 270: "right"}
    out = []
    for k in range(max(1, n)):
        off = 360.0 * k / max(1, n)
        yaw = math.radians(base + off)
        loc = [centre[0] + dist * math.cos(yaw), centre[1] + dist * math.sin(yaw), centre[2] + 0.25 * dist]
        out.append((names.get(round(off), f"yaw{off:03.0f}"), {"name": "groom", "loc": loc,
                                                                "rot": _framing.look_at(loc, centre), "fov": fov,
                                                                "aspect": 1.0, "post": None}))
    return out


def _measure(label: str, component: str = "", views: int = 2, size_px: int = 256, out_dir: str = "", tag: str = ""):
    """Generator: per view, the hair mask (groom-only depth), the share of the head silhouette it covers, and the
    hair's colour in the lit scene."""
    a = find_actor(label)
    comps = _pick(label, component)
    face = [c for c in a.get_components_by_class(unreal.PrimitiveComponent) if c.get_name() in FACE_PARTS]
    per = {}
    try:
        for name, cam in _views(a, comps, views):
            rt = yield from capture(cam, size_px, size_px, "depth", show_only=comps, warmup=1)
            hair = [d < EMPTY_DEPTH for d in read_pixels(rt, "r")[0]]
            head = hair
            if face:
                rt = yield from capture(cam, size_px, size_px, "depth", show_only=face + comps, warmup=1)
                head = [d < EMPTY_DEPTH for d in read_pixels(rt, "r")[0]]
            rt = yield from capture(cam, size_px, size_px, "final", warmup=4)
            img = to_image(rt)
            m = _metrics.masked(img, hair)
            m["share_of_head"] = round(m["pixels"] / max(1, sum(head)), 4)
            if out_dir:
                from ..qa.geometry import mask_overlay
                p = os.path.join(out_dir, f"groom_{tag or 'now'}_{name}.png")
                _image.write(img, p)
                _image.write(mask_overlay(img, bytearray(255 if h else 0 for h in hair), (0, 255, 120), 0.35),
                             p[:-4] + "_mask.png")
                m["still"] = p
            per[name] = m
    finally:
        remove_rig()
    seen = [v for v in per.values() if v.get("pixels")]
    agg = {}
    if seen:
        agg = {"share_of_head": round(sum(v["share_of_head"] for v in seen) / len(seen), 4),
               "stops": round(sum(v["stops"] for v in seen) / len(seen), 2),
               "mean_rgb": [round(sum(v["mean_rgb"][k] for v in seen) / len(seen), 1) for k in range(3)],
               "saturation": round(sum(v["saturation"] for v in seen) / len(seen), 3)}
        h, s, val = _image.hsv(*[c / 255 for c in agg["mean_rgb"]])
        agg.update(hue=round(h, 1), name=_image.hue_name(h, s, val))
    return {"views": per, "mean": agg}


def _delta(before: dict, after: dict) -> dict:
    b, a = before.get("mean") or {}, after.get("mean") or {}
    if not (a and b):
        return {}
    return {"share_of_head": round(a["share_of_head"] - b["share_of_head"], 4), "stops": round(a["stops"] - b["stops"], 2),
            "mean_rgb": [round(y - x, 1) for x, y in zip(b["mean_rgb"], a["mean_rgb"])],
            "saturation": round(a["saturation"] - b["saturation"], 3)}


@op("groom.measure", mutates=False, idempotent=True, tags=["gpu"])
def measure(*, label: str, component: str = "", views: int = 2, size_px: int = 256, out_dir: str = ""):
    """What the hair looks like, in numbers: per view, the hair's pixels (a groom-only depth capture), its share of
    the head's silhouette (thinner or shorter hair shows more scalp/face: a density proxy), and its colour in the lit
    scene (mean RGB, stops from mid grey, saturation, hue and its name).

    Args: label: the character. component: one groom component (default all). views: around the head from the face
    (2: front, back; 4 adds the sides). size_px: capture size. out_dir: write each view's still and mask.
    Returns: {"views": {name: {pixels, share_of_head, mean_rgb, stops, saturation, hue, name, box, still?}},
    "mean": {...}}. Multi-tick.
    Example: film-ue op groom.measure label=Ada views=4 out_dir=/srv/qa/hair
    """
    return (yield from _measure(label, component, views, size_px, out_dir))


@op("groom.set", mutates=True, idempotent=True, tags=["gpu"])
def set_(*, label: str, component: str = "", group: int = -1, width_cm: float | None = None,
         root_scale: float | None = None, tip_scale: float | None = None, shadow_density: float | None = None,
         lod_bias: float | None = None, length_scale: float | None = None, melanin: float | None = None,
         redness: float | None = None, roughness: float | None = None, white: float | None = None,
         light: float | None = None, dye: list | None = None, params: dict | None = None,
         strand_fraction: float | None = None, edit_asset: bool = False, measure_views: int = 0,
         out_dir: str = ""):
    """Tune hair on one actor, per instance, and (with measure_views) measure it before and after.

    Args: label: the character. component: one groom component (default all: hair, brows, beard, ...). group: one
    hair group (default all). width_cm: strand width (cm; MetaHuman scalp hair ~0.005-0.01). root_scale/tip_scale:
    width multipliers along the strand. shadow_density: how opaque the hair's self-shadow is (thin hair: lower).
    lod_bias: -7..7 (positive: coarser LODs, fewer strands drawn). length_scale: 0..1 of the strand length.
    melanin/redness/roughness/white/light: 0..1 hair material parameters (hairMelanin, hairRedness, HairRoughness,
    WhiteAmount, LightAmount); dye: [r, g, b] linear (HairDye); params: other material parameters by their names,
    {name: number | [r, g, b]}. strand_fraction: 0..1 of the strands (asset decimation; needs edit_asset=true:
    rebuilds the groom asset for EVERY actor using it, and is saved only with assets.save). measure_views: measure
    with groom.measure before and after (0: no measuring). out_dir: stills of both measurements.
    Returns: {"changed", "groups": {component: {group: {arg: [before, after]}}}, "materials": {component: {slot:
    {param: [before, after]}}}, "asset": {...}?, "before"?, "after"?, "delta"?}. Multi-tick.
    Example: film-ue op groom.set label=Ada melanin=0.95 redness=0.1 width_cm=0.008 measure_views=2
    """
    values = {k: v for k, v in (("width_cm", width_cm), ("root_scale", root_scale), ("tip_scale", tip_scale),
                                ("shadow_density", shadow_density), ("lod_bias", lod_bias),
                                ("length_scale", length_scale)) if v is not None}
    scalars = {PARAMS[k]: float(v) for k, v in (("melanin", melanin), ("redness", redness), ("roughness", roughness),
                                                ("white", white), ("light", light)) if v is not None}
    vectors = {VECTOR_PARAMS["dye"]: list(dye)} if dye is not None else {}
    for k, v in (params or {}).items():
        (vectors if isinstance(v, (list, tuple)) else scalars)[k] = v
    for k in ("melanin", "redness", "roughness", "white", "light", "length_scale"):
        v = locals()[k]
        if v is not None and not 0.0 <= float(v) <= 1.0:
            raise OpError(f"{k} {v}: 0..1", code="bad_args")
    if width_cm is not None and not 0.0001 <= width_cm <= 1.0:
        raise OpError(f"width_cm {width_cm}: 0.0001..1 cm (strands are ~0.005-0.01 cm)", code="bad_args")
    if strand_fraction is not None and not edit_asset:
        raise OpError("strand_fraction changes the groom asset (all its users, a rebuild): pass edit_asset=true",
                      code="bad_args", hint="or thin the look per instance: shadow_density, lod_bias, width_cm")
    if not (values or scalars or vectors or strand_fraction is not None):
        raise OpError("nothing to set", code="bad_args", hint="give width_cm, melanin, ... (groom.describe shows them)")
    comps = _pick(label, component)  # validates before anything changes
    if scalars or vectors:
        have = set()
        for c in comps:
            for m in c.get_materials():
                have |= set(_scalar_names(m)) | set(_vector_names(m))
        missing = [n for n in list(scalars) + list(vectors) if n not in have]
        if missing:
            from ..errors import closest
            raise OpError(f"no hair material on {label} has {missing}", code="not_found",
                          candidates=closest(missing[0], sorted(have)), hint="groom.describe lists scalar_names")
    out = {"changed": False, "groups": {}, "materials": {}}
    if measure_views:
        out["before"] = yield from _measure(label, component, measure_views, out_dir=out_dir, tag="before")
    for c in _pick(label, component):  # afresh: a Blueprint actor may have rebuilt them
        name = c.get_name()
        if values:
            ch = _set_desc(c, group, values)
            if ch:
                out["groups"][name] = ch
    for c in _pick(label, component):
        name = c.get_name()
        if scalars or vectors:
            ch = _set_params(c, scalars, vectors)
            if ch:
                out["materials"][name] = ch
    if strand_fraction is not None:
        out["asset"] = _decimate(_pick(label, component), float(strand_fraction))
    out["changed"] = bool(out["groups"] or out["materials"] or (out.get("asset") or {}).get("changed"))
    for _ in range(3):  # let the render state pick the change up
        yield
    lost = _verify(label, component, group, values, scalars)
    if lost:
        out["lost"] = lost
        out["hint"] = "a Blueprint construction script reset these: set them again, or on the Blueprint's defaults"
    if measure_views:
        out["after"] = yield from _measure(label, component, measure_views, out_dir=out_dir, tag="after")
        out["delta"] = _delta(out["before"], out["after"])
    return out


def _verify(label, component, group, values, scalars) -> dict:
    """What did not stick (read back afresh)."""
    lost = {}
    for c in _pick(label, component):
        descs = list(c.get_editor_property("groom_groups_desc"))
        for g in (range(len(descs)) if group < 0 else [group]):
            if g >= len(descs):
                continue
            got = _desc(descs[g])
            for arg, v in values.items():
                if arg in got and abs(got[arg] - float(v)) > 1e-4:
                    lost.setdefault(c.get_name(), {})[f"group{g}.{arg}"] = got[arg]
        for i, m in enumerate(c.get_materials()):
            for n, v in scalars.items():
                if n in _scalar_names(m):
                    cur = _get_scalar(m, n)
                    if cur is not None and abs(cur - float(v)) > 1e-4:
                        lost.setdefault(c.get_name(), {})[f"slot{i}.{n}"] = cur
    return lost


def _decimate(comps, fraction: float) -> dict:
    """Asset-level strand decimation on each distinct groom asset (HairGroupsInterpolation.DecimationSettings
    .CurveDecimation); set through set_editor_property so the editor rebuilds it."""
    if not 0.0 < fraction <= 1.0:
        raise OpError(f"strand_fraction {fraction}: (0, 1]", code="bad_args")
    done, changed = {}, False
    for c in comps:
        asset = c.get_editor_property("groom_asset")
        if not isinstance(asset, unreal.Object) or _path(asset) in done:
            continue
        groups = list(asset.get_editor_property("hair_groups_interpolation"))
        before = []
        for g in groups:
            ds = g.get_editor_property("decimation_settings")
            before.append(float(ds.get_editor_property("curve_decimation")))
            ds.set_editor_property("curve_decimation", fraction)
            g.set_editor_property("decimation_settings", ds)
        if any(abs(b - fraction) > 1e-6 for b in before):
            asset.set_editor_property("hair_groups_interpolation", groups)
            changed = True
        done[_path(asset)] = {"before": before, "after": fraction}
    return {"assets": done, "changed": changed, "note": "saved only with assets.save (the groom asset is shared)"}


# --- the LOD lock (round 5: her hair shortened at the cut to a wide shot) ---------------------------------------
# What decides how much hair a groom draws (UE 5.8.4 source, HairStrandsCore):
# - the LOD index: LODSync's ForcedLOD reaches a groom only if the groom's NAME is in LODSync.ComponentsToSync
#   (resolved to live components on register: LODSyncComponent.cpp InitializeSyncComponents); else the groom picks
#   its LOD from screen size (GroomManager.cpp GetHairInstanceLODIndex) and MetaHuman grooms go to cards/helmet
#   meshes on a small screen size. UGroomComponent::SetForcedLOD is not a UFUNCTION: LODSync is the only Python path.
# - Auto LOD (r.HairStrands.LODMode, default 1 = Auto, RenderUtils.cpp; per asset GroomAsset.LODMode Default/Manual/
#   Auto): even at a forced LOD 0 the strands draw RestCurveCount x clamp(screen size + bias) curves
#   (GroomManager.cpp ComputeActiveCurveCount), shuffled, so a wide shot thins the hair to a fraction and its
#   sparse long ends vanish: SHORTER hair. bAutoLOD is read once per groom in InitResources (register), so the mode
#   cvar must be set BEFORE the render world registers its grooms (MRQ's PIE world does, after this op);
#   r.HairStrands.AutoLOD.Bias is read every frame, and 1.0 keeps every curve whatever the mode.
# - MRQ's "Use LOD Zero" (game overrides) sets r.ForceLOD / r.SkeletalMeshLODBias only: never the grooms.
LOCK_CVARS = {"r.HairStrands.LODMode": 0, "r.HairStrands.AutoLOD.Bias": 1.0, "r.HairStrands.UseCardsInsteadOfStrands": 0}
GEOMETRY = ("STRANDS", "CARDS", "MESHES")


def _cvar_num(name: str):
    try:
        return float(unreal.SystemLibrary.get_console_variable_float_value(name))
    except Exception:
        return _cvar(name)


def _enum_name(v) -> str:
    s = str(getattr(v, "name", v))
    return s.split(".")[-1].upper()


def _asset_lods(asset, lod: int) -> dict:
    """The groom asset's LOD setup: mode, bias, and per group the geometry drawn at `lod` (+ visible)."""
    out = {"lod_mode": None, "auto_lod_bias": None, "groups": []}
    if not isinstance(asset, unreal.Object):
        return out
    for k in ("lod_mode", "auto_lod_bias"):
        try:
            v = asset.get_editor_property(k)
            out[k] = _enum_name(v) if k == "lod_mode" else round(float(v), 4)
        except Exception:
            pass
    try:
        for g in asset.get_editor_property("hair_groups_lod"):
            lods = list(_lods(g))
            row = {"lods": len(lods)}
            if lod < len(lods):
                s = lods[lod]
                row.update(geometry=_enum_name(s.get_editor_property("geometry_type")),
                           visible=bool(s.get_editor_property("visible")),
                           screen_size=round(float(s.get_editor_property("screen_size")), 4),
                           curve_decimation=round(float(s.get_editor_property("curve_decimation")), 4))
            out["groups"].append(row)
    except Exception as e:  # noqa: BLE001 - report what could not be read
        out["error"] = f"{type(e).__name__}: {e}"[:160]
    return out


def _lods(group) -> list:
    """FHairGroupsLOD.LODs: Python spells it `lo_ds` (UE's snake case of "LODs", the 5.6 API pages); `lods` too."""
    for k in ("lo_ds", "lods"):
        try:
            return group.get_editor_property(k)
        except Exception:
            continue
    raise OpError("FHairGroupsLOD has neither lo_ds nor lods", code="engine",
                  hint="film-ue exec -c 'print(dir(unreal.HairGroupsLOD))' and fix groom._lods")


def _sync_debug(c) -> dict:
    """LODSync's own view of what it drives: {component name: rendered LOD} (GetLODSyncDebugText, the only
    readback of a groom's forced LOD from Python)."""
    out = {}
    try:
        text = str(c.get_lod_sync_debug_text())
    except Exception:
        return out
    for line in text.splitlines():
        if " : " in line:
            name, rest = line.split(" : ", 1)
            try:
                out[name.strip()] = int(rest.split()[0])
            except (ValueError, IndexError):
                continue
    return out


def _lock_state(label: str, lod: int) -> dict:
    """What the render will draw for one character's grooms, read afresh, with every problem and its fix."""
    a = find_actor(label)
    comps = list(a.get_components_by_class(unreal.ActorComponent))
    trash = [c.get_name() for c in comps if c.get_name().startswith("TRASH_")]
    syncs = []
    for c in comps:
        if c.get_class().get_name() != "LODSyncComponent" or c.get_name().startswith("TRASH_"):
            continue
        listed = [str(s.get_editor_property("name")) for s in c.get_editor_property("components_to_sync")]
        syncs.append({"name": c.get_name(), "forced_lod": int(c.get_editor_property("forced_lod")),
                      "listed": listed, "live": _sync_debug(c)})
    grooms = []
    for c in _grooms(a):
        if c.get_name().startswith("TRASH_"):
            continue
        n = c.get_name()
        g = {"name": n, "visible": bool(c.is_visible()), "asset": _path(c.get_editor_property("groom_asset")),
             "use_cards": bool(c.get_editor_property("use_cards")),
             "listed": any(n in s["listed"] for s in syncs),
             "length_scale": [d.get("length_scale") for d in (_desc(x) for x in c.get_editor_property("groom_groups_desc"))
                              if d.get("length_scale_override")],
             "live_lod": next((s["live"][n] for s in syncs if n in s["live"]), None)}
        g.update(_asset_lods(c.get_editor_property("groom_asset"), lod))
        grooms.append(g)
    skel = [{"name": c.get_name(), "forced_lod_model": int(c.get_editor_property("forced_lod_model"))}
            for c in a.get_components_by_class(unreal.SkeletalMeshComponent) if not c.get_name().startswith("TRASH_")]
    problems, notes = [], []
    if trash:
        problems.append(f"{label}: stale TRASH_ components {trash}: a lock on them does nothing. Fix: level.save, "
                        "level.open, then respawn/re-dress the character and lock again")
    if not syncs:
        problems.append(f"{label}: no live LODSync component: nothing forces the grooms' LOD. Fix: recreate it on "
                        "the Blueprint (a copied MetaHuman BP can lose it) or rebuild the character (mh.build)")
    for s in syncs:
        if s["forced_lod"] != lod:
            problems.append(f"{label}: {s['name']} forced_lod {s['forced_lod']} (want {lod}). Fix: groom.lock")
    for g in grooms:
        if not g["visible"]:
            continue
        n = g["name"]
        if not g["listed"]:
            problems.append(f"{label}: groom {n} is not in LODSync's components_to_sync, so the forced LOD never "
                            f"reaches it (screen size picks cards on a wide shot). Fix: groom.lock (adds it)")
        elif syncs and g["live_lod"] is None:
            notes.append(f"{label}: {n} is listed but LODSync has not resolved it yet (it does on register: the "
                         "render's world will; level.save + level.open shows it here)")
        elif g["live_lod"] is not None and g["live_lod"] != lod:
            problems.append(f"{label}: groom {n} renders LOD {g['live_lod']} (want {lod})")
        short = [v for v in g["length_scale"] if v is not None and v < 0.999]
        if short:
            notes.append(f"{label}: groom {n} has hair_length_scale overrides {short} (shorter strands by design: "
                         "the same in every shot, unless a sequence keys it)")
        if g["use_cards"]:
            problems.append(f"{label}: groom {n} use_cards is on (cards, not strands). Fix: groom.lock")
        for i, grp in enumerate(g["groups"]):
            if "geometry" not in grp:
                problems.append(f"{label}: groom {n} group {i} has {grp.get('lods')} LODs, no LOD {lod}")
            elif grp["geometry"] != "STRANDS" or not grp["visible"]:
                problems.append(f"{label}: groom {n} group {i} LOD {lod} is {grp['geometry']}"
                                f"{'' if grp['visible'] else ' (hidden)'}, not strands: lock a strands LOD")
        if g.get("lod_mode") == "AUTO":
            notes.append(f"{label}: {n}'s asset is in Auto LOD mode itself (r.HairStrands.LODMode does not change "
                         "it): r.HairStrands.AutoLOD.Bias 1 keeps its curves")
    for s in skel:
        if s["forced_lod_model"] != lod + 1:
            problems.append(f"{label}: {s['name']} forced_lod_model {s['forced_lod_model']} (want {lod + 1} = "
                            f"LOD {lod}). Fix: groom.lock")
    return {"label": label, "trash": trash, "lodsync": syncs, "grooms": grooms, "skeletal": skel,
            "problems": problems, "notes": notes}


def _cvar_problems(want: dict) -> list:
    out = []
    for k, v in want.items():
        got = _cvar_num(k)
        if got is None or abs(float(got) - float(v)) > 1e-6:
            out.append(f"cvar {k} is {got} (want {v}). Fix: groom.lock; and pass render_cvars to the render spec")
    return out


@op("groom.lock_check", mutates=False, idempotent=True)
def lock_check(*, labels: list, lod: int = 0) -> dict:
    """Read-only: will these characters' hair render the same in every shot? For each: no TRASH_ components, a
    live LODSync forcing `lod`, every visible groom in its components_to_sync (and, where LODSync has resolved it,
    rendering `lod`), strands (not cards/meshes, not hidden) at that LOD in every group, use_cards off, skeletal
    meshes pinned; plus the hair LOD cvars (r.HairStrands.LODMode 0, r.HairStrands.AutoLOD.Bias 1,
    r.HairStrands.UseCardsInsteadOfStrands 0) live in the editor.

    Args: labels: the characters' actor labels. lod: the LOD that must render (0).
    Returns: {"pass", "problems": [str], "notes": [str], "actors": {label: state}, "cvars": {...},
    "render_cvars"}. The review gate's hair.lock item is this op's pass.
    Example: film-ue op groom.lock_check 'labels=["Host","Presenter"]'
    """
    if not labels:
        raise OpError("labels: the characters to check", code="bad_args")
    states = {lab: _lock_state(lab, int(lod)) for lab in labels}
    problems = [p for s in states.values() for p in s["problems"]] + _cvar_problems(LOCK_CVARS)
    return {"pass": not problems, "problems": problems, "notes": [n for s in states.values() for n in s["notes"]],
            "actors": states, "cvars": {k: _cvar_num(k) for k in LOCK_CVARS}, "render_cvars": dict(LOCK_CVARS)}


@op("groom.lock", mutates=True, idempotent=True)
def lock(*, labels: list, lod: int = 0, persist: bool = False, release: bool = False):
    """Lock characters' hair (and bodies) to one LOD for rendering, so a wide shot draws the same hair as a close
    one: each live LODSync's forced_lod = `lod`, every visible groom added to its components_to_sync (Passive) if
    missing, use_cards off, skeletal meshes forced_lod_model = lod + 1; the hair LOD cvars set live
    (r.HairStrands.LODMode 0: manual LODs; r.HairStrands.AutoLOD.Bias 1: no screen-size curve thinning;
    r.HairStrands.UseCardsInsteadOfStrands 0). Then it reads everything back (groom.lock_check).

    Pass `render_cvars` from the result into the render spec's cvars, and lock BEFORE the render starts: a groom
    reads its LOD mode when it registers. Save the level after (level.save) so the pins persist.

    Args: labels: actor labels. lod: 0 (the full groom). persist: also write the cvars into the project's
    DefaultEngine.ini [SystemSettings] (editor.project_setting) so every editor start has them. release: undo the
    pins (LODSync -1, skeletal 0, cvars back to the engine defaults 1 / 0.1); components added to the sync list stay.
    Returns: {"changed": [str], "check": groom.lock_check's result, "pass", "render_cvars"}. Multi-tick.
    Example: film-ue op groom.lock 'labels=["Host","Presenter"]'
    """
    if not labels:
        raise OpError("labels: the characters to lock", code="bad_args")
    lod = int(lod)
    sync_lod, skel_lod = (-1, 0) if release else (lod, lod + 1)
    want_cvars = {"r.HairStrands.LODMode": 1, "r.HairStrands.AutoLOD.Bias": 0.1} if release else LOCK_CVARS
    changed = []
    for lab in labels:
        a = find_actor(lab)
        comps = list(a.get_components_by_class(unreal.ActorComponent))
        if any(c.get_name().startswith("TRASH_") for c in comps) and not release:
            raise OpError(f"{lab} has stale TRASH_ components: a lock would land on dead copies", code="failed",
                          hint="level.save, level.open, then respawn/re-dress the character, then groom.lock again")
        groom_names = [c.get_name() for c in _grooms(a) if c.is_visible()]
        syncs = [c for c in comps if c.get_class().get_name() == "LODSyncComponent"]
        for c in syncs:
            if int(c.get_editor_property("forced_lod")) != sync_lod:
                c.set_editor_property("forced_lod", sync_lod)
                changed.append(f"{lab}.{c.get_name()}.forced_lod={sync_lod}")
            if release:
                continue
            lst = list(c.get_editor_property("components_to_sync"))
            have = {str(s.get_editor_property("name")) for s in lst}
            add = [n for n in groom_names if n not in have]
            if add:
                for n in add:
                    lst.append(unreal.ComponentSync(name=n, sync_option=unreal.SyncOption.PASSIVE))
                c.set_editor_property("components_to_sync", lst)
                changed.append(f"{lab}.{c.get_name()}.components_to_sync+={add}")
        if not release:
            for c in _grooms(a):
                if c.get_editor_property("use_cards"):
                    c.set_editor_property("use_cards", False)
                    changed.append(f"{lab}.{c.get_name()}.use_cards=False")
        for c in a.get_components_by_class(unreal.SkeletalMeshComponent):
            if int(c.get_editor_property("forced_lod_model")) != skel_lod:
                c.set_editor_property("forced_lod_model", skel_lod)
                changed.append(f"{lab}.{c.get_name()}.forced_lod_model={skel_lod}")
        a.modify()
    for k, v in want_cvars.items():
        got = _cvar_num(k)
        if got is None or abs(float(got) - float(v)) > 1e-6:
            unreal.SystemLibrary.execute_console_command(None, f"{k} {v}")
            changed.append(f"{k}={v}")
    if persist:
        from . import call
        for k, v in want_cvars.items():
            call("editor.project_setting", file="Engine", section="SystemSettings", key=k, value=v)
        changed.append("DefaultEngine.ini [SystemSettings]")
    for _ in range(3):
        yield
    if release:
        return {"changed": changed, "pass": True, "released": labels}
    check = lock_check(labels=labels, lod=lod)
    return {"changed": changed, "check": check, "pass": check["pass"], "render_cvars": dict(LOCK_CVARS)}


@op("groom.sky_lighting", mutates=True, idempotent=True)
def sky_lighting(*, enable: bool = False, measure_label: str = "", measure_views: int = 1, out_dir: str = ""):
    """The hair sky-lighting guard (unreal/README.md: indoors, hair takes the sky light unoccluded and reads white):
    set r.HairStrands.SkyLighting in the editor, and give the cvar to pass to renders.

    Args: enable: false (the guard: 0) or true (1). measure_label: a character to measure (groom.measure) before
    and after, so the effect is a number.
    Returns: {"changed", "before", "after", "render_cvars": {"r.HairStrands.SkyLighting": 0|1} (pass to render.*
    cvars), "measure"?: {"before", "after", "delta"}}. Multi-tick.
    Example: film-ue op groom.sky_lighting enable=false measure_label=Ada
    """
    want = 1 if enable else 0
    before = _cvar(SKY_CVAR)
    res = {"before": before}
    if measure_label:
        mb = yield from _measure(measure_label, "", measure_views, out_dir=out_dir, tag="sky_before")
    if before != want:
        unreal.SystemLibrary.execute_console_command(None, f"{SKY_CVAR} {want}")
    for _ in range(3):
        yield
    after = _cvar(SKY_CVAR)
    res.update(after=after, changed=before != after, render_cvars={SKY_CVAR: want})
    if after is not None and after != want:
        raise OpError(f"{SKY_CVAR} is {after} after setting {want}", code="engine",
                      hint="a device profile or ini may pin it (film-ue log)")
    if measure_label:
        ma = yield from _measure(measure_label, "", measure_views, out_dir=out_dir, tag="sky_after")
        res["measure"] = {"before": mb, "after": ma, "delta": _delta(mb, ma)}
    return res
