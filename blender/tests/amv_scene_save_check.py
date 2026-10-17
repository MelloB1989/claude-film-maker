"""Blender-side: a saved AMV .blend keeps its textures, as '//' paths, and they resolve after the folder moves.

    blender -b --factory-startup -P blender/tests/amv_scene_save_check.py

Builds the scene from relative --layers / --overlays paths (the cwd-relative case that went magenta), saves it with the
layers next to it, reopens it, then copies the folder elsewhere and reopens that. Exits non-zero on any missing file.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))

import bpy  # noqa: E402

from amv import scene as S  # noqa: E402
from filmtools.amv import plan as amv_plan  # noqa: E402


def missing():
    out = []
    for im in bpy.data.images:
        if im.source in ("FILE", "SEQUENCE") and im.filepath and not im.packed_file:
            if not im.filepath.startswith("//"):
                out.append(f"{im.name}: not relative: {im.filepath}")
            elif not os.path.exists(bpy.path.abspath(im.filepath)):
                out.append(f"{im.name}: missing {bpy.path.abspath(im.filepath)}")
    return out


def main():
    film = ROOT / "films" / "timeless"
    plan = amv_plan.load(film)
    work = Path(tempfile.mkdtemp())
    amv = work / "out" / "amv"
    img = bpy.data.images.new("ph", 4, 4)
    for shot in plan.shots[:3]:
        d = amv / "layers" / shot.name
        d.mkdir(parents=True)
        img.filepath_raw = str(d / f"{shot.a:04d}.png")
        img.file_format = "PNG"
        img.save()
    os.chdir(work)
    built = S.build_scene(film, Path("out/amv/layers"), res_scale=0.25, samples=1, log=lambda *_: None)
    blend = amv / "t.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), relative_remap=True)
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    bad = missing()
    moved = work / "moved"
    shutil.copytree(amv, moved)
    bpy.ops.wm.open_mainfile(filepath=str(moved / "t.blend"))
    bad += [f"moved: {m}" for m in missing()]
    print("images checked:", len(bpy.data.images), "problems:", bad or "none")
    sys.exit(1 if bad else 0)


main()
