"""Her garments, hoops and watch follow her body from SEQ_Reel itself, not from the level. Round 3's preview r1 (16:58)
had her garments in bind pose and the watch floating at her chest although the leader pose and the watch's seat had
been set and saved (16:37, 16:47): an editor restart reloaded the level in between, and a leader pose or an attachment
to one of her instance components does not survive that (or the render's PIE copy). Tracks in the sequence do.

- Top, Trousers, Overshirt: each gets the same animation sections as Presenter's Body (copied from SEQ_Reel's Body
  track, every row: idle -> performance -> idle and the life layer), so each plays her body's pose with or without a
  leader. With the leader set, the leader still wins: nothing changes where it holds.
- HerWatch, HerEarL, HerEarR: an attach track (whole sequence) onto Presenter's Body/Face bone, and a transform
  track holding the offset each has from that bone now. So run dress_her.py first: it seats them and checks them.

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
    b = E.binding(seq, lab, "", create=True)
    for t in list(b.find_tracks_by_type(unreal.MovieScene3DAttachTrack)):
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
