"""WP10's groom fakes (B28): GroomComponent (a MeshComponent with groom/binding assets, GroomGroupsDesc per group
and hair material instances), HairGroupDesc, MaterialInstanceDynamic, the MaterialEditingLibrary parameter reads, and
the r.HairStrands.SkyLighting cvar.

    fake.groom(actor, name="Hair", groups=1, params={"hairMelanin": 0.5, ...})   a groom component with an MIC
A material's parameters live in its _props["scalars"] / _props["vectors"] dicts.
"""
from __future__ import annotations

from . import core


class HairGroupDesc(core.Object):
    DEFAULTS = {"hair_width": 0.1, "hair_width_override": False, "hair_root_scale": 1.0,
                "hair_root_scale_override": False, "hair_tip_scale": 1.0, "hair_tip_scale_override": False,
                "hair_shadow_density": 1.0, "hair_shadow_density_override": False, "lod_bias": 0.0,
                "hair_length_scale": 1.0, "hair_length_scale_override": False}

    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **{**self.DEFAULTS, **props})


class MaterialInstanceDynamic(core.MaterialInstance):
    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        self._props.setdefault("scalars", {})
        self._props.setdefault("vectors", {})

    def set_scalar_parameter_value(self, name, value):
        self._props["scalars"][str(name)] = float(value)

    def get_scalar_parameter_value(self, name):
        return float(self._props["scalars"].get(str(name), 0.0))

    def set_vector_parameter_value(self, name, value):
        self._props["vectors"][str(name)] = [value.r, value.g, value.b, value.a]


class GroomComponent(core.MeshComponent):
    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        self._props.setdefault("groom_groups_desc", [])
        self._props.setdefault("use_cards", False)

    def get_materials(self):
        return list(self._props.get("override_materials", []))

    def create_dynamic_material_instance(self, element_index, source_material=None, optional_name=None):
        src = source_material or self.get_material(element_index)
        mid = MaterialInstanceDynamic(str(optional_name or f"MID_{element_index}"), self)
        mid._props["scalars"] = dict((src._props.get("scalars") or {}) if src is not None else {})
        mid._props["vectors"] = dict((src._props.get("vectors") or {}) if src is not None else {})
        mid._props["parent"] = src
        self.set_material(element_index, mid)
        return mid


class MaterialEditingLibrary(core.Object):
    @staticmethod
    def get_scalar_parameter_names(material):
        return [core.Name(n) for n in (material._props.get("scalars") or {})] if material is not None else []

    @staticmethod
    def get_vector_parameter_names(material):
        return [core.Name(n) for n in (material._props.get("vectors") or {})] if material is not None else []

    @staticmethod
    def get_material_instance_scalar_parameter_value(instance, parameter_name, association=None):
        return float((instance._props.get("scalars") or {}).get(str(parameter_name), 0.0))


class ComponentSync(core.Object):
    """FComponentSync: its `name` is a property (the synced component's), not the object's name."""

    def __init__(self, name=None, sync_option=None, **props):
        super().__init__("ComponentSync", None, **props)
        self._props.update(name=name, sync_option=sync_option)


class LODSyncComponent(core.ActorComponent):
    """R5 groom.lock: forced_lod, components_to_sync (ComponentSync name/sync_option), and the debug text of what it
    resolved. As in the engine, the names resolve to live components on register only (`fake.lodsync(...)` and
    `register()`), not when the list is edited."""

    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        self._props.setdefault("forced_lod", -1)
        self._props.setdefault("num_lods", -1)
        self._props.setdefault("components_to_sync", [])
        self._resolved = []

    def register(self):
        names = {c.get_name() for c in self.get_owner().get_components_by_class(core.ActorComponent)}
        self._resolved = [str(s.get_editor_property("name")) for s in self._props["components_to_sync"]
                          if str(s.get_editor_property("name")) in names]

    def get_lod_sync_debug_text(self):
        lod = self._props["forced_lod"] if self._props["forced_lod"] >= 0 else 3  # auto: a wide shot's LOD
        return "".join(f"{n} : {lod}\n" for n in self._resolved)


def _both(name, theirs, mine):
    """A MaterialEditingLibrary read that answers from WP2's storage and from ours."""
    if name.endswith("_names"):
        def names(material):
            out = list(theirs(material) or [])
            have = {str(x) for x in out}
            return out + [x for x in mine(material) if str(x) not in have]
        return names

    def value(instance, parameter_name, association=None):
        if str(parameter_name) in (instance._props.get("scalars") or {}):
            return mine(instance, parameter_name, association)
        return theirs(instance, parameter_name, association)
    return value


def install(fake):
    for cls in (HairGroupDesc, MaterialInstanceDynamic, GroomComponent, LODSyncComponent, ComponentSync):
        setattr(fake, cls.__name__, cls)
        fake._classes[cls.__name__] = cls
    # keep any MaterialEditingLibrary another ext made: add the reads it lacks
    mel = fake._classes.get("MaterialEditingLibrary")
    if mel is None or not isinstance(mel, type):
        fake.MaterialEditingLibrary = MaterialEditingLibrary
        fake._classes["MaterialEditingLibrary"] = MaterialEditingLibrary
    else:  # WP2's library (ext_assets) keeps instance params in _props["__params"]; ours in "scalars"/"vectors":
        # each read answers from both, so a groom material made here is readable through either library
        mine = MaterialEditingLibrary.__dict__
        for n in ("get_scalar_parameter_names", "get_vector_parameter_names",
                  "get_material_instance_scalar_parameter_value"):
            theirs = next((k.__dict__[n] for k in mel.__mro__ if n in k.__dict__), None)
            if theirs is None:
                setattr(mel, n, mine[n])
                continue
            setattr(mel, n, staticmethod(_both(n, theirs.__func__ if isinstance(theirs, staticmethod) else theirs,
                                               mine[n].__func__)))
    fake.cvars.setdefault("r.HairStrands.SkyLighting", "1")
    for k, v in (("r.HairStrands.LODMode", "1"), ("r.HairStrands.AutoLOD.Bias", "0.1"),
                 ("r.HairStrands.UseCardsInsteadOfStrands", "0")):
        fake.cvars.setdefault(k, v)

    def groom(actor, name="Hair", groups=1, params=None, asset="/Game/Hair/GR_Hair"):
        a = fake.actor(actor) if isinstance(actor, str) else actor
        c = a.add_component(GroomComponent, name)
        c._props["groom_groups_desc"] = [HairGroupDesc(f"desc{g}", c) for g in range(groups)]
        mic = core.MaterialInstanceConstant(f"MI_{name}")
        mic._props["scalars"] = dict(params or {"hairMelanin": 0.5, "hairRedness": 0.3, "HairRoughness": 0.4,
                                               "WhiteAmount": 0.0, "LightAmount": 0.0})
        mic._props["vectors"] = {"HairDye": [0, 0, 0, 1]}
        c.set_material(0, mic)
        ga = fake.add_asset(asset, "GroomAsset") if asset not in fake.assets else fake.assets[asset]
        if "hair_groups_lod" not in ga._props:  # a MetaHuman groom: strands LOD 0-1, cards 2-3, helmet mesh 4
            geo = ["STRANDS", "STRANDS", "CARDS", "CARDS", "MESHES"]
            lods = [core.Object(f"lod{i}", ga, geometry_type=core.EnumValue("GroomGeometryType", t), visible=True,
                                screen_size=[1.0, 0.8, 0.4, 0.2, 0.1][i], curve_decimation=1.0)
                    for i, t in enumerate(geo)]
            ga._props["hair_groups_lod"] = [core.Object(f"group{g}", ga, lo_ds=lods, auto_lod_bias=0.0)
                                            for g in range(groups)]
            ga._props["lod_mode"] = core.EnumValue("GroomLODMode", "DEFAULT")
            ga._props["auto_lod_bias"] = 0.0
        c._props["groom_asset"] = ga
        return c

    fake.groom = groom

    def lodsync(actor, names=("Body", "Face", "Hair", "Eyebrows"), name="LODSync"):
        a = fake.actor(actor) if isinstance(actor, str) else actor
        c = a.add_component(LODSyncComponent, name)
        c._props["components_to_sync"] = [ComponentSync(name=n, sync_option=core.EnumValue(
            "SyncOption", "DRIVE" if n in ("Body", "Face") else "PASSIVE")) for n in names]
        c.register()
        return c

    fake.lodsync = lodsync
