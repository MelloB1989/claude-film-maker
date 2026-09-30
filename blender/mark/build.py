"""The woven mark in Blender: the four threads as meshes, a Geometry Nodes window that draws each on, and the shaders.

Each thread is one mesh (sweep.py) with its per-point attributes. The window (node group `weave_window`) keeps the
mesh's topology and only moves points, so Cycles motion-blurs it as it deforms:
  k   = min(taper(s - s0, tail), taper(s1 - s, head)), taper(d, w) = sqrt(u (2 - u)), u = clamp(d / w + 1, 0, 1)
        (a point outside [s0 - tail, s1 + head] sits on the centreline; the ends round off over `tail` and `head`)
  P'  = C' + (P + dt*bt + dh*bh + dz*(cinch - 1) - C') * k,   C' = c + dz*(cinch - 1)
bt and bh bring in the tail's and the head's terminal shapes (0 while the thread runs, 1 at rest); cinch scales the
weave's lift (1 at rest). Every input is a modifier input the shot keys per frame.

The material reads the attributes: thread (m = 0) is the film's fibre, dyed, with the blood and moss strands' glowing
core ((N.V)^28, as thread3d.ts); ribbon (m = 1) is satin in the palette's bone, blood or moss; the blood and moss ribbons
carry their light in their rounded edges (|v| near 1, the type's diff glow), so the faces stay satin and the bloom
halates round them in the engine's post. Bone never emits.
"""
from __future__ import annotations

import bpy
import numpy as np

from . import strands as S
from .sweep import sweep

MU = 0.001  # metres per mark px: the mark is about 25 cm across
INPUTS = ("s0", "s1", "tail", "head", "bt", "bh", "cinch", "glow")

# linear colours: the palette for the ribbons; the thread's dyed blood and moss (thread3d.ts THREAD_LOOK)
BONE = (0.847, 0.799, 0.823)
BLOOD = (0.539, 0.0242, 0.0595)
MOSS = (0.0685, 0.418, 0.125)
BLOOD_DYED = (0.319, 0.0156, 0.0399)
MOSS_DYED = (0.0218, 0.102, 0.0369)
GLOW_BLOOD = (1.0, 0.0448, 0.110)
GLOW_MOSS = (0.164, 1.0, 0.299)
THREAD_CORE = 1.6
AO_DIST = 0.006  # m: the ribbons' contact shadow reaches about 6 mark px
AO_FLOOR = 0.5  # the running threads' filament (thread3d's 3.4 reads as neon at this size)
EDGE = (0.93, 0.995)  # |v| over which a ribbon's edge comes into the glow: its side walls


def _n(nt, kind, loc=(0, 0), **props):
    node = nt.nodes.new(kind)
    node.location = loc
    for k, v in props.items():
        setattr(node, k, v)
    return node


def window_group():
    """The node group that draws a thread on (see the module doc)."""
    ng = bpy.data.node_groups.get("weave_window")
    if ng is not None:
        return ng
    ng = bpy.data.node_groups.new("weave_window", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    for name in INPUTS[:7]:
        ng.interface.new_socket(name, in_out="INPUT", socket_type="NodeSocketFloat")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nt = ng
    gi = _n(nt, "NodeGroupInput", (-1400, 0))
    go = _n(nt, "NodeGroupOutput", (800, 0))
    L = nt.links.new

    def attr(name, vec, y):
        a = _n(nt, "GeometryNodeInputNamedAttribute", (-1200, y), data_type="FLOAT_VECTOR" if vec else "FLOAT")
        a.inputs["Name"].default_value = name
        return a.outputs["Attribute"]

    def math(op, a, b=None, y=0, x=-900):
        m = _n(nt, "ShaderNodeMath", (x, y), operation=op)
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                m.inputs[i].default_value = v
            else:
                L(v, m.inputs[i])
        return m.outputs[0]

    def vmath(op, a, b, y=0, x=0):
        m = _n(nt, "ShaderNodeVectorMath", (x, y), operation=op)
        L(a, m.inputs[0])
        if op == "SCALE":
            L(b, m.inputs["Scale"]) if not isinstance(b, (int, float)) else setattr(m.inputs["Scale"], "default_value", b)
        else:
            L(b, m.inputs[1])
        return m.outputs[0]

    s = attr("s", False, 300)
    c = attr("c", True, 150)
    dt = attr("dt", True, 0)
    dh = attr("dh", True, -150)
    dz = attr("dz", True, -300)
    pos = _n(nt, "GeometryNodeInputPosition", (-1200, -450)).outputs[0]

    def taper(d, w, y):
        # a round end: sqrt(u (2 - u)), a quarter circle over the taper's length
        u = math("ADD", math("DIVIDE", d, math("MAXIMUM", w, 1e-4, y), y), 1.0, y)
        u = math("MINIMUM", math("MAXIMUM", u, 0.0, y), 1.0, y)
        return math("SQRT", math("MULTIPLY", u, math("SUBTRACT", 2.0, u, y), y), None, y)

    kt = taper(math("SUBTRACT", s, gi.outputs["s0"], 500), gi.outputs["tail"], 500)
    kh = taper(math("SUBTRACT", gi.outputs["s1"], s, 700), gi.outputs["head"], 700)
    k = math("MINIMUM", kt, kh, 600, -500)
    cin = math("SUBTRACT", gi.outputs["cinch"], 1.0, -600, -500)
    lift = vmath("SCALE", dz, cin, -300, -500)
    c1 = vmath("ADD", c, lift, 150, -300)
    p1 = vmath("ADD", vmath("ADD", pos, vmath("SCALE", dt, gi.outputs["bt"], 0, -500), -100, -300),
               vmath("SCALE", dh, gi.outputs["bh"], -150, -500), -150, -200)
    p1 = vmath("ADD", p1, lift, -200, -100)
    out = vmath("ADD", c1, vmath("SCALE", vmath("SUBTRACT", p1, c1, -200, 100), k, -200, 250), 0, 400)
    sp = _n(nt, "GeometryNodeSetPosition", (600, 0))
    L(gi.outputs["Geometry"], sp.inputs["Geometry"])
    L(out, sp.inputs["Position"])
    L(sp.outputs["Geometry"], go.inputs["Geometry"])
    return ng


def weave_material(name: str = "weave"):
    """One material for every thread, driven by the mesh's attributes and the object's `glow` (the ribbons' core)."""
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    L = nt.links.new
    out = _n(nt, "ShaderNodeOutputMaterial", (1200, 0))
    bsdf = _n(nt, "ShaderNodeBsdfPrincipled", (800, 0))
    L(bsdf.outputs["BSDF"], out.inputs["Surface"])

    def attr(nm, y, kind="GEOMETRY"):
        a = _n(nt, "ShaderNodeAttribute", (-1400, y), attribute_name=nm, attribute_type=kind)
        return a.outputs["Fac"]

    blood, moss, m, v = attr("blood", 400), attr("moss", 250), attr("m", 100), attr("v", -50)
    glow = attr("glow", -200, "OBJECT")

    def mixc(fac, a, b, y, x=-600):
        mx = _n(nt, "ShaderNodeMix", (x, y), data_type="RGBA", blend_type="MIX")
        L(fac, mx.inputs["Factor"]) if not isinstance(fac, (int, float)) else setattr(mx.inputs["Factor"], "default_value", fac)
        for sock, val in ((mx.inputs[6], a), (mx.inputs[7], b)):
            if isinstance(val, tuple):
                sock.default_value = (*val, 1.0)
            else:
                L(val, sock)
        return mx.outputs[2]

    def mixf(fac, a, b, y, x=-600):
        mx = _n(nt, "ShaderNodeMix", (x, y), data_type="FLOAT")
        L(fac, mx.inputs["Factor"])
        for sock, val in ((mx.inputs[2], a), (mx.inputs[3], b)):
            if isinstance(val, (int, float)):
                sock.default_value = val
            else:
                L(val, sock)
        return mx.outputs[0]

    def math(op, a, b=None, y=0, x=-300):
        mm = _n(nt, "ShaderNodeMath", (x, y), operation=op)
        for i, val in enumerate((a, b)):
            if val is None:
                continue
            if isinstance(val, (int, float)):
                mm.inputs[i].default_value = val
            else:
                L(val, mm.inputs[i])
        return mm.outputs[0]

    # colour: bone, then blood or moss by weight; the thread's dyed, the ribbon's the palette's
    dyed = mixc(moss, mixc(blood, BONE, BLOOD_DYED, 500, -1000), MOSS_DYED, 450, -800)
    pal = mixc(moss, mixc(blood, BONE, BLOOD, 300, -1000), MOSS, 250, -800)
    # contact shadow where the ribbons press on each other (ray-traced occlusion, a few mark px out)
    ao = _n(nt, "ShaderNodeAmbientOcclusion", (-300, 500), samples=12, only_local=False)
    ao.inputs["Distance"].default_value = AO_DIST
    shade = mixf(ao.outputs["AO"], AO_FLOOR, 1.0, 550, -100)
    base = _n(nt, "ShaderNodeMix", (0, 350), data_type="RGBA", blend_type="MULTIPLY")
    base.inputs["Factor"].default_value = 1.0
    L(mixc(m, dyed, pal, 350), base.inputs[6])
    L(shade, base.inputs[7])
    L(base.outputs[2], bsdf.inputs["Base Color"])
    L(mixf(m, 0.6, 0.33, 150), bsdf.inputs["Roughness"])
    L(mixf(m, 0.35, 0.62, 100), bsdf.inputs["Specular IOR Level"])
    L(mixf(m, 0.0, 0.3, 50), bsdf.inputs["Coat Weight"])
    bsdf.inputs["Coat Roughness"].default_value = 0.12
    L(mixf(m, 0.6, 0.3, 0), bsdf.inputs["Sheen Weight"])
    L(mixf(m, 0.35, 0.6, -50), bsdf.inputs["Sheen Roughness"])
    L(mixc(m, (1.0, 1.0, 1.0), pal, -100), bsdf.inputs["Sheen Tint"])

    # emission: blood or moss light, never bone
    ecol = mixc(moss, mixc(blood, (0.0, 0.0, 0.0), GLOW_BLOOD, -250, -1000), GLOW_MOSS, -300, -800)
    L(ecol, bsdf.inputs["Emission Color"])
    lw = _n(nt, "ShaderNodeLayerWeight", (-1000, -500))
    lw.inputs["Blend"].default_value = 0.5
    nv = math("SUBTRACT", 1.0, lw.outputs["Facing"], -500, -800)
    core = math("ADD", math("MULTIPLY", math("POWER", nv, 40.0, -450, -650), 0.8, -450, -500),
                math("MULTIPLY", math("POWER", nv, 4.0, -550, -650), 0.2, -550, -500), -500, -350)
    thread_e = math("MULTIPLY", core, THREAD_CORE, -500, -200)
    # the ribbon's light lives in its rounded edges (|v| -> 1), as the type's diff glow does; its faces stay satin
    edge = _n(nt, "ShaderNodeMapRange", (-700, -400), interpolation_type="SMOOTHSTEP")
    L(math("ABSOLUTE", v, None, -700, -600), edge.inputs["Value"])
    edge.inputs["From Min"].default_value, edge.inputs["From Max"].default_value = EDGE[0], EDGE[1]
    ribbon_e = math("MULTIPLY", edge.outputs["Result"], glow, -700, -50)
    strength = math("MULTIPLY", mixf(m, thread_e, ribbon_e, -600, -100), math("ADD", blood, moss, -800, -300), -600, 100)
    L(strength, bsdf.inputs["Emission Strength"])
    return mat


def thread_object(st: S.Strand, parent=None, coll=None):
    """The thread `st` as a mesh object with its attributes, the window modifier (at rest) and the material."""
    msh = sweep(st.rings, S.H, S.RC)
    k = (len(msh.verts) - 2) // len(st.rings.s)
    me = bpy.data.meshes.new(st.name)
    me.vertices.add(len(msh.verts))
    me.vertices.foreach_set("co", msh.verts.astype(np.float32).ravel())
    nq, ntr = len(msh.quads), len(msh.tris)
    me.loops.add(nq * 4 + ntr * 3)
    me.polygons.add(nq + ntr)
    me.loops.foreach_set("vertex_index", np.concatenate([msh.quads.ravel(), msh.tris.ravel()]).astype(np.int32))
    starts = np.concatenate([np.arange(nq) * 4, nq * 4 + np.arange(ntr) * 3]).astype(np.int32)
    me.polygons.foreach_set("loop_start", starts)
    me.update(calc_edges=True)
    me.validate(clean_customdata=False)

    def per_point(x):
        x = np.asarray(x)
        return np.concatenate([np.repeat(x, k, axis=0), x[[0, -1]]], axis=0)

    attrs = dict(msh.attrs)
    attrs["blood"] = per_point(st.blood)
    attrs["moss"] = per_point(st.moss)
    dz = np.zeros((len(st.rings.s), 3))
    dz[:, 1] = -st.zoff  # the lift, toward the viewer
    attrs["dz"] = per_point(dz)
    for name, val in attrs.items():
        val = np.asarray(val, np.float32)
        a = me.attributes.new(name, "FLOAT_VECTOR" if val.ndim == 2 else "FLOAT", "POINT")
        a.data.foreach_set("vector" if val.ndim == 2 else "value", val.ravel())
    me.shade_smooth()
    me.materials.append(weave_material())
    ob = bpy.data.objects.new(st.name, me)
    (coll or bpy.context.scene.collection).objects.link(ob)
    if parent is not None:
        ob.parent = parent
    ob["glow"] = 0.0
    mod = ob.modifiers.new("window", "NODES")
    mod.node_group = window_group()
    set_window(ob, s0=st.s_band, s1=st.length, tail=0.0, head=0.0, bt=1.0, bh=1.0, cinch=1.0)
    return ob


def input_path(ob, name: str) -> str:
    """The data path of window input `name` on `ob` (Blender 5: modifiers[..].properties.inputs.<Socket_n>.value)."""
    if name == "glow":
        return '["glow"]'
    idn = ob.modifiers["window"].node_group.interface.items_tree[name].identifier
    return f'modifiers["window"].properties.inputs.{idn}.value'


def set_window(ob, **values):
    """Set the window's inputs (and `glow`, the object's ribbon core level) for a still."""
    ins = ob.modifiers["window"].properties.inputs
    for k, v in values.items():
        if k == "glow":
            ob["glow"] = float(v)
        else:
            idn = ob.modifiers["window"].node_group.interface.items_tree[k].identifier
            getattr(ins, idn).value = float(v)


def _fcurves(ob):
    act = ob.animation_data.action
    if hasattr(act, "layers") and act.layers:
        for layer in act.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    yield from bag.fcurves
    elif hasattr(act, "fcurves"):
        yield from act.fcurves


def key_series(ob, data_path: str, frames, values, interpolation: str = "LINEAR"):
    """Key `data_path` of `ob` at every frame in `frames` (film frames, may be fractional) to `values`, in one go."""
    frames = np.asarray(frames, float)
    values = np.asarray(values, float)
    ob.keyframe_insert(data_path, frame=float(frames[0]))
    fc = next(f for f in _fcurves(ob) if f.data_path == data_path)
    fc.keyframe_points.clear()
    fc.keyframe_points.add(len(frames))
    fc.keyframe_points.foreach_set("co", np.column_stack([frames, values]).ravel().astype(np.float32))
    fc.keyframe_points.foreach_set("interpolation", [bpy.types.Keyframe.bl_rna.properties["interpolation"]
                                                     .enum_items[interpolation].value] * len(frames))
    fc.update()
    return fc


def mark(parent=None, coll=None, p: dict | None = None) -> dict:
    """The four threads at rest (the finished mark), parented to `parent`. Returns {name: object}."""
    return {n: thread_object(st, parent, coll) for n, st in S.all_strands(p).items()}
