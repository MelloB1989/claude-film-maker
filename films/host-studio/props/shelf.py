"""shelf — one light-oak floating shelf with a recessed LED channel under its front edge.

150 cm long (Y) x 26 cm deep (X) x 4.5 cm thick, solid light oak with 2 mm rounded edges;
the two end faces are end grain (their own slot, M_OakEnd). Under the front edge, 2 cm back
from it, a recessed aluminium U-channel 1.6 cm wide x 1 cm deep runs nearly the full length
with a frosted diffuser strip (M_LedStrip) flush in its mouth, ready to glow in Unreal.
Origin: the centre of the shelf's BACK edge at its BOTTOM (back against the wall at x = 0,
the shelf grows towards +X). UVs world-scale (1 UV unit = 1 m), grain along U = along Y.

    blender -b --factory-startup -P films/host-studio/props/shelf.py -- --out films/host-studio/props/out

Writes <out>/shelf.fbx, shelf.png (3/4), shelf_front.png and shelf_close.png (below-front).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _furniture as F  # noqa: E402

NAME = "shelf"
cm = 0.01

LEN = 150 * cm
DEPTH = 26 * cm
THICK = 4.5 * cm
EDGE = 0.2 * cm              # rounded edges

CH_W = 1.6 * cm              # LED channel
CH_D = 1.0 * cm
CH_FRONT = 2.0 * cm          # channel's front edge, back from the shelf's front edge
CH_END = 2.0 * cm            # channel stops this short of each end
CH_WALL = 0.1 * cm
CLEAR = 0.01 * cm            # clearance groove <-> channel, channel <-> diffuser (no coplanar faces)

X1 = DEPTH - CH_FRONT        # channel outer faces, X
X0 = X1 - CH_W
Y_CH = LEN / 2 - CH_END


def materials():
    return dict(
        oak=F.oak(),
        end=F.oak_end(),
        alu=F.plain("M_Alu", (0.80, 0.80, 0.81), 0.32, metallic=1.0),
        led=F.emissive("M_LedStrip", (1.0, 0.80, 0.58), 4.0, roughness=0.35),
    )


def channel(mats):
    """Aluminium U-channel, open side down, its lips flush with the shelf's bottom (z = 0)."""
    t, h = CH_WALL, CH_D
    x0, x1 = X0, X1
    prof = [(x0, 0), (x0 + t, 0), (x0 + t, h - t), (x1 - t, h - t), (x1 - t, 0), (x1, 0), (x1, h), (x0, h)]
    verts, faces = [], []
    for y in (-Y_CH, Y_CH):
        verts += [(x, y, z) for x, z in prof]
    n = len(prof)
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    for a, b, c, d in ((0, 1, 2, 7), (7, 2, 3, 6), (3, 4, 5, 6)):   # the concave U cap as 3 quads
        faces.append((a, b, c, d))
        faces.append((n + d, n + c, n + b, n + a))
    ob = F.mesh("channel", verts, faces, [mats["alu"]])
    return F.uv_box(ob, "y")


def build(mats=None):
    mats = mats or materials()
    body = F.bevel_box("shelf_body", (0, -LEN / 2, 0), (DEPTH, LEN / 2, THICK), mats["oak"], EDGE, segments=3)
    body.data.materials.append(mats["end"])
    cutter = S.box("groove", (X0 - CLEAR, -Y_CH - CLEAR, -0.5 * cm), (X1 + CLEAR, Y_CH + CLEAR, CH_D + CLEAR),
                   mats["oak"])
    F.boolean_cut(body, cutter)
    # end grain on the two end faces (and their rounded edges), not on the groove's ends
    F.uv_box(body, "y", offset=(0.37, 0.11), end_slot=1,
             end_test=lambda c: abs(c.y) > LEN / 2 - 0.01)

    ch = channel(mats)
    t = CH_WALL + CLEAR
    diff = S.box("diffuser", (X0 + t, -Y_CH + CLEAR, 0.03 * cm), (X1 - t, Y_CH - CLEAR, 0.35 * cm), mats["led"])
    F.uv_box(diff, "y")
    return [body, ch, diff]


def main():
    args = S.parse_args(__file__)
    S.reset_scene()
    ob = F.finalize(NAME, build(), origin=(0, 0, 0))
    F.export(ob, args)
    if args.no_render:
        return
    lo, hi = S.bbox(ob)
    F.stage(floor=False, wall_x=-0.0005)
    F.led_light("_led", ((X0 + X1) / 2, 0, -0.001), 2 * Y_CH)
    out = args.out
    F.shoot(os.path.join(out, NAME + ".png"), (1.0, 0.75, 0.55), lo, hi, args.samples, lens=60)
    F.shoot(os.path.join(out, NAME + "_front.png"), (1.0, 0.0, 0.06), lo, hi, args.samples, lens=60)
    F.shoot(os.path.join(out, NAME + "_close.png"), (1.0, 0.45, -0.55), lo, hi, args.samples, lens=40,
            target=(0.17, 0.55, 0.0), distance=0.55, light_size=0.8)


if __name__ == "__main__":
    main()
