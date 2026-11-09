"""Him, ready for a presenter render: his garments (Trousers, and the default garment with his tee) follow his body
both on the level and from SEQ_Reel itself, as dress_her.py + seq_dress.py do for her. host_swap.py sets each
garment's leader pose, but a leader pose does not survive an editor restart or level reload, and a change to any of
his instance components re-creates the others without it: a garment then stands in its bind pose while the body moves
(her S17/S18 in round 3's preview r1). So:

- level: every garment's leader set to Body (anim class None), read back, set again if a step undid another (up to 3
  passes); raises unless all hold; saves the level.
- SEQ_Reel: each garment gets the same animation sections as Host's Body (copied from the Body track perf.py place
  wrote), so it plays his pose with or without a leader. Saves SEQ_Reel.

Run with film-ue exec after host_swap.py (Trey or the operator: whoever is on the Host mark) and perf.py place, as the
last step before a presenter render, next to dress_her.py/seq_dress.py; again after any re-place or editor restart.
"""
import unreal

from fmbridge.ops import level as L
from fmbridge.ops import seq as Q
from fmbridge.ops.seqcore import _engine as E

SEQ = "/Game/Reel/SEQ_Reel"
WHO = "Host"


def comps():
    return {c.get_name(): c for c in L.actor(WHO).get_components_by_class(unreal.SkeletalMeshComponent)}


def garments():  # not the stale TRASH_* a Blueprint re-instance leaves (op <-> trey swap): save, reopen, re-swap first
    return sorted(n for n in comps() if n not in ("Body", "Face") and not n.startswith("TRASH_"))


def apply():
    for n in garments():
        c = comps()[n]  # fetched afresh: a change on one component rebuilds the others
        c.set_anim_instance_class(None)
        c.set_leader_pose_component(comps()["Body"])


def check():
    bad = {}
    for n, c in comps().items():
        if n not in garments():
            continue
        lead = c.get_editor_property("leader_pose_component")
        if lead is None or lead.get_name() != "Body":
            bad[n] = f"leader {lead.get_name() if lead else None}"
    return bad


trash = sorted(n for n in comps() if n.startswith("TRASH_"))
if trash:
    raise RuntimeError(f"dress_him: {WHO} has stale components {trash}: save and reopen the level (or respawn), then "
                       "run host_swap.py again before dressing him")
if not garments():
    raise RuntimeError(f"dress_him: {WHO} has no garments (only {sorted(comps())}): run host_swap.py first")
passes = []
for _ in range(3):
    apply()
    bad = check()
    passes.append(bad)
    if not bad:
        break
if bad:
    raise RuntimeError(f"dress_him: still wrong after {len(passes)} passes: {passes}")
L.save_level()

seq = unreal.load_asset(SEQ)
body = E.track_by_id(E.describe(SEQ), ("anim", WHO, "Body", ""))
if not body or not body.get("sections"):
    raise RuntimeError(f"dress_him: SEQ_Reel has no animation on {WHO}'s Body: run perf.py place first")
seqd = {}
for g in garments():
    E.binding(seq, WHO, g, create=True)
    Q._write(seq, [Q._track("anim", WHO, g, sections=body["sections"])])
    seqd[g] = len(body["sections"])
unreal.EditorAssetLibrary.save_asset(SEQ)
result = {"ok": True, "who": WHO, "bp": L.actor(WHO).get_class().get_name(), "passes": len(passes),
          "first_pass_lost": passes[0] if len(passes) > 1 else {}, "seq_sections": seqd}
