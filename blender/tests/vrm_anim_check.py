"""Blender-side check of blender/lib/vrm_anim.py on a real VRM (films/rain-ferry/assets/vroid/shinza.vrm, or --vrm):

    blender -b --factory-startup -P blender/tests/vrm_anim_check.py -- [--vrm path/to.vrm]

  - a prop carried by a bone keeps its place when the shot moves the character between carry() and bake(), and goes
    on with the hand from the handoff without a jump
  - a hand reaching a hilt over its shoulder (a target close to the shoulder) lands on it with the elbow folded out,
    not on it
  - a heavy walk and a charge plant their feet: each IK end on its target, a grounded foot still in the world
  - a walk over a slope lands each footfall on the ground under it
Prints each check and exits non-zero when one fails.
"""
import argparse
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

from lib import vrm, vrm_anim as va  # noqa: E402

FAILED = []


def check(name: str, ok: bool, detail: str) -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {detail}", flush=True)
    if not ok:
        FAILED.append(name)


def fresh(path):
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    coll = bpy.data.collections.new("check")
    bpy.context.scene.collection.children.link(coll)
    ch = vrm.load(path, coll, name="who")
    vrm.scale_to(ch, 1.76)
    vrm.pose(ch, va.STAND)
    for ob in ch.meshes:                 # only the bones are read: no skinning on every frame
        for md in ob.modifiers:
            md.show_viewport = False
    return ch


def at(ch, f, bone):
    bpy.context.scene.frame_set(f)
    return np.array(ch.point(bone))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--vrm", default=str(HERE.parent / "films" / "rain-ferry" / "assets" / "vroid" / "shinza.vrm"))
    a = ap.parse_args(argv)
    sc = bpy.context.scene

    # ---- a carried prop, the character moved after carry(); a reach over the shoulder
    ch = fresh(a.vrm)
    bpy.ops.mesh.primitive_cube_add(size=0.1, location=(-0.1, 0.1, 1.4))
    cube = bpy.context.active_object
    vrm.attach(cube, ch, "upperChest")
    p = va.Performance(ch)
    p.carry(cube, 30, "rightHand")
    ch.root.location = (5.0, -1.0, 0.0)
    ch.root.rotation_euler = (0.0, 0.0, math.radians(90.0))
    bpy.context.view_layer.update()
    w0 = np.array(cube.matrix_world)[:3, 3]
    sh = p.rest_heads["rightUpperArm"]
    p.reach(10, "rightHand", ("char", sh + np.array([0.0, 0.12, 0.17])), pole=(-0.45, 0.2, 1.75))
    p.reach(40, "rightHand", ("char", (-0.2, -0.4, 1.1)), pole=(-0.6, 0.1, 0.9))
    p.bake(0, 50)
    sc.frame_set(0)
    d = float(np.linalg.norm(np.array(cube.matrix_world)[:3, 3] - w0))
    check("carry keeps the prop where it was", d < 1e-3, f"{d * 1000:.1f} mm off at the first frame")
    sc.frame_set(29)
    before = np.array(cube.matrix_world)
    sc.frame_set(30)
    jump = float(np.linalg.norm(np.array(cube.matrix_world)[:3, 3] - before[:3, 3]))
    check("the handoff does not jump", jump < 0.02, f"{jump * 1000:.1f} mm between frames 29 and 30")
    hand0 = at(ch, 32, "rightHand")
    sc.frame_set(32)
    c0 = np.array(cube.matrix_world)[:3, 3] - hand0
    hand1 = at(ch, 45, "rightHand")
    c1 = np.array(cube.matrix_world)[:3, 3] - hand1
    check("the prop goes on with the hand", abs(np.linalg.norm(c0) - np.linalg.norm(c1)) < 1e-3,
          f"its distance from the wrist {np.linalg.norm(c0):.3f} then {np.linalg.norm(c1):.3f} m")
    sc.frame_set(20)
    tgt = np.array(ch.handles["rightHand-target"].matrix_world.translation)
    miss = float(np.linalg.norm(at(ch, 20, "rightHand") - tgt))
    elbow = float(np.linalg.norm(at(ch, 20, "rightLowerArm") - tgt))
    check("a reach over the shoulder lands the wrist", miss < 0.01 and elbow > 0.15,
          f"wrist {miss * 1000:.1f} mm off, elbow {elbow:.2f} m from the target")

    # ---- a prop dangled from a pivot hangs as it was at rest
    ch = fresh(a.vrm)
    bpy.ops.mesh.primitive_cube_add(size=0.1, location=(0.0, 0.15, 1.1))
    cape = bpy.context.active_object
    vrm.attach(cape, ch, "upperChest")
    p = va.Performance(ch)
    p.secondary(chains=[[]])
    p.dangle(cape, (0.0, 0.15, 1.35), length=0.25, stiffness=12.0)
    bpy.context.view_layer.update()
    w0 = np.array(cape.matrix_world)[:3, 3]
    p.bake(0, 20)
    sc.frame_set(10)
    d = float(np.linalg.norm(np.array(cape.matrix_world)[:3, 3] - w0))
    check("a dangled prop hangs where it was", d < 0.03, f"{d * 1000:.0f} mm off at rest")

    # ---- walks: planted feet
    for gait, ground in (("heavy", None), ("charge", None), ("heavy", lambda x, y: 0.12 * x)):
        ch = fresh(a.vrm)
        p = va.Performance(ch)
        end = p.walk([(0.0, 0.0), (4.0, 0.0)], 0, gait=gait, ground=ground)
        p.secondary(wind=(0.0, 1.0, 0.0))
        t0 = time.time()
        p.bake(0, end + 5)
        print(f"     {gait}: baked {end + 5} frames with secondary chains in {time.time() - t0:.1f}s", flush=True)
        # the secondary pass's FK of the baked body is the body Blender evaluates (no IK in the spine and head)
        off = 0.0
        arm = ch.armature
        for fi in (0, end // 2, end):
            sc.frame_set(fi)
            fk_ = p._world_mats(fi)
            for h in ("hips", "upperChest", "head"):
                bn = ch.bones[h]
                real = np.array(arm.matrix_world) @ np.array(arm.pose.bones[bn].matrix)
                off = max(off, float(np.abs(fk_[bn] - real).max()))
        check(f"{gait}: the FK read-back matches Blender", off < 2e-3, f"worst matrix entry {off:.2e} off")
        worst, slide, prev = 0.0, 0.0, {}
        for f in range(0, end + 5):
            sc.frame_set(f)
            for side in ("left", "right"):
                foot = np.array(ch.point(f"{side}Foot"))
                tgt = np.array(ch.handles[f"{side}Foot-target"].matrix_world.translation)
                worst = max(worst, float(np.linalg.norm(foot - tgt)))
                grounded = round(float(f), 3) not in p._air.get(f"{side}Foot", ())
                if grounded and side in prev and prev[side][1]:
                    slide = max(slide, float(np.linalg.norm((foot - prev[side][0])[:2])))
                prev[side] = (foot, grounded)
        what = f"{gait}" + (" uphill" if ground else "")
        check(f"{what}: feet on their targets", worst < 0.03, f"worst {worst * 1000:.0f} mm")
        check(f"{what}: grounded feet do not slide", slide < 0.02, f"worst {slide * 1000:.0f} mm a frame")
        if ground:
            sc.frame_set(end + 4)
            foot = np.array(ch.point("leftFoot"))
            check("uphill: the last footfall on the slope", abs(foot[2] - ground(foot[0], foot[1]) - p.feet_now["leftFoot"][2]) < 0.02,
                  f"ankle {foot[2]:.3f} m over ground {ground(foot[0], foot[1]):.3f}")
    print("all ok" if not FAILED else f"{len(FAILED)} failed: {', '.join(FAILED)}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
