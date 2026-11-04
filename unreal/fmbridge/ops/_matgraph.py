"""A material described as data (WP2): the pure half of `mat.graph`, and the master materials of the library.

A graph spec is a dict:

    {"blend": "opaque", "shading": "default_lit", "two_sided": false,
     "nodes": {
        "uv":    {"type": "TexCoord"},
        "til":   {"type": "Scalar", "name": "Tiling", "default": 1.0},
        "uvm":   {"type": "Multiply", "in": {"A": "uv", "B": "til"}},
        "base":  {"type": "Texture", "name": "BaseColorMap", "texture": "/Engine/EngineResources/WhiteSquareTexture",
                  "sampler": "color", "in": {"UVs": "uvm"}},
        "tint":  {"type": "Vector", "name": "Tint", "default": [1, 1, 1, 1]},
        "col":   {"type": "Multiply", "in": {"A": "base.RGB", "B": "tint"}},
        "rough": {"type": "Multiply", "in": {"A": "orm.G", "B": 0.8}}},          # a number makes a Constant
     "outputs": {"BaseColor": "col", "Roughness": "rough"}}

- `type`: a short name from NODE_TYPES (Scalar, Vector, Texture, Switch, Multiply, Lerp, ...) or any engine class
  by its full name (`MaterialExpressionSine`), passed through (pins unchecked).
- `in`: input pin -> source. A source is "node" (its first output), "node.Output" (a named output: RGB, R, G, B, A
  of a texture), a number, or a list of 2-4 numbers (a constant node is made).
- other keys are the expression's editor properties (snake_case), with short names for the common ones
  (name -> parameter_name, default -> default_value, texture, sampler -> sampler_type, group).
- `outputs`: material input -> source: BaseColor, Metallic, Specular, Roughness, Anisotropy, EmissiveColor, Opacity,
  OpacityMask, Normal, Tangent, WorldPositionOffset, SubsurfaceColor, CustomData0, CustomData1,
  AmbientOcclusion, Refraction, PixelDepthOffset, ShadingModel.

`normalize(spec)` checks all of it (unknown node, pin, source, property shorthand) and returns a plan the bridge
builds in one pass: nodes in dependency order with x/y laid out by depth, the connections and the outputs. The spec's
`fingerprint` names a built material so re-running converges without rebuilding.
"""
from __future__ import annotations

import difflib
import hashlib
import json

NODE_TYPES = {
    # parameters (an instance can change them)
    "Scalar": "MaterialExpressionScalarParameter",
    "Vector": "MaterialExpressionVectorParameter",
    "Texture": "MaterialExpressionTextureSampleParameter2D",
    "Switch": "MaterialExpressionStaticSwitchParameter",
    "StaticBool": "MaterialExpressionStaticBoolParameter",
    # constants
    "Const": "MaterialExpressionConstant",
    "Const2": "MaterialExpressionConstant2Vector",
    "Const3": "MaterialExpressionConstant3Vector",
    "Const4": "MaterialExpressionConstant4Vector",
    # maths
    "Add": "MaterialExpressionAdd",
    "Subtract": "MaterialExpressionSubtract",
    "Multiply": "MaterialExpressionMultiply",
    "Divide": "MaterialExpressionDivide",
    "Lerp": "MaterialExpressionLinearInterpolate",
    "OneMinus": "MaterialExpressionOneMinus",
    "Power": "MaterialExpressionPower",
    "Saturate": "MaterialExpressionSaturate",
    "Clamp": "MaterialExpressionClamp",
    "Min": "MaterialExpressionMin",
    "Max": "MaterialExpressionMax",
    "Abs": "MaterialExpressionAbs",
    "Dot": "MaterialExpressionDotProduct",
    "Append": "MaterialExpressionAppendVector",
    "Mask": "MaterialExpressionComponentMask",
    "Desaturate": "MaterialExpressionDesaturation",
    # inputs
    "TexCoord": "MaterialExpressionTextureCoordinate",
    "VertexColor": "MaterialExpressionVertexColor",
    "Fresnel": "MaterialExpressionFresnel",
    "WorldPosition": "MaterialExpressionWorldPosition",
    "Time": "MaterialExpressionTime",
    "TwoSidedSign": "MaterialExpressionTwoSidedSign",
    "PixelDepth": "MaterialExpressionPixelDepth",
    "CameraVector": "MaterialExpressionCameraVectorWS",
    "Function": "MaterialExpressionMaterialFunctionCall",
    "Collection": "MaterialExpressionCollectionParameter",
}
# input pins of the types above (the engine matches them by name; "" is a single-input node's only pin)
NODE_INPUTS = {
    "Add": ("A", "B"), "Subtract": ("A", "B"), "Multiply": ("A", "B"), "Divide": ("A", "B"), "Min": ("A", "B"),
    "Max": ("A", "B"), "Dot": ("A", "B"), "Append": ("A", "B"), "Power": ("Base", "Exp"),
    "Lerp": ("A", "B", "Alpha"), "Clamp": ("", "Min", "Max"), "OneMinus": ("",), "Saturate": ("",), "Abs": ("",),
    "Mask": ("",), "Desaturate": ("", "Fraction"), "Texture": ("UVs",), "Switch": ("True", "False"),
    "Fresnel": ("ExponentIn", "BaseReflectFractionIn", "Normal"),
    "Scalar": (), "Vector": (), "StaticBool": (), "Const": (), "Const2": (), "Const3": (), "Const4": (),
    "TexCoord": (), "VertexColor": (), "WorldPosition": (), "Time": (), "TwoSidedSign": (), "PixelDepth": (),
    "CameraVector": (), "Collection": (),
}
NODE_OUTPUTS = {"Texture": ("RGB", "R", "G", "B", "A", "RGBA"), "Vector": ("RGB", "R", "G", "B", "A", "RGBA"),
                "VertexColor": ("RGB", "R", "G", "B", "A"), "Const4": ("RGB", "R", "G", "B", "A")}
# shorthand -> editor property
PROP_ALIASES = {"name": "parameter_name", "default": "default_value", "sampler": "sampler_type", "group": "group",
                "priority": "sort_priority", "value": "r", "function": "material_function",
                "collection": "collection", "u_tiling": "u_tiling", "v_tiling": "v_tiling",
                "index": "coordinate_index", "doc": "desc", "exponent": "exponent", "base_reflect": "base_reflect_fraction"}
SAMPLERS = {"color": "SAMPLERTYPE_COLOR", "linear_color": "SAMPLERTYPE_LINEAR_COLOR", "normal": "SAMPLERTYPE_NORMAL",
            "masks": "SAMPLERTYPE_MASKS", "grayscale": "SAMPLERTYPE_GRAYSCALE",
            "linear_grayscale": "SAMPLERTYPE_LINEAR_GRAYSCALE", "alpha": "SAMPLERTYPE_ALPHA"}
# material input -> MaterialProperty enum entry
OUTPUTS = {"BaseColor": "MP_BASE_COLOR", "Metallic": "MP_METALLIC", "Specular": "MP_SPECULAR",
           "Roughness": "MP_ROUGHNESS", "Anisotropy": "MP_ANISOTROPY", "EmissiveColor": "MP_EMISSIVE_COLOR",
           "Opacity": "MP_OPACITY", "OpacityMask": "MP_OPACITY_MASK", "Normal": "MP_NORMAL",
           "Tangent": "MP_TANGENT", "WorldPositionOffset": "MP_WORLD_POSITION_OFFSET",
           "SubsurfaceColor": "MP_SUBSURFACE_COLOR", "CustomData0": "MP_CUSTOM_DATA0",
           "CustomData1": "MP_CUSTOM_DATA1", "AmbientOcclusion": "MP_AMBIENT_OCCLUSION",
           "Refraction": "MP_REFRACTION", "PixelDepthOffset": "MP_PIXEL_DEPTH_OFFSET",
           "ShadingModel": "MP_SHADING_MODEL"}
BLENDS = {"opaque": "BLEND_OPAQUE", "masked": "BLEND_MASKED", "translucent": "BLEND_TRANSLUCENT",
          "additive": "BLEND_ADDITIVE", "modulate": "BLEND_MODULATE", "alpha_composite": "BLEND_ALPHA_COMPOSITE",
          "alpha_holdout": "BLEND_ALPHA_HOLDOUT"}
SHADINGS = {"unlit": "MSM_UNLIT", "default_lit": "MSM_DEFAULT_LIT", "subsurface": "MSM_SUBSURFACE",
            "preintegrated_skin": "MSM_PREINTEGRATED_SKIN", "clear_coat": "MSM_CLEAR_COAT",
            "subsurface_profile": "MSM_SUBSURFACE_PROFILE", "two_sided_foliage": "MSM_TWO_SIDED_FOLIAGE",
            "hair": "MSM_HAIR", "cloth": "MSM_CLOTH", "eye": "MSM_EYE", "thin_translucent": "MSM_THIN_TRANSLUCENT"}
DOMAINS = {"surface": "MD_SURFACE", "deferred_decal": "MD_DEFERRED_DECAL", "light_function": "MD_LIGHT_FUNCTION",
           "volume": "MD_VOLUME", "post_process": "MD_POST_PROCESS", "ui": "MD_UI"}
TRANSLUCENCY_LIGHTING = {"volumetric_nondirectional": "TLM_VOLUMETRIC_NON_DIRECTIONAL",
                         "volumetric_directional": "TLM_VOLUMETRIC_DIRECTIONAL",
                         "volumetric_perpixel_nondirectional": "TLM_VOLUMETRIC_PER_VERTEX_NON_DIRECTIONAL",
                         "surface": "TLM_SURFACE", "surface_per_pixel": "TLM_SURFACE_PER_PIXEL_LIGHTING"}
# Material bool properties a spec may set: usage flags (a material used on a skeletal mesh without the flag is
# replaced by the default material in a cooked/headless build) and the rest
USAGES = {"skeletal_mesh": "used_with_skeletal_mesh", "instanced": "used_with_instanced_static_meshes",
          "nanite": "used_with_nanite", "groom": "used_with_hair_strands", "morph_targets": "used_with_morph_targets",
          "particles": "used_with_particle_sprites", "niagara": "used_with_niagara_sprites",
          "geometry_cache": "used_with_geometry_cache", "spline_mesh": "used_with_spline_meshes",
          "static_lighting": "used_with_static_lighting", "clothing": "used_with_clothing",
          "virtual_heightfield": "used_with_virtual_heightfield_mesh", "editor": "used_with_editor_compositing"}
MATERIAL_KEYS = {"blend", "shading", "two_sided", "domain", "translucency_lighting", "usage", "opacity_mask_clip",
                 "nodes", "outputs", "description", "dither_opacity_mask", "tangent_space_normal", "props"}


class GraphError(ValueError):
    """A spec that cannot be built: `message` names the node/pin, `candidates` are near names."""

    def __init__(self, message: str, candidates=()):
        super().__init__(message)
        self.candidates = list(candidates)


def _near(name, names):
    return difflib.get_close_matches(str(name), [str(n) for n in names], n=3, cutoff=0.5)


def node_class(t: str) -> str:
    """'Multiply' / 'MaterialExpressionMultiply' / 'TextureSampleParameter2D' -> 'MaterialExpressionMultiply'."""
    if t in NODE_TYPES:
        return NODE_TYPES[t]
    if t.startswith("MaterialExpression") and t.isidentifier():
        return t  # any engine expression class, unchecked here (the bridge checks it exists)
    raise GraphError(f"unknown node type {t!r} (a short name, or a full MaterialExpression... class name)",
                     _near(t, NODE_TYPES))


def _src(ref, where: str, nodes: dict):
    """A source -> (node id, output name) or ("#const", value)."""
    if isinstance(ref, bool):
        raise GraphError(f"{where}: a bool is not a value; use 0 or 1")
    if isinstance(ref, (int, float)):
        return ("#const", [float(ref)])
    if isinstance(ref, (list, tuple)):
        if not 2 <= len(ref) <= 4 or not all(isinstance(v, (int, float)) for v in ref):
            raise GraphError(f"{where}: a constant vector has 2-4 numbers, got {ref!r}")
        return ("#const", [float(v) for v in ref])
    if not isinstance(ref, str) or not ref:
        raise GraphError(f"{where}: a source is 'node', 'node.Output' or a number, got {ref!r}")
    nid, _, out = ref.partition(".")
    if nid not in nodes:
        raise GraphError(f"{where}: no node {nid!r}", _near(nid, nodes))
    t = nodes[nid].get("type", "")
    if out and t in NODE_OUTPUTS and out not in NODE_OUTPUTS[t]:
        raise GraphError(f"{where}: {t} {nid!r} has no output {out!r} (it has {', '.join(NODE_OUTPUTS[t])})",
                         _near(out, NODE_OUTPUTS[t]))
    return (nid, out)


def _props(nid: str, node: dict) -> dict:
    props = {}
    for k, v in node.items():
        if k in ("type", "in", "x", "y"):
            continue
        key = PROP_ALIASES.get(k, k)
        if key == "sampler_type" and isinstance(v, str):
            low = v.lower()
            if low in SAMPLERS:
                v = SAMPLERS[low]
            elif v.upper() not in SAMPLERS.values():
                raise GraphError(f"node {nid!r}: sampler {v!r} is not one of {', '.join(SAMPLERS)}", _near(low, SAMPLERS))
            else:
                v = v.upper()
        if not key.replace("_", "").isalnum() or key != key.lower():
            raise GraphError(f"node {nid!r}: property {k!r} is not snake_case (editor properties are, e.g. "
                             f"parameter_name, default_value)")
        props[key] = v
    return props


def normalize(spec: dict) -> dict:
    """Check a graph spec and return the build plan: {"material": {...enum names...}, "nodes": [{"id", "class",
    "props", "x", "y"}] (sources before users), "links": [(src, out, dst, pin)], "outputs": [(MP_*, src, out)],
    "fingerprint"}. Raises GraphError naming what is wrong."""
    if not isinstance(spec, dict):
        raise GraphError("a material spec is a dict with nodes and outputs")
    bad = set(spec) - MATERIAL_KEYS - {"kind", "version", "name", "path", "master"}
    if bad:
        k = sorted(bad)[0]
        raise GraphError(f"unknown material key {k!r}", _near(k, MATERIAL_KEYS))
    nodes = dict(spec.get("nodes") or {})
    for nid, node in nodes.items():
        if not isinstance(node, dict) or "type" not in node:
            raise GraphError(f"node {nid!r} needs a type (one of {', '.join(sorted(NODE_TYPES))})")
        if not str(nid).replace("_", "").isalnum():
            raise GraphError(f"node id {nid!r}: letters, digits and _ only")
    mat = {}
    for key, table, prop in (("blend", BLENDS, "blend_mode"), ("shading", SHADINGS, "shading_model"),
                             ("domain", DOMAINS, "material_domain"),
                             ("translucency_lighting", TRANSLUCENCY_LIGHTING, "translucency_lighting_mode")):
        v = spec.get(key)
        if v is None:
            continue
        if v not in table:
            raise GraphError(f"{key} {v!r} is not one of {', '.join(table)}", _near(v, table))
        mat[prop] = table[v]
    for key, prop in (("two_sided", "two_sided"), ("dither_opacity_mask", "dither_opacity_mask"),
                      ("tangent_space_normal", "tangent_space_normal")):
        if key in spec:
            mat[prop] = bool(spec[key])
    if "opacity_mask_clip" in spec:
        mat["opacity_mask_clip_value"] = float(spec["opacity_mask_clip"])
    for u in spec.get("usage") or []:
        if u not in USAGES:
            raise GraphError(f"usage {u!r} is not one of {', '.join(USAGES)}", _near(u, USAGES))
        mat[USAGES[u]] = True
    mat.update(spec.get("props") or {})

    links, consts, deps = [], [], {nid: set() for nid in nodes}
    for nid, node in nodes.items():
        t = node["type"]
        node_class(t)
        pins = NODE_INPUTS.get(t)
        for pin, ref in (node.get("in") or {}).items():
            if pins is not None and pin not in pins:
                raise GraphError(f"node {nid!r} ({t}) has no input {pin!r}" +
                                 (f" (it has {', '.join(repr(p) for p in pins)})" if pins else " (it takes none)"),
                                 _near(pin, pins or ()))
            s = _src(ref, f"node {nid!r} input {pin!r}", nodes)
            if s[0] == "#const":
                cid = f"_c{len(consts)}"
                consts.append((cid, s[1]))
                links.append((cid, "", nid, pin))
                deps[nid].add(cid)
            else:
                links.append((s[0], s[1], nid, pin))
                deps[nid].add(s[0])
    outs = []
    for name, ref in (spec.get("outputs") or {}).items():
        if name not in OUTPUTS:
            raise GraphError(f"no material input {name!r}", _near(name, OUTPUTS))
        s = _src(ref, f"output {name!r}", nodes)
        if s[0] == "#const":
            cid = f"_c{len(consts)}"
            consts.append((cid, s[1]))
            s = (cid, "")
        outs.append((OUTPUTS[name], s[0], s[1]))
    if not outs:
        raise GraphError("a material spec needs outputs (e.g. {'BaseColor': 'col'})")
    allnodes = []
    for cid, vals in consts:
        cls = {1: "Const", 2: "Const2", 3: "Const3", 4: "Const4"}[len(vals)]
        props = {"r": vals[0]} if len(vals) == 1 else (
            {"r": vals[0], "g": vals[1]} if len(vals) == 2 else {"constant": vals})
        allnodes.append((cid, {"type": cls}, props))
        deps[cid] = set()
    for nid, node in nodes.items():
        allnodes.append((nid, node, _props(nid, node)))
    # dependency order and depth (a cycle is an error)
    depth, state, order = {}, {}, []

    def visit(n, trail):
        if state.get(n) == 1:
            raise GraphError(f"the graph has a cycle: {' -> '.join(trail + [n])}")
        if state.get(n) == 2:
            return depth[n]
        state[n] = 1
        d = 0
        for m in sorted(deps[n]):
            d = max(d, visit(m, trail + [n]) + 1)
        state[n], depth[n] = 2, d
        order.append(n)
        return d
    for nid, _, _ in allnodes:
        visit(nid, [])
    maxd = max(depth.values() or [0])
    by_id = {nid: (node, props) for nid, node, props in allnodes}
    rows: dict = {}
    plan_nodes = []
    for nid in order:
        node, props = by_id[nid]
        col = maxd - depth[nid]
        if nid.startswith("_c"):  # constants sit beside their user
            col = max(0, col)
        row = rows.get(col, 0)
        rows[col] = row + 1
        plan_nodes.append({"id": nid, "type": node["type"], "class": node_class(node["type"]), "props": props,
                           "x": int(node.get("x", -300 * (maxd - col + 1))), "y": int(node.get("y", 160 * row))})
    plan = {"material": mat, "nodes": plan_nodes, "links": links, "outputs": outs}
    plan["fingerprint"] = fingerprint(spec)
    return plan


def fingerprint(spec: dict) -> str:
    """A short stable hash of a spec (key order does not matter): a material built from it carries it as metadata
    so re-running with the same spec changes nothing."""
    s = json.dumps(spec, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(s.encode()).hexdigest()[:12]


def parameters(spec: dict) -> dict:
    """The parameters a spec exposes: {name: {"kind": scalar|vector|texture|switch, "default", "group", "doc"}}."""
    out = {}
    kinds = {"Scalar": "scalar", "Vector": "vector", "Texture": "texture", "Switch": "switch", "StaticBool": "switch"}
    for nid, node in (spec.get("nodes") or {}).items():
        k = kinds.get(node.get("type"))
        if k and node.get("name"):
            out[node["name"]] = {"kind": k, "default": node.get("default", node.get("texture")),
                                 "group": node.get("group", ""), "doc": node.get("doc", "")}
    return out
