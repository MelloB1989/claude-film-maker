"""Who plays him, without rebuilding the studio: run studio.py's "host swap" block (HOST=trey|op: the Blueprint on the
'Host' mark, SEQ_Reel's Host binding re-pointed) and its "his outfit" block (his trousers under the body, the default
shorts hidden, the leader pose on every garment), then his shirt colour and lighting channels as studio.py sets them,
and the leader check. In the editor:

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
exec(block(src, "his outfit"))
K.channels(["Host"], [0, 1])
mh.garment("Host", "Shirt", vectors={"diffuse_color_1": (0.032, 0.034, 0.038), "diffuse_color_2": (0.045, 0.047, 0.052)})
lc = mh.leader_check(label="Host")
host = L.actor("Host")
result = {"host": HOST, "bp": host.get_class().get_path_name(),
          "components": sorted(c.get_name() for c in host.get_components_by_class(unreal.SkeletalMeshComponent)),
          "leader_pass": lc["pass"], "leader_gap_cm": lc["metric"], "why": lc.get("why", "")}
print(result)
