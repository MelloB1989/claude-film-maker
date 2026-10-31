"""MetaHumans: presets, a character from a preset, Epic's cloud rig and high-resolution textures, wardrobe (hair,
beard, brows, clothes), the cinematic build to a Blueprint, and how an assembled character is driven."""
from __future__ import annotations

import unreal

from . import op
from .assets import EAL, list_assets, load
from .level import actor

PRESETS = "/MetaHumanCharacter/Optional/Presets"
GROOMS = "/MetaHumanCharacter/Optional/Grooms/Bindings"


def sub():
    return unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)


def _char(path: str):
    c = load(path)
    s = sub()
    if not s.is_object_added_for_editing(c):
        s.try_add_object_to_edit(c)
    return c


@op("mh.presets")
def presets() -> list:
    """The preset characters MetaHuman Creator ships (needs the engine's Creator Core Data)."""
    return [p.rsplit("/", 1)[1] for c, p in list_assets(PRESETS, "MetaHumanCharacter")]


@op("mh.wardrobe")
def wardrobe(kind: str = "") -> list:
    """Wardrobe items (grooms and clothing): kind Hair, Beards, Eyebrows, Eyelashes, Mustaches, Peachfuzz, Clothing."""
    items = [p for c, p in list_assets("/MetaHumanCharacter/Optional", "MetaHumanWardrobeItem")]
    return [p for p in items if not kind or f"/{kind}/" in p]


@op("mh.from_preset")
def from_preset(preset: str, dest: str, overwrite: bool = False) -> str:
    """A new character asset copied from a preset (e.g. 'Trey'), opened for editing."""
    if overwrite and EAL.does_asset_exist(dest):
        EAL.delete_asset(dest)
    if not EAL.does_asset_exist(dest):
        EAL.duplicate_asset(f"{PRESETS}/{preset}", dest)
    _char(dest)
    return dest


@op("mh.rig")
def rig(character: str, full: bool = True) -> str:
    """Epic's cloud auto-rig (full: joints + blend shapes, what facial animation needs). Blocks until done."""
    p = unreal.MetaHumanCharacterAutoRiggingRequestParams()
    p.rig_type = unreal.MetaHumanRigType.JOINTS_AND_BLEND_SHAPES if full else unreal.MetaHumanRigType.JOINTS_ONLY
    p.blocking, p.report_progress = True, True
    sub().request_auto_rigging(_char(character), p)
    EAL.save_asset(character)
    return character


@op("mh.textures")
def textures(character: str) -> bool:
    """Epic's cloud high-resolution skin textures. Blocks until done; returns whether they arrived."""
    p = unreal.MetaHumanCharacterTextureRequestParams()
    p.blocking, p.report_progress = True, True
    c = _char(character)
    sub().request_texture_sources(c, p)
    EAL.save_asset(character)
    return bool(c.get_editor_property("has_high_resolution_textures"))


@op("mh.palette")
def palette(character: str) -> dict:
    """What the character wears now: its collection's slots and selected items."""
    c = _char(character)
    coll = c.get_editor_property("internal_collection")
    out = {"slots": [str(s) for s in coll.get_slot_names()] if coll else []}
    try:
        out["items"] = [str(k) for k in coll.get_all_item_keys()]
    except Exception as e:
        out["items_error"] = str(e)
    return out


@op("mh.add_item")
def add_item(character: str, item: str) -> str:
    """Add a wardrobe item (a groom or garment from mh.wardrobe) to the character's collection."""
    c = _char(character)
    coll = c.get_editor_property("internal_collection")
    key = coll.try_add_item_from_wardrobe_item(load(item))
    EAL.save_asset(character)
    return str(key)


@op("mh.build")
def build(character: str, name: str, cinematic: bool = True) -> str:
    """Assemble the character into a Blueprint (cinematic pipeline and quality by default); returns its path."""
    c = _char(character)
    p = unreal.MetaHumanCharacterEditorBuildParameters()
    p.name_override = name
    if not cinematic:
        p.pipeline_type = unreal.MetaHumanDefaultPipelineType.OPTIMIZED
        p.pipeline_quality = unreal.MetaHumanQualityLevel.HIGH
    sub().build_meta_human(c, p)
    folder = character.rsplit("/", 1)[0]
    bps = [p for k, p in list_assets(folder, "Blueprint") if p.endswith(f"BP_{name}")]
    return bps[0] if bps else ""


@op("mh.components")
def components(label: str) -> dict:
    """An assembled MetaHuman actor's skeletal mesh components: mesh, animation mode and class."""
    out = {}
    for c in actor(label).get_components_by_class(unreal.SkeletalMeshComponent):
        m = c.get_skeletal_mesh_asset()
        out[c.get_name()] = {"mesh": m.get_path_name() if m else None, "mode": str(c.get_editor_property("animation_mode")),
                             "anim_class": str(c.get_editor_property("anim_class"))}
    return out


@op("mh.drive_face")
def drive_face(label: str, component: str = "Face") -> str:
    """Let a sequence's animation track drive the face: its own Blueprint (ABP_Face) has no slot for Sequencer, so the
    component plays the animation directly; Epic's post-process rig (RigLogic) still runs on top."""
    c = next(c for c in actor(label).get_components_by_class(unreal.SkeletalMeshComponent) if c.get_name() == component)
    c.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    return str(c.get_editor_property("animation_mode"))


@op("mh.cloth_inflate")
def cloth_inflate(label: str, cm: float = 0.6, component: str = "SkeletalMesh", folder: str = "/Game/FM/Cloth") -> dict:
    """Push a garment out along its normals by `cm`, so skin under tight cloth stops poking through: its material
    chain is copied out of the plugin into `folder`, and the master gains a World Position Offset (normal x
    FM_Inflate). Re-running only changes the amount."""
    MEL = unreal.MaterialEditingLibrary
    comp = next(c for c in actor(label).get_components_by_class(unreal.SkeletalMeshComponent) if c.get_name() == component)
    done = {}
    for mi in {m.get_path_name(): m for m in comp.get_materials() if m}.values():
        chain, x = [], mi
        while isinstance(x, unreal.MaterialInstance):
            chain.append(x)
            x = x.get_editor_property("parent")
        copies = []  # the chain from the first plugin asset down, now as project copies
        for a in chain[1:] + [x]:
            path = a.get_path_name().split(".")[0]
            if path.startswith("/Game/"):
                copies.append(a)
                continue
            dst = f"{folder}/{path.rsplit('/', 1)[1]}_FM"
            if not EAL.does_asset_exist(dst):
                EAL.duplicate_asset(path, dst)
            copies.append(load(dst))
        for child, parent in zip([chain[0]] + copies[:-1], copies):
            if child.get_editor_property("parent") != parent:
                MEL.set_material_instance_parent(child, parent)
        master = copies[-1]
        if "FM_Inflate" not in [str(n) for n in MEL.get_scalar_parameter_names(master)]:
            n = MEL.create_material_expression(master, unreal.MaterialExpressionVertexNormalWS, -900, 1400)
            k = MEL.create_material_expression(master, unreal.MaterialExpressionScalarParameter, -900, 1500)
            k.set_editor_property("parameter_name", "FM_Inflate")
            k.set_editor_property("default_value", 0.0)
            mul = MEL.create_material_expression(master, unreal.MaterialExpressionMultiply, -700, 1450)
            MEL.connect_material_expressions(n, "", mul, "A")
            MEL.connect_material_expressions(k, "", mul, "B")
            wpo = unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET
            prev = MEL.get_material_property_input_node(master, wpo)
            if prev:
                add = MEL.create_material_expression(master, unreal.MaterialExpressionAdd, -500, 1450)
                MEL.connect_material_expressions(prev, MEL.get_material_property_input_node_output_name(master, wpo), add, "A")
                MEL.connect_material_expressions(mul, "", add, "B")
                MEL.connect_material_property(add, "", wpo)
            else:
                MEL.connect_material_property(mul, "", wpo)
            MEL.recompile_material(master)
        MEL.set_material_instance_scalar_parameter_value(chain[0], "FM_Inflate", float(cm))
        for a in [chain[0]] + copies:
            EAL.save_asset(a.get_path_name().split(".")[0])
        done[chain[0].get_name()] = [c.get_name() for c in copies]
    return done


@op("mh.garment")
def garment(label: str, which: str = "Shirt", vectors: dict | None = None, scalars: dict | None = None,
            component: str = "SkeletalMesh") -> dict:
    """Set parameters on a worn garment's material (slots whose name contains `which`): `vectors` take linear [r,g,b],
    e.g. the default garment's {"diffuse_color_1": [...], "diffuse_color_2": [...]} is its colour."""
    MEL = unreal.MaterialEditingLibrary
    comp = next(c for c in actor(label).get_components_by_class(unreal.SkeletalMeshComponent) if c.get_name() == component)
    done = {}
    for name, mi in zip(comp.get_material_slot_names(), comp.get_materials()):
        if which.lower() not in str(name).lower() or not isinstance(mi, unreal.MaterialInstanceConstant):
            continue
        for k, v in (vectors or {}).items():
            MEL.set_material_instance_vector_parameter_value(mi, k, unreal.LinearColor(*v, 1.0))
        for k, v in (scalars or {}).items():
            MEL.set_material_instance_scalar_parameter_value(mi, k, float(v))
        EAL.save_asset(mi.get_path_name().split(".")[0])
        done[mi.get_name()] = sorted({*(vectors or {}), *(scalars or {})})
    return done
