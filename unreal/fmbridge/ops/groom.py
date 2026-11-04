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
