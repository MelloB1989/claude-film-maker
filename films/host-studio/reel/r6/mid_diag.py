"""Round 6 (agent-02, the orchestrator's 3-min diagnostic on HER neckline band): is the band SHADING or TEXTURE?
TEMPORARY: a dynamic material instance of MI_K_HerTop on her Top component (transient, never saved), one knob
changed, a still, then RESTORE. Her Top's material is the K Pbr lib material with a TILED rib knit (T_HerRib_A
base colour, T_HerRib_N normal, T_HerRib_M packed AO/roughness, Tiling 50): there is no painted binding region, so
the suspects are the edge wall's UVs sampling one dark groove of the rib (base colour, AO) or its normals (normal
map / the mesh's own normals).

    film-ue exec -c "STAGE='apply'; VARIANT='white'; exec(open('<tree>/films/host-studio/reel/r6/mid_diag.py').read())"
    (render the still: the same finals-spec MCU f29 frame as test30)
    film-ue exec -c "STAGE='restore'; exec(open('<tree>/films/host-studio/reel/r6/mid_diag.py').read())"

VARIANT: white (BaseColorMap -> engine white, Tint white), flatnormal (NormalStrength 0), noao (AOStrength 0),
all (the three together). STAGE 'check' reports what the Top wears now and the material's parameter names.
Every apply first restores, so variants never stack by accident. Restore puts the original instance back."""
import unreal

STAGE = globals().get("STAGE", "check")
VARIANT = globals().get("VARIANT", "white")
LABEL = globals().get("LABEL", "Presenter")
COMP = globals().get("COMP", "Top")
SLOT = globals().get("SLOT", "M_Top")
ORIG = globals().get("ORIG", "")  # default: the slot's material when it is not a MID, else the MID's parent
WHITE = "/Engine/EngineResources/WhiteSquareTexture"
MEL = unreal.MaterialEditingLibrary

a = next(x for x in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
         if x.get_actor_label() == LABEL)
c = next(x for x in a.get_components_by_class(unreal.SkeletalMeshComponent) if x.get_name() == COMP)
names = [str(n) for n in c.get_material_slot_names()]
idx = names.index(SLOT)
cur = c.get_material(idx)
orig = unreal.load_asset(ORIG) if ORIG else (cur.get_editor_property("parent")
                                             if isinstance(cur, unreal.MaterialInstanceDynamic) else cur)


def params(m):
    out = {}
    for kind in ("scalar", "vector", "texture"):
        fn = getattr(MEL, f"get_{kind}_parameter_names", None)
        try:
            out[kind] = sorted(str(n) for n in fn(m)) if fn else None
        except Exception as e:  # noqa: BLE001
            out[kind] = f"? {e}"
    return out


result = {"slot": SLOT, "index": idx, "wearing": cur.get_path_name() if cur else None,
          "wearing_class": type(cur).__name__ if cur else None, "original": orig.get_path_name() if orig else None}
if STAGE == "check":
    result["params"] = params(orig)
elif STAGE == "restore":
    c.set_material(idx, orig)
    result["now"] = c.get_material(idx).get_path_name()
elif STAGE == "apply":
    c.set_material(idx, orig)
    mid = c.create_dynamic_material_instance(idx, orig)
    p = params(orig)
    done = []

    def has(kind, n):
        return isinstance(p.get(kind), list) and n in p[kind]

    if VARIANT in ("white", "all"):
        if has("texture", "BaseColorMap"):
            mid.set_texture_parameter_value("BaseColorMap", unreal.load_asset(WHITE))
            done.append("BaseColorMap=white")
        if has("vector", "Tint"):
            mid.set_vector_parameter_value("Tint", unreal.LinearColor(1, 1, 1, 1))
            done.append("Tint=1")
    if VARIANT in ("flatnormal", "all") and has("scalar", "NormalStrength"):
        mid.set_scalar_parameter_value("NormalStrength", 0.0)
        done.append("NormalStrength=0")
    if VARIANT in ("noao", "all") and has("scalar", "AOStrength"):
        mid.set_scalar_parameter_value("AOStrength", 0.0)
        done.append("AOStrength=0")
    if not done:
        c.set_material(idx, orig)
        raise RuntimeError(f"VARIANT {VARIANT}: none of its parameters on {orig.get_path_name()}: {p}")
    result.update({"variant": VARIANT, "set": done, "now": c.get_material(idx).get_path_name()})
else:
    raise RuntimeError(f"STAGE {STAGE}?")
