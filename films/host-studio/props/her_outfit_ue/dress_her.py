"""Her, ready for a presenter render: garments on leader pose to Body, her hair's MI_K_HerHair* look, her hoops and
watch seated on her bones; all applied in one pass, read back, and applied again if a step undid another (a change to
any of her instance components re-creates them: a re-created garment loses its leader and stands in bind pose (round 3
preview, S17/S18), what rode her bones loses its offset, her hair loses its materials (teal)). Raises unless all of it
holds; saves the level when it does.

Run with film-ue exec as the LAST step before any presenter render, after REEL_PERF.md's re-place runbook (perf.py
drive_faces/place). It replaces running restore_leader.py, her_hair.py and attach_accessories.py one after another.
Needs MI_K_HerHair{,_Cards,_Helmet} to exist (her_hair.py makes them once).
"""
import unreal

from fmbridge.ops import level as L

GARMENTS = ("Top", "Trousers", "Overshirt")
HAIR = [f"/Game/Studio/Materials/MI_K_HerHair{s}" for s in ("", "_Cards", "_Helmet")]
WATCH_BONE, WATCH_UP_ARM = "lowerarm_twist_01_l", 3.6
# Her hair's strand coverage (round 3, gate c), reel/hair_cover_ab.py's winner on S16: {GroomGroupsDesc field: value}
# for every group of her Hair groom, absolute (this runs after every re-place). Empty leaves the groom's own. Set FIRST
# in apply(): a groom_groups_desc change re-creates the component, which drops its materials and its forced LOD 0
# (run reel/build.py --lod0 on after this script, as before every presenter render).
COVERAGE = {}
rule, keep = unreal.AttachmentRule.KEEP_WORLD, unreal.DetachmentRule.KEEP_WORLD


def comps():
    her = L.actor("Presenter")
    return ({c.get_name(): c for c in her.get_components_by_class(unreal.SkeletalMeshComponent)},
            next((g for g in her.get_components_by_class(unreal.GroomComponent) if g.get_name() == "Hair"), None))


def hair_mats():
    mats = [unreal.load_asset(p) for p in HAIR]
    missing = [p for p, m in zip(HAIR, mats) if m is None]
    if missing:
        raise RuntimeError(f"dress_her: {missing} missing: run her_hair.py once first")
    return mats


def coverage_off(hair) -> dict:
    return {i: {f: d.get_editor_property(f) for f in COVERAGE} for i, d in
            enumerate(hair.get_editor_property("groom_groups_desc"))
            if any(abs(float(d.get_editor_property(f)) - float(v)) > 1e-4 for f, v in COVERAGE.items()
                   if not f.endswith("_override"))}


def apply():
    sk, hair = comps()
    if hair is not None and COVERAGE and coverage_off(hair):
        descs = list(hair.get_editor_property("groom_groups_desc"))
        for d in descs:
            for f, v in COVERAGE.items():
                d.set_editor_property(f, v)
        hair.set_editor_property("groom_groups_desc", descs)
    sk, hair = comps()
    for i, m in enumerate(hair_mats()):
        if hair is not None:
            hair.set_material(i, m)
    sk, hair = comps()
    for n in GARMENTS:
        if n in sk:
            sk[n].set_anim_instance_class(None)
            sk[n].set_leader_pose_component(sk["Body"])
    sk, hair = comps()
    face, body_ = sk["Face"], sk["Body"]

    def ride(lab):
        a = L.actor(lab)
        a.root_component.set_mobility(unreal.ComponentMobility.MOVABLE)
        a.detach_from_actor(keep, keep, keep)
        return a

    for side, bone in (("L", "FACIAL_L_Ear4"), ("R", "FACIAL_R_Ear4")):
        a = ride(f"HerEar{side}")
        p = face.get_socket_location(bone)
        a.set_actor_location(unreal.Vector(p.x - 0.1, p.y + (0.25 if side == "L" else -0.25), p.z + 0.15), False,
                             False)
        a.attach_to_component(face, bone, rule, rule, rule, False)
    w, P = ride("HerWatch"), body_.get_socket_location
    hand = P("hand_l")
    fwd = (hand - P("lowerarm_l")).normal()
    across = P("index_metacarpal_l") - P("pinky_metacarpal_l")
    across = (across - fwd * across.dot(fwd)).normal()
    at, rot = hand - fwd * WATCH_UP_ARM, unreal.MathLibrary.make_rot_from_yz(fwd, fwd.cross(across).normal())
    w.set_actor_location_and_rotation(at, rot, False, False)
    w.attach_to_component(body_, WATCH_BONE, rule, rule, rule, False)
    w.set_actor_location_and_rotation(at, rot, False, False)


def check():
    sk, hair = comps()
    body_ = sk["Body"]
    bad = {}
    for n in GARMENTS:
        if n in sk:
            lead = sk[n].get_editor_property("leader_pose_component")
            if lead is None or lead.get_name() != "Body":
                bad[n] = f"leader {lead.get_name() if lead else None}"
    if hair is not None:
        got = [hair.get_material(i).get_path_name() if hair.get_material(i) else "" for i in range(3)]
        if not all(g.startswith(p) for g, p in zip(got, HAIR)):
            bad["Hair"] = got
        if COVERAGE and coverage_off(hair):
            bad["Hair_coverage"] = coverage_off(hair)
    for lab, comp, bone in (("HerEarL", sk["Face"], "FACIAL_L_Ear4"), ("HerEarR", sk["Face"], "FACIAL_R_Ear4"),
                            ("HerWatch", body_, WATCH_BONE)):
        rc = L.actor(lab).root_component
        par = rc.get_attach_parent()
        if par is None or par.get_name() != comp.get_name() or str(rc.get_attach_socket_name()) != bone:
            bad[lab] = f"rides {par.get_name() if par else None}/{rc.get_attach_socket_name()}"
    w = L.actor("HerWatch")
    hand = body_.get_socket_location("hand_l")
    fwd = (hand - body_.get_socket_location("lowerarm_l")).normal()
    watch = {"from_hand_cm": round((w.get_actor_location() - hand).length(), 2),
             "band_along_forearm": round(w.get_actor_right_vector().dot(fwd), 3)}
    if abs(watch["from_hand_cm"] - WATCH_UP_ARM) > 0.5 or watch["band_along_forearm"] < 0.98:
        bad["HerWatch_seat"] = watch
    return bad, watch


passes = []
for _ in range(3):
    apply()
    bad, watch = check()
    passes.append(bad)
    if not bad:
        break
if bad:
    raise RuntimeError(f"dress_her: still wrong after {len(passes)} passes: {passes}")
L.save_level()
result = {"ok": True, "passes": len(passes), "watch": watch, "first_pass_lost": passes[0] if len(passes) > 1 else {}}
