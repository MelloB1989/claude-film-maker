"""smalls_combo — preview of all the small shelf objects together, at real relative scale.

Builds every prop exactly as its own script does (nothing is exported here) and sets them on a
light-oak board against a plaster wall, roughly as they stand on the shelves in the concept:
the speckled bottle vase, the lyzn block, the lit candle, the coin leaning on the wall at about
75 degrees, the pickaxe lying on its side, then the black and the white vase.
Renders smalls_combo.png (1800 x 1000: the lineup is wide and low).

    blender -b --factory-startup -P films/host-studio/props/smalls_combo.py -- --out films/host-studio/props/out
"""
import math
import os
import sys

import bpy

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _studio as S  # noqa: E402
import _smalls as M  # noqa: E402
import bitcoin_coin  # noqa: E402
import candle  # noqa: E402
import lyzn_block  # noqa: E402
import pickaxe  # noqa: E402
import vase_black  # noqa: E402
import vase_speckle  # noqa: E402
import vase_white  # noqa: E402

WALL_X = -0.10      # the wall plane; the shelf runs along Y


def make(mod, name, origin=None, post=None, sharp=45):
    parts = mod.build()
    ob = M.bake(parts[0]) if len(parts) == 1 else S.join(name, parts)
    ob.name = name
    lo, hi = S.bbox(ob)
    S.set_origin(ob, origin if origin is not None else ((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    S.tidy(ob, sharp)
    if post:
        post(ob)
    return ob


def place_against_wall(ob, y, gap=0.012, x=None):
    """Stand the object on z = 0 at screen position y, its back `gap` off the wall."""
    lo, hi = S.bbox(ob)
    dx = (WALL_X + gap - lo.x) if x is None else x
    ob.data.transform(Matrix.Translation((dx, y - (lo.y + hi.y) / 2, -lo.z)))
    ob.data.update()


def main():
    args = S.parse_args(__file__)
    S.reset_scene()
    obs = {}
    obs["vase_speckle"] = make(vase_speckle, "vase_speckle", sharp=60)
    obs["lyzn_block"] = make(lyzn_block, "lyzn_block", origin=(0, 0, 0), post=lyzn_block.face_front, sharp=40)
    obs["candle"] = make(candle, "candle", sharp=50)
    obs["bitcoin_coin"] = make(bitcoin_coin, "bitcoin_coin", origin=(0, 0, 0), post=bitcoin_coin.flat_normals, sharp=55)
    obs["pickaxe"] = make(pickaxe, "pickaxe", sharp=45)
    obs["vase_black"] = make(vase_black, "vase_black", sharp=60)
    obs["vase_white"] = make(vase_white, "vase_white", sharp=60)

    place_against_wall(obs["vase_speckle"], -0.265)
    place_against_wall(obs["lyzn_block"], -0.160, gap=0.03)
    place_against_wall(obs["candle"], -0.060, gap=0.035)

    # the coin stood up facing +X and leant back on the wall (75 degrees from the board)
    coin = obs["bitcoin_coin"]
    coin.data.transform(Matrix.Rotation(math.radians(75), 4, "Y"))
    lo, hi = S.bbox(coin)
    coin.data.transform(Matrix.Translation((WALL_X + 0.0005 - lo.x, 0.012 - (lo.y + hi.y) / 2, -lo.z)))
    # the wall is vertical and the coin leans at 75 degrees: put its top edge on the wall
    lo, hi = S.bbox(coin)
    top = max(coin.data.vertices, key=lambda v: v.co.z).co
    coin.data.transform(Matrix.Translation((WALL_X + 0.0005 - top.x, 0, 0)))
    coin.data.update()

    pick = obs["pickaxe"]
    lo, hi = S.bbox(pick)
    pick.data.transform(Matrix.Translation((0.0 - (lo.x + hi.x) / 2, 0.105 - (lo.y + hi.y) / 2, -lo.z)))
    pick.data.update()

    place_against_wall(obs["vase_black"], 0.255)
    place_against_wall(obs["vase_white"], 0.370, gap=0.02)

    lo = Vector((min(S.bbox(o)[0].x for o in obs.values()), min(S.bbox(o)[0].y for o in obs.values()), 0.0))
    hi = Vector((max(S.bbox(o)[1].x for o in obs.values()), max(S.bbox(o)[1].y for o in obs.values()),
                 max(S.bbox(o)[1].z for o in obs.values())))
    M.stage(lo, hi, wall_gap=lo.x - WALL_X + 0.0003, light_scale=0.55)
    flame_z = (candle.FLAME_BASE + 0.7) * M.CM
    c_lo, c_hi = S.bbox(obs["candle"])
    M.point_light("_flame", ((c_lo.x + c_hi.x) / 2, (c_lo.y + c_hi.y) / 2, flame_z), 0.35)
    os.makedirs(args.out, exist_ok=True)
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 1800, 1000      # the lineup is wide and low
    M.shoot(os.path.join(args.out, "smalls_combo.png"), lo, hi, (1.0, -0.30, 0.36), lens=50,
            margin=1.04, samples=args.samples)


main()
