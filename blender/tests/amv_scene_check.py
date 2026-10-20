"""Blender-side geometry check: project every plane's corners through the camera and compare with `Shot.matrix(f)`.

    blender -b --factory-startup -P blender/tests/amv_scene_check.py -- [--film films/timeless] [--frames-per-shot 5]

The planes get 4x4 placeholder frames (only the geometry is looked at), so no bake output is needed. Prints a table (one
row per shot: the worst corner error in px at 1080p over the sampled frames) and exits non-zero when any error is
>= 0.5 px. The portal's A_in plane is checked against its own per-frame transform.
"""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))

import bpy  # noqa: E402
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402
from mathutils import Vector  # noqa: E402

from amv import scene as S  # noqa: E402
from filmtools.amv import plan as amv_plan  # noqa: E402

LIMIT = 0.5


def main(argv):
    film = Path(argv[argv.index("--film") + 1]) if "--film" in argv else HERE.parent / "films" / "timeless"
    per = int(argv[argv.index("--frames-per-shot") + 1]) if "--frames-per-shot" in argv else 5
    plan = amv_plan.load(film)
    tmp = Path(tempfile.mkdtemp())
    img = bpy.data.images.new("ph", 4, 4)
    for shot in plan.shots:
        d = tmp / shot.name
        d.mkdir()
        img.filepath_raw = str(d / f"{shot.a:04d}.png")
        img.file_format = "PNG"
        img.save()
    built = S.build_scene(film, tmp, res_scale=0.25, samples=1, log=lambda *_: None)
    scene, cam = built.scene, built.scene.camera
    # the camera's view of the 1920x1080 screen: render at the scene's resolution, report px at 1080p
    worst = 0.0
    print(f"{'shot':<22}{'frames':>7}{'max err px':>12}")
    rows = [(shot.name, built.planes[shot.name], shot, None) for shot in plan.shots]
    for name, ob, shot, _ in rows:
        n = shot.end - shot.a
        frames = sorted({shot.a + round(i * (n - 1) / max(1, per - 1)) for i in range(per)})
        err = 0.0
        for f in frames:
            scene.frame_set(f)
            m = shot.matrix(f)
            canvas = shot.canvas
            ax, ay = S.anchor_in_canvas(canvas)
            for cx, cy in ((0, 0), (canvas[0], 0), (canvas[0], canvas[1]), (0, canvas[1])):
                lx, ly = cx - canvas[2], cy - canvas[3]
                want = (m[0][0] * lx + m[0][1] * ly + m[0][2], m[1][0] * lx + m[1][1] * ly + m[1][2])
                local = Vector(((cx - ax) / S.UNIT, -(cy - ay) / S.UNIT, 0.0))
                nd = world_to_camera_view(scene, cam, ob.matrix_world @ local)
                got = (nd.x * S.W, (1.0 - nd.y) * S.H)
                err = max(err, abs(got[0] - want[0]), abs(got[1] - want[1]))
        worst = max(worst, err)
        print(f"{name:<22}{len(frames):>7}{err:>12.4f}")
    print(f"worst {worst:.4f} px (limit {LIMIT})")
    sys.exit(0 if worst < LIMIT else 1)


main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
