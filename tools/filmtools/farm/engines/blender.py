"""Blender on a worker: `blender -b`, Cycles on the GPU (OptiX, else CUDA) or EEVEE, the missing frames only.

The job's "blender" settings:

    {"file": "s3://BUCKET/farm/scenes/x.blend" | "/abs/path/on/the/box.blend",
     "build": "bpy code that makes the scene (instead of file; saved as a .blend, then rendered)",
     "engine": "CYCLES" | "BLENDER_EEVEE_NEXT" | "BLENDER_EEVEE",   # default: what the file says
     "device": "OPTIX" | "CUDA",                                     # Cycles; default OPTIX
     "samples": 128, "resolution": [1920, 1080], "percent": 100,     # optional overrides
     "camera": "Camera", "scene": "Scene",                            # optional
     "version": "5.2.2", "python": "...optional extra bpy lines run before rendering..."}

Cycles and EEVEE keep nothing from one frame to the next, so no pre-roll is needed: frames are rendered in runs of
the missing ones (`-s A -e B -a`), each run one Blender process. A .blend with physics must have its caches baked
in the file (a farm renders frames out of order).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time

from . import RenderError, frames_on_disk
from .. import model

CONTIGUOUS = False
DEFAULT_VERSION = "5.2.2"   # the repo's RunPod bootstrap's (tools/filmtools/pod_bootstrap.sh)
LIBS = ("libsm6 libice6 libgl1 libegl1 libxi6 libxxf86vm1 libxfixes3 libxrender1 libxkbcommon0 xz-utils ffmpeg")


def _bin(version: str) -> str:
    return f"/opt/blender-{version}-linux-x64/blender"


def install(version: str, ctx) -> str:
    """Blender under /opt (from the farm's S3 cache, else blender.org, then cached), and its X/GL libraries."""
    b = _bin(version)
    if os.path.exists(b):
        return b
    name = f"blender-{version}-linux-x64.tar.xz"
    major = ".".join(version.split(".")[:2])
    cache = f"s3://{ctx.conf['bucket']}/farm/bin/{name}"
    ctx.sh(f"export DEBIAN_FRONTEND=noninteractive; (apt-get install -y -qq {LIBS} || "
           f"(apt-get update -qq && apt-get install -y -qq {LIBS})) >/dev/null", timeout=1800)
    tmp = f"/srv/farm/{name}"
    os.makedirs("/srv/farm", exist_ok=True)
    if ctx.sh(f"aws s3 cp --only-show-errors {cache} {tmp}", check=False, timeout=1800) != 0:
        ctx.log(f"blender {version}: not cached, from blender.org")
        ctx.sh(f"curl -sSfL -o {tmp} https://download.blender.org/release/Blender{major}/{name}", timeout=1800)
        ctx.sh(f"aws s3 cp --only-show-errors {tmp} {cache}", check=False, timeout=1800)
    ctx.sh(f"tar xJf {tmp} -C /opt && rm -f {tmp}", timeout=1800)
    if not os.path.exists(b):
        raise RenderError(f"blender {version}: not at {b} after install")
    return b


def prepare(job: dict, ctx) -> None:
    bl = job.get("blender") or {}
    ctx.state["blender"] = install(str(bl.get("version") or DEFAULT_VERSION), ctx)
    src = bl.get("file") or ""
    if bl.get("build"):  # a scene made by a script (the same on every box): saved, then rendered like a file
        src = os.path.join("/srv/farm", job["id"], "scene", "built.blend")
        os.makedirs(os.path.dirname(src), exist_ok=True)
        py = os.path.join(os.path.dirname(src), "build.py")
        with open(py, "w") as f:
            f.write(str(bl["build"]) + f"\nimport bpy\nbpy.ops.wm.save_as_mainfile(filepath={src!r})\n")
        ctx.sh(f"{ctx.state['blender']} -b --factory-startup --python {py}", timeout=1800)
    if not src:
        raise RenderError("blender job: no 'file' (s3://... or a path on the box) and no 'build' script")
    if src.startswith("s3://"):
        local = os.path.join("/srv/farm", job["id"], "scene", os.path.basename(src))
        os.makedirs(os.path.dirname(local), exist_ok=True)
        ctx.sh(f"aws s3 cp --only-show-errors {src} {local}", timeout=3600)
        src = local
        # textures etc. packed next to the .blend: a sibling folder "<name>_assets/" is synced too, if there is one
        assets = bl.get("assets")
        if assets:
            ctx.sh(f"aws s3 sync --only-show-errors {assets} {os.path.dirname(local)}/", timeout=3600)
    if not os.path.exists(src):
        raise RenderError(f"blender job: no file {src} on the box")
    ctx.state["blend"] = src
    # the editor would hold the GPU: a Blender worker made from a UE image stops it
    ctx.sh("systemctl stop ue-editor 2>/dev/null || true", check=False)


def setup_py(bl: dict, out_dir: str, out: dict) -> str:
    """The Python Blender runs before rendering: GPU devices, engine, overrides, the output path and format."""
    fmt = {"png": "PNG", "exr": "OPEN_EXR", "jpeg": "JPEG", "jpg": "JPEG", "tif": "TIFF", "tiff": "TIFF"}[out["ext"]]
    lines = ["import bpy",
             f"sc = bpy.data.scenes[{bl['scene']!r}]" if bl.get("scene") else "sc = bpy.context.scene"]
    if bl.get("engine"):
        lines.append(f"sc.render.engine = {bl['engine']!r}")
    lines += ["if sc.render.engine == 'CYCLES':",
              "    p = bpy.context.preferences.addons['cycles'].preferences",
              f"    p.compute_device_type = {str(bl.get('device') or 'OPTIX')!r}",
              "    p.get_devices()",
              "    n = 0",
              "    for d in p.devices:",
              "        d.use = d.type == p.compute_device_type",
              "        n += d.use",
              "    if not n: raise SystemExit('farm: no ' + p.compute_device_type + ' device')",
              "    sc.cycles.device = 'GPU'"]
    if bl.get("samples"):
        lines += ["if sc.render.engine == 'CYCLES': sc.cycles.samples = %d" % int(bl["samples"]),
                  "else: sc.eevee.taa_render_samples = %d" % int(bl["samples"])]
    if bl.get("resolution"):
        w, h = bl["resolution"]
        lines += [f"sc.render.resolution_x = {int(w)}", f"sc.render.resolution_y = {int(h)}"]
    if bl.get("percent"):
        lines.append(f"sc.render.resolution_percentage = {int(bl['percent'])}")
    if bl.get("camera"):
        lines.append(f"sc.camera = bpy.data.objects[{bl['camera']!r}]")
    lines += [f"sc.render.image_settings.file_format = {fmt!r}",
              f"sc.render.filepath = {os.path.join(out_dir, '#' * int(out['pad']))!r}",
              "sc.render.use_file_extension = True", "sc.render.use_overwrite = True",
              "sc.render.use_placeholder = False"]
    if bl.get("python"):
        lines.append(str(bl["python"]))
    return "\n".join(lines) + "\n"


def command(blender: str, blend: str, py: str, a: int, b: int, scene: str = "") -> list[str]:
    """One Blender process for frames [a, b) (end exclusive; -e is inclusive)."""
    cmd = [blender, "-b", blend]
    if scene:
        cmd += ["-S", scene]
    return cmd + ["--python", py, "-s", str(a), "-e", str(b - 1), "-a"]


def render(job: dict, chunk: dict, todo: dict, scratch: str, ctx):
    bl, out = job.get("blender") or {}, job["output"]
    os.makedirs(scratch, exist_ok=True)
    py = os.path.join(scratch, "_farm_setup.py")
    with open(py, "w") as f:
        f.write(setup_py(bl, scratch, out))
    seen: set = set()
    for a, b in model.runs(todo["frames"]):
        cmd = command(ctx.state["blender"], ctx.state["blend"], py, a, b, bl.get("scene") or "")
        ctx.log(f"blender [{a},{b}): {' '.join(cmd[1:])}")
        logf = open(os.path.join(scratch, f"_blender_{a}.log"), "w")
        p = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT)
        try:
            while True:
                rc = p.poll()
                disk = frames_on_disk(scratch, out["ext"])
                done = {f: q for f, q in disk.items() if a <= f < b and f not in seen and (rc is not None or
                        any(g > f for g in disk))}  # a frame is finished once a later one exists (or Blender ended)
                for f in sorted(done):
                    seen.add(f)
                    yield f, done[f]
                if rc is not None:
                    break
                if ctx.stopping():
                    p.terminate()
                    raise RenderError("stopped (lease lost or box going down)")
                time.sleep(2)
        finally:
            if p.poll() is None:
                p.kill()
            logf.close()
        if rc != 0:
            tail = open(logf.name, errors="replace").read()[-800:]
            raise RenderError(f"blender exited {rc} on [{a},{b}): {tail}")
    missing = [f for f in todo["frames"] if f not in seen]
    if missing:
        raise RenderError(f"blender wrote no file for frames {missing[:10]}")


def cleanup(scratch: str) -> None:
    shutil.rmtree(scratch, ignore_errors=True)
