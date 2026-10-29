"""Cast sheets: a film's characters, built by its own builders, rendered in its toon look from the front, three
quarters, the side and the back, with a close-up of the head, side by side on one sheet: the quickest way to judge a
design and to see what a change did.

    blender -b -P blender/castsheet.py -- --film <id> --module rf.cast --builders shinza,tsuru [--res 640x900]
        [--out out/<id>/cast] [--outline 2.2] [--shift 0.5] [--rim 0.85]
    blender -b -P blender/castsheet.py -- --film <id> --vrm path/to/a.vrm[,b.vrm] [--pose relaxed|rest]
        [--height 1.75] [--out out/<id>/vroid] [--vrm-outline 1.6]

`--module` is a module under films/<id>/blender/ (dotted), each builder a function in it taking (collection, look)
and returning a dict with the character's "root" (and "head", the head's centre, for the close-up). Characters are
built facing +x with their feet at the origin (blender/lib/anime.py). Writes <out>/<builder>.png, one sheet each.

`--vrm` sheets VRM files as they come (blender/lib/vrm.py: VRoid Studio's exports), standing easy (`--pose relaxed`,
vrm.RELAXED) or in their T-pose (`rest`), scaled to `--height` metres when given; each sheet is <out>/<file stem>.png
(default out/<id>/vroid). A builder may build from a VRM too: it returns the vrm.Character as "vrm". A VRM's MToon
draws its own outline, so its sheet adds no ink of its own and sets the MToon outline to `--vrm-outline` px in every
tile.
"""
from __future__ import annotations

import argparse
import importlib
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

from lib import film as films, outline, setup, toon, vrm  # noqa: E402

VIEWS = [("front", 0.0), ("three-quarter", 40.0), ("side", 90.0), ("back", 180.0)]


def args(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", required=True)
    ap.add_argument("--module")
    ap.add_argument("--builders")
    ap.add_argument("--vrm", help="VRM files to sheet as they come, comma-separated (instead of --module/--builders)")
    ap.add_argument("--pose", choices=["relaxed", "rest"], default="relaxed", help="--vrm: the pose to sheet them in")
    ap.add_argument("--height", type=float, help="--vrm: scale each to this standing height (m)")
    ap.add_argument("--vrm-outline", type=float, default=1.6, help="a VRM's MToon outline, px (0: as the file has it)")
    ap.add_argument("--res", default="640x900")
    ap.add_argument("--out")
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--outline", type=float, default=2.2, help="the ink outline round the cast, px (0: none)")
    ap.add_argument("--shift", type=float, default=0.5, help="the shadows' anime hue shift (toon.shadow_hue)")
    ap.add_argument("--rim", type=float, default=0.85, help="the rim light's strength on the shadow side (0: none)")
    a = ap.parse_args(argv[argv.index("--") + 1:] if "--" in argv else [])
    if not a.vrm and not (a.module and a.builders):
        ap.error("give --module and --builders, or --vrm")
    return a


def vrm_builder(path: Path, pose: str, height: float | None):
    """A builder for a VRM file as it comes: loaded, scaled, standing easy (or in its T-pose)."""
    def build(coll, look):
        ch = vrm.load(path, coll, name=path.stem)
        if height:
            vrm.scale_to(ch, height)
        vrm.pose(ch, vrm.RELAXED if pose == "relaxed" else {})
        return {"root": ch.root, "head": tuple(ch.face()), "vrm": ch}
    return build


def vrm_outline(ch, px: float, dist: float, lens: float, h_px: int, sensor: float = 36.0) -> None:
    """Every MToon outline of a VRM at `px` pixels for a camera `dist` metres off with a `lens` mm lens (the default
    sensor fit to a portrait frame's height, `h_px` tall)."""
    if px > 0:
        vrm.key_outline(ch, vrm.outline_width(px / h_px, dist, lens, gate=sensor), bpy.context.scene.frame_current)


def render_to(path: Path) -> np.ndarray:
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(str(path))
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    return px


def main():
    a = args(sys.argv)
    film = films.load(a.film)
    sys.path.insert(0, str(film.root / "blender"))
    if a.vrm:
        paths = [Path(v).expanduser() for v in a.vrm.split(",")]
        builders = [(p.stem, vrm_builder(p if p.is_absolute() else film.repo / p, a.pose, a.height)) for p in paths]
    else:
        mod = importlib.import_module(a.module)
        builders = [(name, getattr(mod, name)) for name in a.builders.split(",")]
    w, h = (int(v) for v in a.res.split("x"))
    out = Path(a.out) if a.out else film.repo / "out" / film.id / ("vroid" if a.vrm else "cast")
    out.mkdir(parents=True, exist_ok=True)

    scene = setup.new_scene((w, h), fps=film.fps, engine="BLENDER_EEVEE", samples=a.samples, motion_blur=0, view="Standard")
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.035, 0.038, 0.045, 1)
    look = toon.Look(fog=(0.62, 0.64, 0.68), fog_near=100, fog_far=500)
    cast_look = toon.Look(fog=look.fog, fog_near=look.fog_near, fog_far=look.fog_far, shade_shift=a.shift,
                          rim=(None, 0.3, a.rim) if a.rim > 0 else None)
    # a pale ground and a pale backdrop so the ink reads
    bpy.ops.mesh.primitive_plane_add(size=40)
    ground = bpy.context.active_object
    ground.data.materials.append(toon.cel("sheet-ground", (0.55, 0.56, 0.58), (0.4, 0.41, 0.44), look=look))
    sun = bpy.data.lights.new("key", "SUN")
    sun.energy = 4.2
    sun.angle = math.radians(3)
    key = bpy.data.objects.new("key", sun)
    scene.collection.objects.link(key)
    key.rotation_euler = Vector((-0.5, 0.55, -0.7)).to_track_quat("-Z", "Y").to_euler()
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens = 50
    aim = bpy.data.objects.new("aim", None)
    scene.collection.objects.link(aim)
    tc = cam.constraints.new("TRACK_TO")
    tc.target = aim
    tc.track_axis = "TRACK_NEGATIVE_Z"
    tc.up_axis = "UP_Y"

    for name, builder in builders:
        coll = toon.collection(f"sheet-{name}")
        before = set(bpy.data.objects)
        built = builder(coll, cast_look)
        group = f"{outline.GROUP}-{name}"
        ch = built.get("vrm")
        if ch is not None:
            ink = None     # MToon's own outline (vrm_outline, per tile)
        elif a.outline > 0:
            # drawn as the shots draw it: an ink outline round every part, Line Art for the inner lines only,
            # the clothes' shading smoothed (lib/outline.py)
            body = getattr(built.get("person"), "body", None)
            for ob in list(coll.all_objects):
                if ob.type == "MESH" and ob is not body and outline.wants_hull(ob) and max(ob.dimensions) > 0.25 \
                        and any(m.type == "ARMATURE" for m in ob.modifiers) and "hair" not in ob.name:
                    outline.smooth_normals(ob, 6)
            if body is not None:
                outline.taper(body, {"finger": 0.35, "toe": 0.5, "metacarpal": 0.7})
            outline.apply(coll, a.outline, scale=outline.pixel_scale(50.0, 36.0, w), look=cast_look, group=group)
            ink = toon.ink(f"ink-{name}", coll, radius=0.0028, creases=False, drawn=True)
        else:
            ink = toon.ink(f"ink-{name}", coll, radius=0.0042)
        tiles = []
        # a VRM framed to its own height (the frame a quarter again as tall as it), level with its middle
        tall = vrm.standing_height(ch) if ch is not None else None
        for label, deg in VIEWS:
            r = math.radians(deg)
            dist = 5.2 if tall is None else 1.25 * tall * cam.data.lens / 36.0
            cam.location = (dist * math.cos(r), -dist * math.sin(r), 1.0 if tall is None else tall * 0.55)
            aim.location = (0, 0, 0.85 if tall is None else tall * 0.5)
            if ch is not None:
                vrm_outline(ch, a.vrm_outline, dist, cam.data.lens, h)
            tiles.append(render_to(out / f"_{name}-{label}.png"))
        head = built.get("head", (0.1, 0.0, 1.5))
        cam.data.lens = 85
        if ch is not None:
            vrm_outline(ch, a.vrm_outline, math.hypot(1.1, 0.75), cam.data.lens, h)
        else:
            outline.set_width(scale=outline.pixel_scale(85.0, 36.0, w), group=group)
        cam.location = (head[0] + 1.1, head[1] - 0.75, head[2] + 0.05)
        aim.location = head
        tiles.append(render_to(out / f"_{name}-head.png"))
        cam.data.lens = 50
        sheet = np.concatenate(tiles, axis=1)
        img = bpy.data.images.new(f"sheet-{name}", sheet.shape[1], sheet.shape[0], alpha=True)
        img.pixels = sheet.ravel().tolist()
        img.filepath_raw = str(out / f"{name}.png")
        img.file_format = "PNG"
        img.save()
        print(f"castsheet: {out / f'{name}.png'}")
        # everything this builder made, wherever it put it (a prop in its own collection would haunt the next sheet)
        for ob in set(bpy.data.objects) - before:
            bpy.data.objects.remove(ob, do_unlink=True)


if __name__ == "__main__":
    main()
