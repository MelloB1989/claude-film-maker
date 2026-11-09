"""Her garments, hoops and watch follow her body from SEQ_Reel itself, not from the level. Round 3's preview r1 (16:58)
had her garments in bind pose and the watch floating at her chest although the leader pose and the watch's seat had
been set and saved (16:37, 16:47): an editor restart reloaded the level in between, and a leader pose or an attachment
to one of her instance components does not survive that (or the render's PIE copy). Tracks in the sequence do.

- Top, Trousers, Overshirt: each gets the same animation sections as Presenter's Body (copied from SEQ_Reel's Body
  track, every row: idle -> performance -> idle and the life layer), so each plays her body's pose with or without a
  leader. With the leader set, the leader still wins: nothing changes where it holds.
- HerWatch, HerEarL, HerEarR: an attach track (whole sequence) onto Presenter's Body/Face bone, and a transform
  track holding the offset each has from that bone now (the watch: from its seat rule, as dress_her.py seats it).
  So run dress_her.py first: it seats them and checks them.

Run with film-ue exec after perf.py place (it copies the Body track place wrote) and after dress_her.py; run again
after any re-place. Saves SEQ_Reel. Returns what it wrote and each accessory's offset.
"""
import unreal

from fmbridge.ops import level as L
from fmbridge.ops import seq as Q
from fmbridge.ops.seqcore import _engine as E

SEQ = "/Game/Reel/SEQ_Reel"
GARMENTS = ("Top", "Trousers", "Overshirt")
RIDERS = {"HerWatch": ("Body", "lowerarm_twist_01_l"), "HerEarL": ("Face", "FACIAL_L_Ear4"),
          "HerEarR": ("Face", "FACIAL_R_Ear4")}
KR = unreal.AttachmentRule.KEEP_RELATIVE
WATCH_UP_ARM = 3.6  # dress_her.py's seat: the watch this far up the forearm from hand_l, band across the wrist

seq = unreal.load_asset(SEQ)
her = L.actor("Presenter")
comps = {c.get_name(): c for c in her.get_components_by_class(unreal.SkeletalMeshComponent)}
out = {"garments": {}, "riders": {}}

# --- garments: the Body's sections on each
body = E.track_by_id(E.describe(SEQ), ("anim", "Presenter", "Body", ""))
if not body or not body.get("sections"):
    raise RuntimeError("seq_dress: SEQ_Reel has no animation on Presenter's Body: run perf.py place first")
for g in GARMENTS:
    if g not in comps:
        out["garments"][g] = "no such component"
        continue
    E.binding(seq, "Presenter", g, create=True)
    Q._write(seq, [Q._track("anim", "Presenter", g, sections=body["sections"])])
    out["garments"][g] = len(body["sections"])

# --- riders: attached to her bone in the sequence, at the offset they have now
pres = E.binding(seq, "Presenter", "", create=True)
pid = seq.get_binding_id(pres)
for lab, (comp, bone) in RIDERS.items():
    a = L.actor(lab)
    rc = a.root_component
    par = rc.get_attach_parent()
    if par is None or par.get_name() != comp or str(rc.get_attach_socket_name()) != bone:
        raise RuntimeError(f"seq_dress: {lab} rides {par.get_name() if par else None}/{rc.get_attach_socket_name()}, "
                           f"not {comp}/{bone}: run dress_her.py first")
    rl, rr = rc.relative_location, rc.relative_rotation
    if lab == "HerWatch":
        # the watch's offset from its seat rule, not read back from the actor: cast_op2/3 rendered it 8.2 cm from
        # hand_l while dress_her had just seated it at 3.6 (likely Sequencer re-applying the transform track's old
        # key between dress_her and here, so keying what the actor then holds keeps the old seat)
        bc = comps[comp]
        P = bc.get_socket_location
        hand = P("hand_l")
        fwd = (hand - P("lowerarm_l")).normal()
        across = P("index_metacarpal_l") - P("pinky_metacarpal_l")
        across = (across - fwd * across.dot(fwd)).normal()
        rot = unreal.MathLibrary.make_rot_from_yz(fwd, fwd.cross(across).normal())
        seat = unreal.Transform(hand - fwd * WATCH_UP_ARM, rot, unreal.Vector(1, 1, 1))
        rel = seat.make_relative(bc.get_socket_transform(bone, unreal.RelativeTransformSpace.RTS_WORLD))
        was = [round(rl.x, 2), round(rl.y, 2), round(rl.z, 2)]
        rl, rr = rel.translation, rel.rotation.rotator()
        out.setdefault("watch_actor_rel_was", was)
    b = E.binding(seq, lab, "", create=True)
    for t in list(b.find_tracks_by_type(unreal.MovieScene3DAttachTrack)) + list(
            b.find_tracks_by_type(unreal.MovieScene3DTransformTrack)):  # no old seat's keys left to win
        b.remove_track(t)
    sec = b.add_track(unreal.MovieScene3DAttachTrack).add_section()
    sec.set_start_frame_bounded(False)
    sec.set_end_frame_bounded(False)
    sec.set_constraint_binding_id(pid)
    sec.set_editor_property("attach_component_name", comp)
    sec.set_editor_property("attach_socket_name", bone)
    for k in ("attachment_location_rule", "attachment_rotation_rule", "attachment_scale_rule"):
        try:
            sec.set_editor_property(k, KR)
        except Exception:  # noqa: BLE001 (older names)
            pass
    # attached, an actor's transform track is its offset from the bone: one constant key holds it
    Q.key_transform(SEQ, lab, [[seq.get_playback_start(), [rl.x, rl.y, rl.z],
                                {"roll": rr.roll, "pitch": rr.pitch, "yaw": rr.yaw}]], interp="constant")
    out["riders"][lab] = {"bone": f"{comp}/{bone}", "rel_loc": [round(rl.x, 2), round(rl.y, 2), round(rl.z, 2)],
                          "rel_rot": [round(rr.roll, 1), round(rr.pitch, 1), round(rr.yaw, 1)]}
unreal.EditorAssetLibrary.save_asset(SEQ)
result = out
