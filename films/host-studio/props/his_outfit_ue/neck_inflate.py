"""Round 4 (agent-02): his tee's inflate master with a NECKLINE term, for the operator's MetaHuman, whose throat (the
face mesh's lower neck) stood up to 2.5 cm out through the tee's front under the collar (reel/r4/neck_probe.py).

World Position Offset += vertex normal x (FM_Inflate + FM_Neck x t x f), where t ramps 0..1 over the tee's
pre-skinned (reference pose, mesh space, cm) height FM_NeckZ0..FM_NeckZ1 and f = saturate(y x FM_NeckFront +
FM_NeckFrontBias) weights the front (mesh +Y or -Y, by the sign of FM_NeckFront). With FM_Neck 0 (the default) it is
mh.cloth_inflate's plain inflate. Tuning is a plain parameter change on the worn instance (safe while it is drawn):
    film-ue op mh.garment label=Host which=Shirt component=SkeletalMesh \
        'scalars={"FM_Neck": 2.8, "FM_NeckZ0": 135, "FM_NeckZ1": 147, "FM_NeckFront": 0.1, "FM_NeckFrontBias": 0.5}'
host_swap.py builds it (instead of the plain master) for HOST op, in its own folder /Game/FM/ClothOp, so no material
already drawn is ever recompiled.
"""
import unreal

FOLDER = "/Game/FM/ClothOp"
PARAMS = {"FM_Inflate": 0.0, "FM_Neck": 0.0, "FM_NeckZ0": 0.0, "FM_NeckZ1": 1.0, "FM_NeckFront": 0.0,
          "FM_NeckFrontBias": 1.0}


def add_neck_inflate(master):
    """mh.cloth_inflate's _add_inflate, with the neckline term (on a fresh master copy only)."""
    MEL = unreal.MaterialEditingLibrary
    X = lambda cls, x, y: MEL.create_material_expression(master, cls, x, y)  # noqa: E731
    have = [str(n) for n in MEL.get_scalar_parameter_names(master)]
    p = {}
    for i, (name, dv) in enumerate(PARAMS.items()):
        if name in have:
            raise RuntimeError(f"{master.get_name()} already has {name}: build from the plugin master, not a copy")
        e = X(unreal.MaterialExpressionScalarParameter, -1700, 1400 + 90 * i)
        e.set_editor_property("parameter_name", name)
        e.set_editor_property("default_value", dv)
        p[name] = e

    def op(cls, a, b, x, y):
        e = X(cls, x, y)
        MEL.connect_material_expressions(a, "", e, "A")
        MEL.connect_material_expressions(b, "", e, "B")
        return e

    def sat(a, x, y):
        e = X(unreal.MaterialExpressionSaturate, x, y)
        MEL.connect_material_expressions(a, "", e, "")
        return e

    psl = X(unreal.MaterialExpressionPreSkinnedLocalPosition, -1700, 2000)
    masks = {}
    for ch, y in (("b", 2000), ("g", 2100)):
        m = X(unreal.MaterialExpressionComponentMask, -1500, y)
        for k in "rgba":
            m.set_editor_property(k, k == ch)
        MEL.connect_material_expressions(psl, "", m, "")
        masks[ch] = m
    t = sat(op(unreal.MaterialExpressionDivide,
               op(unreal.MaterialExpressionSubtract, masks["b"], p["FM_NeckZ0"], -1300, 1950),
               op(unreal.MaterialExpressionSubtract, p["FM_NeckZ1"], p["FM_NeckZ0"], -1300, 2050), -1100, 2000),
            -950, 2000)
    f = sat(op(unreal.MaterialExpressionAdd,
               op(unreal.MaterialExpressionMultiply, masks["g"], p["FM_NeckFront"], -1300, 2150),
               p["FM_NeckFrontBias"], -1100, 2150), -950, 2150)
    neck = op(unreal.MaterialExpressionMultiply, p["FM_Neck"],
              op(unreal.MaterialExpressionMultiply, t, f, -800, 2075), -650, 2000)
    amt = op(unreal.MaterialExpressionAdd, p["FM_Inflate"], neck, -500, 1900)
    n = X(unreal.MaterialExpressionVertexNormalWS, -500, 1800)
    off = op(unreal.MaterialExpressionMultiply, n, amt, -350, 1850)
    wpo = unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET
    prev = MEL.get_material_property_input_node(master, wpo)
    if prev:
        add = X(unreal.MaterialExpressionAdd, -200, 1850)
        MEL.connect_material_expressions(prev, MEL.get_material_property_input_node_output_name(master, wpo), add, "A")
        MEL.connect_material_expressions(off, "", add, "B")
        MEL.connect_material_property(add, "", wpo)
    else:
        MEL.connect_material_property(off, "", wpo)
    master.set_editor_property("used_with_skeletal_mesh", True)
    MEL.recompile_material(master)
