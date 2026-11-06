"""Who plays him, without rebuilding the studio: run studio.py's "host swap" block (HOST=trey|op: the Blueprint on the
'Host' mark, SEQ_Reel's Host binding re-pointed) and its "his outfit" block (his trousers under the body, the default
shorts hidden, the leader pose on every garment), then his shirt colour and lighting channels as studio.py sets them,
then his tee pushed out INFLATE_CM (default 0.4, as studio.py's finish() does; multi-tick) and the leader check.
On HOST op the trousers are SKM_Host_Trousers_Op when it exists (his own fit: props/his_outfit_ue/r4_fit_op.sh).
In the editor:

    film-ue exec -c "HOST='op'; CHECKOUT='<checkout>'; exec(open(CHECKOUT + '/films/host-studio/unreal/host_swap.py').read())"

Then the clipping checks (multi-tick, so as ops): film-ue op mh.clip_check label=Host garment=Trousers, and
garment=SkeletalMesh (the tee).
"""
import os

import unreal
from fmbridge.ops import level as L, look as K, mh

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or
                                       os.path.join(globals().get("CHECKOUT", os.getcwd()),
                                                    "films/host-studio/unreal/host_swap.py")))
T, S, M = "/Game/Studio/Textures", "/Game/Studio/Surfaces", "/Game/Studio/Materials"
HOST = globals().get("HOST", os.environ.get("HOST_BODY", "trey"))


def tex(folder, name):
    p = f"{folder}/{name}"
    return p if unreal.EditorAssetLibrary.does_asset_exist(p) else ""


def block(src: str, name: str) -> str:
    a, b = src.index(f"# >>> {name}\n"), src.index(f"# <<< {name}\n")
    return src[a:b]


src = open(os.path.join(HERE, "studio.py")).read()
exec(block(src, "host swap"))
# lighting channels first: the host's lights are on channel 1 only, so a new Host on channel 0 alone renders as a black
# silhouette (round 3: the swap crashed in the outfit block before this ran, and S17 showed him unlit)
K.channels(["Host"], [0, 1])
exec(block(src, "his outfit"))
K.channels(["Host"], [0, 1])  # again for the components the outfit block added or re-created
_g = his_garment()
if _g is not None:
    # his tee: Trey keeps studio.py's charcoal; the operator wears a mid grey (~0.12 linear, sRGB ~0.38), so the tee
    # reads apart from his charcoal trousers (round 3: "charcoal trousers + grey tee")
    tee = ({"diffuse_color_1": (0.12, 0.12, 0.125), "diffuse_color_2": (0.135, 0.135, 0.14)} if HOST == "op" else
           {"diffuse_color_1": (0.032, 0.034, 0.038), "diffuse_color_2": (0.045, 0.047, 0.052)})
    mh.garment("Host", "Shirt", component=_g.get_name(), vectors=tee)
INFLATE_CM = float(globals().get("INFLATE_CM", 0.4))
NECK = globals().get("NECK") or {}  # e.g. {"FM_Neck": 2.8, "FM_NeckZ0": ..}: neck_inflate.py (HOST op only)


def finish():
    """Multi-tick (film-ue exec runs a generator result): his tee pushed out INFLATE_CM along its normals, as
    studio.py's finish() does on a full build. A swap alone never did it: Host_Op's tee in cast_op1-4 was the bare
    MetaHuman instance (tee_slots: MI_WI_DefaultGarment...), tight on his skin (round 4, agent-02). The inflate swaps
    the tee's material, so the leader pose is set again on every garment after it."""
    g = his_garment()
    inflated = {}
    if g is not None and INFLATE_CM > 0:
        kw = {}
        if HOST == "op":  # his own master copy, with a neckline term (props/his_outfit_ue/neck_inflate.py; 0 = off)
            import importlib.util
            import fmbridge.ops.mh.actor as _act
            spec = importlib.util.spec_from_file_location(
                "neck_inflate", os.path.join(HERE, "..", "props", "his_outfit_ue", "neck_inflate.py"))
            ni = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ni)
            plain, _act._add_inflate = _act._add_inflate, ni.add_neck_inflate
            kw["folder"] = ni.FOLDER
        try:
            inflated = yield from mh.cloth_inflate("Host", cm=INFLATE_CM, component=g.get_name(), which="Shirt", **kw)
        finally:
            if kw:
                _act._add_inflate = plain
        if NECK:  # the neckline term's knobs (only on HOST op's master)
            mh.garment("Host", "Shirt", component=his_garment().get_name(), scalars=NECK)
        for c in L.actor("Host").get_components_by_class(unreal.SkeletalMeshComponent):
            if c.get_name() not in ("Body", "Face"):
                c.set_leader_pose_component(his_part("Body"))
    g = his_garment()
    lc = mh.leader_check(label="Host")
    host = L.actor("Host")
    out = {"host": HOST, "bp": host.get_class().get_path_name(), "tee": g.get_name() if g is not None else None,
           "tee_slots": ({str(n_): (m_.get_name() if m_ else None) for n_, m_ in
                          zip(g.get_material_slot_names(), g.get_materials())} if g is not None else {}),
           "inflated": inflated,
           "trousers": (lambda t: t.get_skeletal_mesh_asset().get_name() if t else None)(his_part("Trousers")),
           "components": sorted(c.get_name() for c in host.get_components_by_class(unreal.SkeletalMeshComponent)),
           "leader_pass": lc["pass"], "leader_gap_cm": lc["metric"], "why": lc.get("why", "")}
    print(out)
    return out


result = finish()
