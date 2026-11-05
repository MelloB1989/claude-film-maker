"""The MetaHuman fakes (WP3): a UMetaHumanCharacter asset with its settings structs, the MetaHuman Character editor
subsystem (body constraints, face model, commits, cloud rig/textures that finish over ticks and write the engine's
log lines, build), the palette (collection, default instance, slot selections, instance parameters) and the engine
enums the mh ops name. Faithful in shape (names, copies, the order things must happen in), not in geometry.

Test knobs on the fake (`ue`): ue.mh_rig_ticks / ue.mh_tex_ticks (how long a cloud request takes),
ue.mh_fail_rig (log a rig failure instead), ue.mh_log (the log file the requests write to).
"""
from __future__ import annotations

import copy
import os

from . import core


# ------------------------------------------------------------------------------------------------------- structs

class FakeStruct:
    """An engine struct value: named fields, attribute and editor-property access, copy()."""

    _FIELDS: dict = {}

    def __init__(self, **values):
        object.__setattr__(self, "_v", copy.deepcopy(self._FIELDS))
        for k, v in values.items():
            self.set_editor_property(k, v)

    def _fm_fields(self):
        return list(self._v)

    def get_editor_property(self, name):
        if name not in self._v:
            raise AttributeError(f"{type(self).__name__} has no property {name!r}")
        return copy.deepcopy(self._v[name]) if isinstance(self._v[name], FakeStruct) else self._v[name]

    def set_editor_property(self, name, value, notify_mode=None):
        if name not in self._v:
            raise AttributeError(f"{type(self).__name__} has no property {name!r}")
        self._v[name] = copy.deepcopy(value) if isinstance(value, FakeStruct) else value

    def __getattr__(self, name):
        v = object.__getattribute__(self, "_v")
        if name in v:
            return copy.deepcopy(v[name]) if isinstance(v[name], FakeStruct) else v[name]
        raise AttributeError(name)

    def __setattr__(self, name, value):
        self.set_editor_property(name, value)

    def copy(self):
        return copy.deepcopy(self)

    def __eq__(self, other):
        return type(other) is type(self) and other._v == self._v

    def __repr__(self):
        return f"<{type(self).__name__} {self._v}>"


def struct(name: str, fields: dict):
    return type(name, (FakeStruct,), {"_FIELDS": fields})


_ENUM_CLASSES: dict = {}


def fenum(name: str, members: list):
    """An engine enum class whose members exist up front (so the ops' name lookup can list them); its values are
    instances of it, as in the engine (type(value) is the enum class)."""
    cls = _ENUM_CLASSES.get(name)
    if cls is None:
        cls = type(name, (core.EnumValue,), {"__module__": "unreal"})
        for m in members:
            setattr(cls, m, cls(name, m))
        _ENUM_CLASSES[name] = cls
    return cls


ENUMS = {
    "MetaHumanRigType": ["JOINTS_ONLY", "JOINTS_AND_BLEND_SHAPES"],
    "MetaHumanDefaultPipelineType": ["CINEMATIC", "OPTIMIZED", "UEFN"],
    "MetaHumanQualityLevel": ["LOW", "MEDIUM", "HIGH", "CINEMATIC"],
    "MetaHumanCharacterFrecklesMask": ["NONE", "TYPE1", "TYPE2", "TYPE3"],
    "MetaHumanCharacterEyesIrisPattern": [f"IRIS00{i}" for i in range(1, 10)],
    "MetaHumanCharacterEyesBlendMethod": ["RADIAL", "STRUCTURAL"],
    "MetaHumanCharacterEyelashesType": ["NONE", "SHORT_SPARSE", "SHORT_FINE", "SHORT_THIN", "LONG_SLIGHT_CURL",
                                        "LONG_CURL", "LONG_THICK_CURL"],
    "MetaHumanCharacterEyeMakeupType": ["NONE", "THIN_LINER", "SOFT_SMOKEY", "FULL_THIN_LINER", "CAT_EYE",
                                        "PANDA_SMUDGE", "DRAMATIC_SMUDGE", "DOUBLE_MOD", "CLASSIC_BAR"],
    "MetaHumanCharacterBlushMakeupType": ["NONE", "ANGLED", "APPLE", "LOW_SWEEP", "HIGH_CURVE"],
    "MetaHumanCharacterLipsMakeupType": ["NONE", "NATURAL", "HOLLYWOOD", "CUPID"],
    "RequestTextureResolution": ["RES2K", "RES4K", "RES8K"],
    "MetaHumanCharacterInstanceParameterType": ["NONE", "BOOL", "FLOAT", "NAME", "STRING", "COLOR", "OBJECT",
                                                "SOFT_OBJECT"],
}


def _e(enum: str, member: str):
    return getattr(fenum(enum, ENUMS[enum]), member)


def _lc(r, g, b, a=1.0):
    return core.LinearColor(r, g, b, a)


SkinProperties = struct("MetaHumanCharacterSkinProperties", {
    "u": 0.5, "v": 0.5, "show_top_underwear": True, "body_texture_index": 0, "face_texture_index": 0,
    "roughness": 1.06, "palm_lightness": 0.75, "fingernail_tint_color": _lc(0.083, 0.0, 0.005), "fingernail_tint_intensity": 0.0})
Freckles = struct("MetaHumanCharacterFrecklesProperties", {
    "density": 0.5, "strength": 0.2, "saturation": 0.6, "tone_shift": 0.65, "mask": _e("MetaHumanCharacterFrecklesMask", "NONE")})
Accent = struct("MetaHumanCharacterAccentRegionProperties", {"redness": 0.5, "saturation": 0.5, "lightness": 0.5})
Accents = struct("MetaHumanCharacterAccentRegions", {k: Accent() for k in (
    "scalp", "forehead", "nose", "under_eye", "cheeks", "lips", "chin", "ears")})
Resolutions = struct("MetaHumanCharacterTextureSourceResolutions", {k: _e("RequestTextureResolution", "RES2K") for k in (
    "face_albedo", "face_normal", "face_cavity", "face_animated_maps", "body_albedo", "body_normal", "body_cavity",
    "body_masks")})
SkinSettings = struct("MetaHumanCharacterSkinSettings", {
    "skin": SkinProperties(), "freckles": Freckles(), "accents": Accents(),
    "desired_texture_sources_resolutions": Resolutions(), "enable_texture_overrides": False})
Iris = struct("MetaHumanCharacterEyeIrisProperties", {
    "pattern": _e("MetaHumanCharacterEyesIrisPattern", "IRIS001"), "rotation": 0.0, "primary_color_u": 0.5, "primary_color_v": 0.5,
    "secondary_color_u": 0.5, "secondary_color_v": 0.5, "color_blend": 0.5, "blend_method": _e("MetaHumanCharacterEyesBlendMethod", "STRUCTURAL"),
    "limbal_ring_size": 0.725, "limbal_ring_color": _lc(0, 0, 0)})
Pupil = struct("MetaHumanCharacterEyePupilProperties", {"dilation": 0.95, "feather": 0.45})
Sclera = struct("MetaHumanCharacterEyeScleraProperties", {"rotation": 0.0, "use_custom_tint": False, "tint": _lc(1, 1, 1),
                                                         "vascularity_intensity": 1.0, "vascularity_coverage": 0.2})
Cornea = struct("MetaHumanCharacterEyeCorneaProperties", {"size": 0.165, "limbus_softness": 0.09})
Eye = struct("MetaHumanCharacterEyeProperties", {"iris": Iris(), "pupil": Pupil(), "cornea": Cornea(),
                                                 "sclera": Sclera()})
EyesSettings = struct("MetaHumanCharacterEyesSettings", {"eye_left": Eye(), "eye_right": Eye()})
Eyelashes = struct("MetaHumanCharacterEyelashesProperties", {
    "type": _e("MetaHumanCharacterEyelashesType", "NONE"), "dye_color": _lc(1, 1, 1), "melanin": 0.3, "redness": 0.28, "roughness": 0.25, "salt_and_pepper": 0.2,
    "lightness": 0.5, "enable_grooms": True})
Teeth = struct("MetaHumanCharacterTeethProperties", {
    "tooth_length": 0.0, "tooth_spacing": 0.0, "upper_shift": 0.0, "lower_shift": 0.0, "overbite": 0.0,
    "overjet": 0.0, "worn_down": 0.0, "polycanine": 0.0, "receding_gums": 0.0, "narrowness": 0.0, "variation": 0.0,
    "jaw_open": 0.0, "teeth_color": _lc(1, 1, 1), "gum_color": _lc(1, 1, 1), "plaque_color": _lc(1, 1, 1),
    "plaque_amount": 0.0, "enable_show_teeth_expression": False})
HeadModel = struct("MetaHumanCharacterHeadModelSettings", {"eyelashes": Eyelashes(), "teeth": Teeth()})
Foundation = struct("MetaHumanCharacterFoundationMakeupProperties", {"apply_foundation": False, "color": _lc(0, 0, 0),
                                                                    "intensity": 0.5, "concealer": 0.57})
EyeMakeup = struct("MetaHumanCharacterEyeMakeupProperties", {"type": _e("MetaHumanCharacterEyeMakeupType", "NONE"), "primary_color": _lc(0.086, 0.013, 0.004), "opacity": 0.85})
Blush = struct("MetaHumanCharacterBlushMakeupProperties", {"type": _e("MetaHumanCharacterBlushMakeupType", "NONE"), "color": _lc(0.224, 0.011, 0.02), "intensity": 0.4})
Lips = struct("MetaHumanCharacterLipsMakeupProperties", {"type": _e("MetaHumanCharacterLipsMakeupType", "NONE"), "color": _lc(0.22, 0.01, 0.008), "opacity": 0.7})
Makeup = struct("MetaHumanCharacterMakeupSettings", {"foundation": Foundation(), "eyes": EyeMakeup(),
                                                     "blush": Blush(), "lips": Lips()})
BodyConstraint = struct("MetaHumanCharacterBodyConstraint", {
    "name": "", "is_active": False, "target_measurement": 100.0, "min_measurement": 50.0, "max_measurement": 50.0})
RigParams = struct("MetaHumanCharacterAutoRiggingRequestParams", {"rig_type": None, "report_progress": True,
                                                                   "blocking": False})
TexParams = struct("MetaHumanCharacterTextureRequestParams", {"report_progress": True, "blocking": False})
BuildParams = struct("MetaHumanCharacterEditorBuildParameters", {
    "pipeline_type": None, "pipeline_quality": None, "animation_system_name": "", "absolute_build_path": "",
    "name_override": "", "common_folder_path": "", "enable_wardrobe_item_validation": True})

BODY = {"Height": (170.0, 140, 210), "Chest": (95.0, 70, 140), "Waist": (75.0, 55, 130), "Hip": (95.0, 70, 140),
        "Across Shoulder": (40.0, 30, 55), "Neck": (35.0, 28, 50), "Bicep": (28.0, 20, 45), "Thigh": (52.0, 38, 80),
        "Fat": (0.0, -3, 3), "Muscularity": (0.0, -3, 3), "Masculine/Feminine": (0.0, -3, 3)}
GROOM_PARAMS = {"Melanin": 0.16, "Redness": 0.0, "Roughness": 0.25, "Whiteness": 0.0, "Lightness": 0.0,
                "DyeColor": core.LinearColor(1, 1, 1), "bUseOmbre": False, "OmbreU": 0.0, "OmbreV": 0.0,
                "OmbreIntensity": 0.0}


# ---------------------------------------------------------------------------------------------------- the palette

class PaletteKey(FakeStruct):
    _FIELDS = {"name": ""}

    def to_asset_name_string(self):
        return self._v["name"]

    def is_null(self):
        return not self._v["name"]


class ItemPath(FakeStruct):
    _FIELDS = {"item": None}


class SlotSelection(FakeStruct):
    _FIELDS = {"slot_name": "", "selected_item": None}

    def get_selected_item_path(self):
        return ItemPath(item=self._v["selected_item"])


class SlotSelectionData(FakeStruct):
    _FIELDS = {"selection": None}


class InstanceParameter(FakeStruct):
    """A live handle on one parameter of an item on an instance (FMetaHumanCharacterInstanceParameter)."""
    _FIELDS = {"name": "", "type": None, "item_path": None}

    def _bag(self):
        return self._fm_inst._params[self._fm_key]

    def _get(self, kind):
        return self._bag().get(self._v["name"]) if self._v["type"] == kind else None

    def _set(self, kind, v):
        if self._v["type"] != kind:
            return False
        self._bag()[self._v["name"]] = v
        return True

    def get_float(self):
        return self._get("FLOAT")

    def set_float(self, v):
        return self._set("FLOAT", float(v))

    def get_bool(self):
        return self._get("BOOL")

    def set_bool(self, v):
        return self._set("BOOL", bool(v))

    def get_name(self):
        return self._get("NAME")

    def set_name(self, v):
        return self._set("NAME", str(v))

    def get_string(self):
        return self._get("STRING")

    def set_string(self, v):
        return self._set("STRING", str(v))

    def get_color(self):
        return self._get("COLOR")

    def set_color(self, v):
        return self._set("COLOR", v)


class MetaHumanCharacterAssemblyResult:
    SUCCEEDED = "<MetaHumanCharacterAssemblyResult.SUCCEEDED: 0>"
    FAILED = "<MetaHumanCharacterAssemblyResult.FAILED: 1>"


class Assembled:
    """unreal.MetaHumanCharacterAssembled: the dynamic delegate MetaHumanInstance.assemble calls when done."""

    def __init__(self):
        self._fns = []

    def bind_callable(self, fn):
        import inspect
        n = len([p for p in inspect.signature(fn).parameters.values()
                 if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)])
        if n != 1:  # live 5.8.4: the delegate passes the assembly result
            raise Exception(f"MetaHumanCharacterAssembled: Callable has the incorrect number of arguments "
                            f"(expected 1, got {n})")
        self._fns = [fn]

    def _fire(self, result=None):
        for f in self._fns:
            f(result)


class MetaHumanInstance(core.Object):
    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        object.__setattr__(self, "_sel", {})       # slot -> key name
        object.__setattr__(self, "_params", {})    # key name -> {param: value}
        object.__setattr__(self, "_assembled", False)  # live: no item has instance parameters until assembled
        object.__setattr__(self, "_pending", None)     # (delegate, polls left) of an assembly not done yet

    def get_slot_selection_data(self):
        return [SlotSelectionData(selection=SlotSelection(slot_name=s, selected_item=PaletteKey(name=k)))
                for s, k in self._sel.items()]

    def set_single_slot_selection(self, slot_name, item_key):
        core._fake().calls.append(("MetaHumanInstance.set_single_slot_selection", (slot_name, item_key), {}))
        self._sel[str(slot_name)] = item_key.to_asset_name_string() if item_key is not None else ""
        object.__setattr__(self, "_assembled", False)  # a new selection needs a new assembly for its parameters

    def is_assembled(self):
        pend = getattr(self, "_pending", None)
        if pend:
            d, n = pend
            object.__setattr__(self, "_pending", (d, n - 1))
            if n - 1 <= 0:
                self._finish()
        return self._assembled

    ASYNC_POLLS = 0  # >0: the assembly finishes only after that many is_assembled() polls (live it may take ticks)

    def assemble(self, on_assembled):
        """x.assemble(on_assembled) -> None (live 5.8.4 doc): the delegate is called when the assembly is done."""
        core._fake().calls.append(("MetaHumanInstance.assemble", (on_assembled,), {}))
        if not isinstance(on_assembled, Assembled):
            raise TypeError("assemble() required argument 'on_assembled' (pos 1) not found")
        object.__setattr__(self, "_pending", (on_assembled, self.ASYNC_POLLS))
        if not self.ASYNC_POLLS:
            self._finish()

    def _finish(self):
        d, _ = self._pending
        object.__setattr__(self, "_pending", None)
        c = getattr(self, "_char", None)
        # live 5.8.4 (day 1): 'Failed to assemble Instance ..., as the referenced Collection ... has not been built'
        # (FAILED, at once): the character's internal collection is built by mh.build (BuildMetaHuman)
        ok = c is None or getattr(c._props["internal_collection"], "_built", False)
        object.__setattr__(self, "_assembled", bool(ok))
        d._fire(MetaHumanCharacterAssemblyResult.SUCCEEDED if ok else MetaHumanCharacterAssemblyResult.FAILED)

    def get_instance_parameter_item_paths(self):
        if not self._assembled:
            return []
        return [ItemPath(item=PaletteKey(name=k)) for k in self._sel.values() if k and k in self._params]

    def get_instance_parameters(self, item_path):
        key = item_path.item.to_asset_name_string() if item_path.item is not None else ""
        if not self._assembled:  # day 1, UE 5.8.4: get_instance_parameter_item_paths() == [] before assembly
            return []
        bag = self._params.setdefault(key, {})
        out = []
        for n, v in bag.items():
            t = "BOOL" if isinstance(v, bool) else "FLOAT" if isinstance(v, float) else "COLOR"
            p = InstanceParameter(name=n, type=_e("MetaHumanCharacterInstanceParameterType", t))
            object.__setattr__(p, "_fm_inst", self)
            object.__setattr__(p, "_fm_key", key)
            out.append(p)
        return out


class MetaHumanCollection(core.Object):
    SLOTS = ("Hair", "Eyebrows", "Beard", "Mustache", "Eyelashes", "Peachfuzz", "Outfits")

    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        object.__setattr__(self, "_items", {})  # key name -> (slot, wardrobe item path)
        self._props["default_instance"] = MetaHumanInstance("DefaultInstance")

    def get_slot_names(self):
        return list(self.SLOTS)

    def get_all_item_keys(self):
        return [PaletteKey(name=k) for k in self._items]

    def get_item_keys_for_wardrobe_item(self, wardrobe_item):
        p = core._package(wardrobe_item.get_path_name())
        return [PaletteKey(name=k) for k, (s, w) in self._items.items() if w == p]

    def get_item_slot_name(self, key):
        return self._items.get(key.to_asset_name_string(), ("", ""))[0]

    def get_item_display_name(self, key):
        return key.to_asset_name_string().removeprefix("WI_")

    def try_add_item_from_wardrobe_item(self, slot_name, wardrobe_item):
        core._fake().calls.append(("MetaHumanCollection.try_add_item_from_wardrobe_item", (slot_name, wardrobe_item), {}))
        if str(slot_name) not in self.SLOTS:
            return None
        name = wardrobe_item.get_name()
        n, i = name, 2
        while n in self._items:  # the engine makes a second entry for the same item
            n, i = f"{name} ({i})", i + 1
        self._items[n] = (str(slot_name), core._package(wardrobe_item.get_path_name()))
        defaults = dict(GROOM_PARAMS) if str(slot_name) != "Outfits" else {"PrimaryColor": _lc(0.5, 0.5, 0.5)}
        self._props["default_instance"]._params[n] = defaults
        return PaletteKey(name=n)


# ------------------------------------------------------------------------------------------------- the character

class MetaHumanCharacter(core.Object):
    def __init__(self, name=None, outer=None, **props):
        props = copy.deepcopy(props)  # EAL.duplicate_asset passes the source's props: a copy owns its own state
        super().__init__(name, outer, **props)
        p = self._props
        p.setdefault("skin_settings", SkinSettings())
        p.setdefault("eyes_settings", EyesSettings())
        p.setdefault("makeup_settings", Makeup())
        p.setdefault("head_model_settings", HeadModel())
        p.setdefault("has_high_resolution_textures", False)
        p.setdefault("has_face_dna_blendshapes", False)
        p.setdefault("fixed_body_type", False)
        p.setdefault("internal_collection", MetaHumanCollection("InternalCollection"))
        p.setdefault("__fm_face", [0.0] * 8)
        p.setdefault("__fm_landmarks", [core.Vector(float(i), 0.0, 160.0) for i in range(4)])
        p.setdefault("__fm_body", {k: [False, v[0]] for k, v in BODY.items()})
        p.setdefault("__fm_rigged", False)
        object.__setattr__(p["internal_collection"]._props["default_instance"], "_char", self)


class MetaHumanCharacterEditorSubsystem(core.Object):
    """UMetaHumanCharacterEditorSubsystem."""

    def __init__(self, name=None, outer=None, **props):
        super().__init__(name, outer, **props)
        object.__setattr__(self, "_editing", set())

    def _rec(self, name, *args):
        core._fake().calls.append((f"MetaHumanCharacterEditorSubsystem.{name}", args, {}))

    def _need(self, c):
        if id(c) not in self._editing:
            raise RuntimeError(f"{c.get_name()} is not added for editing (the engine logs and does nothing)")

    def try_add_object_to_edit(self, c):
        self._editing.add(id(c))
        return True

    def is_object_added_for_editing(self, c):
        return id(c) in self._editing

    def remove_object_to_edit(self, c):
        self._editing.discard(id(c))

    # body
    def get_body_constraints(self, c, scale=False):
        self._need(c)
        return [BodyConstraint(name=k, is_active=a, target_measurement=float(v), min_measurement=float(BODY[k][1]),
                               max_measurement=float(BODY[k][2])) for k, (a, v) in c._props["__fm_body"].items()]

    def set_body_constraints(self, c, constraints):
        self._need(c)
        self._rec("set_body_constraints", c, constraints)
        c._props["__fm_pending_body"] = {x.name: [x.is_active, x.target_measurement] for x in constraints}

    def commit_body_state(self, c):
        self._need(c)
        self._rec("commit_body_state", c)
        c._props["__fm_body"].update(c._props.pop("__fm_pending_body", {}))

    # face
    def get_face_model_coefficients(self, c):
        self._need(c)
        return list(c._props["__fm_face"])

    def set_face_model_coefficients(self, c, coeffs):
        self._need(c)
        self._rec("set_face_model_coefficients", c, coeffs)
        c._props["__fm_pending_face"] = [float(x) for x in coeffs]

    def get_face_landmarks(self, c):
        self._need(c)
        return list(c._props["__fm_landmarks"])

    def translate_face_landmarks(self, c, indices, deltas):
        self._need(c)
        self._rec("translate_face_landmarks", c, indices, deltas)
        lm = c._props["__fm_landmarks"]
        for i, d in zip(indices, deltas):
            lm[i] = lm[i] + d

    def commit_face_state(self, c):
        self._need(c)
        self._rec("commit_face_state", c)
        if "__fm_pending_face" in c._props:
            c._props["__fm_face"] = c._props.pop("__fm_pending_face")

    def remove_face_rig(self, c):
        self._need(c)
        self._rec("remove_face_rig", c)
        c._props["__fm_rigged"] = False
        c._props["has_face_dna_blendshapes"] = False

    # settings
    def commit_skin_settings(self, c, s):
        self._need(c)
        self._rec("commit_skin_settings", c, s)
        c._props["skin_settings"] = copy.deepcopy(s)
        c._props["has_high_resolution_textures"] = False  # the engine discards them

    def commit_eyes_settings(self, c, s):
        self._need(c)
        self._rec("commit_eyes_settings", c, s)
        c._props["eyes_settings"] = copy.deepcopy(s)

    def commit_makeup_settings(self, c, s):
        self._need(c)
        self._rec("commit_makeup_settings", c, s)
        c._props["makeup_settings"] = copy.deepcopy(s)

    def commit_head_model_settings(self, c, s):
        self._rec("commit_head_model_settings", c, s)
        c._props["head_model_settings"] = copy.deepcopy(s)

    # cloud
    def _later(self, ticks, fn):
        f = core._fake()
        state = {"n": 0}

        def cb(dt):
            state["n"] += 1
            if state["n"] == ticks:
                fn()
                f.unregister_slate_post_tick_callback(h)
        h = f.register_slate_post_tick_callback(cb)

    def _log(self, line):
        f = core._fake()
        with open(f.mh_log, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def request_auto_rigging(self, c, params):
        self._need(c)
        self._rec("request_auto_rigging", c, params)
        f = core._fake()
        self._log(f"LogMetaHumanCharacterEditor: Display: Requesting Auto-Rigging for {c.get_name()}. Blocking: "
                  f"{params.blocking}")

        def finish():
            if f.mh_fail_rig:
                self._log("LogMetaHumanCharacterEditor: Error: Auto-Rigging of Face failed with code 'Unauthorized'")
                return
            c._props["__fm_rigged"] = True
            c._props["has_face_dna_blendshapes"] = params.rig_type == "JOINTS_AND_BLEND_SHAPES"
            self._log("LogMetaHumanCharacterEditor: Display: Auto-Rigging finished in 28.5 seconds")
        self._later(f.mh_rig_ticks, finish)

    def request_texture_sources(self, c, params):
        self._need(c)
        self._rec("request_texture_sources", c, params)
        f = core._fake()

        def finish():
            self._log("LogMetaHumanCharacterEditor: Display: Download of source body textures finished in 4.3 seconds")
            self._log("LogMetaHumanCharacterEditor: Display: Download of source face textures finished in 11.3 seconds")
            c._props["has_high_resolution_textures"] = True
        self._later(f.mh_tex_ticks, finish)

    # build
    def can_build_meta_human(self, c, log_error=False):
        return id(c) in self._editing and bool(c._props["__fm_rigged"]) and bool(
            c._props["has_high_resolution_textures"])

    def build_meta_human(self, c, params):
        self._rec("build_meta_human", c, params)
        if not self.can_build_meta_human(c):
            return
        f = core._fake()
        name = params.name_override or c.get_name()
        folder = params.absolute_build_path or core._package(c.get_path_name()).rsplit("/", 1)[0] + f"/Unpacked/{name}"
        f.add_asset(f"{folder}/BP_{name}", "Blueprint")
        object.__setattr__(c.get_editor_property("internal_collection"), "_built", True)

    def spawn_meta_human_actor(self, c, keep_transient=False):
        self._rec("spawn_meta_human_actor", c, keep_transient)
        return core._fake().spawn("Actor", label=f"{c.get_name()}_Preview")


def install(fake):
    for name, members in ENUMS.items():
        setattr(fake, name, fenum(name, members))
        fake._classes[name] = getattr(fake, name)
    for cls in (SkinSettings, EyesSettings, Makeup, HeadModel, BodyConstraint):
        setattr(fake, cls.__name__, cls)
    fake.MetaHumanCharacterAutoRiggingRequestParams = RigParams
    fake.MetaHumanCharacterTextureRequestParams = TexParams
    fake.MetaHumanCharacterEditorBuildParameters = BuildParams
    fake.MetaHumanPaletteItemKey = PaletteKey
    fake.MetaHumanCharacterAssembled = Assembled
    fake.MetaHumanCharacter = MetaHumanCharacter
    fake.MetaHumanCharacterEditorSubsystem = MetaHumanCharacterEditorSubsystem
    fake.MetaHumanCollection = MetaHumanCollection
    fake._classes.update({"MetaHumanCharacter": MetaHumanCharacter,
                          "MetaHumanCharacterEditorSubsystem": MetaHumanCharacterEditorSubsystem})
    fake.mh_rig_ticks, fake.mh_tex_ticks, fake.mh_fail_rig = 3, 3, False
    logs = os.path.join(fake.root, "Saved", "Logs")
    os.makedirs(logs, exist_ok=True)
    fake.mh_log = os.path.join(logs, "FakeProject.log")
    open(fake.mh_log, "w").close()


def add_presets(fake, names=("Ada", "Jorge", "Vivian")):
    """Preset characters where the engine keeps them, each with a different face and height."""
    brows = fake.add_asset("/MetaHumanCharacter/Optional/Grooms/Bindings/Eyebrows/WI_Eyebrows_M_Natural",
                           "MetaHumanWardrobeItem")
    for i, n in enumerate(names):
        c = fake.put_asset(f"/MetaHumanCharacter/Optional/Presets/{n}", MetaHumanCharacter(n))
        c._props["__fm_face"] = [float(i + 1)] * 8
        c._props["__fm_body"]["Height"] = [True, 160.0 + 10 * i]
        coll = c._props["internal_collection"]  # presets come wearing eyebrows
        coll._props["default_instance"].set_single_slot_selection("Eyebrows",
                                                                  coll.try_add_item_from_wardrobe_item("Eyebrows", brows))
    return names


def add_wardrobe(fake):
    """A few wardrobe items under the engine's Optional folder."""
    paths = ["/MetaHumanCharacter/Optional/Grooms/Bindings/Hair/WI_Hair_S_BuzzCut",
             "/MetaHumanCharacter/Optional/Grooms/Bindings/Hair/WI_Hair_L_Straight",
             "/MetaHumanCharacter/Optional/Grooms/Bindings/Beards/WI_Beard_S_Stubble",
             "/MetaHumanCharacter/Optional/Clothing/Outfits/WI_Outfit_Casual"]
    for p in paths:
        fake.add_asset(p, "MetaHumanWardrobeItem")
    return paths
