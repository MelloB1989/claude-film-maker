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

import json
import os

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
    _install_meshes(fake)
    _install_import(fake)
    _install_import_results(fake)


def _install_meshes(fake):
    """Meshes with numbers, the static mesh editor subsystem, asset registry tags and references."""
    core = __import__(f"{__package__}.core", fromlist=["core"])
    fake.refs = {}  # package -> set of packages it depends on

    class Box(core.Object):
        pass

    class StaticMaterial(core.Object):
        pass

    def mesh_data(m):
        return m._props.setdefault("__mesh", {"size": [100.0, 100.0, 100.0], "tris": 1000, "lods": 1,
                                              "nanite": False, "keep": 1.0, "simple": 0, "convex": 0,
                                              "uv": 1, "lod_group": "None"})

    def get_num_lods(self):
        return mesh_data(self)["lods"]

    def get_num_triangles(self, lod_index=0):
        return int(mesh_data(self)["tris"] / (2 ** lod_index))

    def get_num_vertices(self, lod_index=0):
        return int(mesh_data(self)["tris"] * 0.6 / (2 ** lod_index))

    def get_bounding_box(self):
        x, y, z = mesh_data(self)["size"]
        b = Box("Box")
        b._props.update({"min": core.Vector(-x / 2, -y / 2, 0), "max": core.Vector(x / 2, y / 2, z)})
        return b

    def get_bounds(self):
        x, y, z = mesh_data(self)["size"]
        b = Box("BoxSphereBounds")
        b._props.update({"origin": core.Vector(0, 0, z / 2), "box_extent": core.Vector(x / 2, y / 2, z / 2)})
        return b

    def set_material(self, material_index, new_material):
        slots = self._props.get("static_materials") or []
        slots[material_index]._props["material_interface"] = new_material

    for cls in (core.StaticMesh, core.SkeletalMesh):
        cls.get_bounds = get_bounds
    core.StaticMesh.get_num_lods = get_num_lods
    core.StaticMesh.get_num_triangles = get_num_triangles
    core.StaticMesh.get_num_vertices = get_num_vertices
    core.StaticMesh.get_bounding_box = get_bounding_box
    core.StaticMesh.set_material = set_material

    class SME(core.Object):
        def get_nanite_settings(self, static_mesh):
            d = mesh_data(static_mesh)
            s = core.Object("MeshNaniteSettings")
            s._props.update({"enabled": d["nanite"], "keep_percent_triangles": d["keep"]})
            return s

        def set_nanite_settings(self, static_mesh, nanite_settings, apply_changes=True):
            d = mesh_data(static_mesh)
            d["nanite"] = bool(nanite_settings._props["enabled"])
            d["keep"] = float(nanite_settings._props["keep_percent_triangles"])

        def get_lod_count(self, static_mesh):
            return mesh_data(static_mesh)["lods"]

        def set_lods(self, static_mesh, reduction_options):
            n = len(reduction_options._props.get("reduction_settings") or [])
            mesh_data(static_mesh)["lods"] = n
            return n

        def get_lod_group(self, static_mesh):
            return fake.Name(mesh_data(static_mesh)["lod_group"])

        def set_lod_group(self, static_mesh, lod_group, rebuild_immediately=True):
            mesh_data(static_mesh)["lod_group"] = str(lod_group)
            return True

        def get_simple_collision_count(self, static_mesh):
            return mesh_data(static_mesh)["simple"]

        def get_convex_collision_count(self, static_mesh):
            return mesh_data(static_mesh)["convex"]

        def remove_collisions(self, static_mesh):
            mesh_data(static_mesh).update(simple=0, convex=0)
            return True

        def add_simple_collisions(self, static_mesh, shape_type):
            mesh_data(static_mesh)["simple"] += 1
            static_mesh._props["body_setup"] = core.Object("BodySetup")
            return 0

        def set_convex_decomposition_collisions(self, static_mesh, hull_count, max_hull_verts, hull_precision):
            mesh_data(static_mesh).update(convex=int(hull_count), simple=int(hull_count))
            return True

        def set_generate_lightmap_uv(self, static_mesh, generate_lightmap_uv):
            mesh_data(static_mesh)["lightmap"] = bool(generate_lightmap_uv)
            return True

        def set_allow_cpu_access(self, static_mesh, allow_cpu_access):
            static_mesh._props["allow_cpu_access"] = bool(allow_cpu_access)

        def get_num_uv_channels(self, static_mesh, lod_index=0):
            return mesh_data(static_mesh)["uv"]

    fake.StaticMeshEditorSubsystem = SME
    fake._classes["StaticMeshEditorSubsystem"] = SME

    def add_mesh(path, size=(100, 100, 100), tris=1000, lods=1, materials=("Body",), skeletal=False, nanite=False,
                 saved=True):
        m = fake.add_asset(path, "SkeletalMesh" if skeletal else "StaticMesh")
        mesh_data(m).update(size=[float(v) for v in size], tris=tris, lods=lods, nanite=nanite)
        slots = []
        for n in materials:
            s = StaticMaterial(n)
            s._props.update({"material_slot_name": fake.Name(n), "material_interface": None})
            slots.append(s)
        m._props["static_materials" if not skeletal else "materials"] = slots
        m._props["allow_cpu_access"] = False
        m._props["__saved_tags"] = saved
        return m

    fake.add_mesh = add_mesh

    def get_tag_value(self, tag):
        a = self._obj
        tags = dict(a._props.get("__tags", {}))
        if "__mesh" in a._props and a._props.get("__saved_tags", True):
            d = a._props["__mesh"]
            tags.update(ApproxSize="x".join(str(int(round(v))) for v in d["size"]), Triangles=str(d["tris"]),
                        Vertices=str(int(d["tris"] * 0.6)), LODs=str(d["lods"]),
                        NaniteEnabled="True" if d["nanite"] else "False",
                        Materials=str(len(a._props.get("static_materials") or a._props.get("materials") or [])))
        v = tags.get(str(tag))
        return None if v is None else str(v)

    def is_redirector(self):
        return type(self._obj).__name__ == "ObjectRedirector"

    fake.tag_providers.append(get_tag_value)
    core.AssetData.is_redirector = is_redirector

    def _objs(v):
        if isinstance(v, core.Object):
            yield v
            if not v._path:  # a struct (a static material slot): what it holds
                for x in v._props.values():
                    if isinstance(x, core.Object):
                        yield x
        elif isinstance(v, (list, tuple)):
            for x in v:
                yield from _objs(x)
        elif isinstance(v, dict):
            for x in v.values():
                yield from _objs(x)

    def _derived(pkg):
        """What an asset points at (parent, slot materials, texture parameters), as the registry records on save."""
        a = fake.assets.get(str(pkg))
        out = set()
        if a is None:
            return out
        for k, v in a._props.items():
            if k in ("__mesh", "__tags", "__expr", "__links", "__roots"):
                continue
            for o in _objs(v):
                q = o._path.split(".")[0] if o._path else ""
                if q and q != str(pkg) and q in fake.assets:
                    out.add(q)
        for e in a._props.get("__expr", []):  # a material's textures
            for o in _objs(e._props.get("texture")):
                if o._path:
                    out.add(o._path.split(".")[0])
        return out

    def _deps(pkg):
        return sorted(set(fake.refs.get(str(pkg), set())) | _derived(pkg))

    def get_dependencies(self, package_name, dependency_options=None):
        return [fake.Name(x) for x in _deps(package_name)] or None  # bool+out: None when nothing

    def get_referencers(self, package_name, dependency_options=None):
        out = [fake.Name(k) for k in sorted(set(fake.refs) | set(fake.assets)) if str(package_name) in _deps(k)]
        return out or None

    def get_metadata_tag_values(obj):
        return {fake.Name(k): v for k, v in obj._props.get("__metadata", {}).items()}

    def remove_metadata_tag(obj, tag):
        obj._props.get("__metadata", {}).pop(str(tag), None)

    core.EditorAssetLibrary.get_metadata_tag_values = staticmethod(get_metadata_tag_values)
    core.EditorAssetLibrary.remove_metadata_tag = staticmethod(remove_metadata_tag)

    core.AssetRegistry.get_dependencies = get_dependencies
    core.AssetRegistry.get_referencers = get_referencers


def _install_import(fake):
    """Interchange pipelines with their real sub-pipelines (the ops set fields on them), and import options whose
    struct-valued fields exist (conversion settings)."""
    core = __import__(f"{__package__}.core", fromlist=["core"])

    def sub(name):
        return type(name, (core.Object,), {"__module__": "unreal"})

    Mesh, Common, Skel = sub("InterchangeGenericMeshPipeline"), sub("InterchangeGenericCommonMeshesProperties"), \
        sub("InterchangeGenericCommonSkeletalMeshesAndAnimationsProperties")
    Anim, Mat, Tex = sub("InterchangeGenericAnimationPipeline"), sub("InterchangeGenericMaterialPipeline"), \
        sub("InterchangeGenericTexturePipeline")

    class InterchangeGenericAssetsPipeline(core.Object):
        def __init__(self, name=None, outer=None, **props):
            super().__init__(name, outer, **props)
            mat = Mat("material_pipeline", self)
            mat._props["texture_pipeline"] = Tex("texture_pipeline", mat)
            self._props.update(mesh_pipeline=Mesh("mesh_pipeline", self), animation_pipeline=Anim("anim", self),
                               common_meshes_properties=Common("common", self), material_pipeline=mat,
                               common_skeletal_meshes_and_animations_properties=Skel("skel", self),
                               import_offset_uniform_scale=1.0)

    class InterchangePipelineStackOverride(core.Object):
        def add_pipeline(self, pipeline):
            self._props.setdefault("override_pipelines", []).append(pipeline)

    class Conversion(core.Object):
        pass

    class AbcImportSettings(core.Object):
        def __init__(self, name=None, outer=None, **props):
            super().__init__(name, outer, **props)
            self._props["conversion_settings"] = Conversion("AbcConversionSettings")

    class GroomImportOptions(core.Object):
        def __init__(self, name=None, outer=None, **props):
            super().__init__(name, outer, **props)
            self._props["conversion_settings"] = Conversion("GroomConversionSettings")

    for c in (InterchangeGenericAssetsPipeline, InterchangePipelineStackOverride, AbcImportSettings,
              GroomImportOptions, Mesh, Common, Skel, Anim, Mat, Tex):
        setattr(fake, c.__name__, c)
        fake._classes[c.__name__] = c


def _install_import_results(fake):
    """import_asset_tasks as WP2 needs it: the source file in the AssetImportData registry tag and import data
    (as the engine writes them), a mesh's size and triangles read from an OBJ / glTF file, a re-import (replace
    over an existing asset) re-reading the file, and Interchange's reimport_asset."""
    core = __import__(f"{__package__}.core", fromlist=["core"])
    tools_cls = core.AssetTools
    # the core's own import, captured once: install() runs per fresh fake and must not wrap its own wrapper (a
    # chain of wrappers would write into earlier tests' fakes)
    if not hasattr(core, "_wp2_core_import"):
        core._wp2_core_import = tools_cls.import_asset_tasks
    base_import = core._wp2_core_import

    def read_mesh(f):
        ext = os.path.splitext(f)[1].lower()
        try:
            if ext == ".obj":
                vs, faces = [], 0
                for line in open(f):
                    if line.startswith("v "):
                        vs.append([float(x) for x in line.split()[1:4]])
                    elif line.startswith("f "):
                        faces += len(line.split()) - 3
                if vs:
                    return [max(v[i] for v in vs) - min(v[i] for v in vs) for i in range(3)], faces
            if ext == ".gltf":
                acc = json.load(open(f))["accessors"][0]
                return [100.0 * (b - a) for a, b in zip(acc["min"], acc["max"])], 12
        except (OSError, ValueError, KeyError, IndexError):
            pass
        return None, None

    class ImportData(core.Object):
        def extract_filenames(self):
            return list(self._props.get("files", []))

        def scripted_add_filename(self, filename, index, label):
            files = self._props.setdefault("files", [])
            files[index:index + 1] = [filename]

    def tag_source(asset, f):
        asset._props.setdefault("__tags", {})["AssetImportData"] = json.dumps([{"RelativeFilename": f}])
        asset._props["asset_import_data"] = ImportData("AssetImportData", files=[f])
        size, tris = read_mesh(f)
        if size and type(asset).__name__ in ("StaticMesh", "SkeletalMesh"):
            d = asset._props.setdefault("__mesh", {"size": [100.0] * 3, "tris": 1000, "lods": 1, "nanite": False,
                                                   "keep": 1.0, "simple": 0, "convex": 0, "uv": 1,
                                                   "lod_group": "None"})
            d.update(size=[round(v, 3) for v in size], tris=tris)
            if not asset._props.get("static_materials"):  # one default slot, as an OBJ without a .mtl gets
                slot = core.Object("StaticMaterial", material_slot_name=fake.Name("DefaultMaterial"),
                                   material_interface=None)
                asset._props["static_materials"] = [slot]

    def import_asset_tasks(self, import_tasks):
        for t in import_tasks:  # replace over an existing asset: the engine re-imports it in place
            stem = os.path.splitext(os.path.basename(t.filename))[0]
            path = f"{t.destination_path.rstrip('/')}/{t.destination_name or stem}"
            if path in fake.assets and t.replace_existing:
                tag_source(fake.assets[path], t.filename)
                t.imported_object_paths = [f"{path}.{path.rsplit('/', 1)[-1]}"]
                fake.imports.append((t.filename, path))
        base_import(self, [t for t in import_tasks if not t.imported_object_paths])
        for t in import_tasks:
            for op_ in t.imported_object_paths or []:
                tag_source(fake.assets[op_.split(".")[0]], t.filename)

    tools_cls.import_asset_tasks = import_asset_tasks

    class InterchangeManager(core.Object):
        @staticmethod
        def get_interchange_manager_scripted():
            return fake.singleton(InterchangeManager)

        @staticmethod
        def create_source_data(in_file_name):
            return core.Object("InterchangeSourceData", filename=in_file_name)

        def reimport_asset(self, object_to_reimport, import_asset_parameters):
            files = object_to_reimport._props.get("asset_import_data")
            files = files.extract_filenames() if files is not None else []
            if not files or not os.path.isfile(files[0]):
                return None
            tag_source(object_to_reimport, files[0])
            return [object_to_reimport]

    fake.InterchangeManager = InterchangeManager  # a test swaps the manager: fake._singletons[InterchangeManager]
    fake._classes["InterchangeManager"] = InterchangeManager
