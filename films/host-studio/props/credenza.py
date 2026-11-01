"""credenza — a low light-oak sideboard, 190 cm long (Y) x 45 cm deep (X) x 72 cm tall.

Slab construction as in the concept: a 3 cm top overhanging the carcass by 1 cm at the front
and the ends, two full-height sides, a bottom and a back, and four flat push-to-open doors
(no handles) between the sides with 3 mm reveals. The carcass stands on four slim black
tapered steel legs on mounting plates (the concept's close-up shows a slim black leg at the
front corner rather than a plinth); the legs keep the brief's slot name M_Plinth.
Grain (UV, 1 unit = 1 m, grain along U): horizontal on the top, bottom and back, vertical on
the sides and the doors; the doors share one projection so the grain runs on across them.
Origin: the bottom centre of the BACK face (back against the wall at x = 0, grows to +X).

    blender -b --factory-startup -P films/host-studio/props/credenza.py -- --out films/host-studio/props/out

Writes <out>/credenza.fbx, credenza.png (3/4), credenza_front.png, and furniture_combo.png:
the credenza against an off-white wall with the four floating shelves (shelf.py) above it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _furniture as F  # noqa: E402

NAME = "credenza"
cm = 0.01

L, D, H = 190 * cm, 45 * cm, 72 * cm
TOP_T = 3.0 * cm
OVER = 1.0 * cm               # top overhang at the front and both ends
PANEL = 1.9 * cm              # sides, bottom, doors
BACK_T = 1.0 * cm
REVEAL = 0.3 * cm
LEG_H = 8.0 * cm              # floor -> underside of the carcass
PLATE_T = 0.4 * cm
BEV = 0.15 * cm
TINY = 0.02 * cm              # keeps touching faces from being coplanar

Z_TOP = H - TOP_T             # underside of the top
X_FRONT = D - OVER            # carcass / door fronts
Y_OUT = L / 2 - OVER          # carcass ends
Y_IN = Y_OUT - PANEL          # inner faces of the sides
N_DOORS = 4

# shelves in furniture_combo.png (tops, cm) and their span in Y (credenza runs -95..95)
SHELF_TOPS = (125, 162, 199, 236)
SHELF_Y = (-35 * cm, 115 * cm)    # start 60 cm in from the left end, overhang the right end by 20 cm


def build(mats):
    oak, metal = mats["oak"], mats["metal"]
    parts = []

    def board(name, lo, hi, grain, offset, mat=oak, width=BEV):
        ob = F.bevel_box(name, lo, hi, mat, width)
        F.uv_box(ob, grain, offset)
        parts.append(ob)
        return ob

    board("top", (0, -L / 2, Z_TOP), (D, L / 2, H), "y", (0.13, 0.42))
    for k, sgn in enumerate((-1, 1)):
        y0, y1 = sorted((sgn * Y_OUT, sgn * Y_IN))
        board(f"side{k}", (0, y0, LEG_H), (X_FRONT, y1, Z_TOP - TINY), "z", (0.71 + 0.3 * k, 0.23))
    door_back = X_FRONT - PANEL
    board("bottom", (0, -Y_IN + TINY, LEG_H), (door_back - TINY, Y_IN - TINY, LEG_H + PANEL), "y", (0.52, 0.9))
    board("back", (0, -Y_IN + TINY, LEG_H + PANEL + TINY), (BACK_T, Y_IN - TINY, Z_TOP - TINY), "y", (0.05, 0.6))

    # doors: one projection for all four -> the vertical grain runs on across the reveals
    span = 2 * (Y_IN - REVEAL)
    w = (span - (N_DOORS - 1) * REVEAL) / N_DOORS
    for i in range(N_DOORS):
        y0 = -Y_IN + REVEAL + i * (w + REVEAL)
        board(f"door{i}", (door_back, y0, LEG_H), (X_FRONT, y0 + w, Z_TOP - REVEAL), "z", (0.31, 0.0))

    # legs: square mounting plate + round tapered leg with a slightly rounded foot
    for xi, x in enumerate((6 * cm, X_FRONT - 6 * cm)):
        for yi, y in enumerate((-Y_OUT + 6 * cm, Y_OUT - 6 * cm)):
            plate = F.bevel_box(f"plate{xi}{yi}", (x - 3 * cm, y - 3 * cm, LEG_H - PLATE_T),
                                (x + 3 * cm, y + 3 * cm, LEG_H - TINY), metal, 0.1 * cm, segments=2)
            F.uv_box(plate, "x")
            leg = S.cylinder(f"leg{xi}{yi}", (x, y, 0), (x, y, LEG_H - PLATE_T + TINY), 0.85 * cm, metal,
                             segs=24, r2=1.35 * cm)
            S.bevel(leg, 0.12 * cm, segments=2)
            F.bake(leg)
            F.uv_tube(leg, (x, y, 0), (x, y, LEG_H))
            parts += [plate, leg]
    return parts


def combo(cred, args):
    """The credenza against an off-white wall with the four shelves above it."""
    import shelf
    sh = F.finalize("shelf_combo", shelf.build(shelf.materials()), origin=(0, 0, 0))
    yc = sum(SHELF_Y) / 2
    shelves = [sh]
    for i in range(1, len(SHELF_TOPS)):
        o = sh.copy()
        bpy_link(o)
        shelves.append(o)
    for o, top in zip(shelves, SHELF_TOPS):
        o.location = (0, yc, top * cm - shelf.THICK)
        F.led_light(f"_led{top}", ((shelf.X0 + shelf.X1) / 2, yc, top * cm - shelf.THICK - 0.001),
                    2 * shelf.Y_CH, energy=12.0)
    lo = (0, -L / 2, 0)
    hi = (D, SHELF_Y[1], SHELF_TOPS[-1] * cm)
    F.shoot(os.path.join(args.out, "furniture_combo.png"), (1.0, -0.22, 0.12), lo, hi, args.samples,
            lens=45, margin=1.08)


def bpy_link(o):
    import bpy
    bpy.context.scene.collection.objects.link(o)


def main():
    args = S.parse_args(__file__)
    S.reset_scene()
    mats = dict(oak=F.oak(), metal=F.black_metal())
    ob = F.finalize(NAME, build(mats), origin=(0, 0, 0))
    F.export(ob, args)
    if args.no_render:
        return
    lo, hi = S.bbox(ob)
    F.stage(floor=True, wall_x=-0.0005)
    out = args.out
    F.shoot(os.path.join(out, NAME + ".png"), (1.0, 0.75, 0.55), lo, hi, args.samples, lens=60)
    F.shoot(os.path.join(out, NAME + "_front.png"), (1.0, 0.0, 0.15), lo, hi, args.samples, lens=60)
    combo(ob, args)


if __name__ == "__main__":
    main()
