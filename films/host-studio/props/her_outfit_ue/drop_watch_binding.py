"""r7 (agent-05): her watch is dropped (the operator: "watch is clipping through hand, drop the watch"). Removes every
binding named HerWatch* (possessables and spawnables, with their attach / transform tracks) from her sequences, so no
binding points at the actor dress_her.py destroys (agent-06: a dangling binding could trip the leader or MRQ checks).
Idempotent; saves only a sequence it changed. Run with film-ue exec after set.py's dress step:

    film-ue exec -c "exec(open('<tree>/films/host-studio/props/her_outfit_ue/drop_watch_binding.py').read())"
    film-ue exec -c "SEQS=['/Game/Explainer/SEQ_Explain_Her']; exec(open(...).read())"
"""
import unreal

SEQS = list(globals().get("SEQS", ["/Game/Explainer/SEQ_Explain_Her", "/Game/Reel/SEQ_Reel"]))
out = {}
for path in SEQS:
    seq = unreal.load_asset(path)
    if seq is None:
        out[path] = "no such sequence"
        continue
    gone = []
    for b in list(seq.get_bindings()):
        name = str(b.get_display_name())
        if name.startswith("HerWatch"):
            b.remove()
            gone.append(name)
    left = [str(b.get_display_name()) for b in seq.get_bindings() if str(b.get_display_name()).startswith("HerWatch")]
    if gone:
        unreal.EditorAssetLibrary.save_asset(path)
    out[path] = {"removed": gone, "left": left}
    if left:
        raise RuntimeError(f"{path}: HerWatch bindings still there: {left}")
result = out
