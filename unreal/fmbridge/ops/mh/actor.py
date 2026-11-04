"""An assembled MetaHuman in a level (the Blueprint mh.build made, placed as an actor): its components, the face
driven by Sequencer, garments of your own on its body (skeletal FBX garments on the MetaHuman skeleton, posed by the
body through leader pose), props riding its bones, a numeric clipping check, and the legacy garment material ops
(cloth_inflate, garment).

Traps these ops handle (unreal/README.md, films/host-studio):
- A change to one instance component of a Blueprint actor reruns its construction script, which re-creates the
  others: a re-created garment has lost its leader (it stays in its bind pose while the body moves). So leader pose is
  set LAST, on every garment in one pass (mh.leader), and re-applied after any change (mh.dress does it).
- Garments are authored in cm on the MetaHuman skeleton. A garment whose root bone carries a scale (bones in metres
  under a x100 root) shrinks to nothing as soon as anything poses it: mh.import_garment refuses it.
- A prop spawns Static, and a Static root silently refuses to attach to a moving bone: mh.attach makes it Movable.
"""
from __future__ import annotations

import unreal

from .. import op
from ...errors import OpError, not_found
from ..assets import EAL, load
from ..level import actor
from . import _core as K

@op("mh.components", mutates=False, idempotent=True)
def components(label: str) -> dict:
    """An assembled MetaHuman actor's skeletal mesh components: mesh, animation mode and class.

    Returns: {component name: {"mesh", "mode", "anim_class"}}.
    Example: film-ue op mh.components label=Presenter
    """
    out = {}
    for c in actor(label).get_components_by_class(unreal.SkeletalMeshComponent):
        m = c.get_skeletal_mesh_asset()
        out[c.get_name()] = {"mesh": m.get_path_name() if m else None, "mode": str(c.get_editor_property("animation_mode")),
                             "anim_class": str(c.get_editor_property("anim_class"))}
    return out


@op("mh.drive_face", mutates=True, idempotent=True)
def drive_face(label: str, component: str = "Face") -> str:
    """Let a sequence's animation track drive the face: its own Blueprint (ABP_Face) has no slot for Sequencer, so the
    component plays the animation directly; Epic's post-process rig (RigLogic) still runs on top.

    Returns: the component's animation mode.
    Example: film-ue op mh.drive_face label=Presenter
    """
    c = next(c for c in actor(label).get_components_by_class(unreal.SkeletalMeshComponent) if c.get_name() == component)
    c.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    return str(c.get_editor_property("animation_mode"))


def _has_inflate(m) -> bool:
    return "FM_Inflate" in [str(n) for n in unreal.MaterialEditingLibrary.get_scalar_parameter_names(m)]


def _add_inflate(master):
    """World Position Offset += vertex normal x FM_Inflate on a master material, recompiled (a fresh one only)."""
    MEL = unreal.MaterialEditingLibrary
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
    master.set_editor_property("used_with_skeletal_mesh", True)
    MEL.recompile_material(master)


def _in_use() -> set:
    """Every material (and its parents) on a skeletal mesh in the open level: what the renderer may be drawing."""
    used = set()
    for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        for c in a.get_components_by_class(unreal.SkeletalMeshComponent):
            for x in c.get_materials():
                while x:
                    used.add(x.get_path_name())
                    x = x.get_editor_property("parent") if isinstance(x, unreal.MaterialInstance) else None
    return used


def _settle(ticks: int = 8):
    """Let every pending shader and asset compile finish, then a few frames render with the result."""
    for _ in range(2):
        yield
    unreal.AutomationUtilsBlueprintLibrary.finish_all_asset_compilation()
    for _ in range(ticks):
        yield
    yield 0.5


@op("mh.cloth_inflate", mutates=True, idempotent=True, tags=["slow"])
def cloth_inflate(label: str, cm: float = 0.6, component: str = "SkeletalMesh", folder: str = "/Game/FM/Cloth",
                  which: str = ""):
    """Push a garment out along its normals by `cm`, so skin under tight cloth stops poking through. A multi-tick job.

    Nothing the renderer is drawing is ever edited: a material in use that is reparented or recompiled while frames
    render trips `UniformExpressionCache... == Material.GetRenderingThreadShaderMap()` and takes the editor down (it
    did, right after a MetaHuman rebuild had made fresh garment instances). So the worn instance is copied to
    `{folder}/{label}_<name>_Inflate`, the copy is parented on project copies of its plugin chain whose master gains a
    World Position Offset (normal x FM_Inflate), every shader finishes compiling, the editor ticks a few frames, and
    only then does the component swap to the copy. A master already in use is never recompiled (a new one is made);
    re-running on an inflated garment only changes the amount, a plain parameter change that is safe. `which` limits it
    to the garments whose material name contains it (e.g. "Shirt": a top pushed out over shorts that stay put, else
    both move together and the shorts' waistband still shows through the tee); others already inflated go back to 0.

    Returns: {material name: amount or [copies made]}.
    Example: film-ue op mh.cloth_inflate label=Presenter cm=1.0 which=Shirt
    """
    MEL = unreal.MaterialEditingLibrary

    def comp():  # fetched afresh: a Blueprint's construction script may have replaced it
        return next((c for c in actor(label).get_components_by_class(unreal.SkeletalMeshComponent)
                     if c.get_name() == component), None)

    if comp() is None:  # built without the default garment (her own outfit is attached separately)
        return {}
    used = _in_use()
    swaps, done = {}, {}
    for mi in {m.get_path_name(): m for m in comp().get_materials() if isinstance(m, unreal.MaterialInstance)}.values():
        hit = which.lower() in mi.get_name().lower()
        if mi.get_path_name().startswith(folder + "/") and _has_inflate(mi):  # inflated already: only the amount
            MEL.set_material_instance_scalar_parameter_value(mi, "FM_Inflate", float(cm) if hit else 0.0)
            EAL.save_asset(mi.get_path_name().split(".")[0])
            done[mi.get_name()] = float(cm) if hit else 0.0
            continue
        if not hit:
            continue
        chain, x = [], mi
        while isinstance(x, unreal.MaterialInstance):
            chain.append(x)
            x = x.get_editor_property("parent")
        master_src = x.get_path_name().split(".")[0]
        master_dst = f"{folder}/{master_src.rsplit('/', 1)[1]}_FM"
        if EAL.does_asset_exist(master_dst) and not _has_inflate(load(master_dst)):
            master_dst += "2"  # an old copy without the offset: never recompile one that may be drawn
        copies = []  # the parents from the first plugin asset up, as project copies
        for a in chain[1:]:
            path = a.get_path_name().split(".")[0]
            if path.startswith("/Game/"):
                copies.append(a)
                continue
            dst = f"{folder}/{path.rsplit('/', 1)[1]}_FM"
            if not EAL.does_asset_exist(dst):
                EAL.duplicate_asset(path, dst)
            copies.append(load(dst))
        if not EAL.does_asset_exist(master_dst):
            EAL.duplicate_asset(master_src, master_dst)
            _add_inflate(load(master_dst))
        master = load(master_dst)
        if not _has_inflate(master):
            raise RuntimeError(f"{master_dst} has no FM_Inflate")
        copies.append(master)
        for child, parent in zip(copies[:-1], copies[1:]):
            if child.get_editor_property("parent") != parent:
                if child.get_path_name() in used:
                    raise RuntimeError(f"{child.get_name()} is being drawn; not reparenting it")
                MEL.set_material_instance_parent(child, parent)
        new = f"{folder}/{label}_{mi.get_name()}_Inflate"
        if EAL.does_asset_exist(new):  # a copy of an older build's instance: not drawn, so brought up to date in place
            if new + "." + new.rsplit("/", 1)[1] in used:
                raise RuntimeError(f"{new} is being drawn but not by {label}.{component}")
            n = load(new)
            for k in ("scalar_parameter_values", "vector_parameter_values", "texture_parameter_values"):
                n.set_editor_property(k, mi.get_editor_property(k))
        else:
            EAL.duplicate_asset(mi.get_path_name().split(".")[0], new)
            n = load(new)
        if n.get_editor_property("parent") != copies[0]:
            MEL.set_material_instance_parent(n, copies[0])
        MEL.set_material_instance_scalar_parameter_value(n, "FM_Inflate", float(cm))
        MEL.update_material_instance(n)
        for a in [n] + copies:
            EAL.save_asset(a.get_path_name().split(".")[0])
        swaps[mi.get_path_name()] = n
        done[mi.get_name()] = [n.get_name()] + [c.get_name() for c in copies]
    if swaps:
        yield from _settle()
        c = comp()
        for i, m in enumerate(c.get_materials()):
            if m and m.get_path_name() in swaps:
                c.set_material(i, swaps[m.get_path_name()])
        yield from _settle(4)
    return done


@op("mh.garment", mutates=True, idempotent=True)
def garment(label: str, which: str = "Shirt", vectors: dict | None = None, scalars: dict | None = None,
            component: str = "SkeletalMesh") -> dict:
    """Set parameters on a worn garment's material (slots whose name contains `which`): `vectors` take linear [r,g,b],
    e.g. the default garment's {"diffuse_color_1": [...], "diffuse_color_2": [...]} is its colour.

    Returns: {material instance: [parameters set]}.
    Example: film-ue op mh.garment label=Presenter which=Shirt 'vectors={"diffuse_color_1": [0.2, 0.3, 0.2]}'
    """
    MEL = unreal.MaterialEditingLibrary
    comp = next((c for c in actor(label).get_components_by_class(unreal.SkeletalMeshComponent)
                 if c.get_name() == component), None)
    done = {}
    if comp is None:  # built without the default garment
        return done
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


# ------------------------------------------------------------------------------------- garments of your own (dress)

SKELETONS = {  # the MetaHuman body skeleton (all bodies share it; the per-type folders hold the same asset)
    "metahuman": "/MetaHumanCharacter/Female/Medium/NormalWeight/Body/metahuman_base_skel",
}
HIDDEN = "/Game/FM/MH/M_FM_Hidden"
BONE_PROBES = ("pelvis", "spine_03", "head", "hand_l", "hand_r", "calf_l", "calf_r")


def _skm(label: str) -> dict:
    """The actor's skeletal mesh components by name, fetched afresh (a Blueprint may have re-created them)."""
    return {c.get_name(): c for c in actor(label).get_components_by_class(unreal.SkeletalMeshComponent)}


def _actor(label: str):
    try:
        return actor(label)
    except ValueError:
        names = [a.get_actor_label() for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()]
        raise not_found("actor", label, names, hint="place the built Blueprint (mh.build's bp) in the level first")


def _root_scale(comp) -> float:
    try:
        t = comp.get_ref_pose_transform(comp.get_bone_index("root"))
        s = t.scale3d
        return max(abs(float(s.x)), abs(float(s.y)), abs(float(s.z)))
    except Exception:
        return 1.0


@op("mh.import_garment", mutates=True, idempotent=True, tags=["metahuman"])
def import_garment(*, fbx: str, dest: str, skeleton: str = "", replace: bool = True) -> dict:
    """Import a garment FBX (authored in cm, skinned to the MetaHuman body skeleton) as a skeletal mesh on that
    skeleton, for mh.dress. Checks the units: a garment that comes in tiny or huge (metres vs cm) is an error.

    Args: fbx: the file on the box (absolute path). dest: the asset path (/Game/Outfits/Ava/SKM_Ava_Top).
    skeleton: the skeleton asset (default the MetaHuman body skeleton). replace: re-import over an existing one.
    Returns: {"path", "changed", "bounds_cm": [x, y, z] half sizes, "slots": [material slot names]}.
    Example: film-ue op mh.import_garment fbx=/srv/proj/Saved/Import/her_top.fbx dest=/Game/Outfits/Ava/SKM_Ava_Top
    """
    import os
    dest = K.package(dest)
    if not os.path.exists(fbx):
        raise OpError(f"no file {fbx} on the box", code="not_found", hint="push it first (client.push)")
    if EAL.does_asset_exist(dest) and not replace:
        m = load(dest)
        b = m.get_bounds()
        return {"path": dest, "changed": False, "bounds_cm": [round(b.box_extent.x, 1), round(b.box_extent.y, 1),
                                                              round(b.box_extent.z, 1)],
                "slots": [str(s.material_slot_name) for s in m.materials]}
    skel = load(K.package(skeleton) if skeleton else SKELETONS["metahuman"])
    t = unreal.AssetImportTask()
    t.set_editor_property("filename", fbx)
    t.set_editor_property("destination_path", K.folder_of(dest))
    t.set_editor_property("destination_name", dest.rsplit("/", 1)[1])
    for k, v in (("automated", True), ("replace_existing", True), ("save", True)):
        t.set_editor_property(k, v)
    ui = unreal.FbxImportUI()
    for k, v in (("import_mesh", True), ("import_as_skeletal", True), ("import_materials", False),
                 ("import_textures", False), ("import_animations", False), ("create_physics_asset", False)):
        ui.set_editor_property(k, v)
    ui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
    ui.set_editor_property("skeleton", skel)
    sk = ui.get_editor_property("skeletal_mesh_import_data")
    for k, v in dict(normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS,
                     update_skeleton_reference_pose=False, use_t0_as_reference_pose=False, convert_scene=True,
                     force_front_x_axis=False, convert_scene_unit=False).items():
        try:  # the names vary across engine versions: skip what this one lacks
            sk.set_editor_property(k, v)
        except Exception:
            pass
    t.set_editor_property("options", ui)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
    m = EAL.load_asset(dest)
    if m is None:
        raise OpError(f"importing {fbx} made no asset at {dest}", code="engine",
                      hint="see the editor log (LogFbx): is it skinned to the MetaHuman skeleton's bone names?")
    b = m.get_bounds()
    ext = [round(b.box_extent.x, 1), round(b.box_extent.y, 1), round(b.box_extent.z, 1)]
    if max(ext) < 3 or max(ext) > 250:
        raise OpError(f"{dest} is {ext} cm (half size): not a garment in cm", code="failed",
                      details={"bounds_cm": ext},
                      hint="export the FBX in cm (Blender: unit scale 0.01, apply scale) with a root bone of scale 1")
    return {"path": dest, "changed": True, "bounds_cm": ext, "slots": [str(s.material_slot_name) for s in m.materials]}


def _hidden_material():
    """A masked material with opacity mask 0 (nothing drawn): how a built-in garment's slots are cut out."""
    if EAL.does_asset_exist(HIDDEN):
        return load(HIDDEN)
    MEL = unreal.MaterialEditingLibrary
    m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(HIDDEN.rsplit("/", 1)[1], K.folder_of(HIDDEN),
                                                                unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    m.set_editor_property("used_with_skeletal_mesh", True)
    zero = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, -300, 0)
    zero.set_editor_property("r", 0.0)
    MEL.connect_material_property(zero, "", unreal.MaterialProperty.MP_OPACITY_MASK)
    MEL.recompile_material(m)
    EAL.save_asset(HIDDEN)
    return m


def _add_component(label: str, name: str, parent: str = "Body"):
    """An instance SkeletalMeshComponent `name` under `parent` on a placed Blueprint actor (SubobjectDataSubsystem:
    the Blueprint's own components come back as their templates, matched by variable name)."""
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    SDL = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_instance(actor(label))
    parent_h = next((h for h in handles if str(SDL.get_variable_name(SDL.get_data(h))) == parent), None)
    if parent_h is None:
        raise OpError(f"{label} has no component {parent}", code="not_found", hint="mh.components lists them")
    new_h, why = sds.add_new_subobject(unreal.AddNewSubobjectParams(parent_handle=parent_h,
                                                                    new_class=unreal.SkeletalMeshComponent))
    if why and str(why):
        raise OpError(f"adding {name} to {label}: {why}", code="engine")
    sds.rename_subobject(new_h, unreal.Text(name))


def _lead_all(label: str, body: str = "Body") -> dict:
    """Leader pose on every garment (all skeletal mesh components but the body and face), in one pass, last."""
    comps = _skm(label)
    if body not in comps:
        raise OpError(f"{label} has no {body} component", code="not_found", candidates=list(comps))
    for n, c in comps.items():
        if n in (body, "Face"):
            continue
        c.set_anim_instance_class(None)
        c.set_leader_pose_component(comps[body])
    return leader_state(label, body)


def leader_state(label: str, body: str = "Body") -> dict:
    comps = _skm(label)
    out = {}
    for n, c in comps.items():
        if n in (body, "Face"):
            continue
        lead = c.get_editor_property("leader_pose_component")
        gap = 0.0
        if lead is not None:
            for b in BONE_PROBES:
                if c.get_bone_index(b) >= 0:
                    gap = max(gap, (c.get_socket_location(b) - comps[body].get_socket_location(b)).length())
        out[n] = {"leader": lead.get_name() if lead is not None else None, "bone_gap_cm": round(gap, 3),
                  "ok": lead is not None and lead.get_name() == body and gap < 0.1}
    return out


@op("mh.leader", mutates=True, idempotent=True, tags=["metahuman"])
def leader(*, label: str, body: str = "Body") -> dict:
    """Put every garment of a placed MetaHuman back on leader pose to its body, in one pass (a garment that lost it
    stays in its bind pose while the body moves). Run it after any change to the actor's components, after a level
    load, and before rendering.

    Returns: {"garments": {name: {"leader", "bone_gap_cm", "ok"}}, "ok", "changed"}.
    Example: film-ue op mh.leader label=Presenter
    """
    _actor(label)
    before = leader_state(label, body)
    after = _lead_all(label, body)
    return {"garments": after, "ok": all(v["ok"] for v in after.values()),
            "changed": any(before.get(k, {}).get("leader") != v["leader"] for k, v in after.items())}


@op("mh.leader_check", mutates=False, idempotent=True, tags=["metahuman"])
def leader_check(*, label: str, body: str = "Body") -> dict:
    """Whether every garment follows the body: a verdict for QA. Each garment must lead from the body and sit on the
    body's bones (the largest gap over pelvis, spine, head, hands, calves under 0.1 cm).

    Returns: {"pass", "metric": worst bone gap cm, "threshold": 0.1, "why", "garments"}.
    Example: film-ue op mh.leader_check label=Presenter
    """
    _actor(label)
    st = leader_state(label, body)
    bad = [n for n, v in st.items() if not v["ok"]]
    worst = max([v["bone_gap_cm"] for v in st.values()] or [0.0])
    return {"pass": not bad, "metric": worst, "threshold": 0.1,
            "why": ("all garments follow " + body) if not bad else f"not following {body}: {', '.join(bad)} (mh.leader)",
            "garments": st}


@op("mh.dress", mutates=True, idempotent=True, tags=["metahuman"])
def dress(*, label: str, garments: dict, hide_slots: dict | None = None, body: str = "Body") -> dict:
    """Dress a placed MetaHuman in garments of your own: each a skeletal mesh component under its body, posed by the
    body (leader pose, set last on every garment), lit like the body; optionally cut slots out of the built-in garment.

    Converges: an existing component of that name is updated, not duplicated. Save the level (level.save) to keep it.
    Args: label: the placed MetaHuman actor. garments: {component name: {"mesh": skeletal mesh path (mh.import_garment),
    "materials": {slot name: material path}}}. hide_slots: {component: [slot name substrings]} drawn with nothing
    (e.g. {"SkeletalMesh": ["short"]} cuts the default garment's shorts). body: the body component.
    Returns: {"changed", "garments": {name: {"leader", "bone_gap_cm", "ok"}}, "hidden": [...], "ok"}.
    Example: film-ue op mh.dress label=Presenter 'garments={"Top": {"mesh": "/Game/Outfits/Ava/SKM_Ava_Top", "materials": {"M_Top": "/Game/Outfits/Ava/MI_Top"}}}'
    """
    _actor(label)
    for n, g in garments.items():  # validate before touching the actor
        if n in (body, "Face"):
            raise OpError(f"{n} is the MetaHuman's own component", code="bad_args", hint="name the garment, e.g. Top")
        mesh = K.package((g or {}).get("mesh", ""))
        if not EAL.does_asset_exist(mesh):
            raise OpError(f"garment {n}: no skeletal mesh {mesh!r}", code="not_found", hint="mh.import_garment first")
        for mat in (g.get("materials") or {}).values():
            if not EAL.does_asset_exist(K.package(mat)):
                raise OpError(f"garment {n}: no material {mat!r}", code="not_found")
    changed = False
    for n, g in garments.items():
        if n not in _skm(label):
            _add_component(label, n, body)
            changed = True
        c = _skm(label)[n]
        mesh = load(K.package(g["mesh"]))
        if c.get_skeletal_mesh_asset() != mesh:
            c.set_skeletal_mesh_asset(mesh)
            changed = True
        if _root_scale(_skm(label)[n]) > 1.001:
            raise OpError(f"garment {n}: its root bone is scaled x{_root_scale(_skm(label)[n]):.0f} (bones in metres?)",
                          code="failed", hint="re-export the FBX in cm with an unscaled root; it would vanish when posed")
        for slot, mat in (g.get("materials") or {}).items():
            c = _skm(label)[n]
            m = load(K.package(mat))
            names = [str(s) for s in c.get_material_slot_names()]
            if slot not in names:
                raise OpError(f"garment {n} has no material slot {slot!r}", code="bad_args",
                              candidates=K.closest(slot, names))
            if c.get_material(names.index(slot)) != m:
                c.set_material_by_name(slot, m)
                changed = True
        c = _skm(label)[n]
        c.set_editor_property("lighting_channels", _skm(label)[body].get_editor_property("lighting_channels"))
        _skm(label)[n].set_editor_property("use_bounds_from_leader_pose_component", True)
    hidden = []
    for comp, subs in (hide_slots or {}).items():
        c = _skm(label).get(comp)
        if c is None:
            continue  # built without that garment
        hm = _hidden_material()
        for i, slot in enumerate(c.get_material_slot_names()):
            if any(s.lower() in str(slot).lower() for s in subs):
                if c.get_material(i) != hm:
                    _skm(label)[comp].set_material(i, hm)
                    changed = True
                hidden.append(f"{comp}.{slot}")
    st = _lead_all(label, body)  # last: every change above may have re-created the components
    return {"changed": changed, "garments": st, "hidden": hidden, "ok": all(v["ok"] for v in st.values())}


@op("mh.attach", mutates=True, idempotent=True)
def attach(*, label: str, prop: str, bone: str, component: str = "Body") -> dict:
    """Make a prop (an actor in the level) ride a bone of a placed MetaHuman, keeping where it is now: earrings on the
    face's ear bones, a watch on the forearm. The prop is made Movable first (a Static root refuses to attach to a
    moving bone without a word).

    Args: label: the MetaHuman actor. prop: the prop's label. bone: the bone or socket (FACIAL_L_Ear4,
    lowerarm_twist_02_l). component: Body or Face.
    Returns: {"changed", "parent": component, "bone"}.
    Example: film-ue op mh.attach label=Presenter prop=HerWatch bone=lowerarm_twist_02_l
    """
    comps = _skm(label)
    if component not in comps:
        raise OpError(f"{label} has no {component}", code="not_found", candidates=list(comps))
    comp = comps[component]
    if comp.get_bone_index(bone) < 0:
        raise OpError(f"{label}.{component} has no bone {bone!r}", code="not_found",
                      hint="bone names are the MetaHuman skeleton's (level.bone shows positions)")
    p = _actor(prop)
    root = p.root_component
    if root.get_attach_parent() == comp and str(root.get_attach_socket_name()) == bone:
        return {"changed": False, "parent": component, "bone": bone}
    root.set_mobility(unreal.ComponentMobility.MOVABLE)
    rule = unreal.AttachmentRule.KEEP_WORLD
    p.attach_to_component(comp, bone, rule, rule, rule, False)
    if root.get_attach_parent() != comp:
        raise OpError(f"{prop} did not attach to {label}.{component}:{bone}", code="engine")
    return {"changed": True, "parent": component, "bone": bone}


# ------------------------------------------------------------------------------------------------ clipping (numbers)

def _pick(res, cls_name: str):
    """From an engine call's result (one value or a tuple of the return value and out params) the one of a class."""
    items = res if isinstance(res, tuple) else (res,)
    for x in items:
        if type(x).__name__ == cls_name:
            return x
    return items[0]


@op("mh.clip_check", mutates=False, idempotent=True, tags=["metahuman", "experimental"])
def clip_check(*, label: str, garment: str, body: str = "Body", tolerance_cm: float = 0.1, near_cm: float = 3.0,
               samples: int = 3000, max_poke_fraction: float = 0.002):
    """Does the body poke through a garment in the current pose? A numeric check (multi-tick): the posed body and
    garment are copied as meshes (Geometry Script, render LOD 0), and for body points under the garment (nearer than
    near_cm) the signed distance to the garment's surface is measured; a point outside the garment by more than
    tolerance_cm pokes through.

    Needs the Geometry Script plugin. Scrub the sequence to the frame first (seq.stills / a pose) to check a pose.
    Args: label: the MetaHuman actor. garment: its garment component. samples: body points checked (spread evenly).
    max_poke_fraction: the share of checked points allowed through.
    Returns: {"pass", "metric": poke fraction, "threshold", "why", "checked", "pokes", "max_cm", "worst": [[x, y, z,
    cm], ...]}.
    Example: film-ue op mh.clip_check label=Presenter garment=Top
    """
    if not hasattr(unreal, "GeometryScript_SceneUtils"):
        raise OpError("the Geometry Script plugin is not enabled", code="unsupported",
                      hint="enable GeometryScripting in the project's .uproject Plugins, restart the editor")
    comps = _skm(label)
    for n in (body, garment):
        if n not in comps:
            raise OpError(f"{label} has no component {n}", code="not_found", candidates=K.closest(n, comps))
    SU, SP, MQ, LU = (unreal.GeometryScript_SceneUtils, unreal.GeometryScript_MeshSpatial,
                      unreal.GeometryScript_MeshQueries, unreal.GeometryScript_List)
    opts = unreal.GeometryScriptCopyMeshFromComponentOptions()
    lod = unreal.GeometryScriptMeshReadLOD()
    lod.set_editor_property("lod_type", unreal.GeometryScriptLODType.RENDER_DATA)  # the posed, skinned mesh
    lod.set_editor_property("lod_index", 0)
    opts.set_editor_property("requested_lod", lod)

    def copy(comp):
        dm = unreal.DynamicMesh()
        SU.copy_mesh_from_component(comp, dm, opts, True)
        return dm

    g, b = copy(comps[garment]), copy(comps[body])
    yield
    bvh = _pick(SP.build_bvh_for_mesh(g), "GeometryScriptDynamicMeshBVH")
    pts = LU.convert_vector_list_to_array(_pick(MQ.get_all_vertex_positions(b, False), "GeometryScriptVectorList"))
    gp = LU.convert_vector_list_to_array(_pick(MQ.get_all_vertex_positions(g, False), "GeometryScriptVectorList"))
    if not gp or not pts:
        raise OpError("could not read the posed meshes", code="engine", hint="is the garment visible and skinned?")
    lo = [min(p.x for p in gp), min(p.y for p in gp), min(p.z for p in gp)]
    hi = [max(p.x for p in gp), max(p.y for p in gp), max(p.z for p in gp)]
    inside = [p for p in pts if lo[0] - near_cm <= p.x <= hi[0] + near_cm and lo[1] - near_cm <= p.y <= hi[1] + near_cm
              and lo[2] - near_cm <= p.z <= hi[2] + near_cm]
    step = max(1, len(inside) // max(1, samples))
    qopt = unreal.GeometryScriptSpatialQueryOptions()
    checked, pokes, worst = 0, 0, []
    for i, p in enumerate(inside[::step]):
        res = SP.find_nearest_point_on_mesh(g, bvh, p, qopt)
        tp = _pick(res, "GeometryScriptTrianglePoint")
        if not tp.get_editor_property("valid"):
            continue
        q = tp.get_editor_property("position")
        d = p - q
        dist = d.length()
        if dist > near_cm:
            continue
        n = _pick(MQ.get_triangle_face_normal(g, tp.get_editor_property("triangle_id")), "Vector")
        signed = d.dot(n)
        checked += 1
        if signed > tolerance_cm:
            pokes += 1
            worst.append([round(p.x, 1), round(p.y, 1), round(p.z, 1), round(signed, 2)])
        if i % 400 == 399:
            yield
    worst.sort(key=lambda w: -w[3])
    frac = pokes / checked if checked else 0.0
    ok = checked > 0 and frac <= max_poke_fraction
    return {"pass": ok, "metric": round(frac, 5), "threshold": max_poke_fraction,
            "why": (f"{pokes} of {checked} body points under {garment} poke through by > {tolerance_cm} cm" if checked
                    else f"no body points within {near_cm} cm of {garment}: is it on the body?"),
            "checked": checked, "pokes": pokes, "max_cm": worst[0][3] if worst else 0.0, "worst": worst[:20]}
