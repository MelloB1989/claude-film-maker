"""WP2's fakes: material editing (graphs, instances, parameters, statistics) and meshes/textures with the numbers
assets.* reads (bounds, triangles, LODs, Nanite, collision, material slots), import options classes, and redirectors.

Faithful where the ops depend on it:
- MaterialEditingLibrary: a Material keeps its expressions (`m._props["__expr"]`), links and root connections;
  pins and outputs are checked like the engine does (`""` = first output; texture/vector outputs RGB R G B A RGBA;
  an unknown input pin fails). The MI setters return False as 5.8's do (bResult is never set) and accept any name.
  `delete_all_material_expressions` keeps every other node, as 5.8's iterate-while-delete does.
  `recompile_material` returns `fake.mat_errors.get(path, [])`; `get_statistics` gives num_samplers -1 for those.
- Meshes: `ue.add_mesh(path, size=[x, y, z], tris=, lods=, materials=[slot names], skeletal=False)`.
Knobs: `ue.mat_errors[path] = ["error text"]`.
"""
from __future__ import annotations

_OUTS = {"MaterialExpressionTextureSampleParameter2D": ("RGB", "R", "G", "B", "A", "RGBA"),
         "MaterialExpressionTextureSample": ("RGB", "R", "G", "B", "A", "RGBA"),
         "MaterialExpressionVectorParameter": ("RGB", "R", "G", "B", "A", "RGBA"),
         "MaterialExpressionVertexColor": ("R", "G", "B", "A"),
         "MaterialExpressionConstant4Vector": ("RGB", "R", "G", "B", "A")}
_INS = {"MaterialExpressionMultiply": ("A", "B"), "MaterialExpressionAdd": ("A", "B"),
        "MaterialExpressionSubtract": ("A", "B"), "MaterialExpressionDivide": ("A", "B"),
        "MaterialExpressionLinearInterpolate": ("A", "B", "Alpha"), "MaterialExpressionOneMinus": ("",),
        "MaterialExpressionSaturate": ("",), "MaterialExpressionComponentMask": ("",),
        "MaterialExpressionPower": ("Base", "Exp"), "MaterialExpressionTextureSampleParameter2D": ("UVs", "Tex"),
        "MaterialExpressionStaticSwitchParameter": ("True", "False"), "MaterialExpressionMin": ("A", "B"),
        "MaterialExpressionMax": ("A", "B"), "MaterialExpressionAppendVector": ("A", "B"),
        "MaterialExpressionClamp": ("", "Min", "Max")}
_PARAM_KIND = {"MaterialExpressionScalarParameter": "scalar", "MaterialExpressionVectorParameter": "vector",
               "MaterialExpressionTextureSampleParameter2D": "texture",
               "MaterialExpressionStaticSwitchParameter": "switch", "MaterialExpressionStaticBoolParameter": "switch"}


def install(fake):
    core = __import__(f"{__package__}.core", fromlist=["core"])
    fake.mat_errors = {}

    def exprs(m):
        return m._props.setdefault("__expr", [])

    def base(m):
        seen = 0
        while isinstance(m, core.MaterialInstance) and seen < 20:
            m = m._props.get("parent")
            seen += 1
        return m

    class Stats(core.Object):
        pass

    class MEL(core.Object):
        @staticmethod
        def create_material_expression(material, expression_class, node_pos_x=0, node_pos_y=0):
            e = expression_class(None, material)
            e._props.update({"material_expression_editor_x": node_pos_x, "material_expression_editor_y": node_pos_y})
            if expression_class.__name__ == "MaterialExpressionComponentMask":
                e._props.update({"r": True, "g": True, "b": False, "a": False})
            exprs(material).append(e)
            return e

        @staticmethod
        def get_material_expressions(material):
            return list(exprs(material))

        @staticmethod
        def get_num_material_expressions(material):
            return len(exprs(material))

        @staticmethod
        def delete_material_expression(material, expression):
            ex = exprs(material)
            if expression in ex:
                ex.remove(expression)
            material._props["__links"] = [l for l in material._props.get("__links", [])
                                          if expression not in (l[0], l[2])]
            material._props["__roots"] = {k: v for k, v in material._props.get("__roots", {}).items()
                                          if v[0] is not expression}

        @staticmethod
        def delete_all_material_expressions(material):  # 5.8: skips every other node
            ex = exprs(material)
            material._props["__expr"] = ex[1::2]

        @staticmethod
        def connect_material_expressions(from_expression, from_output_name, to_expression, to_input_name):
            cf, ct = type(from_expression).__name__, type(to_expression).__name__
            if from_output_name and from_output_name not in _OUTS.get(cf, ()) and \
                    cf != "MaterialExpressionMaterialFunctionCall":
                return False
            if ct in _INS and to_input_name not in _INS[ct]:
                return False
            m = to_expression.get_outer()
            m._props.setdefault("__links", []).append((from_expression, from_output_name, to_expression,
                                                       to_input_name))
            return True

        @staticmethod
        def connect_material_property(from_expression, from_output_name, property_):
            cf = type(from_expression).__name__
            if from_output_name and from_output_name not in _OUTS.get(cf, ()):
                return False
            m = from_expression.get_outer()
            m._props.setdefault("__roots", {})[str(property_)] = (from_expression, from_output_name)
            return True

        @staticmethod
        def get_material_property_input_node(material, property_):
            r = material._props.get("__roots", {}).get(str(property_))
            return r[0] if r else None

        @staticmethod
        def recompile_material(material):
            material._props["__compiled"] = material._props.get("__compiled", 0) + 1
            return list(fake.mat_errors.get(material.get_path_name().split(".")[0], []))

        @staticmethod
        def layout_material_expressions(material):
            return None

        @staticmethod
        def get_statistics(material):
            m = base(material)
            s = Stats("MaterialStatistics")
            bad = m is not None and fake.mat_errors.get(m.get_path_name().split(".")[0])
            n = sum(1 for e in exprs(m) if "TextureSample" in type(e).__name__) if m is not None else 0
            s._props.update({"num_samplers": -1 if bad else n, "num_pixel_shader_instructions": 40 + 5 * n,
                             "num_vertex_shader_instructions": 30})
            return s

        # parameters
        @staticmethod
        def _names(material, kind):
            m = base(material)
            if m is None:
                return []
            return [fake.Name(e._props.get("parameter_name")) for e in exprs(m)
                    if _PARAM_KIND.get(type(e).__name__) == kind]

        @staticmethod
        def get_scalar_parameter_names(material):
            return MEL._names(material, "scalar")

        @staticmethod
        def get_vector_parameter_names(material):
            return MEL._names(material, "vector")

        @staticmethod
        def get_texture_parameter_names(material):
            return MEL._names(material, "texture")

        @staticmethod
        def get_static_switch_parameter_names(material):
            return MEL._names(material, "switch")

        @staticmethod
        def set_material_instance_parent(instance, new_parent):
            instance._props["parent"] = new_parent

        @staticmethod
        def _default(instance, name):
            m = instance
            while m is not None:
                if isinstance(m, core.MaterialInstance):
                    v = m._props.get("__params", {}).get(str(name))
                    if v is not None:
                        return v
                    m = m._props.get("parent")
                    continue
                for e in exprs(m):
                    if str(e._props.get("parameter_name")) == str(name):
                        return e._props.get("texture") if "Texture" in type(e).__name__ else \
                            e._props.get("default_value")
                return None
            return None

        @staticmethod
        def _set(instance, name, value):
            instance._props.setdefault("__params", {})[str(name)] = value
            fake.calls.append(("MaterialEditingLibrary.set_param", (str(name), value), {}))
            return False  # as 5.8: bResult is never set

        @staticmethod
        def set_material_instance_scalar_parameter_value(instance, parameter_name, value, association=None):
            return MEL._set(instance, parameter_name, float(value))

        @staticmethod
        def set_material_instance_vector_parameter_value(instance, parameter_name, value, association=None):
            return MEL._set(instance, parameter_name, value)

        @staticmethod
        def set_material_instance_texture_parameter_value(instance, parameter_name, value, association=None):
            return MEL._set(instance, parameter_name, value)

        @staticmethod
        def set_material_instance_static_switch_parameter_value(instance, parameter_name, value, association=None,
                                                                update_material_instance=True):
            return MEL._set(instance, parameter_name, bool(value))

        @staticmethod
        def get_material_instance_scalar_parameter_value(instance, parameter_name, association=None):
            v = MEL._default(instance, parameter_name)
            return float(v) if isinstance(v, (int, float)) else 0.0

        @staticmethod
        def get_material_instance_vector_parameter_value(instance, parameter_name, association=None):
            v = MEL._default(instance, parameter_name)
            return v if isinstance(v, core.LinearColor) else core.LinearColor(0, 0, 0, 0)

        @staticmethod
        def get_material_instance_texture_parameter_value(instance, parameter_name, association=None):
            v = MEL._default(instance, parameter_name)
            return v if isinstance(v, core.Object) else None

        @staticmethod
        def get_material_instance_static_switch_parameter_value(instance, parameter_name, association=None):
            return bool(MEL._default(instance, parameter_name) or False)

        @staticmethod
        def update_material_instance(instance):
            instance._props["__updated"] = instance._props.get("__updated", 0) + 1

    fake.MaterialEditingLibrary = MEL
    fake._classes["MaterialEditingLibrary"] = MEL
