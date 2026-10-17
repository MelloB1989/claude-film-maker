"""Make a .blend portable: report what it references, pack every external resource, make the remaining paths relative.

    blender -b --factory-startup <in.blend> -P blender/amv2/pack_blend.py -- --out <out.blend> [--report report.json]
        [--no-pack]

Run by `tools/filmtools/amv2/package.py` (bpy-free) on the Timeless v2 .blend files. Images, fonts, sounds, movie clips and
volumes are packed into the file (`pack_all`); library links and anything that cannot be packed are made `//`-relative.
The report lists, per datablock type, what was external before, what is packed after, and what is still external
(`missing`: file not found at pack time; `external`: still outside the .blend).
"""
import argparse
import json
import os
import sys

import bpy


def externals():
    out = []
    for coll, kind in ((bpy.data.images, "image"), (bpy.data.fonts, "font"), (bpy.data.sounds, "sound"),
                       (bpy.data.movieclips, "movieclip"), (bpy.data.libraries, "library"), (bpy.data.volumes, "volume"),
                       (bpy.data.cache_files, "cache")):
        for d in coll:
            fp = getattr(d, "filepath", "")
            if not fp or getattr(d, "source", "") in ("GENERATED", "VIEWER"):
                continue
            if kind == "font" and d.filepath in ("<builtin>", ""):
                continue
            packed = bool(getattr(d, "packed_file", None)) or bool(getattr(d, "packed_files", None))
            out.append({"kind": kind, "name": d.name, "path": fp, "packed": packed,
                        "exists": os.path.exists(bpy.path.abspath(fp))})
    return out


def index_search(dirs):
    """{basename: path} of every file under `dirs` (skips VCS, node_modules and out/ trees)."""
    idx = {}
    for d in dirs:
        for root, sub, files in os.walk(d):
            sub[:] = [x for x in sub if x not in (".git", "node_modules", "out", "__pycache__")]
            for f in files:
                idx.setdefault(f, os.path.join(root, f))
    return idx


def relocate(search):
    """Point every external file that is missing at its place of the same name under `search` (the .blend was saved
    on a machine whose relative layout is gone), return what was relocated."""
    idx, moved = None, []
    for coll, kind in ((bpy.data.images, "image"), (bpy.data.fonts, "font"), (bpy.data.sounds, "sound"),
                       (bpy.data.movieclips, "movieclip")):
        for d in coll:
            fp = getattr(d, "filepath", "")
            if not fp or fp == "<builtin>" or getattr(d, "source", "") in ("GENERATED", "VIEWER") or getattr(d, "packed_file", None):
                continue
            if os.path.exists(bpy.path.abspath(fp)):
                continue
            idx = idx if idx is not None else index_search(search)
            hit = idx.get(os.path.basename(fp.replace("\\", "/")))
            if hit:
                d.filepath = hit
                moved.append({"kind": kind, "name": d.name, "was": fp, "now": hit})
    return moved


def pack_each(errors):
    """Pack datablock by datablock (one missing file must not stop the rest)."""
    for coll in (bpy.data.images, bpy.data.fonts, bpy.data.sounds):
        for d in coll:
            fp = getattr(d, "filepath", "")
            if not fp or fp == "<builtin>" or getattr(d, "source", "") in ("GENERATED", "VIEWER") or getattr(d, "packed_file", None):
                continue
            try:
                d.pack()
            except Exception as e:
                errors.append(f"pack {d.name}: {e}")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    ap.add_argument("--no-pack", action="store_true")
    ap.add_argument("--search", action="append", default=[], help="folder to look in for files the .blend lost (repeatable)")
    a = ap.parse_args(argv)
    before = externals()
    errors = []
    moved = relocate(a.search) if a.search else []
    if not a.no_pack:
        pack_each(errors)
    try:
        bpy.ops.file.make_paths_relative()
    except Exception as e:
        errors.append(f"make_paths_relative: {e}")
    after = externals()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out), compress=True, relative_remap=True)
    rep = {"blend": os.path.basename(a.out), "external_before": before, "after": after, "errors": errors, "relocated": moved,
           "missing": [e for e in after if not e["packed"] and not e["exists"]],
           "external": [e for e in after if not e["packed"] and e["kind"] != "library" and not e["path"].startswith("//")],
           "scene": {"frame_start": bpy.context.scene.frame_start, "frame_end": bpy.context.scene.frame_end,
                     "fps": bpy.context.scene.render.fps, "res": [bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y],
                     "engine": bpy.context.scene.render.engine}, "blender": bpy.app.version_string}
    if a.report:
        with open(a.report, "w") as fh:
            json.dump(rep, fh, indent=1)
    print("PACK_BLEND " + json.dumps({k: rep[k] for k in ("blend", "errors", "missing", "external")}))


main()
