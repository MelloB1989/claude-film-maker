"""Will Cycles motion-blur every deforming object of a shot? A headless check that builds the shot and renders nothing.

  /Applications/Blender.app/Contents/MacOS/Blender -b -P blender/check_deform.py -- --shot b01_thread [--shot ...]

Cycles exports an object's points at each motion-blur step only when Blender reports the object as deform-modified
(Object.is_deform_modified: a deforming or Geometry Nodes modifier, or shape keys). For any other object it copies the
frame's own positions into every step, so geometry whose points a frame handler moves (lib/thread.py MacroRope, the
debris of b01_thread) renders sharp with motion blur on, while its camera still blurs.

Each shot is built as render.py builds it; then every mesh, curve and hair-curves object's evaluated points (object
space, so keyed transforms, which Cycles blurs anyway, don't count) are sampled at frames across the shot. Per object
it prints whether its points move and whether Cycles will see it deform. Exit 1 if any object's points move and it is
not deform-modified, else 0. Nothing is written. The fix for such an object is lib/thread.py deform_blur(ob), a
modifier that changes nothing (MacroRope and its hair curves carry it already).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

import render  # noqa: E402  (load_shot and Ctx; its main() runs only as __main__)
from lib import cli, setup, timing  # noqa: E402

SAMPLES = 13  # frames across the shot at which each object's points are compared
GEOMETRY = ("MESH", "CURVE", "CURVES")


def points(ob, depsgraph) -> np.ndarray:
    """The object's evaluated points, in its own space: after its modifiers and whatever a frame handler wrote."""
    ev = ob.evaluated_get(depsgraph)
    if ob.type == "CURVES":
        pos = ev.data.attributes["position"].data
        out = np.empty(len(pos) * 3, np.float32)
        pos.foreach_get("vector", out)
        return out.reshape(-1, 3)
    me = ev.to_mesh()
    try:
        out = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", out)
        return out.reshape(-1, 3)
    finally:
        ev.to_mesh_clear()


def check(name: str) -> list[str]:
    """Build shot `name`, print its geometry objects, and return the ones that move their points unseen by Cycles."""
    for handlers in (bpy.app.handlers.frame_change_pre, bpy.app.handlers.frame_change_post):
        handlers.clear()  # an earlier shot's handlers must not pose this one
    mod = render.load_shot(name)
    f0, f1 = cli.shot_frames(mod.SHOT)
    scene = setup.new_scene((960, 540), samples=1)  # Cycles: is_deform_modified is asked for render settings
    scene.frame_start, scene.frame_end = f0, f1 - 1
    scene["shot"] = name
    mod.build(render.Ctx(scene, name, "preview", f0, f1, (960, 540), timing.film()))
    obs = sorted((ob for ob in scene.objects if ob.type in GEOMETRY), key=lambda o: o.name)
    frames = sorted({int(round(f)) for f in np.linspace(f0, f1 - 1, SAMPLES)})
    seen: dict[str, list[np.ndarray]] = {ob.name: [] for ob in obs}
    for f in frames:
        scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        for ob in obs:
            seen[ob.name].append(points(ob, dg))
    print(f"[{name}] film frames [{f0}, {f1}), points compared at frames {frames[0]}..{frames[-1]} ({len(frames)})")
    unseen = []
    for ob in obs:
        first, *rest = seen[ob.name]
        moves = any(p.shape != first.shape or not np.array_equal(p, first) for p in rest)
        deform = bool(ob.is_deform_modified(scene, "RENDER"))
        mods = ", ".join(f"{m.name}:{m.type}" for m in ob.modifiers) or "none"
        verdict = "UNSEEN (renders sharp)" if moves and not deform else "ok"
        print(f"  {ob.name:<24} {ob.type:<6} points move: {'yes' if moves else 'no ':<3}  "
              f"is_deform_modified: {deform!s:<5}  modifiers: {mods:<24} {verdict}")
        if moves and not deform:
            unseen.append(ob.name)
    return unseen


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="blender -b -P blender/check_deform.py --",
                                 description="Check that Cycles will motion-blur every deforming object of a shot")
    ap.add_argument("--shot", action="append", required=True, help="blender/shots/<shot>.py (repeatable)")
    a = ap.parse_args(argv)
    unseen = {name: check(name) for name in a.shot}
    bad = {k: v for k, v in unseen.items() if v}
    for name, obs in bad.items():
        print(f"[{name}] {len(obs)} object(s) move their points but are not deform-modified: Cycles renders them "
              f"sharp with motion blur on (give each lib/thread.py deform_blur(ob)): {', '.join(obs)}")
    if not bad:
        print("deformation blur OK: every object whose points move is deform-modified")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
